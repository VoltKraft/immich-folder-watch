"""Regression tests for the reduced Avalonia PE/CLI exclusion boundary."""

from pathlib import Path
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_reduced_avalonia import AuditError, FORBIDDEN_TYPES, audit, type_definitions


def image(name="Button", namespace="Avalonia.Controls", *, native=False,
          pe64=False, large_heaps=False, uncompressed=False, type_reference="Calendar"):
    """Construct a minimal PE with independently laid-out ECMA-335 tables."""
    data = bytearray(2048)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x86, 1)
    optional_size = 240 if pe64 else 224
    struct.pack_into("<H", data, 0x94, optional_size)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x20B if pe64 else 0x10B)
    directory = 112 if pe64 else 96
    struct.pack_into("<I", data, optional + directory - 4, 16)
    if native:
        return bytes(data)
    struct.pack_into("<II", data, optional + directory + 14 * 8, 0x2000, 72)
    section = optional + optional_size
    data[section:section + 5] = b".text"
    struct.pack_into("<IIII", data, section + 8, 1536, 0x2000, 1536, 512)
    strings = b"\0" + name.encode() + b"\0" + namespace.encode() + b"\0" + type_reference.encode() + b"\0"
    ns_index = 2 + len(name.encode())
    ref_index = ns_index + len(namespace.encode()) + 1
    width = "I" if large_heaps else "H"
    tables = bytearray(struct.pack("<IBBBBQQIII", 0, 2, 0, 3 if large_heaps else 0, 1, 7, 0, 1, 1, 1))
    tables += struct.pack("<H" + width * 4, 0, 0, 0, 0, 0)  # Module
    tables += struct.pack("<H" + width * 2, 0, ref_index, ns_index)  # TypeRef
    tables += struct.pack("<I" + width * 2 + "HHH", 1, 1, ns_index, 0, 1, 1)  # TypeDef
    strings_offset = (56 + len(tables) + 3) & ~3
    metadata = bytearray(strings_offset + len(strings))
    struct.pack_into("<4sHHII4sHH", metadata, 0, b"BSJB", 1, 1, 0, 4, b"v4\0\0", 0, 2)
    struct.pack_into("<II4s", metadata, 24, 56, len(tables), b"#-\0\0" if uncompressed else b"#~\0\0")
    struct.pack_into("<II12s", metadata, 36, strings_offset, len(strings), b"#Strings\0\0\0\0")
    metadata[56:56 + len(tables)] = tables
    metadata[strings_offset:] = strings
    struct.pack_into("<IHHII", data, 512, 72, 2, 5, 0x2080, len(metadata))
    data[640:640 + len(metadata)] = metadata
    return bytes(data)


class ReducedAvaloniaMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_reads_pe32_pe64_large_heaps_and_uncompressed_tables(self):
        for pe64 in (False, True):
            for large in (False, True):
                for uncompressed in (False, True):
                    with self.subTest(pe64=pe64, large=large, uncompressed=uncompressed):
                        self.assertEqual(type_definitions(image(pe64=pe64, large_heaps=large,
                                                                uncompressed=uncompressed)),
                                         [("Avalonia.Controls", "Button")])

    def test_native_pe_is_distinguished_from_malformed_binary(self):
        self.assertIsNone(type_definitions(image(native=True)))
        for data in (b"", b"not a PE", image()[:680]):
            with self.subTest(size=len(data)), self.assertRaises(AuditError):
                type_definitions(data)

    def test_every_excluded_type_is_rejected_in_ref_or_tools_archive_entries(self):
        package = self.root / "framework.nupkg"
        for name in FORBIDDEN_TYPES:
            with self.subTest(name=name):
                with zipfile.ZipFile(package, "w") as archive:
                    archive.writestr("lib/net10.0/Clean.dll", image())
                    archive.writestr("ref/net10.0/Avalonia.Controls.dll", image(name))
                with self.assertRaisesRegex(AuditError, "excluded type definitions"):
                    audit([package])
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("tools/designer/Host.dll", image("Calendar"))
        with self.assertRaisesRegex(AuditError, "tools/designer/Host.dll"):
            audit([package])

    def test_namespace_and_typeref_do_not_cause_false_positives(self):
        (self.root / "Runtime.dll").write_bytes(image("Calendar", "System.Globalization"))
        (self.root / "Framework.dll").write_bytes(image(type_reference="Calendar"))
        (self.root / "Native.dll").write_bytes(image(native=True))
        self.assertEqual(audit([self.root]), (2, 1))

    def test_helpers_and_primitives_are_rejected(self):
        path = self.root / "Framework.dll"
        for ns, name in [("Avalonia.Controls.Primitives", "CalendarButton"),
                         ("Avalonia.Controls.Utils", "ISelectionAdapter"),
                         ("Avalonia.Controls.Automation.Peers", "CalendarAutomationPeer")]:
            with self.subTest(namespace=ns):
                path.write_bytes(image(name, ns))
                with self.assertRaises(AuditError):
                    audit([path])

    def test_invalid_string_index_fails_closed(self):
        data = bytearray(image())
        # TypeDef follows the tables header/counts, Module row, and TypeRef row.
        struct.pack_into("<H", data, 640 + 56 + 36 + 10 + 6 + 4, 65535)
        with self.assertRaises(AuditError):
            type_definitions(bytes(data))

    def test_zero_cli_rva_with_nonzero_size_is_not_native(self):
        data = bytearray(image())
        struct.pack_into("<I", data, 0x98 + 96 + 14 * 8, 0)
        with self.assertRaisesRegex(AuditError, "CLI directory"):
            type_definitions(bytes(data))

    def test_missing_empty_and_native_only_inputs_do_not_pass(self):
        with self.assertRaisesRegex(AuditError, "does not exist"):
            audit([self.root / "missing"])
        with self.assertRaisesRegex(AuditError, "no managed"):
            audit([self.root])
        (self.root / "Host.exe").write_bytes(image(native=True))
        with self.assertRaisesRegex(AuditError, "no managed"):
            audit([self.root])

    def test_duplicate_assembly_zip_entry_is_rejected(self):
        path = self.root / "duplicate.nupkg"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("lib/Framework.dll", image())
                archive.writestr("lib/Framework.dll", image())
        with self.assertRaisesRegex(AuditError, "duplicate assembly"):
            audit([path])


class NestedTypeAuditTests(unittest.TestCase):
    def test_nested_autocomplete_helper_with_empty_namespace_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.dll"
            path.write_bytes(image(name="AutoCompleteSearch", namespace=""))
            with self.assertRaisesRegex(AuditError, "AutoCompleteSearch"):
                audit([path])


if __name__ == "__main__":
    unittest.main()
