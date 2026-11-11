# Third-Party Notices

This file lists third-party packages, licenses, and attribution notices used by
`immich-folder-watch`.

## Runtime Dependencies

| Package | Version | License | URL | Notes |
| --- | --- | --- | --- | --- |
| Microsoft.Data.Sqlite | 11.0.0 | MIT | https://www.nuget.org/packages/Microsoft.Data.Sqlite/11.0.0 | Direct dependency; lightweight ADO.NET provider for SQLite. |
| SQLitePCLRaw.bundle_e_sqlite3 | 3.0.5 | Apache-2.0 | https://github.com/ericsink/SQLitePCL.raw | Direct compatibility override for the native provider used by Microsoft.Data.Sqlite. |
| SQLite | Version supplied by the resolved SQLitePCLRaw native bundle | Public Domain | https://www.sqlite.org/copyright.html | Embedded SQLite database engine. |

Microsoft.Data.Sqlite is distributed under the MIT License. SQLitePCLRaw is
distributed under the Apache License, Version 2.0. The SQLite deliverable code
has been dedicated to the public domain by its authors. Follow the project URLs
above for the complete license and copyright terms applicable to the resolved
packages.

This notice summarizes the dependencies introduced for persistent sync state; it
does not replace the license texts supplied with packages or release artifacts.

## Linux UI framework and protocol integration

The Linux application uses the project-specific reduced Avalonia 12.1.6.1
packages derived from official 12.1.6 sources. Retained components use MIT,
Apache-2.0 and BSD-style licenses; excluded MS-PL implementations/resources are
listed in [the source-removal inventory](packaging/avalonia-reduced/removals.json).
Original LICENSE/NOTICE texts are preserved without claiming that removed
components remain shipped. Retained SixLabors Apache-2.0 and Apple BSD-2-Clause
source attribution is included in the [Flatpak notice catalog](packaging/flatpak/licenses/README.md).
See [build/provenance details](docs/reduced-avalonia.md) and the
[component audit](docs/avalonia-component-audit-20261111.md).

Tmds.DBus.Protocol 0.94.1 is MIT-licensed. Its upstream source is commit
`b4a7fed0b878f74cb54f7cca84d2889af4e596ba`; the complete upstream COPYING text is
retained by Flatpak packaging. These updates do not change the Windows WPF host.
