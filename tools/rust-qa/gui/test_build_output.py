"""Check publication when two ordinary Linux GUI builds share an output directory."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import build
import publication


def fill(root, names, label):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(label + "/" + name)


def read_set(root, names):
    return [(root / name).read_text() for name in names]


class BuildOutputTests(TestCase):
    def test_interrupted_switch_preserves_all_five_legacy_files(self):
        files = publication.BUILD_FILES
        with TemporaryDirectory() as temp:
            root = Path(temp) / "build"
            fill(root, files, "stock")
            previous = publication.pin_build(root)
            expected = read_set(previous, files)
            staging = root / "stage"
            fill(staging, files, "updated")
            with publication.writer(root), patch.object(publication, "_switch", side_effect=OSError("interrupted")):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    publication.publish(root, staging, files)
            self.assertEqual(publication.pin_build(root), previous)
            self.assertEqual(read_set(root, files), expected)
            self.assertEqual(read_set(previous, files), expected)

    def test_overlapping_reader_finishes_from_the_generation_it_pinned(self):
        files = publication.BUILD_FILES
        pinned, consumed = Event(), Event()
        with TemporaryDirectory() as temp:
            root = Path(temp) / "build"
            fill(root, files, "stock")
            before = publication.pin_build(root)

            def reader():
                version = publication.pin_build(root)
                first = (version / files[0]).read_text()
                pinned.set()
                self.assertTrue(consumed.wait(5))
                return [first, *read_set(version, files[1:])]

            with ThreadPoolExecutor(1) as pool:
                pending = pool.submit(reader)
                try:
                    self.assertTrue(pinned.wait(5))
                    stage = root / "stage"
                    fill(stage, files, "updated")
                    with publication.writer(root):
                        updated = publication.publish(root, stage, files)
                finally:
                    consumed.set()
                self.assertEqual(pending.result(timeout=5), read_set(before, files))
            self.assertNotEqual(updated, before)
            self.assertEqual(publication.pin_build(root), updated)
            self.assertEqual(read_set(root, files), ["updated/" + name for name in files])

    def test_complete_wrappers_publish_isolated_evidence_after_their_tests(self):
        script = Path(build.__file__).resolve().parents[1] / "build-gui-probe.py"
        spec = importlib.util.spec_from_file_location("gui_probe_test", script)
        wrapper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wrapper)
        entered, second, proceed = Event(), Event(), Event()
        private = []
        files = publication.NATIVE_FILES
        with TemporaryDirectory() as temp:
            area = Path(temp)
            target = "x86_64-unknown-linux-gnu"
            root = area / "gui-native" / target
            fill(root, files, "previous")
            previous = publication.pin_native(root)

            def build_gui(args, staging):
                first = not private
                private.append(staging)
                if first:
                    (staging / "gui-unit-tests.log").write_text("in-progress")
                    entered.set()
                    self.assertTrue(proceed.wait(5))
                    raise RuntimeError("unit test failed")
                second.set()
                self.assertFalse((staging / "gui-unit-tests.log").exists())
                fill(staging, files, "second")

            with patch.object(wrapper, "ARTIFACTS", area), patch.object(wrapper, "build_gui", side_effect=build_gui), \
                    patch.object(sys, "argv", [str(script), target, "--offline"]), ThreadPoolExecutor(2) as pool:
                first = pool.submit(wrapper.main)
                self.assertTrue(entered.wait(5))
                next_run = pool.submit(wrapper.main)
                try:
                    self.assertFalse(second.wait(0.15))
                    self.assertEqual(read_set(root, files), read_set(previous, files))
                finally:
                    proceed.set()
                with self.assertRaisesRegex(RuntimeError, "unit test failed"):
                    first.result(timeout=5)
                next_run.result(timeout=5)
            self.assertNotEqual(*private)
            self.assertTrue(all(not path.exists() for path in private))
            self.assertEqual(read_set(publication.pin_native(root), files), ["second/" + name for name in files])
            self.assertEqual(read_set(previous, files), ["previous/" + name for name in files])

    def test_failed_build_preserves_the_previous_stream_and_releases_the_next_writer(self):
        entered, second_open, release = Event(), Event(), Event()
        staged_dirs = []

        def compile_gui(args, output, staging):
            staged_dirs.append(staging)
            log = staging / "gui-compiler.jsonl"
            log.write_text(args.label)
            if args.label == "first":
                entered.set()
                self.assertTrue(release.wait(5))
                raise ValueError("compiler failed")
            second_open.set()
            self.assertEqual((output / log.name).read_text(), "previous")
            log.replace(output / log.name)

        with TemporaryDirectory() as temp, patch.object(build, "OUTPUT", Path(temp)), \
                patch.object(build, "compile_gui", side_effect=compile_gui):
            out = Path(temp) / "test"
            out.mkdir()
            log = out / "gui-compiler.jsonl"
            log.write_text("previous")
            with ThreadPoolExecutor(2) as workers:
                first = workers.submit(build.main, SimpleNamespace(output=out, label="first"))
                self.assertTrue(entered.wait(5))
                second = workers.submit(build.main, SimpleNamespace(output=out, label="second"))
                try:
                    self.assertFalse(second_open.wait(0.15))
                    self.assertEqual(log.read_text(), "previous")
                finally:
                    release.set()
                with self.assertRaisesRegex(ValueError, "compiler failed"):
                    first.result(timeout=5)
                second.result(timeout=5)
            self.assertNotEqual(*staged_dirs)
            self.assertFalse(any(path.exists() for path in staged_dirs))
            self.assertEqual(log.read_text(), "second")
