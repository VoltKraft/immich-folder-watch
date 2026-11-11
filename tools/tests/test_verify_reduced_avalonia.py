"""Reject regressions that restore or publish the unmodified framework DLLs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_reduced_avalonia import ASSEMBLIES, verify


class ReducedPayloadTests(unittest.TestCase):
    def setUp(self):
        # Binary parsing has its own real PE/CLI fixtures. These tests isolate
        # provenance and byte matching using small synthetic payloads.
        self.audit_patch = patch("verify_reduced_avalonia.audit")
        self.metadata_audit = self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.publish = self.root / "publish"
        self.publish.mkdir()
        commit = "a" * 40
        checksum = "b" * 128
        lock = {
            "schemaVersion": 1, "sdkVersion": "10.0.401", "upstreamCommit": commit,
            "upstreamVersion": "12.1.6", "packageVersion": "12.1.6.1",
            "source": {"filename": "avalonia-source.tar.gz", "sha512": checksum,
                       "url": f"https://codeload.github.com/AvaloniaUI/Avalonia/tar.gz/{commit}"},
            "packages": [{"id": name, "version": "12.1.6", "sha512": checksum,
                          "filename": f"{name}.12.1.6.nupkg",
                          "url": f"https://api.nuget.org/v3-flatcontainer/{name}/12.1.6/{name}.12.1.6.nupkg"}
                         for name in (*ASSEMBLIES, "avalonia.remote.protocol")],
        }
        lock_path = self.root / "packaging/avalonia-reduced/inputs.json"
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text(json.dumps(lock))
        (lock_path.parent / "removals.json").write_text(json.dumps({"removedSources": [], "modifiedSources": []}))
        self.feed = self.root / "artifacts/reduced-avalonia/feed"
        self.feed.mkdir(parents=True)
        self.libraries = {}
        for name, filename in ASSEMBLIES.items():
            identity = name + "/12.1.6.1"
            self.libraries[identity] = {"type": "package"}
            package = self.cache / identity
            binary = package / "lib/net10.0" / filename
            binary.parent.mkdir(parents=True)
            content = b"test reduced bytes for " + filename.encode()
            binary.write_bytes(content)
            (self.publish / filename).write_bytes(content)
            archive_name = f"{name}.12.1.6.1.nupkg"
            provenance_bytes = json.dumps({
                "schemaVersion": 1, "upstreamCommit": commit, "packageVersion": "12.1.6.1",
                "sourceArchiveSha512": checksum,
                "assemblies": {filename: hashlib.sha256(content).hexdigest()},
                "removedSources": [], "modifiedSources": [],
            }).encode("utf-8")
            with zipfile.ZipFile(self.feed / archive_name, "w") as archive:
                archive.writestr("reduced-avalonia.json", provenance_bytes)
                archive.writestr(f"lib/net10.0/{filename}", content)
            (package / archive_name).write_bytes((self.feed / archive_name).read_bytes())
            (package / "reduced-avalonia.json").write_bytes(provenance_bytes)
        self.assets = self.root / "project.assets.json"
        self.write_assets()

    def write_assets(self):
        self.assets.write_text(json.dumps({
            "libraries": self.libraries, "packageFolders": {str(self.cache): {}}
        }))

    def test_matching_source_build_and_published_bytes_pass(self):
        verify(self.assets, self.root, self.publish)
        self.metadata_audit.assert_called_once_with([self.publish])

    def test_original_package_version_is_rejected(self):
        self.libraries["avalonia/12.1.6"] = self.libraries.pop("avalonia/12.1.6.1")
        self.write_assets()
        with self.assertRaisesRegex(ValueError, "reduced package is required"):
            verify(self.assets, self.root)

    def test_replaced_published_dll_is_rejected(self):
        (self.publish / "Avalonia.Controls.dll").write_bytes(b"original upstream DLL")
        with self.assertRaisesRegex(ValueError, "not the validated reduced build"):
            verify(self.assets, self.root, self.publish)

    def test_duplicate_dll_in_subdirectory_is_rejected(self):
        extra = self.publish / "fallback/Avalonia.Controls.dll"
        extra.parent.mkdir()
        extra.write_bytes(b"upstream DLL")
        with self.assertRaisesRegex(ValueError, "duplicate published"):
            verify(self.assets, self.root, self.publish)

    def test_original_fallback_framework_is_rejected(self):
        extra = self.cache / "avalonia/12.1.6.1/lib/net8.0/Avalonia.Controls.dll"
        extra.parent.mkdir()
        extra.write_bytes(b"original DLL")
        with self.assertRaisesRegex(ValueError, "framework copies"):
            verify(self.assets, self.root)

    def test_changed_restored_dll_is_rejected(self):
        binary = self.cache / "avalonia/12.1.6.1/lib/net10.0/Avalonia.Controls.dll"
        binary.write_bytes(b"tampered DLL")
        with self.assertRaisesRegex(ValueError, "Restored reduced assembly checksum"):
            verify(self.assets, self.root)

    def test_different_source_revision_is_rejected(self):
        path = self.cache / "avalonia/12.1.6.1/reduced-avalonia.json"
        data = json.loads(path.read_text())
        data["upstreamCommit"] = "c" * 40
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "provenance does not match"):
            verify(self.assets, self.root)

    def test_stale_package_cache_is_rejected_after_rebuild(self):
        (self.feed / "avalonia.12.1.6.1.nupkg").write_bytes(b"new build")
        with self.assertRaisesRegex(ValueError, "Stale package cache"):
            verify(self.assets, self.root)

    def test_joint_extracted_provenance_and_dll_tampering_is_rejected(self):
        package = self.cache / "avalonia/12.1.6.1"
        archive_name = "avalonia.12.1.6.1.nupkg"
        original_archive = (package / archive_name).read_bytes()
        substitute = b"different assembly without forbidden type names"
        (package / "lib/net10.0/Avalonia.Controls.dll").write_bytes(substitute)
        (self.publish / "Avalonia.Controls.dll").write_bytes(substitute)
        path = package / "reduced-avalonia.json"
        provenance = json.loads(path.read_text())
        provenance["assemblies"]["Avalonia.Controls.dll"] = hashlib.sha256(substitute).hexdigest()
        path.write_text(json.dumps(provenance))
        self.assertEqual(original_archive, (package / archive_name).read_bytes())
        self.assertEqual(original_archive, (self.feed / archive_name).read_bytes())
        with self.assertRaisesRegex(ValueError, "Extracted provenance does not match"):
            verify(self.assets, self.root, self.publish)

    def test_new_removal_recipe_requires_rebuild(self):
        (self.root / "packaging/avalonia-reduced/removals.json").write_text(json.dumps({
            "removedSources": ["newly identified component.cs"], "modifiedSources": []
        }))
        with self.assertRaisesRegex(ValueError, "source-removal recipe"):
            verify(self.assets, self.root)


if __name__ == "__main__":
    unittest.main()
