#!/usr/bin/env python3
"""Emit a single AppStream <release> block for a given version.

Reads the matching ``## [<version>] - <date>`` section from CHANGELOG.md and
writes a release element to stdout. Bullet items tagged ``(Windows)`` are
filtered out so the Linux-facing AppStream metadata only documents what
Linux users will see; ``(Linux)`` and ``(Both)`` markers are kept and the
trailing tag itself is stripped.

Usage:
    tools/update-appstream.py <version> [path/to/CHANGELOG.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(
    r"^## \[(?P<version>[^\]]+)\](?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)
SUB_HEADING_RE = re.compile(r"^###\s+(?P<title>.+?)\s*$")
LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s+(?P<text>.*)$")
PLATFORM_TAG_RE = re.compile(r"\s*\((?P<tag>Windows|Linux|Both)\)\s*$", re.IGNORECASE)


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(f"Usage: {sys.argv[0]} <version> [CHANGELOG.md]\n")
        return 2

    version = sys.argv[1]
    changelog = Path(
        sys.argv[2]
        if len(sys.argv) > 2
        else Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    )

    if not changelog.is_file():
        sys.stderr.write(f"CHANGELOG not found: {changelog}\n")
        return 1

    body, date = _extract_section(changelog.read_text(encoding="utf-8"), version)
    if body is None:
        sys.stderr.write(f"No '## [{version}]' section in {changelog}\n")
        return 1

    print(_to_release_block(version, date, body))
    return 0


def _extract_section(text: str, target_version: str) -> tuple[str | None, str | None]:
    lines = text.splitlines()
    start: int | None = None
    end = len(lines)
    date: str | None = None
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        if match.group("version") == target_version:
            start = idx + 1
            date = match.group("date")
        elif start is not None:
            end = idx
            break

    if start is None:
        return None, None

    return "\n".join(lines[start:end]).strip(), date


def _to_release_block(version: str, date: str | None, body: str) -> str:
    description = _markdown_to_description(body)
    date_attr = f' date="{date}"' if date else ""
    return (
        f'<release version="{version}"{date_attr}>\n'
        f"  <description>\n"
        f"{description}\n"
        f"  </description>\n"
        f"</release>"
    )


def _markdown_to_description(body: str) -> str:
    rendered: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            rendered.append("    </ul>")
            in_ul = False

    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        sub = SUB_HEADING_RE.match(line)
        if sub:
            close_ul()
            rendered.append(f"    <p>{_xml_escape(sub.group('title'))}:</p>")
            continue

        item = LIST_ITEM_RE.match(line)
        if item:
            text, kept = _strip_platform_tag(item.group("text"))
            if not kept:
                continue
            if not in_ul:
                rendered.append("    <ul>")
                in_ul = True
            rendered.append(f"      <li>{_xml_escape(text)}</li>")
            continue

        text, kept = _strip_platform_tag(line.strip())
        if not kept:
            continue
        close_ul()
        rendered.append(f"    <p>{_xml_escape(text)}</p>")

    close_ul()

    if not rendered:
        return "    <p>No notable changes.</p>"

    return "\n".join(rendered)


def _strip_platform_tag(text: str) -> tuple[str, bool]:
    """Return (text-without-tag, keep) — drop entries tagged (Windows)."""
    match = PLATFORM_TAG_RE.search(text)
    if not match:
        return text, True
    tag = match.group("tag").lower()
    if tag == "windows":
        return "", False
    return PLATFORM_TAG_RE.sub("", text).rstrip(), True


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    sys.exit(main())
