# Third-Party Notices

This file lists third-party packages, licenses, and attribution notices used by
`immich-folder-watch`.

## Runtime Dependencies

| Package | Version | License | URL | Notes |
| --- | --- | --- | --- | --- |
| Microsoft.Data.Sqlite | 10.0.10 | MIT | https://www.nuget.org/packages/Microsoft.Data.Sqlite/10.0.10 | Direct dependency; lightweight ADO.NET provider for SQLite. |
| SQLitePCLRaw.bundle_e_sqlite3 | 3.0.5 | Apache-2.0 | https://github.com/ericsink/SQLitePCL.raw | Direct compatibility override for the native provider used by Microsoft.Data.Sqlite. |
| SQLite | Version supplied by the resolved SQLitePCLRaw native bundle | Public Domain | https://www.sqlite.org/copyright.html | Embedded SQLite database engine. |

Microsoft.Data.Sqlite is distributed under the MIT License. SQLitePCLRaw is
distributed under the Apache License, Version 2.0. The SQLite deliverable code
has been dedicated to the public domain by its authors. Follow the project URLs
above for the complete license and copyright terms applicable to the resolved
packages.

This notice summarizes the dependencies introduced for persistent sync state; it
does not replace the license texts supplied with packages or release artifacts.
