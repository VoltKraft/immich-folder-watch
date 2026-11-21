# Ubuntu Noble Documents portal file locks

The released Ubuntu 24.04 package `xdg-desktop-portal 1.18.4-1ubuntu2.24.04.3` refused cooperative file locking on a private Documents grant. Both the shipping C# reader and the Rust filesystem reader received `ENOSYS`. Building the exact Ubuntu sources produced the same result. Applying upstream's single `xdp_fuse_flock` function let both readers acquire shared leases and excluded a consenting exclusive writer across the backing and FUSE views. The local execution used native x86-64 Ubuntu 24.04.5 userspace on Fedora kernel `7.3.4-300.fc45.x86_64`. Native Ubuntu runner results for x64 and ARM64 are pending. Availability of a supported Ubuntu package that implements this capability remains open. [Ubuntu package and source](https://packages.ubuntu.com/noble-updates/xdg-desktop-portal) · [Upstream change](https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57).

## Native observations

Each private service returned a fresh opaque document ID and a kernel mount of type `fuse.portal`. The exporter used the D-Bus `AddFull` method with a descriptor for a temporary directory and read/write authorization for `org.example.IfwServices`. A second mount namespace hid the entire producer directory from each grant consumer and dropped its capabilities. Both views contained the same regular synthetic JPEG fixture. The C# probe called `SecureWatchRoot.OpenRead`; the Rust probe called the workspace's `Directory::open_file`, checked the contents and revalidated the entry identity while keeping the handle open. A third, independent process requested nonblocking shared or exclusive `flock` leases on the same file. [Managed caller](../../tools/rust-qa/linux-services/dotnet/Program.cs) · [Rust caller](../../tools/rust-qa/portal-noble/read.rs) · [D-Bus and lock observations](../../tools/rust-qa/portal-noble/observe.py).

| Independent check | Packaged Noble service and unmodified source build | Private Ubuntu backport |
| --- | --- | --- |
| Uncontended read via grant | Both readers reported errno 38 | Both read the expected bytes |
| Shared reader and a second shared reader | Backing control succeeded. Grant requests reported errno 38 | Both directions acquired shared locks |
| Exclusive writer against a live shared lease | Backing control reported errno 11. Grant requests reported errno 38 | Both directions refused the writer with errno 11 |
| Exclusive lease held while Rust or C# requests a read | Backing contention observed. Grant requests reported errno 38 | Both directions refused the read. C# reported errno 11 and Rust reported `WouldBlock` |
| Release and subsequent acquisition | Backing access resumed. Grant still reported errno 38 | Both views allowed subsequent reads and exclusive acquisition |
| Revoke grant and read back the producer file | App view disappeared and contents were intact | App view disappeared and contents were intact |

The probe observes ordinary BSD `flock` operations on cooperating opens. An exclusive participant acquires its real lock on a read/write descriptor and checks the known bytes. The fixture's synthetic application identity is supplied by the private exporter. Installed Flatpak identity and desktop chooser behavior have their own tests. [Installed Flatpak grants](rw02-portal-dialog.md).

The offline run `amd64-kgndqoro` took 31.3 seconds on 2026-11-21. Its worktree was based on `c9b50ef371c724d5a2eb5c211cc46e20f5b9dfe9`; the report independently binds every fixture source file by SHA-256. .NET reported runtime 10.0.12. The top-level result SHA-256 is `73623ad642b3e10e429f72b13e2d64f4f96f0a685d75f7158ced7ee6f1055ad6`. Three fresh builds produced identical unmodified and patched executables.

| Running service SHA-256 | Document ID | Lease observations | Observation JSON SHA-256 |
| --- | --- | ---: | --- |
| Packaged `44dd7e1eb2df2a4de1d8c1189a3fee4451539ffab5db6ba4d21718c6d43af3dc` | `598dc14c` | 28 | `ae56165903f9735628a9e5ed4ed710c15f62823056beab77c673a19cf7ddc5ed` |
| Unmodified `d9c1db7cc7e00b592802a8a26ee273f062db5128845fcea51cf621acf41ce736` | `56d7c438` | 28 | `d3451b56ba68b0e3857ded0363fdabe884e020846022f5601292c90ff58efbe7` |
| Backport `17980d7a8269396cf9a711f01e05ea2d62eddc0cb9459a0380a639eb74512852` | `e42a75c2` | 42 | `503cfb9ccd034937eff0ea27de7fe328de83e7949f18c3b78a12784b92b272f3` |

