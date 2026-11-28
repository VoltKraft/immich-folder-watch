"""Check publication when two ordinary Linux GUI builds share an output directory."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import build


class BuildOutputTests(TestCase):
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
