"""Run SPDX controls. With a native evidence input, also exercise both input forms and tampering controls."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import sbom


class Controls(unittest.TestCase):
    def test_cargo_build_section_ends_with_its_parent(self):
        tree = """app v1|
|-- builder v1|
|   [build-dependencies]
|   `-- library v1|
|       `-- transitive v1|
`-- library v1| (*)
"""
        features = {name + " v1": [[]] for name in ("app", "builder", "library", "transitive")}
        root, edges = sbom.graph_edges(tree, features)
        self.assertEqual(root, "app v1")
        self.assertEqual(edges, {("app v1", "DEPENDS_ON", "builder v1"), ("library v1", "BUILD_DEPENDENCY_OF", "builder v1"),
                                 ("library v1", "DEPENDS_ON", "transitive v1"), ("app v1", "DEPENDS_ON", "library v1")})
        features["omitted v1"] = [[]]
        with self.assertRaisesRegex(ValueError, "Missing Cargo tree"):
            sbom.graph_edges(tree, features)

    def test_identifiers_distinguish_names_versions_and_reserved_characters(self):
        keys = ["a_b v1.1", "a-b v1.1", "a-5fb v1.1", "a-b v1+1", "a-b v1.2", "a b v1.1"]
        ids = {sbom.ident("Cargo", name) for name in keys}
        self.assertEqual(len(keys), len(ids))
        for name in ids:
            self.assertRegex(name, r"^SPDXRef-[A-Za-z0-9.-]+$")

    def test_extracted_license_must_match_text_and_links(self):
        text = "Synthetic file-specific grant.\n"
        extracted = {}
        ref = sbom.extract(extracted, "Example", text)
        package = sbom.package("SPDXRef-Test", "Example", "SOURCE", ref, ref)
        doc = {"packages": [package], "relationships": [], "documentDescribes": ["SPDXRef-Test"],
               "hasExtractedLicensingInfos": list(extracted.values())}
        sbom.validate_references(doc)
        broken = copy.deepcopy(doc)
        broken["hasExtractedLicensingInfos"][0]["extractedText"] = "different"
        with self.assertRaisesRegex(ValueError, "Changed extracted grant"):
            sbom.validate_references(broken)
        broken = copy.deepcopy(doc)
        broken["hasExtractedLicensingInfos"] = []
        with self.assertRaisesRegex(ValueError, "Dangling or unreferenced"):
            sbom.validate_references(broken)
        doc["relationships"].append({"spdxElementId": package["SPDXID"], "relatedSpdxElement": "SPDXRef-Unknown"})
        with self.assertRaisesRegex(ValueError, "Dangling SPDX relationship"):
            sbom.validate_references(doc)

    def test_unreviewed_absent_xml_notice_fails(self):
        with self.assertRaisesRegex(ValueError, "Unreviewed protocol"):
            sbom.protocol_package("example v1", "other.xml", {"copyright": "", "licenseIds": [], "sha256": "a" * 64},
                                  {"supplementalNotices": {}}, {})

    def test_zip_requires_the_published_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("unrelated", "fixture")
            with self.assertRaisesRegex(ValueError, "requires"):
                sbom.read_run(path, "target", None)
            with self.assertRaisesRegex(ValueError, "archive checksum mismatch"):
                sbom.read_run(path, "target", "c" * 64)

    def test_source_verification_only_accepts_checkout_line_endings_on_windows(self):
        lf = b"first\nsecond\n"
        windows_hash = sbom.sha(b"first\r\nsecond\r\n")
        sbom.source_matches(lf, windows_hash, True, "fixture.rs")
        with self.assertRaisesRegex(ValueError, "Source checksum"):
            sbom.source_matches(lf, windows_hash, False, "fixture.rs")
        with self.assertRaisesRegex(ValueError, "Source checksum"):
            sbom.source_matches(b"other", windows_hash, True, "fixture.rs")


def check_build(args):
    case = unittest.TestCase()
    receipt, digest, files = sbom.read_run(args.input, args.target, args.archive_sha256)
    doc = sbom.assemble(receipt, digest, files, args.revision, args.target)
    case.assertEqual(doc, json.loads(args.document.read_bytes()))
    if args.schema:
        # Optional development validation. The generator and ordinary control suite require only the stdlib.
        from jsonschema import Draft201909Validator
        schema = args.schema.read_bytes()
        case.assertEqual(sbom.sha(schema), "4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212")
        validator = Draft201909Validator(json.loads(schema), format_checker=Draft201909Validator.FORMAT_CHECKER)
        validator.validate(doc)
    packages = {p["SPDXID"]: p for p in doc["packages"]}
    cargo = {k: v for k, v in packages.items() if k.startswith("SPDXRef-Cargo-")}
    case.assertEqual(len(cargo), receipt["native"]["compilerUnits"]["packages"])
    case.assertEqual(packages[sbom.BINARY]["checksums"][0]["checksumValue"], receipt["native"]["binarySha256"])
    case.assertEqual(len([k for k in packages if k.startswith("SPDXRef-Font-")]), 5)
    case.assertEqual(packages["SPDXRef-SQLiteSource"]["licenseConcluded"], "blessing")
    for p in cargo.values():
        roles = json.loads(p["comment"])["compiledUnits"]
        if all(unit["compiledFor"] == ["host"] for unit in roles):
            case.assertFalse(any(r["relatedSpdxElement"] == p["SPDXID"] and r["relationshipType"] == "DEPENDS_ON"
                                 for r in doc["relationships"]))
        if p["name"] in {"base64", "egui", "epaint", "unicode-bidi"}:
            case.assertEqual(p["downloadLocation"], "NOASSERTION")
            case.assertNotIn("checksums", p)
            case.assertIn("upstreamArchiveSha256", json.loads(p["sourceInfo"]))
    case.assertIn("LicenseRef-GranitParserNotice-" + sbom.sha(sbom.GRANIT_NOTICE.encode()),
                  {e["licenseId"] for e in doc["hasExtractedLicensingInfos"]})
    protocols = [p for k, p in packages.items() if k.startswith("SPDXRef-Protocol-")]
    case.assertEqual(len(protocols), 100 if "linux" in args.target else 0)
    case.assertEqual(sum(p["licenseConcluded"] == "LGPL-2.1-or-later" for p in protocols),
                     18 if "linux" in args.target else 0)
    if "windows" in args.target:
        arch = args.target.split("-")[0]
        imports = next(p for p in cargo.values() if p["name"] == f"windows_{arch}_msvc")
        case.assertIn("lib/windows.0.52.0.lib", json.loads(imports["sourceInfo"])["retainedNativeInputs"])
    wrong = copy.deepcopy(receipt)
    wrong["native"]["target"] = "another-native-target"
    with case.assertRaisesRegex(ValueError, "Native compiler target mismatch"):
        sbom.verify(wrong, files, args.revision, args.target)
    with case.assertRaisesRegex(ValueError, "requested revision"):
        sbom.verify(receipt, files, "0" * 40, args.target)
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        files_to_copy = [*receipt["outputs"], "result.json"]
        if args.input.is_dir():
            for name in files_to_copy:
                (run / name).write_bytes((args.input / name).read_bytes())
        else:
            prefix = f"combined-profile/runs/{args.target}/"
            with ZipFile(args.input) as archive:
                for name in files_to_copy:
                    (run / name).write_bytes(archive.read(prefix + name))
        direct_receipt, direct_digest, direct = sbom.read_run(run, args.target, None)
        case.assertEqual(doc, sbom.assemble(direct_receipt, direct_digest, direct, args.revision, args.target))
        inventory = json.loads((run / "inventory.json").read_bytes())
        inventory["packages"][0]["selected"] = "CC0-1.0"
        altered = json.dumps(inventory).encode()
        (run / "inventory.json").write_bytes(altered)
        with case.assertRaisesRegex(ValueError, "Output checksum mismatch"):
            sbom.read_run(run, args.target, None)
        direct_receipt["outputs"]["inventory.json"] = sbom.sha(altered)
        (run / "result.json").write_text(json.dumps(direct_receipt), encoding="utf-8")
        direct_receipt, _, direct = sbom.read_run(run, args.target, None)
        with case.assertRaisesRegex(ValueError, "Changed reviewed source inventory"):
            sbom.verify(direct_receipt, direct, args.revision, args.target)
    fake = copy.deepcopy(receipt)
    unit_data = json.loads(files["compiler-units.json"])
    unit_data["units"][0]["compiledFor"] = ["host"] if unit_data["units"][0]["compiledFor"] != ["host"] else [args.target]
    altered = json.dumps(unit_data).encode()
    fake["native"]["compilerUnits"]["reportSha256"] = fake["outputs"]["compiler-units.json"] = sbom.sha(altered)
    with case.assertRaisesRegex(ValueError, "differs from the native Cargo build log"):
        sbom.verify(fake, {**files, "compiler-units.json": altered}, args.revision, args.target)
    print(f"Passed {args.target}: {len(packages)} SPDX packages, {len(doc['relationships'])} relationships")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--archive-sha256")
    parser.add_argument("--document", type=Path)
    parser.add_argument("--schema", type=Path)
    options = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise SystemExit(1)
    if options.target:
        if not (options.input and options.document and options.revision):
            parser.error("Native controls require --input, --document and --revision")
        check_build(options)