## Source, package and license binding

The public source comes from Ubuntu's signed `noble-updates/main/source/Sources.xz`. The recipe verifies Ubuntu Archive Automatic Signing Key (2018) fingerprint `F6ECB3762474EDA9D21B7022871920D1991BC93C`, the index digest, the exact package version and all four source objects. It independently checks the binary package SHA-256 and verifies the installed daemon, permission store and copyright file against that package. Both running service executables are then hashed through their private `/proc/<pid>/exe` descriptors. Each native run records its input and output hashes. [Archive validation](../../tools/rust-qa/portal-noble/verify.py) · [Source archive pins](../../tools/rust-qa/portal-noble/inputs.py).

`dpkg-source` applies all ten Noble packaging patches first. Both builds use the same Meson options, compiler and build-only declarations `-D_GNU_SOURCE=1 -include sys/file.h`. Ubuntu's package carries libglnx as a separate original archive and links it into `subprojects/libglnx` as specified in `debian/rules`. No subproject download is permitted. Only the Documents daemon is built. The patched function is byte-identical to the function in upstream commit `caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57`. The resulting complete C file changes from SHA-256 `aff36d56cc496e449047ad17d024139812b7160ef6d8f1e5b3eb22fbb5b76730` to `a3cf626fa1e2971b9e3a7bfb0081c353c79603a75a30c5a2b8db82a36b432f92`. The build inventories every source-file change and verifies the original notices and FUSE headers. [Build recipe](../../tools/rust-qa/portal-noble/build.py) · [Noble-specific patch](../../tools/rust-qa/portal-noble/flock.patch).

The patch is a development adaptation of Sebastian Wick's upstream change. The original Documents source credits Red Hat, Inc. and GNOME Foundation Inc. and uses LGPL-2.1-or-later. The Noble GVDB sources use LGPL-2.0-or-later. Bundled libglnx contains LGPL-2.0-or-later and LGPL-2.1-or-later files. Ubuntu's FUSE 3.14.0 headers and library carry the upstream LGPL-2.1 terms. The recipe retains the original source and Ubuntu packaging notices, hashes the exact FUSE inputs, and records package versions, development copyright files and the 15 loader-resolved libraries in the local comparison. The Ubuntu loader and all host services remain system-supplied. The three daemons are development subjects. This work adds no portal binary or library to application distribution. [Retained upstream license](../../tools/rust-qa/portal-reference/LICENSE.upstream-LGPL-2.1.txt) · [libfuse 3.14.0 licensing](https://github.com/libfuse/libfuse/blob/fuse-3.14.0/LICENSE).

## Reproduction

On a disposable Ubuntu Noble x64 or ARM64 runner, first build the existing `linux-services/native.py oracle` and install the project's pinned Rust toolchain. The runtime needs the packaged Documents portal, its permission store, Python GI, Bubblewrap, a usable private user namespace and `/dev/fuse`. The build consumes the runner's existing authenticated Noble APT lists. Missing Meson, Ninja, compiler tools and development headers are resolved against signed Ubuntu package indices and extracted into a private compiler view. No APT installation, maintainer script or host service restart is performed.

```sh
export IFW_QA_REFERENCE_SDK="${DOTNET_ROOT:?}"
python3 -B tools/rust-qa/portal-noble/run.py --hosted --download
```

For the maintained local private Noble x64 userspace, run `python3 -B tools/rust-qa/portal-noble/run.py --local-noble --download`. Once the signed source metadata, source archives and required development packages are in the private cache, omitting `--download` runs the comparison offline. The portable command `python3 -B tools/rust-qa/portal-noble/test_control.py` checks that a capability refusal cannot count as contention or success and that unsigned changes to the package index or dependency selection fail.

Every run creates a new `artifacts/rust/portal-noble/runs/<arch>-<id>/`. Preserve `result.json`, each of `packaged/`, `unmodified/` and `backport/` with its JSON/log files, `development/apt-packages.json`, `development/build-packages.json`, `development/package-notices.json` and `build/*.log`. Generated build trees, package archives and executables stay private. [Native launcher](../../tools/rust-qa/portal-noble/run.py).
