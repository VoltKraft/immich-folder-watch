"""Exercise archive controls and optionally compare a notice ZIP against its native build's reviewed inventory."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import unittest
from zipfile import ZIP_STORED, ZipFile

import notices
import sbom


class Controls(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.directory = Path(self.area.name)
        self.archive = self.directory / "fixture-1.crate"

    def crate(self, members):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, data in members:
                info = tarfile.TarInfo("fixture-1/" + name)
                if data is None:
                    info.type, info.linkname = tarfile.SYMTYPE, "LICENSE"
                    archive.addfile(info)
                else:
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
        return sbom.sha(self.archive.read_bytes())

    def selected(self, digest, wanted):
        return notices.crate_members("fixture-1", digest, wanted, [self.directory])

    def test_only_original_selected_bytes_are_copied(self):
        original = b"\xffupstream text\r\n"
        digest = self.crate([("parent/COPYING", original), ("promotional.png", b"unreviewed asset")])
        result = self.selected(digest, {"parent/COPYING": sbom.sha(original)})
        self.assertEqual(result, {"crates/fixture-1/parent/COPYING": original})

    def test_changed_archive_or_selected_member_is_rejected(self):
        digest = self.crate([("LICENSE", b"fixture")])
        with self.assertRaisesRegex(ValueError, "Original archive mismatch"):
            self.selected("0" * 64, {"LICENSE": sbom.sha(b"fixture")})
        with self.assertRaisesRegex(ValueError, "Notice checksum mismatch"):
            self.selected(digest, {"LICENSE": "0" * 64})

    def test_missing_duplicate_and_linked_original_are_rejected(self):
        wanted = {"LICENSE": sbom.sha(b"grant")}
        for entries, error in [
            ([("unused", b"grant")], "Missing notice members"),
            ([("LICENSE", b"grant"), ("LICENSE", b"grant")], "duplicate notice member"),
            ([("LICENSE", None)], "Invalid or duplicate notice member"),
        ]:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.selected(self.crate(entries), wanted)
        self.archive.unlink()
        with self.assertRaisesRegex(ValueError, "Missing fixture-1.crate"):
            self.selected("0" * 64, wanted)

    def test_unsafe_and_case_ambiguous_destinations_are_rejected(self):
        output = self.directory / "notices.zip"
        for path in ("../LICENSE", "/LICENSE", "a//LICENSE", "a/./LICENSE", "a\\LICENSE", "C:/LICENSE"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Unsafe notice path"):
                notices.write_archive(output, {path: b"x"})
        for names in (("license", "LICENSE"), ("a", "A/LICENSE"), ("abc/one", "ABC/two")):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "Ambiguous notice paths"):
                notices.write_archive(output, dict.fromkeys(names, b"test"))
        self.assertFalse(output.exists())

    def test_zip_is_reproducible_and_preserves_an_existing_different_file(self):
        output = self.directory / "example.zip"
        files = {"b": b"second", "a": b"first"}
        digest = notices.write_archive(output, files)
        original = output.read_bytes()
        self.assertEqual(notices.write_archive(output, dict(reversed(files.items()))), digest)
        with self.assertRaisesRegex(ValueError, "different file already exists"):
            notices.write_archive(output, {"other": b"replacement"})
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(list(self.directory.iterdir()), [output])


def check_native(args):
    case = unittest.TestCase()
    receipt, digest, files = sbom.read_run(args.input, args.target, args.archive_sha256)
    inventory, _, units, _, _ = sbom.verify(receipt, files, args.revision, args.target)
    local = sbom.first_party(args.revision, receipt["sources"])
    expected = {"repository/LICENSE": sbom.sha(sbom.blob(args.revision, "LICENSE"))}
    with ZipFile(args.notices) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        index = archive.read("NOTICE.txt")
        expected["NOTICE.txt"] = sbom.sha(index)
        case.assertEqual(manifest["revision"], args.revision)
        case.assertEqual(manifest["target"], args.target)
        case.assertEqual(manifest["nativeArchiveSha256"], args.archive_sha256)
        case.assertEqual(manifest["nativeReceiptSha256"], digest)
        case.assertEqual(manifest["compilerUnitsSha256"], receipt["outputs"]["compiler-units.json"])
        case.assertEqual(manifest["sourceInventorySha256"], receipt["outputs"]["inventory.json"])
        case.assertEqual(manifest["executableSha256"], receipt["native"]["binarySha256"])
        case.assertEqual(manifest["packages"].keys(), units.keys())
        selected = manifest["packages"]
        for key, compiled in units.items():
            case.assertEqual(selected[key]["compiledFor"], sorted({role for u in compiled for role in u["compiledFor"]}))
            case.assertEqual(selected[key]["compiledUnits"], len(compiled))
            case.assertIn(key.encode(), index)
        for key in local:
            case.assertEqual(selected[key]["notices"], ["repository/LICENSE"])
            case.assertEqual(selected[key]["gitSource"], local[key]["sourceInfo"])
            case.assertEqual(selected[key]["reviewedTopLevelLicense"], local[key]["licenseDeclared"])
        xml = {}
        for row in inventory["packages"]:
            key = row["name"] + " v" + row["version"]
            if key not in units:
                continue
            record = selected[key]
            root = "crates/" + row["name"] + "-" + row["version"] + "/"
            prefix = root if row["source"] else "repository/"
            paths = {prefix + p: d for p, d in row["notices"].items()}
            paths.update({"repository/" + p: d for p, d in row["supplementalNotices"].items()})
            case.assertCountEqual(record["notices"], paths.keys())
            case.assertEqual(record["upstreamArchiveSha256"], row["archiveSha256"])
            case.assertEqual(record["reviewedTopLevelLicense"], row["selected"])
            case.assertEqual(record["compilerTree"], row["compilerTree"])
            expected.update(paths)
            protocols = {root + p: data for p, data in row.get("protocols", {}).items()}
            case.assertCountEqual(record.get("protocolXml", []), protocols.keys())
            expected.update({p: data["sha256"] for p, data in protocols.items()})
            xml.update(protocols)
            if row["name"] == "libsqlite3-sys":
                path = root + "sqlite3/sqlite3.h"
                case.assertEqual(record["sqlitePublicDomainHeader"], path)
                expected[path] = row["native"]["sqlite3/sqlite3.h"]
                case.assertIn(b"May you do good and not evil.", archive.read(path))
            if row["name"] == "granit-parser":
                links = re.findall(rb"\]\((\.licenses/[^)]+)\)", archive.read(root + "LICENSE"))
                case.assertEqual(len(set(links)), 4)
                for link in links:
                    case.assertIn(root + link.decode(), paths)
            if row["name"] == "base64":
                case.assertCountEqual(paths, (root + "LICENSE-APACHE", root + "LICENSE-MIT"))
        linux = "linux" in args.target
        case.assertEqual(len(xml), 100 if linux else 0)
        case.assertEqual(sum("LGPL-2.1-or-later" in v["licenseIds"] for v in xml.values()), 18 if linux else 0)
        if linux:
            case.assertTrue(any(p.endswith("/plasma-wayland-protocols/COPYING.LIB") for p in expected))
            case.assertIn("repository/rust/audit/notices/weston-1.5.0-COPYING", expected)
        faces = list(sbom.fonts(args.revision, inventory))
        case.assertCountEqual(manifest["fonts"], [f["name"] for f in faces])
        for face in faces:
            record = manifest["fonts"][face["name"]]
            original, digest = face["licenseComments"].split(", SHA-256 ")
            case.assertEqual(record["notice"], "repository/" + original)
            expected[record["notice"]] = digest
            case.assertEqual(record["assetSha256"], inventory["fonts"][face["name"]]["sha256"])
            case.assertEqual(record["source"], face["downloadLocation"])
            case.assertEqual(record["version"], face["versionInfo"])
            case.assertEqual(record["license"], "OFL-1.1")
            case.assertEqual(record["copyright"], face["copyrightText"])
            case.assertEqual(record["trademark"], face["attributionTexts"])
            for text in [face["name"], face["copyrightText"], *face["attributionTexts"]]:
                case.assertIn(text.encode(), index)
        case.assertEqual(manifest["files"].keys(), expected.keys())
        case.assertEqual(archive.namelist(), sorted([*expected, "manifest.json"]))
        for path, digest in expected.items():
            data = archive.read(path)
            case.assertEqual(manifest["files"][path], {"bytes": len(data), "sha256": digest})
            case.assertEqual(sbom.sha(data), digest, path)
        for info in archive.infolist():
            case.assertEqual(PurePosixPath(info.filename).as_posix(), info.filename)
            case.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
            case.assertEqual((info.compress_type, info.create_system, info.external_attr), (ZIP_STORED, 3, 0o100644 << 16))
    print(f"Passed {args.target}: {len(units)} Cargo packages, {len(xml)} protocol XMLs, "
          f"{len(faces)} fonts, {len(expected) + 1} ZIP members")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--archive-sha256")
    parser.add_argument("--notices", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise SystemExit(1)
    if any(vars(args).values()):
        if not all(vars(args).values()):
            parser.error("Native checks require --target, --input, --revision, --archive-sha256 and --notices")
        check_native(args)
