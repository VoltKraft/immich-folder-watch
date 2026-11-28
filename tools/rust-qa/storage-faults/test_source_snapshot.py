"""Verify source lookup and byte preservation through a hidden-file filter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import run as runner


class SourceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        runner.ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="source-export-", dir=runner.ARTIFACTS)
        self.base = Path(self.directory.name)
        self.repository = self.base / "repository"
        self.inventory = {
            "src/main.rs": b"fn main() {}\n",
            "tools/windows-image/.gitattributes": (runner.HERE / "windows-image/.gitattributes").read_bytes(),
            "tools/windows-image/COPYING.dosfstools": (runner.HERE / "windows-image/COPYING.dosfstools").read_bytes(),
            "tools/windows-image/NOTICE.md": (runner.HERE / "windows-image/NOTICE.md").read_bytes(),
            ".synthetic-metadata/nested/notes.txt": "Synthetic Unicode: Straße\r\n".encode("utf-8"),
            "other/.gitattributes": b"different synthetic metadata\n",
        }
        for logical, data in self.inventory.items():
            path = self.repository / logical
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # This synthetic file is deliberately outside the selected inventory.
        (self.repository / ".unselected-fixture").write_bytes(b"must not be exported")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def export(self, name: str, logical_names=None) -> Path:
        output = self.base / name
        output.mkdir()
        runner.export_source_snapshot(self.repository, output,
            [self.repository / logical for logical in (logical_names or self.inventory)])
        return output

    def test_evidence_inventory_excludes_only_top_level_scratch_build(self) -> None:
        output = self.base / "evidence"
        retained = {
            "result.json": b"synthetic result",
            "native-build-logs/target/release/build/sqlite/run/stdout": b"actual compile options",
            "native-build-logs/target/release/build/sqlite/run/stderr": b"compiler diagnostics",
            "generated-source/target/release/build/faults/out/reviewed-storage.rs": b"reviewed source copy",
            "first-party-sources/build/notice.txt": b"retained synthetic source notice",
        }
        for relative, contents in {**retained, "build/scratch/large-object": b"excluded scratch",
                                   "evidence-hashes.json": b"old index"}.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        expected = {name: hashlib.sha256(contents).hexdigest() for name, contents in retained.items()}
        self.assertEqual(runner.evidence_inventory(output), expected)
        changed = output / "generated-source/target/release/build/faults/out/reviewed-storage.rs"
        changed.write_bytes(b"changed source copy")
        self.assertNotEqual(runner.evidence_inventory(output), expected)

    def test_hidden_filter_preserves_every_inventoried_byte_and_notice(self) -> None:
        output = self.export("original")
        transferred = self.base / "transferred"
        transferred.mkdir()
        # Reproduce the relevant uploader rule without enabling hidden uploads.
        for path in output.rglob("*"):
            relative = path.relative_to(output)
            if path.is_file() and not any(part.startswith(".") for part in relative.parts):
                destination = transferred / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        hashes = json.loads((transferred / "first-party-source-hashes.json").read_text())
        locations = json.loads((transferred / "first-party-source-paths.json").read_text())
        self.assertEqual(set(hashes), set(self.inventory))
        self.assertEqual(set(locations), set(self.inventory))
        self.assertEqual(len(set(locations.values())), len(locations))
        self.assertEqual(len([p for p in transferred.rglob("*") if p.is_file()]), len(self.inventory) + 2)
        for logical, expected in self.inventory.items():
            with self.subTest(logical=logical):
                archived = transferred / locations[logical]
                self.assertEqual(archived.read_bytes(), expected)
                self.assertEqual(runner.sha256(archived), hashes[logical])
                self.assertFalse(any(part.startswith(".") for part in Path(locations[logical]).parts))
        self.assertEqual(locations["src/main.rs"], "first-party-sources/src/main.rs")
        logical = "tools/windows-image/.gitattributes"
        key = hashlib.sha256(logical.encode("utf-8")).hexdigest()
        self.assertEqual(locations[logical], f"first-party-hidden-sources/{key}.source")

    def test_inventory_order_duplicates_and_output_location_do_not_change_snapshot(self) -> None:
        first = self.export("first")
        second = self.export("second", [*reversed(self.inventory), "src/main.rs"])
        first_files = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
        second_files = {p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()}
        self.assertEqual(first_files, second_files)

    def test_compiled_storage_modules_match_the_archived_seed(self) -> None:
        names = ("main.rs", "preflight.rs", "wal_preflight_cases.rs")
        sources = [runner.STORAGE / "src" / name for name in names]
        output = self.base / "reviewed"
        output.mkdir()
        runner.export_source_snapshot(runner.ROOT, output, sources)
        build = self.base / "build"
        compiled = build / "release/build/storage-faults/out"
        compiled.mkdir(parents=True)
        shim = compiled / "reviewed-storage.rs"
        shim.write_bytes(sources[0].read_bytes() + b"\n// synthetic wrapper\n")
        for source in sources[1:]:
            shutil.copyfile(source, compiled / source.name)
        runner.archive_reviewed_storage(build, output)
        for source in compiled.iterdir():
            archived = output / "generated-source" / source.relative_to(build)
            self.assertEqual(archived.read_bytes(), source.read_bytes())
        module = compiled / "preflight.rs"
        module.write_bytes(b"changed compiled module")
        with self.assertRaisesRegex(ValueError, "differs from archived original: preflight.rs"):
            runner.archive_reviewed_storage(build, output)
        module.unlink()
        with self.assertRaises(FileNotFoundError):
            runner.archive_reviewed_storage(build, output)

    def test_uninventoried_files_are_not_discovered(self) -> None:
        output = self.export("selected", ["src/main.rs"])
        hashes = json.loads((output / "first-party-source-hashes.json").read_text())
        self.assertEqual(set(hashes), {"src/main.rs"})
        self.assertEqual(len([p for p in output.rglob("*") if p.is_file()]), 3)

    def test_corrupt_export_is_rejected_before_manifest_publication(self) -> None:
        def corrupt_copy(_source, destination):
            destination.write(b"injected wrong bytes")

        with patch.object(runner.shutil, "copyfileobj", side_effect=corrupt_copy):
            with self.assertRaisesRegex(ValueError, "exported source bytes differ"):
                self.export("corrupted", ["src/main.rs"])
        self.assertFalse((self.base / "corrupted/first-party-source-hashes.json").exists())
        self.assertFalse((self.base / "corrupted/first-party-source-paths.json").exists())

    def test_existing_export_is_not_overwritten(self) -> None:
        output = self.export("existing", ["src/main.rs"])
        original = (output / "first-party-sources/src/main.rs").read_bytes()
        with self.assertRaises(FileExistsError):
            runner.export_source_snapshot(self.repository, output, [self.repository / "src/main.rs"])
        self.assertEqual((output / "first-party-sources/src/main.rs").read_bytes(), original)

    def test_outside_or_parent_relative_inventory_path_is_rejected(self) -> None:
        outside = self.base / "outside.txt"
        outside.write_bytes(b"synthetic outside file")
        for number, source in enumerate((outside, self.repository / "../outside.txt")):
            with self.subTest(source=source):
                output = self.base / f"outside-{number}"
                output.mkdir()
                with self.assertRaises(ValueError):
                    runner.export_source_snapshot(self.repository, output, [source])
                self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
