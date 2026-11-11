#!/usr/bin/env python3
"""Reject excluded Avalonia type definitions in NuGet archives or publish trees.

Reads PE/CLI metadata without loading or executing assemblies. The nested
AutoCompleteSearch helper has an empty TypeDef namespace and is rejected
explicitly as well as excluded types in Avalonia.Controls namespaces. Native PE files
are skipped; malformed managed files fail closed. This verifies the named type
exclusion boundary, not resource contents, provenance, or license compatibility.
"""

import argparse
from pathlib import Path
import struct
import sys
import zipfile


FORBIDDEN_TYPES = frozenset({
    "AutoCompleteBox", "AutoCompleteSearch", "AutoCompleteFilterMode",
    "PopulatedEventArgs", "PopulatingEventArgs", "Calendar", "CalendarMode",
    "CalendarSelectionMode", "CalendarDateChangedEventArgs", "CalendarModeChangedEventArgs",
    "CalendarBlackoutDatesCollection", "CalendarButton", "CalendarDateRange",
    "CalendarDayButton", "CalendarExtensions", "CalendarItem", "DateTimeHelper",
    "SelectedDatesCollection", "CalendarDatePicker", "CalendarDatePickerDateValidationErrorEventArgs",
    "CalendarDatePickerFormat", "ISelectionAdapter", "SelectingItemsControlSelectionAdapter",
    "LayoutTransformControl", "AutoCompleteBoxAutomationPeer", "CalendarAutomationPeer",
    "CalendarDatePickerAutomationPeer", "CalendarDayButtonAutomationPeer",
})
MAX_BINARY_BYTES = 256 * 1024 * 1024


class AuditError(ValueError):
    """An input is malformed, empty, or contains an excluded type."""


