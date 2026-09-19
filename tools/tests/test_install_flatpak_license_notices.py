from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZipFile, ZipInfo


SCRIPT_PATH = Path(__file__).parents[1] / "install-flatpak-license-notices.py"
SPEC = importlib.util.spec_from_file_location("install_flatpak_license_notices", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LicenseNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.feed = self.root / "feed"
        self.feed.mkdir()
        self.output = self.root / "output"
        self.supplements = self.root / "supplements"
        self.supplements.mkdir()
        self.configure_supplements()

    def configure_supplements(self, version: str | None = None) -> None:
        catalog, sources = {}, {}
        if version:
            content = b"Copyright Example contributors\nPermission is hereby granted.\n"
            (self.supplements / "Example-LICENSE.txt").write_bytes(content)
            catalog = {"example": {version: ["Example-LICENSE.txt"]}}
            sources = {"Example-LICENSE.txt": {
                "url": "https://example.org/source/abcdef/LICENSE",
                "sha256": hashlib.sha256(content).hexdigest(),
            }}
        (self.supplements / "catalog.json").write_text(json.dumps(catalog))
        (self.supplements / "sources.json").write_text(json.dumps(sources))

    def package(self, entries: dict | None = None, *, package_id: str = "Example", version: str = "1.0.0", license_element: str = '<license type="expression">MIT</license>') -> Path:
        path = self.feed / f"{len(list(self.feed.iterdir()))}.nupkg"
        with ZipFile(path, "w") as archive:
            archive.writestr("example.nuspec", f"""<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>{package_id}</id><version>{version}</version>
    <authors>Example contributors</authors><copyright>Copyright Example</copyright>
    {license_element}<licenseUrl>https://licenses.nuget.org/MIT</licenseUrl>
    <repository type="git" url="https://example.org/source" commit="abcdef" />
  </metadata>
</package>""")
            for name, content in (entries if entries is not None else {"LICENSE.txt": b"Original license text\n"}).items():
                archive.writestr(name, content)
        return path

    def run_install(self) -> list[dict]:
        return MODULE.install_notices(self.feed, self.output, self.supplements)

    def test_preserves_original_text_and_inventory_with_source_hash(self) -> None:
        path = self.package({
            "LICENSE.TXT": b"Copyright and original terms\r\n",
            "legal/THIRD-PARTY-NOTICES.txt": b"Native dependency notices\n",
            "runtimes/linux-x64/native/example.so": b"\x00binary",
        })
        self.package(package_id="Another", version="2.0.0")
        packages = self.run_install()
        self.assertEqual(["Another", "Example"], [package["id"] for package in packages])
        self.assertEqual(b"Copyright and original terms\r\n", (self.output / "example/1.0.0/archive/LICENSE.TXT").read_bytes())
        self.assertEqual(b"Native dependency notices\n", (self.output / "example/1.0.0/archive/legal/THIRD-PARTY-NOTICES.txt").read_bytes())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), packages[1]["source_sha256"])
        self.assertEqual("abcdef", packages[1]["repository"]["commit"])
        index = json.loads((self.output / "index.json").read_text())
        self.assertIn("not a runtime SBOM", index["scope"])
        self.assertFalse(any(self.output.rglob("*.so")))

    def test_copies_explicit_license_file_with_unusual_name(self) -> None:
        self.package({"legal/terms.txt": b"Full custom license\n"}, license_element='<license type="file">legal/terms.txt</license>')
        self.run_install()
        self.assertEqual(b"Full custom license\n", (self.output / "example/1.0.0/archive/legal/terms.txt").read_bytes())

    def test_installs_version_pinned_supplement_with_provenance(self) -> None:
        self.configure_supplements("1.0.0")
        self.package({"THIRD-PARTY-NOTICES.TXT": b"Original dependency notices"})
        packages = self.run_install()
        notice = self.output / "example/1.0.0/upstream/Example-LICENSE.txt"
        self.assertEqual((self.supplements / "Example-LICENSE.txt").read_bytes(), notice.read_bytes())
        self.assertEqual("https://example.org/source/abcdef/LICENSE", packages[0]["supplemental_sources"][0]["url"])

    def test_missing_license_text_fails_even_with_spdx_expression_and_notices(self) -> None:
        self.package({"THIRD-PARTY-NOTICES.TXT": b"Dependency notices only"})
        with self.assertRaisesRegex(MODULE.NoticeError, "license text missing"):
            self.run_install()
        self.assertFalse(self.output.exists())

    def test_unknown_supplement_version_requires_review(self) -> None:
        self.configure_supplements("1.0.0")
        self.package(version="2.0.0")
        with self.assertRaisesRegex(MODULE.NoticeError, "new package version"):
            self.run_install()
        self.assertFalse(self.output.exists())

    def test_modified_supplement_fails_before_output(self) -> None:
        self.configure_supplements("1.0.0")
        (self.supplements / "Example-LICENSE.txt").write_text("Modified terms")
        self.package()
        with self.assertRaisesRegex(MODULE.NoticeError, "checksum mismatch"):
            self.run_install()
        self.assertFalse(self.output.exists())

    def test_rejects_selected_archive_path_traversal(self) -> None:
        for name in ("../LICENSE", "/LICENSE", "nested/../../LICENSE", "nested\\LICENSE", "C:/LICENSE", "./LICENSE"):
            with self.subTest(name=name):
                path = self.package({name: b"Untrusted license"})
                with self.assertRaisesRegex(MODULE.NoticeError, "unsafe notice path"):
                    self.run_install()
                self.assertFalse(self.output.exists())
                path.unlink()
        self.assertFalse((self.root / "LICENSE").exists())

    def test_rejects_archive_symlink(self) -> None:
        item = ZipInfo("LICENSE")
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.package({item: b"/etc/passwd"})
        with self.assertRaisesRegex(MODULE.NoticeError, "not a regular file"):
            self.run_install()
        self.assertFalse(self.output.exists())

    def test_rejects_missing_explicit_license_file(self) -> None:
        self.package(license_element='<license type="file">terms.txt</license>')
        with self.assertRaisesRegex(MODULE.NoticeError, "declared license file is missing"):
            self.run_install()

    def test_rejects_malicious_package_identity(self) -> None:
        self.package(package_id="../escape")
        with self.assertRaisesRegex(MODULE.NoticeError, "invalid package identity"):
            self.run_install()
        self.assertFalse(self.output.exists())

    def test_rejects_duplicate_zip_entries(self) -> None:
        path = self.package()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(path, "a") as archive:
                archive.writestr("LICENSE.txt", "Different terms")
        with self.assertRaisesRegex(MODULE.NoticeError, "duplicate archive entries"):
            self.run_install()

    def test_rejects_duplicate_package_identity_before_writing(self) -> None:
        self.package()
        self.package(package_id="example")
        with self.assertRaisesRegex(MODULE.NoticeError, "duplicate package identity"):
            self.run_install()
        self.assertFalse(self.output.exists())

    def test_rejects_binary_notice(self) -> None:
        self.package({"LICENSE": b"binary\x00file"})
        with self.assertRaisesRegex(MODULE.NoticeError, "empty or binary"):
            self.run_install()

    def test_preserves_existing_output(self) -> None:
        self.package()
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("Existing output")
        with self.assertRaisesRegex(MODULE.NoticeError, "empty or absent"):
            self.run_install()
        self.assertEqual("Existing output", sentinel.read_text())

    def test_rejects_output_symlink(self) -> None:
        self.package()
        target = self.root / "target"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.NoticeError, "empty or absent"):
            self.run_install()
        self.assertFalse(any(target.iterdir()))


if __name__ == "__main__":
    unittest.main()
