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
| Windows x64 and ARM64 | Inspect the original MSI tables on a fresh disposable runner, verify that the product footprint is absent, seed the isolated profile and run Windows Installer. Check every installed file against the embedded cabinet and inspect the native PE headers. Remove the verified SQLite library, repair missing files, compare the payload again and perform ordinary uninstall. Retain the original logs, registration observations and profile. Check the executable's desktop shortcut and the absence of an application-created Startup link while the app is stopped. |

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

## First native package run

At `1b95ba0` Windows Installer completed the initial installation and cleanup
uninstall on both hosted Windows targets. The x64 logs recorded 439 file
copies and removals, and the ARM64 logs recorded 438. Independent inspection
of both released MSI databases found four custom actions, 29 execute-sequence
entries and one desktop shortcut. The compiled packages omit the migration
and GUI relaunch actions present in the WiX source fragment. The original
test expected the migration action and stopped before checking the installed
payload or running repair. The corrected check binds each verbose log to the
product, package, operation and completed transaction. It checks the stopped
application's actual shortcuts. [x64 logs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426419/artifacts/14835059083) · [ARM64 logs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426419/artifacts/14835003224).

Both Ubuntu hosts imported the original release into OSTree and then
failed to deploy. An x64 Noble 1.14.6 reproduction traced a failed connection
to the absent system bus. The fixture now runs a D-Bus daemon under its own
temporary mount. The only activatable name is the daemon itself.
Flatpak 1.14.6 reports its shared permissions as `network;ipc;`; Fedora's
1.18.4 reports `ipc;network;`. Both declare exactly the same permissions.
The upstream package bytes remain fixed. [Ubuntu x64 log](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426419/artifacts/14836270852) · [Ubuntu ARM64 log](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426419/artifacts/14835164322).

With the private bus, the original x64 Flatpak installed, repaired and
uninstalled in both the Noble userspace and Fedora 45 on the Fedora host.
Each of the 785 original payload entries and the two retained profile files
matched. The local evidence indexes in
`artifacts/rust/shipping-install-noble-local-replay/` and
`artifacts/rust/shipping-install-fedora-private-bus/` have SHA-256
`8a5d3d06713d6cf4b229acfc8a3320287f07a3a264d18e0dc885d08ac1ab24e2`
and `d1485b18398fe3792a778af0eea2cd439fc377ba3810b5b6021c18c943071884`.

## Two ordinary launches of the installed Linux x64 reference

An offline Fedora x64 desktop installed the original 3.0.4 bundle into a
fresh per-user repository. The installed OSTree commit
`abeebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da`
verified against the separately published commit signature and the
repository's release public key. The executable and managed assembly
also matched the earlier installation and repair inventories.
[Release asset](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.4) ·
[Detached commit metadata](https://voltkraft.github.io/immich-folder-watch/repo/objects/ab/eebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da.commitmeta).

The observer started the installed app normally twice with an unconfigured
synthetic profile. The first apphost, PID 54, hid X11 window 4194319. A
second Flatpak instance started apphost PID 132 and exited zero. X-Resource
identified the same first process and window after reopening. The two
instances shared their runtime and configuration directories. The observer
invoked the first app's exported Quit menu item on the private bus. The
original process exited zero, followed by successful uninstall. This
observation covers two launches of the shipping version without watched
sources or an active synchronization workload.

The accepted `result.json` SHA-256 is
`2165bb6d1fc44ffdea1c77143255b3bd317147287b4c3d6b4d719d7b18e217d5`
under `artifacts/rust/shipping-flatpak-launch/x11-vh5z2iam/`. Independent
readback verified the signature, all 16 indexed files, 13 source inputs
and both ordinary exits. Its SHA-256 is
`414c7e789a476371bd1ac74d144a2c2a53a37494e085ca0a595dc272bc91372f`.
For reproduction use the pinned bundle, detached metadata and installed
public Platform and Mesa deployment specified by the [native launch driver](../../tools/RustCompatibilityOracle/installed/launch/run.py).

## Installed reference on all four hosts

At `0f29659`, all four native jobs installed the original shipping package,
repaired one removed file, verified the complete installed payload again and
performed an ordinary uninstall. Direct archive readback matched all 54 indexed
files and ten fixture sources per host. The retained YAML matched the platform
fixture byte-for-byte. Reopening the seed and retained databases independently
reproduced the entire SQL fixture, including both account histories, both owned
albums, all four mappings and the repair journal.

| Native host | Repaired and verified | Uninstall observation |
| --- | --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45212974336/artifacts/14838170053) | All 439 files matched the release cabinet. The restored SQLite DLL had SHA-256 prefix `6ad8e149`. | The registered product, files and desktop link were removed. The seeded profile survived. |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45212974336/artifacts/14836698072) | All 438 files matched the release cabinet. The restored SQLite DLL had SHA-256 prefix `a59c1697`. | The registered product, files and desktop link were removed. The seeded profile survived. |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45212974336/artifacts/14837585968) | Flatpak 1.14.6 restored the metainfo and all 785 original entries of OSTree commit `abeebe13`. | Both ref and deployment disappeared. The seeded profile survived. |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45212974336/artifacts/14837665317) | Flatpak 1.14.6 restored the same metainfo and all 785 original entries of commit `762ff33e`. | Both ref and deployment disappeared. The seeded profile survived. |

Each Linux job recorded three GLib/OSTree diagnostics while importing the
bundle. The command exited successfully, and the independently expected commit,
installed files and repair bytes matched. Each Windows host recorded all three
completed Installer transactions and the continued absence of a Startup link.
Independent Windows review decompressed the original cabinets and verified all
877 installed and repaired files. The verbose repair logs identified only the
missing SQLite DLL for replacement and retained the other 438 and 437 files.
Both removed their synthetic profiles after retaining the two evidence files.
The four-host readback under `artifacts/rust/hosted-shipping-install/45212974336/`
has SHA-256 `ccf92ed76a89e2ce5aeafaeec38b2fa0c0ce48c2e8ea94095b93d03ad17b31d9`.

RI-AC08 still requires the four Rust packages, native old-to-new upgrades,
repair, removal and rollback after activity in the installed Rust application.
[Acceptance matrix](acceptance.md#overall-acceptance).
