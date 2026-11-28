"""Exercise archive controls and optionally compare a notice ZIP against its native build's reviewed inventory."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_STORED, ZipFile

import notices
import sbom
import source_notices


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

    def test_patched_source_keeps_archive_license_and_compiler_excerpt(self):
        license_text = b"unchanged license\n"
        digest = self.crate([("LICENSE", license_text), ("lib.rs", b"// Copyright original\n")])
        compiled = b"// Copyright maintained fixture\n"
        (self.directory / "lib.rs").write_bytes(compiled)
        attributions = {}
        source_notices.note_source(attributions, "lib.rs", compiled)
        row = {"name": "fixture", "version": "1", "archiveSha256": digest, "selected": "MIT",
               "reconstructedSource": {"patchSha256": "e" * 64}, "originalCrate": "fixture-1.crate",
               "compilerTree": {"files": 2}, "supplementalNotices": {}, "notices": {"LICENSE": sbom.sha(license_text)},
               "sourceAttributions": attributions}
        members = {}
        with patch.object(source_notices, "reconstructed_root", return_value=self.directory):
            record = notices.external_notices(row, {}, "revision", [self.directory], members, {}, "target")
        self.assertEqual(record["notices"], ["crates/fixture-1/LICENSE"])
        self.assertEqual(record["reconstructedSource"], row["reconstructedSource"])
        self.assertEqual(members["crates/fixture-1/LICENSE"], license_text)
        self.assertIn(compiled, members.values())

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

    def test_wrapped_grant_and_distinct_copyright_blocks_retain_original_bytes(self):
        data = (b"/* Copyright Holder\r\n * Permission to use this work. */\r\n"
                b"\r\n// Credited to Example; released in the public\r\n// domain.\r\nint value;\r\n")
        spans = source_notices.ranges(data)
        self.assertEqual(len(spans), 2)
        self.assertEqual(source_notices.excerpt_members({"sha256": sbom.sha(data), "ranges": spans}, data),
                         {"source-notices/" + span["sha256"] + ".txt": data[span["start"]:span["start"] + span["bytes"]]
                          for span in spans})
        for broken in [dict(spans[0], sha256="0" * 64), dict(spans[0], start=-1), dict(spans[0], bytes=len(data) + 1)]:
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                source_notices.excerpt_members({"sha256": sbom.sha(data), "ranges": [broken]}, data)
        with self.assertRaisesRegex(ValueError, "source checksum mismatch"):
            source_notices.excerpt_members({"sha256": "0" * 64, "ranges": spans}, data)

    def test_core_protocol_and_reuse_source_selection(self):
        audit = source_notices.audit
        self.assertTrue(audit.protocol_input("wayland-client", PurePosixPath("wayland.xml")))
        self.assertFalse(audit.protocol_input("wayland-scanner", PurePosixPath("tests/scanner_assets/test-protocol.xml")))
        self.assertTrue(audit.notice_path(PurePosixPath("nested/LICENSES/MIT-CMU.txt")))
        with self.assertRaisesRegex(ValueError, "Incomplete Plasma REUSE"):
            source_notices.protocol_license_texts({"packages": [{"name": "wayland-protocols-plasma",
                "version": "1", "notices": {}}]}, ["wayland-protocols-plasma v1"])
        with self.assertRaisesRegex(ValueError, "Changed ring build recipe"):
            source_notices.ring_targets(b"another recipe", {})


def check_native(args):
    case = unittest.TestCase()
    receipt, digest, files = sbom.read_run(args.input, args.target, args.archive_sha256)
    native_inventory, _, units, _, _ = sbom.verify(receipt, files, args.revision, args.target)
    inventory = source_notices.qualified(native_inventory, args.source_inventory)
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
        case.assertEqual(manifest["qualifiedInventorySha256"], sbom.sha(sbom.canonical(inventory).encode()))
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
            prefix = root if row["source"] or row.get("originalCrate") else "repository/"
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
            if protocols:
                for p, source in protocols.items():
                    grant = record["protocolGrants"][p]
                    if source["licenseIds"]:
                        license_id, = source["licenseIds"]
                        case.assertEqual(grant["license"], license_id)
                        case.assertTrue(grant["text"].endswith("/LICENSES/" + license_id + ".txt"))
                    elif not source["copyright"]:
                        case.assertTrue(grant["text"].endswith("/weston-1.5.0-COPYING"))
                    else:
                        case.assertEqual(grant["text"], p)
                    case.assertIn(grant["text"], archive.namelist())
            if row.get("sourceAttributions"):
                case.assertEqual(record["sourceAttributions"], row["sourceAttributions"])
                for source in row["sourceAttributions"].values():
                    for span in source["ranges"]:
                        expected["source-notices/" + span["sha256"] + ".txt"] = span["sha256"]
            if row["name"] == "wayland-client":
                case.assertEqual(expected[root + "wayland.xml"], "cc860987e54f8d85c940e97fa1270c69b6e4ad31fbcf5a7f00107ce1157f5e07")
                case.assertEqual(record["protocolGrants"][root + "wayland.xml"]["license"], "MIT")
                expected[root + "src/lib.rs"] = row["coreProtocolGenerator"]["sha256"]
                for name in ("generate_interfaces", "generate_client_code"):
                    case.assertIn(f'wayland_scanner::{name}!("wayland.xml")'.encode(), archive.read(root + "src/lib.rs"))
            if row["name"] == "read-fonts":
                glyphs = record["sourceAttributions"]["data/glyphlist.txt"]
                case.assertEqual(glyphs["sha256"], "7bca3e2431753d85e6c6617707bec21396af7110199e746a3b75e01f0ace2346")
                adobe = archive.read("source-notices/" + glyphs["ranges"][0]["sha256"] + ".txt")
                for line in (b"Copyright 2002-2019 Adobe", b"Redistributions in binary form must reproduce",
                             b"Neither the name of Adobe", b"POSSIBILITY OF SUCH DAMAGE"):
                    case.assertIn(line, adobe)
                case.assertIn("src/ps/encoding.rs", record["sourceAttributions"])
            if row["name"] == "libm":
                inputs = record["sourceAttributions"]["src/math/acos.rs"]
                texts = b"\n".join(archive.read("source-notices/" + span["sha256"] + ".txt") for span in inputs["ranges"])
                for text in (b"FreeBSD", b"1993 by Sun Microsystems", b"Permission to use, copy, modify"):
                    case.assertIn(text, texts)
            if row["name"] == "ring":
                expected[root + "build.rs"] = "9d1928ffb1d8e15766c1c1b9ead73e4b81a21703dd25f7c27b87842a2e6e9cee"
                selected_ring = record["ringTargetSelection"]
                formats = {"x86_64-unknown-linux-gnu": ("-elf.S", 12), "x86_64-pc-windows-msvc": ("-nasm.o", 24),
                           "aarch64-unknown-linux-gnu": ("-linux64.S", 11), "aarch64-pc-windows-msvc": ("-win64.S", 11)}
                suffix, generated_count = formats[args.target]
                generated = selected_ring["generatedFrom"]
                case.assertEqual(len(generated), generated_count)
                name = next(p for p in generated if p.startswith("pregenerated/sha256-") and p.endswith(suffix))
                case.assertIn("/sha512-", generated[name])
                for generated_file, generator in generated.items():
                    case.assertIn(generated_file, record["ringSourceInputs"])
                    case.assertIn(generator, record["sourceAttributions"])
                for path, holder in [("crypto/fipsmodule/aes/aes_nohw.c", b"2019, Google Inc."),
                                     ("crypto/fipsmodule/ec/ecp_nistz.c", b"2014, Intel Corporation"),
                                     ("crypto/poly1305/poly1305.c", b"2014, Google Inc."),
                                     ("src/lib.rs", b"Brian Smith")]:
                    ranges = record["sourceAttributions"][path]["ranges"]
                    original = archive.read("source-notices/" + ranges[0]["sha256"] + ".txt")
                    for text in (holder, b"Permission to use, copy, modify", b"CONNECTION WITH THE USE"):
                        case.assertIn(text, original)
                    if path.endswith("/poly1305.c"):
                        extra = archive.read("source-notices/" + ranges[1]["sha256"] + ".txt")
                        case.assertIn(b"Andrew Moon", extra)
                        case.assertIn(b"public\n// domain.", extra)
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
        case.assertEqual(len(xml), 101 if linux else 0)
        case.assertEqual(sum("LGPL-2.1-or-later" in v["licenseIds"] for v in xml.values()), 18 if linux else 0)
        if linux:
            case.assertTrue(any(p.endswith("/plasma-wayland-protocols/COPYING.LIB") for p in expected))
            case.assertEqual({PurePosixPath(p).stem for p in expected if "/plasma-wayland-protocols/LICENSES/" in p},
                             {"BSD-3-Clause", "CC0-1.0", "LGPL-2.1-or-later", "MIT-CMU", "MIT"})
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
    if args.source_inventory and native_inventory.get("sourceNoticeFormat") is None:
        with tempfile.TemporaryDirectory() as area:
            changed = json.loads(args.source_inventory.read_bytes())
            ring = next(p for p in changed["packages"] if p["name"] == "ring")
            del ring["sourceAttributions"]["crypto/poly1305/poly1305.c"]["ranges"][1]
            path = Path(area) / "tampered.json"
            path.write_text(json.dumps(changed))
            with case.assertRaisesRegex(ValueError, "Supplemental source attribution inventory differs"):
                source_notices.qualified(native_inventory, path)
    print(f"Passed {args.target}: {len(units)} Cargo packages, {len(xml)} protocol XMLs, "
          f"{len(faces)} fonts, {len(expected) + 1} ZIP members")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--archive-sha256")
    parser.add_argument("--notices", type=Path)
    parser.add_argument("--source-inventory", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise SystemExit(1)
    if any(vars(args).values()):
        if not all((args.target, args.input, args.revision, args.archive_sha256, args.notices)):
            parser.error("Native checks require --target, --input, --revision, --archive-sha256 and --notices")
        check_native(args)
