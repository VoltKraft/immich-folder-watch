# RW-02 Linux desktop services

On 2026-11-20 a Fedora 45 x86-64 Documents portal granted a real directory,
accepted handle-relative downloads and refused the shared lock needed for uploads.
The shipping .NET reader and the Rust reader both returned Linux error 38
(`ENOSYS`) for the same media entry. The independent tray trial kept the
application reachable across watcher loss, refused registration and replacement.
The Linux upload feasibility gate remains open for this distribution.

## StatusNotifierItem and desktop activation

A standalone Rust service exported `org.kde.StatusNotifierItem` and
`org.freedesktop.Application` on a private session bus. It used the existing
desktop lifecycle policy and sent actions to a separate native eframe process.
An external X11 client observed the actual mapped window. A synthetic watcher
checked that the registration sender owned the item service name. It accepted,
delayed and refused registrations under separate D-Bus unique names.

| Observed sequence | Native result |
| --- | --- |
| Background launch with an accepting watcher | No mapped window. Calling the registered item's `Activate` mapped the GUI. |
| Close, then remove the watcher | The GUI stayed hidden. Freedesktop `Activate` reopened it without a watcher. |
| Stall one registration, replace that watcher with a refusing owner, then an accepting owner | The service accepted the new owner. The stalled first owner replied afterwards and the service retained the new registration. Its item reopened the window. |
| Lose the final watcher while visible, then invoke desktop Quit | Both native processes drained and exited with status zero. |
| Start with registration refused | The GUI opened. Desktop Quit remained reachable. |

The service subscribes to `NameOwnerChanged` before reading the current owner,
addresses registrations to the unique owner and confirms ownership before
accepting the result. The observed panel was the controllable protocol peer.
Visual integration with GNOME, Plasma and released Flatpak packages is outstanding.
The separate GUI assessment covers native window close and Wayland presentation.
[Native GUI evidence](rw02-native-gui.md)

## Actual Documents grant

The driver ran the packaged `xdg-document-portal` 1.22.1-2.fc45, its real
permission store, libfuse 3.18.3 and kernel 7.3.4-300.fc45.x86_64. The
independent test producer exported a temporary directory descriptor with
`Documents.AddFull`, the directory flag and a read-only grant to
`org.example.IfwServices`. The interface reported version 5. In run
`documents-pfbubzh8`, it returned the opaque document ID
`w6cpph3b65cm8Uzpe9s_8g`. The kernel mount was `fuse.portal` at
`/run/user/0/doc`. The backing directory was `/tmp/producer/source`.
`GetHostPaths` independently reported that backing location.

The Rust consumer requested the mount point and opened
`/run/user/0/doc/by-app/org.example.IfwServices/w6cpph3b65cm8Uzpe9s_8g/source`.
It received only the document ID and directory basename. A second mount
namespace covered the producer tree with an empty filesystem and dropped all
capabilities. This scope also applied to the grant-view .NET caller and independent
native lock contenders. The mount service's namespace root mapped solely to the
invoking user's UID 1000. Creating the private FUSE mount required
`CAP_SYS_ADMIN` inside that user namespace. All test processes used fresh
network, PID, mount, IPC and user namespaces, a private bus and a synthetic home.

| Grant state | Observed filesystem operations |
| --- | --- |
| Read only | Enumerated the album and opened its directory. Shared media reads returned `ENOSYS`. Creating download staging returned `EACCES` (13), with no new backing entry. The adapter rejected `..` and a symlink to an external fixture. |
| Read and write | Published a synthetic download. A second no-replace commit returned `AlreadyExists` and preserved the destination. Cancellation removed its payload. The backing observer verified the bytes, the empty mode-0700 transaction container and the unchanged outside sentinel. Shared media reads still returned `ENOSYS`. |
| Revoked | A fresh consumer could no longer open the granted root. The producer deleted the transient document. |

The granted directory was real. The producer supplied its synthetic selection
directly using `AddFull`. This run exercised the per-application FUSE view in a
private Linux namespace. Installed Flatpak identity and an interactive chooser
require separate tests.

## Independent shipping reference and writer controls

The offline .NET 10.0.401 SDK built a small caller using a project reference to
the unchanged shipping Core. It called `SecureWatchRoot.Open` and
`OpenRead("album/original.jpg")` on .NET runtime 10.0.12. The native adapter
uses a nonblocking shared `flock` on the media handle. A second process
attempted an exclusive nonblocking `flock` before writing and syncing the known
fixture bytes. The D-Bus service, FUSE daemon and both contenders used independent
processes and open handles. [Shipping Linux adapter](../../src/ImmichFolderWatch.Core/Services/SecureFileSystem/SecureNativeFileSystem.Linux.cs)

