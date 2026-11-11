from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("prepare_reduced_avalonia", ROOT / "tools/prepare_reduced_avalonia.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = MODULE.read_lock(ROOT)

    def test_source_archive_and_every_compiler_input_are_locked(self) -> None:
        sources = MODULE.official_sources(self.lock)
        self.assertEqual(3, len(sources))
        self.assertEqual(MODULE.PACKAGE_IDS, {item["id"].lower() for item in self.lock["packages"]})
        manifest = (ROOT / "packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml").read_text()
        self.assertIn(self.lock["source"]["url"], manifest)
        self.assertIn(self.lock["source"]["sha512"], manifest)

    def test_rejects_alternate_hosts_traversal_duplicates_and_missing_hashes(self) -> None:
        invalid = []
        for field, value in [("filename", "../escape"), ("url", "https://example.org/source"), ("sha512", "")]:
            lock = copy.deepcopy(self.lock)
            lock["source"][field] = value
            invalid.append(lock)
        lock = copy.deepcopy(self.lock)
        lock["packages"][1] = lock["packages"][0]
        invalid.append(lock)
        lock = copy.deepcopy(self.lock)
        lock["packages"][0]["filename"] = "../escape"
        invalid.append(lock)
        path = self.root / MODULE.LOCK_PATH
        path.parent.mkdir(parents=True)
        for lock in invalid:
            with self.subTest(lock=lock):
                path.write_text(json.dumps(lock))
                with self.assertRaises(MODULE.PreparationError):
                    MODULE.read_lock(self.root)

    def test_download_verifies_bytes_and_reuses_only_matching_cache(self) -> None:
        content = b"verified archive"
        digest = hashlib.sha512(content).hexdigest()
        destination = self.root / "input.nupkg"
        with patch.object(MODULE.urllib.request, "urlopen", return_value=io.BytesIO(content)) as request:
            MODULE.download_verified("https://example.invalid/input", digest, destination)
            MODULE.download_verified("https://example.invalid/input", digest, destination)
            self.assertEqual(1, request.call_count)
        destination.write_bytes(b"modified")
        with self.assertRaisesRegex(MODULE.PreparationError, "Cached input checksum mismatch"):
            MODULE.download_verified("https://example.invalid/input", digest, destination)

    def test_bad_or_oversized_download_never_publishes_input(self) -> None:
        destination = self.root / "input.nupkg"
        for limit, message in [(100, "checksum mismatch"), (1, "size limit")]:
            with self.subTest(limit=limit), patch.object(MODULE, "MAX_INPUT_BYTES", limit), \
                    patch.object(MODULE.urllib.request, "urlopen", return_value=io.BytesIO(b"bad")):
                with self.assertRaisesRegex(MODULE.PreparationError, message):
                    MODULE.download_verified("https://example.invalid/input", "a" * 128, destination)
            self.assertEqual([], list(self.root.iterdir()))

    def private_feed(self) -> Path:
        feed = self.root / "feed"
        feed.mkdir()
        for identity in MODULE.CUSTOM_IDS:
            (feed / f"{identity}.12.1.6.1.nupkg").write_bytes(f"current {identity}".encode())
        return feed

    def test_invalidates_only_stale_current_private_packages(self) -> None:
        feed = self.private_feed()
        cache = self.root / "cache"
        old = cache / "avalonia/12.1.6.1"
        old.mkdir(parents=True)
        (old / "avalonia.12.1.6.1.nupkg").write_bytes(b"old build")
        matching = cache / "avalonia.themes.fluent/12.1.6.1"
        matching.mkdir(parents=True)
        filename = "avalonia.themes.fluent.12.1.6.1.nupkg"
        (matching / filename).write_bytes((feed / filename).read_bytes())
        untouched = [cache / "avalonia/12.1.6", cache / "avalonia/12.1.6.0", cache / "other/12.1.6.1"]
        for path in untouched:
            path.mkdir(parents=True)
            (path / "preserve").write_bytes(b"unchanged")
        self.assertEqual([old], MODULE.invalidate_stale_private_packages(cache, feed, "12.1.6.1"))
        self.assertFalse(old.exists())
        self.assertTrue((matching / filename).is_file())
        for path in untouched:
            self.assertEqual(b"unchanged", (path / "preserve").read_bytes())
        self.assertEqual([], MODULE.invalidate_stale_private_packages(cache, feed, "12.1.6.1"))

    def test_partial_private_cache_is_removed_but_unknown_version_is_rejected(self) -> None:
        feed = self.private_feed()
        cache = self.root / "cache"
        partial = cache / "avalonia/12.1.6.1"
        partial.mkdir(parents=True)
        with self.assertRaisesRegex(MODULE.PreparationError, "unreviewed package version"):
            MODULE.invalidate_stale_private_packages(cache, feed, "12.1.6.0")
        self.assertTrue(partial.exists())
        self.assertEqual([partial], MODULE.invalidate_stale_private_packages(cache, feed, "12.1.6.1"))

    def test_linked_private_package_aborts_before_any_deletion(self) -> None:
        feed = self.private_feed()
        cache = self.root / "cache"
        partial = cache / "avalonia/12.1.6.1"
        partial.mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "preserve"
        marker.write_bytes(b"unchanged")
        parent = cache / "avalonia.themes.fluent"
        parent.mkdir()
        try:
            (parent / "12.1.6.1").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symbolic links are unavailable")
        with self.assertRaisesRegex(MODULE.PreparationError, "linked private package cache"):
            MODULE.invalidate_stale_private_packages(cache, feed, "12.1.6.1")
        self.assertTrue(partial.exists())
        self.assertEqual(b"unchanged", marker.read_bytes())

    def test_effective_cache_prefers_environment_then_queries_nuget(self) -> None:
        cache = self.root / "configured"
        with patch.dict(os.environ, {"NUGET_PACKAGES": str(cache)}), patch.object(MODULE.subprocess, "run") as run:
            self.assertEqual(cache, MODULE.global_package_cache(self.root, "dotnet"))
            run.assert_not_called()
        with patch.dict(os.environ, {"NUGET_PACKAGES": ""}), patch.object(MODULE.subprocess, "run", return_value=
                subprocess.CompletedProcess([], 0, f"global-packages: {cache}\n", "")) as run:
            self.assertEqual(cache, MODULE.global_package_cache(self.root, "dotnet"))
            self.assertIn("--force-english-output", run.call_args.args[0])
            self.assertNotIn("--clear", run.call_args.args[0])

    def test_cache_discovery_failure_does_not_guess_a_directory(self) -> None:
        with patch.dict(os.environ, {"NUGET_PACKAGES": ""}), patch.object(MODULE.subprocess, "run", return_value=
                subprocess.CompletedProcess([], 1, "", "failure")):
            with self.assertRaisesRegex(MODULE.PreparationError, "effective NuGet"):
                MODULE.global_package_cache(self.root, "dotnet")


class ReadinessTests(unittest.TestCase):
    def test_recipe_and_archive_changes_invalidate_ready_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "packaging/avalonia-reduced").mkdir(parents=True)
            for name in ("inputs.json", "removals.json"):
                (root / "packaging/avalonia-reduced" / name).write_text("{}")
            for name in ("prepare", "build", "verify", "audit"):
                (root / f"tools/{name}_reduced_avalonia.py").write_text("# recipe\n")
            feed = root / "feed"
            feed.mkdir()
            lock = {"packageVersion": "12.1.6.1"}
            for identity in MODULE.CUSTOM_IDS:
                (feed / f"{identity}.12.1.6.1.nupkg").write_bytes(b"original build")
            self.assertFalse(MODULE.ready(root, feed, lock))
            MODULE.mark_ready(root, feed, lock)
            self.assertTrue(MODULE.ready(root, feed, lock))
            (feed / "avalonia.12.1.6.1.nupkg").write_bytes(b"stale or modified build")
            self.assertFalse(MODULE.ready(root, feed, lock))
            MODULE.mark_ready(root, feed, lock)
            (root / "packaging/avalonia-reduced/removals.json").write_text('{"new":true}')
            self.assertFalse(MODULE.ready(root, feed, lock))

    def test_failed_preparation_releases_os_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "build failure"):
                with MODULE.preparation_lock(root):
                    raise RuntimeError("build failure")
            with MODULE.preparation_lock(root):
                self.assertTrue((root / ".prepare.lock").is_file())


if __name__ == "__main__":
    unittest.main()
