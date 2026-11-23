# Installed 3.0.4 migration reference

The four published 3.0.4 packages supply the legacy side of the installed
migration rehearsal. The release tag points to
`4149763b7f322603a012aebad5f8a252450eb08b`. The shipping source reference
used for the worker tests is `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`.
The application source and Flatpak packaging match between those revisions.
The Windows packaging difference is its README. The [release manifest](../../tools/RustCompatibilityOracle/installed/release.json)
records each original filename, release asset ID, size and SHA-256.
[Published 3.0.4 packages](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.4).

Each test uses the shipping YAML defaults with an empty endpoint, key and
watch list. The synthetic SQLite fixture contains two owned albums, two
account histories, four mappings including tombstones, and one repair entry.
The test hashes the original profile and checks its retained bytes after
package removal. SQLite integrity, version, exact table names and row counts
are checked again in the retained copy. The profile and native package logs
are part of the evidence. [Synthetic fixtures](../../rust/tests/fixtures/legacy) · [Native runner](../../tools/RustCompatibilityOracle/installed/run.py).

| Platform | Installed-package checks |
| --- | --- |
| Linux x64 and ARM64 | Deploy the original bundle into a fresh per-user Flatpak installation in a private mount, user, PID, network and IPC namespace. Compare the installed tree against the original OSTree commit. Remove its verified metainfo file, repair from a local repository imported from that bundle, compare the complete tree again, and perform ordinary uninstall. Inspect the ELF machine, runtime declaration and installed application metadata. The application stays stopped. |
| Windows x64 and ARM64 | On a fresh disposable Actions runner, inspect the original MSI, verify that the targeted product, paths, registry values and service are absent, seed the isolated profile, then run Windows Installer. Check all installed bytes against the embedded cabinet digest and inspect the native PE headers. Remove the verified SQLite library, repair missing files, compare the payload again and perform ordinary uninstall. Retain the original Windows Installer logs, registration observations and profile. Record Windows Installer’s start markers for the migration and relaunch actions and the actual Startup shortcut at each checkpoint. |

The x64 MSI contains 439 files totalling 149,235,325 bytes. The ARM64 MSI
contains 438 totalling 160,659,509 bytes. A local reconstruction of the two
original cabinets checked all 877 file destinations and ten PE machine headers.
The native Windows workflow performs the separate installed checks.
[Windows fixture](../../tools/RustCompatibilityOracle/installed/windows.ps1) · [Linux fixture](../../tools/RustCompatibilityOracle/installed/linux.py).

## Fedora x64

Flatpak 1.18.4 on Fedora 45 deployed release asset `745213366` at commit
`abeebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da`.
The original, installed and repaired trees matched across 785 entries. The
Flatpak deployment also contained its empty internal lock file. Repair
restored the metainfo file to SHA-256
`b01ec8e2e96cd3bae15d3b6221963ffaca3ce914a3e1585ab4eb60e4352ee59e`.
After uninstall, the deployment and installed ref were gone. The retained
database and YAML matched the seeds at all four checkpoints. The apphost
and three native runtime libraries identified x86-64. The package declared
Freedesktop 26.08 and bundled .NET 10.0.12. The test ran offline without
installing the shared platform runtime or starting a media worker. The local
evidence is in `artifacts/rust/shipping-install-fedora-linux-x64-private-mount/`.
Independent review verified all 16 indexed files, nine fixture source
digests, 26 native commands and the complete retained SQLite schema and
rows. The evidence index SHA-256 is
`6796b7ab797bf7723d20f47d5e84788058a5924502f86b017ff223e422bfb910`.
[Reproduction](../development.md#original-package-install-and-repair).

The complete Fedora trial repeated from commit `285101b` with a clean
fixture source record. Reading the retained database independently
reproduced the full SQL dump of the shipping fixture. All nine sources and
16 evidence files verified. The index in
`artifacts/rust/shipping-install-fedora-285101b/` has SHA-256
`39c118eacde33f01eeafa59d1b5ecf4f8e8909d16da55d4b62f4b5279e2d2b79`.

RI-AC08 still requires the four Rust packages, native old-to-new upgrades,
repair, removal and rollback after activity in the installed Rust application.
[Acceptance matrix](acceptance.md#overall-acceptance).