| Test on the packaged daemon | Result |
| --- | --- |
| Uncontended .NET backing read | Acquired and verified the source bytes. |
| .NET backing read held, backing writer requests exclusive lock | Writer received `EAGAIN` (11) without writing. |
| Backing writer holds exclusive lock, .NET opens backing source | Reader received `EAGAIN` (11). Both reader and writer succeeded after release. |
| .NET opens uncontended grant source or a backing writer is already active | `Acquire shared media read lock failed.` Inner native error 38. Native shared and exclusive grant-view `flock` also returned 38. The daemon trace records `FLOCK -> error 38`. |
| Whole-file POSIX record locks (`lockf`) | A backing POSIX writer acquired and wrote despite the shipping backing `flock` reader. A second grant-view POSIX writer also acquired and wrote while another process held a grant-view POSIX shared lock. This mechanism fails the required exclusion. |

Uploads through this installed portal must retain the safe capability refusal.

## Private daemon comparison

On the same machine the same driver ran against a private build of the 1.22.1
release containing the upstream native `flock` implementation from commit
`caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57`. The binary's SHA-256 was
`d58417869c6961c5ea318744b563ec728fa6101af9e228a83dd332ac371f90b6`.
[Reference build](../../tools/rust-qa/portal-reference/build.py)

In run `documents-zcmtpflz` the daemon returned document ID
`p8U1OwBjzQ_t4E2nkKRKrw`. Safe Rust reads through both grant scopes returned
the verified fixture bytes and current handle identity
`{ volume: 97, file: 2955573752479479400 }`. The compiled shipping .NET
reader read those bytes through the grant as well.

| Competing processes on this build | Observed result |
| --- | --- |
| .NET shared reader held on either backing or grant view | A consenting exclusive writer on either view received `EAGAIN` (11) without writing. |
| Exclusive writer held on either view | New shipping .NET readers on both views received `EAGAIN` (11). |
| All handles released | Independent writers acquired, wrote and synced fixture bytes through both views. Fresh .NET readers succeeded through both. |
| Read-only, read-write and revoked grants | Write refusal, publication, no-replace collision, cancellation, stable sentinel and post-revocation denial passed as in the distro trial. |

The result establishes a working cooperating-lock path on this specific build.
The installed Fedora package still reproduces the refusal above. Distribution
support and deployment with a released implementation remain open.

## Reproduction and evidence

The standalone workspace uses Rust 1.100.0, edition 2024 and frozen inputs.
All 85 registry lock records match the GUI assessment. The Linux normal/build
tree activates 67 third-party packages. The build driver compared their feature
sets against the GUI tree and verified 3,254 unpacked files against the exact
archives. The product workspace keeps its independent lockfile.
[Service workspace](../../tools/rust-qa/linux-services/Cargo.toml) ·
[GUI dependency assessment](rw02-gui-dependencies.md)

Use the repository's pinned toolchain and public Cargo registry cache, the
native Linux GUI assessment executable, the .NET SDK selected by `global.json`
and the offline Core NuGet cache. The distro trial additionally requires
bubblewrap, an independent Xvfb or Xvnc server, the session D-Bus daemon, PyGObject
with GIO, a native software Vulkan implementation, and user-namespace FUSE mounting.
On this Fedora system the launcher used the portal services under `/usr/libexec`.

```sh
python3 tools/rust-qa/linux-services/native.py build
python3 tools/rust-qa/linux-services/native.py lint
python3 tools/rust-qa/linux-services/native.py oracle
python3 tools/rust-qa/linux-services/native.py tray
python3 tools/rust-qa/linux-services/native.py documents --expect-lock enosys
sha256sum --check tools/rust-qa/linux-services/evidence.sha256
```

To exercise a separately reviewed reference daemon, supply
`documents --portal-binary artifacts/rust/portal-reference-build/PATH --expect-lock supported`.
The launcher resolves and bounds the source path, records the executable's SHA-256
and mounts it read-only at `/probe/xdg-document-portal` in the private namespace.
Each run creates a distinct directory under ignored `artifacts/rust/linux-services`.
The input manifests bind the driver, product and test sources to the executable
hashes. The local hash index covers both daemons' inputs, grant operations,
cross-view lock outcomes and traces, as well as the watcher run's inputs,
observations and late reply. [Evidence index](../../tools/rust-qa/linux-services/evidence.sha256)