class Reader:
    """Bounds-checked little-endian access to one PE file or metadata stream."""

    def __init__(self, data: bytes):
        self.data = data

    def take(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise AuditError("truncated binary or invalid metadata offset")
        return self.data[offset:offset + length]

    def integer(self, offset: int, size: int) -> int:
        return int.from_bytes(self.take(offset, size), "little")

    def text(self, offset: int) -> str:
        self.take(offset, 1)
        end = self.data.find(b"\0", offset)
        if end < 0:
            raise AuditError("unterminated metadata string")
        try:
            return self.data[offset:end].decode("utf-8")
        except UnicodeDecodeError as error:
            raise AuditError("invalid UTF-8 metadata string") from error


def type_definitions(data: bytes) -> list[tuple[str, str]] | None:
    """Return (namespace, type name) definitions, or None for a native PE file.

    Reads ECMA-335 TypeDef rows, including nonpublic types, in PE32/PE32+ images.
    No TypeRef or arbitrary string matches are treated as definitions.
    """
    r = Reader(data)
    if r.take(0, 2) != b"MZ":
        raise AuditError("not a PE image")
    pe = r.integer(0x3C, 4)
    if r.take(pe, 4) != b"PE\0\0":
        raise AuditError("invalid PE signature")
    optional = pe + 24
    optional_size = r.integer(pe + 20, 2)
    header = Reader(r.take(optional, optional_size))
    magic = header.integer(0, 2)
    if magic not in (0x10B, 0x20B):
        raise AuditError("unsupported PE optional header")
    directory = 96 if magic == 0x10B else 112
    if header.integer(directory - 4, 4) <= 14:
        return None
    cli_rva = header.integer(directory + 14 * 8, 4)
    cli_size = header.integer(directory + 14 * 8 + 4, 4)
    if not cli_rva and not cli_size:
        return None
    if not cli_rva or cli_size < 72:
        raise AuditError("invalid CLI directory")
    section_start = optional + optional_size
    sections = []
    for i in range(r.integer(pe + 6, 2)):
        section = section_start + 40 * i
        r.take(section, 40)
        sections.append((r.integer(section + 12, 4), r.integer(section + 16, 4),
                         r.integer(section + 20, 4)))

    def map_rva(address: int, size: int) -> int:
        for virtual, raw_size, raw in sections:
            delta = address - virtual
            if 0 <= delta and delta + size <= raw_size:
                r.take(raw + delta, size)
                return raw + delta
        raise AuditError("CLI address outside file-backed PE sections")

    cli = map_rva(cli_rva, cli_size)
    metadata_size = r.integer(cli + 12, 4)
    metadata = Reader(r.take(map_rva(r.integer(cli + 8, 4), metadata_size), metadata_size))
    if metadata.take(0, 4) != b"BSJB":
        raise AuditError("invalid CLI metadata signature")
    pos = (16 + metadata.integer(12, 4) + 3) & ~3
    count = metadata.integer(pos + 2, 2)
    pos += 4
    streams = {}
    for _ in range(count):
        start, size = metadata.integer(pos, 4), metadata.integer(pos + 4, 4)
        name = metadata.text(pos + 8)
        if name in streams:
            raise AuditError("duplicate CLI metadata stream")
        streams[name] = Reader(metadata.take(start, size))
        pos = (pos + 8 + len(name.encode("utf-8")) + 1 + 3) & ~3
    if "#Strings" not in streams or ("#~" not in streams and "#-" not in streams):
        raise AuditError("missing CLI metadata tables or strings")
    tables = streams.get("#~", streams.get("#-"))
    strings = streams["#Strings"]
    heaps = tables.integer(6, 1)
    valid = tables.integer(8, 8)
    rows = {}
    pos = 24
    for table in range(64):
        if valid & (1 << table):
            rows[table] = tables.integer(pos, 4)
            pos += 4
    # The optional extra-data word precedes the rows in an uncompressed stream.
    if heaps & 0x40:
        tables.take(pos, 4)
        pos += 4
    string_width = 4 if heaps & 1 else 2
    guid_width = 4 if heaps & 2 else 2

    def table_width(table: int) -> int:
        return 4 if rows.get(table, 0) >= 65536 else 2

    def coded_width(targets: tuple[int, ...], bits: int) -> int:
        return 4 if max(rows.get(table, 0) for table in targets) >= (1 << (16 - bits)) else 2

    pos += rows.get(0, 0) * (2 + string_width + 3 * guid_width)  # Module
    pos += rows.get(1, 0) * (coded_width((0, 26, 35, 1), 2) + 2 * string_width)  # TypeRef
    row_size = 4 + 2 * string_width + coded_width((2, 1, 27), 2) + table_width(4) + table_width(6)
    tables.take(pos, rows.get(2, 0) * row_size)
    definitions = []
    for i in range(rows.get(2, 0)):
        row = pos + i * row_size
        name = strings.text(tables.integer(row + 4, string_width))
        namespace = strings.text(tables.integer(row + 4 + string_width, string_width))
        definitions.append((namespace, name))
    return definitions


def audit(paths: list[Path]) -> tuple[int, int]:
    """Audit every DLL/EXE in archives or directories; return managed/native counts.

    Archives are inspected without extraction. Callers must also verify expected
    package identities and resources: an unrelated clean assembly is not proof
    that the required reduced framework is installed.
    """
    managed = native = 0

    def inspect(data: bytes, label: str) -> None:
        nonlocal managed, native
        try:
            definitions = type_definitions(data)
            if definitions is None:
                native += 1
                return
            managed += 1
            forbidden = [f"{ns}.{name}" for ns, name in definitions
                         if (ns == "Avalonia.Controls" or ns.startswith("Avalonia.Controls."))
                         and name in FORBIDDEN_TYPES
                         or (not ns and name == "AutoCompleteSearch")]
            if forbidden:
                raise AuditError("excluded type definitions: " + ", ".join(forbidden))
        except AuditError as error:
            raise AuditError(f"{label}: {error}") from error

    for path in paths:
        if not path.exists():
            raise AuditError(f"input does not exist: {path}")
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if not file.is_file():
                continue
            if file.suffix.lower() == ".nupkg":
                with zipfile.ZipFile(file) as archive:
                    seen = set()
                    for member in archive.infolist():
                        if Path(member.filename).suffix.lower() not in (".dll", ".exe"):
                            continue
                        if member.filename in seen:
                            raise AuditError(f"duplicate assembly entry: {file}!{member.filename}")
                        seen.add(member.filename)
                        if member.file_size > MAX_BINARY_BYTES:
                            raise AuditError(f"assembly exceeds size limit: {file}!{member.filename}")
                        inspect(archive.read(member), f"{file}!{member.filename}")
            elif file.suffix.lower() in (".dll", ".exe"):
                if file.stat().st_size > MAX_BINARY_BYTES:
                    raise AuditError(f"assembly exceeds size limit: {file}")
                inspect(file.read_bytes(), str(file))
    if not managed:
        raise AuditError("no managed assemblies were audited")
    return managed, native


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="NuGet archives or publish/feed directories")
    args = parser.parse_args()
    try:
        managed, native = audit(args.paths)
    except (AuditError, OSError, zipfile.BadZipFile, RuntimeError, struct.error) as error:
        print(f"Reduced Avalonia metadata audit failed: {error}", file=sys.stderr)
        return 1
    print(f"Audited {managed} managed assemblies; skipped {native} native PE images; no excluded type definitions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
