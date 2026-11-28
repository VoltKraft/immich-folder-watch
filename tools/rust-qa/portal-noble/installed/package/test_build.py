"""Check the private Noble source and binary receipt boundaries using synthetic package data."""
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

fixture = runpy.run_path(str(Path(__file__).with_name("build.py")))


class BuildTests(unittest.TestCase):
    def test_payload_manifest_compares_executable_modes_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / "binary"
            file.write_bytes(b"ELF fixture")
            file.chmod(0o640)
            (root / "link").symlink_to("binary")
            (root / ".pc").mkdir()
            (root / ".pc/transient").touch()
            first = fixture["sources"](root)
            self.assertEqual(set(first), {"binary", "link"})
            self.assertEqual(first["link"], ["link", "binary"])
            file.chmod(0o740)
            self.assertNotEqual(fixture["sources"](root), first)
            runtime = fixture["sources"](root, runtime=True)
            self.assertEqual(runtime["binary"][:2], ["file", 0o740])
            self.assertEqual(runtime[".pc"][0], "directory")
            self.assertIn(".pc/transient", runtime)
            file.chmod(0o744)
            self.assertNotEqual(fixture["sources"](root, runtime=True), runtime)

    def test_quilt_and_package_metadata_are_the_only_expected_source_differences(self):
        new = {p: True for p in [fixture["C_FILE"], "debian/changelog", "debian/rules", "debian/patches/series",
                                "debian/patches/" + fixture["PATCH_NAME"]]}
        check = fixture["check_source_delta"]
        check({}, new)
        for wrong in ("debian/postinst", "src/another.c"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                check({}, {**new, wrong: True})
        with self.assertRaises(ValueError):
            check({}, {k: v for k, v in new.items() if k != "debian/rules"})

    def test_packaged_bus_and_systemd_activation_select_the_same_native_services(self):
        verify = fixture["verify_services"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = []
            for bus, image in [("org.freedesktop.portal.Documents", "xdg-document-portal"),
                               ("org.freedesktop.impl.portal.PermissionStore", "xdg-permission-store")]:
                exe = "/usr/libexec/" + image
                unit = image + ".service"
                paths = {root / exe[1:]: "stub", root / ("usr/lib/systemd/user/" + unit):
                         f"[Service]\nType=dbus\nBusName={bus}\nExecStart={exe}\n",
                         root / f"usr/share/dbus-1/services/{bus}.service":
                         f"[D-BUS Service]\nName={bus}\nExec={exe}\nSystemdService={unit}\n"}
                for name, data in paths.items():
                    name.parent.mkdir(exist_ok=True, parents=True)
                    name.write_text(data)
                (root / exe[1:]).chmod(0o755)
                files.extend(paths)
            self.assertEqual(len(verify(root)), 2)
            for case in [(files[1], "Type=dbus", "Type=forking"), (files[2], "Name=", "name="),
                         (files[4], "ExecStart=/usr", "ExecStart=/unrelated"),
                         (files[5], "xdg-permission-store.service", "unknown.service")]:
                name, before, replacement = case
                original = name.read_text()
                with self.subTest(case=case), self.assertRaises((ValueError, KeyError)):
                    name.write_text(original.replace(before, replacement))
                    verify(root)
                name.write_text(original)
            files[0].chmod(0o640)
            with self.assertRaises(ValueError):
                verify(root)

    def test_package_build_and_changes_records_bind_the_complete_set_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root / "test.deb"
            payload.write_bytes(b"native")
            record = root / "test.changes"
            header = f"Source: {fixture['SOURCE']}\nVersion: {fixture['QA_VERSION']}\nChecksums-Sha256:\n"
            row = f" {fixture['sha'](payload)} 6 test.deb\n"
            check = fixture["package_checksums"]
            record.write_text(header + row)
            check(record, {payload.name})
            with self.assertRaises(ValueError):
                check(record, {payload.name, "missing.deb"})
            for wrong in (row + row, row.replace(" 6 ", " 7 "), row.replace("test.deb", "../test.deb")):
                with self.subTest(row=wrong), self.assertRaises(ValueError):
                    record.write_text(header + wrong)
                    check(record, {payload.name})
            record.write_text(header + row)
            payload.write_bytes(b"alterd")
            with self.assertRaises(ValueError):
                check(record, {payload.name})

    def test_elf_machine_and_build_id_are_independent_of_package_filename(self):
        check = fixture["native_image"]
        with patch("subprocess.check_output", side_effect=["  Machine: AArch64\n", " Build ID: 1234abcdef\n"]):
            self.assertEqual(check(Path("daemon"), "arm64"), "1234abcdef")
        with patch("subprocess.check_output", return_value="  Machine: AArch64\n"), self.assertRaises(ValueError):
            check(Path("daemon"), "amd64")
        with (
            patch("subprocess.check_output", side_effect=["  Machine: AArch64\n", ""]),
            self.assertRaises(ValueError),
        ):
            check(Path("daemon"), "arm64")

    def test_debug_split_can_rewrite_the_build_id_only(self):
        check = fixture["allocated_sections"]
        sections = [(".text", "PROGBITS", 0, 4, "AX"), (".rodata", "PROGBITS", 4, 4, "A"),
                    (".dynamic", "DYNAMIC", 8, 4, "WA"), (".dynsym", "DYNSYM", 12, 4, "A"),
                    (".note.gnu.build-id", "NOTE", 16, 36, "A")]
        listing = "\n".join(f" [{i}] {name} {kind} 1000 {offset:x} {size:x} 00 {flags} 0 0 4"
                            for i, (name, kind, offset, size, flags) in enumerate(sections, 1))
        b = bytearray(b"data" * 4 + bytes.fromhex("040000001400000003000000474e5500") + bytes(20))
        with tempfile.TemporaryDirectory() as temp, patch("subprocess.check_output", return_value=listing):
            image = Path(temp) / "daemon"
            image.write_bytes(b)
            original = check(image)
            b[-1] ^= 0xff
            image.write_bytes(b)
            self.assertEqual(check(image), original)
            b[0] ^= 0xff
            image.write_bytes(b)
            self.assertNotEqual(check(image), original)
            b[16] ^= 0xff
            image.write_bytes(b)
            with self.assertRaises(ValueError):
                check(image)


if __name__ == "__main__":
    unittest.main()
