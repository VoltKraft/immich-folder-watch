# Ubuntu Noble Documents portal file locks

The released Ubuntu 24.04 package `xdg-desktop-portal 1.18.4-1ubuntu2.24.04.3` refused cooperative file locking on a private Documents grant. Both the shipping C# reader and the Rust filesystem reader received `ENOSYS`. Building the exact Ubuntu sources produced the same result. Applying upstream's single `xdp_fuse_flock` function let both readers acquire shared leases and excluded a consenting exclusive writer across the backing and FUSE views. The local execution used native x86-64 Ubuntu 24.04.5 userspace on Fedora kernel `7.3.4-300.fc45.x86_64`. Native Ubuntu x64 and ARM64 subsequently reproduced all three outcomes on their own kernels. Availability of a supported Ubuntu package that implements this capability remains open. [Ubuntu package and source](https://packages.ubuntu.com/noble-updates/xdg-desktop-portal) · [Upstream change](https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57).

## Native observations

At `a66e045` each Ubuntu runner recorded 28 checks against the packaged
daemon, 28 against its pristine rebuild and 42 against the private backport.
The packaged and pristine daemons returned errno 38 for the required
lease. Only the backport enforced contention across the portal and backing
views. All grants were revoked. The x64 case was `amd64-hmi8ytft` and
the ARM64 case was `arm64-f72e6u80`. The six observation/input hashes per
target matched their archived files. [Verified native archives](rw02-native-gui.md#native-follow-up-at-a66e045).

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

## Development reader outcomes and retained-grant retry

The earlier Rust caller preserved errno 38 but emitted only `REFUSED errno=38`.
The development caller now reports an explicit outcome and next action for
failures of the normal `Directory::open_file` read-lease acquisition. It preserves
the native errno or Rust's normalized `WouldBlock` value. Root setup, content and
identity-validation failures remain fatal errors outside this classification.

| Read-lease failure | Outcome | Action |
| --- | --- | --- |
| `ENOSYS` (38), `EOPNOTSUPP` (95) | `UnsupportedFileLock` | `CheckPortalFileLockSupport` |
| `EAGAIN` (11), normalized `WouldBlock` | `FileBusy` | `RetryAfterWriterRelease` |
| `EPERM` (1), `EACCES` (13), normalized `PermissionDenied` | `AccessDenied` | `RestoreAuthorizedAccess` |
| Other errors | `ReadLeaseUnavailable` | `InspectNativeError` |

These are development-protocol observations for the fixed synthetic file, not a
production UI or a new core error API. Four Rust controls exercise unsupported,
busy, denied and unknown errors; three Python controls reject contradictory
outcomes/actions and unauthenticated package selections. Native errno 38 and
`WouldBlock` were observed below. The errno 95 and access-denied classifications
have pure controls, not additional native fault injections.

The `retry` mode opens the authorized root and album once and accepts exactly
three explicit attempts followed by `stop`. Each attempt uses the unchanged
filesystem adapter and its required shared lock. A failed acquisition returns
no file lease. Successful reads check the expected bytes and current entry
identity while the file lease is held. The retry releases a successful file
lease before reporting completion, retaining both directory handles throughout.
The observer independently reads the known Rust child's executable hash and
`/proc/<pid>/fd` records. It requires unchanged directory descriptor numbers,
device/inode identities and read-only `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`
flags; the grant, backing-file identity and contents must also remain unchanged.
These metadata observations validate the fixture and confer no filesystem
authority on the consumer.

The offline native x64 run `amd64-msdhalx2` passed on November 22, 2026 in 42.238
seconds under Noble userspace and Fedora kernel `7.3.4-300.fc45.x86_64`. Its
worktree base was `8b64330ce64485597b37f0c37657b759ff21abd9`; the receipt binds all
fixture files and the actual workspace filesystem sources separately. The result
SHA-256 is `7a830f8e58e8ff3491521ae05701bf7d145ef8169e20a5c7e650b827d9abb7ac`.
The Rust reader SHA-256 is
`eb084203c16cb93ca4b9824e2286edd4953e7e33f85412b028ef115ac3c80c54`.
All source, executable, input and observation bindings were rechecked. The
existing three daemon hashes above were unchanged; no new backport was made.

| Service | Document ID | Lease observations | Observation JSON SHA-256 |
| --- | --- | ---: | --- |
| Packaged Noble | `8f7a4bea` | 32 | `a01dbe5ca24b21d775a590fe88cf8383fad5ec9715b07b3583d2e1e49dcfe0d0` |
| Unmodified rebuild | `900dae4d` | 32 | `2affa8a01dac9fe33db41ce3b4862d7d664e13d8322e7152272ab8a1c760fef1` |
| Existing private backport | `7433908b` | 46 | `5709fa41b3903284e13960dc819df94dcf656bf95a5098ced2eb38531d6fff1a` |

The stock and unmodified services reported `UnsupportedFileLock` with errno 38
on all three attempts, including before, during and after the independent
exclusive backing lease. The backport reported an acquired read, then
`FileBusy` while that exclusive lease was held, then an acquired read with the
same file identity after release. Both held directory descriptors remained
unchanged. All three grants were revoked after the checks. The synthetic bytes
retained SHA-256 `b52af4136a0ecafce322a09cbb3efeb16704396715fb7458e07382e7d6d8ef55`.

This demonstrates recovery from contention through the same retained grant on
the supported private service. The stock unsupported capability did not recover.
No retry across grant revocation, service replacement or backing identity change
was attempted. A supported released host fix and production error/retry UI
remain open. These added controls have run locally on x64; the earlier hosted
x64/ARM64 counts above describe the earlier fixture. The initial local attempt
`amd64-xxt06xb_` stopped after 28 observations because its observer incorrectly
expected `O_PATH` directory handles. The corrected observer checks the actual
read-only directory flags and passed in the fresh run recorded here.

## Meson on the Ubuntu runners

Both Ubuntu architectures in workflow run `44950398558` authenticated the Documents package and stopped at the first Meson invocation. The x64 build added 32 signed development packages and ARM64 added 31. Both installed Meson `1.3.2-1ubuntu1` into the private development layer and used the runner's existing Python. Their error logs have the same SHA-256, `9b2f75b0451e1d2ae46a0fb887ef10734a2343943284bd5a6f22f86e59405a17`. Neither job reached the lock measurements. [Hosted assessment](https://github.com/voltkraft/immich-folder-watch/actions/runs/44950398558).

The local x64 control selected the same distribution Python executable from the read-only Noble runtime and kept Meson in the development layer. Python followed the interpreter symlink and chose `/noble-usr` as its prefix. The package was visible under the merged `/usr`, but Python searched only the runtime layer. Executing the real Meson launcher reproduced the hosted traceback byte for byte. The build now supplies `PYTHONHOME=/usr`, gives the distribution package directory priority, and disables the user site. Before configuration it starts the real launcher, checks its version against the imported package, and records the resolved interpreter, launcher, module paths and file hashes. [Python module search path initialization](https://docs.python.org/3.12/library/sys_path_init.html) · [Meson check](../../tools/rust-qa/portal-noble/meson_python.py).

Two offline runs under the local Noble x64 userspace on November 21, 2026 confirmed the correction. Both compiled the same pair of daemon binaries as the earlier control. Each performed 28 lock checks with the packaged service, 28 with the source control and 42 with the private backport, then revoked all three grants. Both hosted architectures subsequently completed these steps on November 22.

| Private compiler layout | Run under `artifacts/rust/portal-noble/runs/` | Result SHA-256 |
| --- | --- | --- |
| Runtime Python and development-layer Meson | `amd64-vlxw1ad1` | `549b17d44ea12e91c8280f9f08365e0088189c19b3d57be314eb1b84f218157f` |
| Python and Meson in the same development layer | `amd64-cx1dy5mt` | `15901a02c80ce65585d59d24142a3c786b91420bd4d987a6b659958246766d82` |

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

For the maintained local private Noble x64 userspace, run `python3 -B tools/rust-qa/portal-noble/run.py --local-noble --download`. Once the signed source metadata, source archives and required development packages are in the private cache, omitting `--download` runs the comparison offline. The portable command `python3 -B tools/rust-qa/portal-noble/test_control.py` checks that a capability refusal cannot count as contention or success, that reported actions match native errors and that unsigned changes to the package index or dependency selection fail. The native build also compiles and executes the four Rust classification controls, retaining `build/reader-tests.log` and its digest.

Use `python3 -B tools/rust-qa/portal-noble/run.py --local-noble --local-split-python` to exercise the hosted package layout offline with the local Noble userspace. The fixture verifies the two interpreter binaries are byte-identical and selects the runtime copy through a link in the newly created private compiler view. It retains the original Meson error in `build/split-python-control.log`. Every build collects the corrected interpreter and Meson inputs in `build/meson-python.log` and the final result.

Every run creates a new `artifacts/rust/portal-noble/runs/<arch>-<id>/`. Preserve `result.json`, each of `packaged/`, `unmodified/` and `backport/` with its JSON/log files, `development/apt-packages.json`, `development/build-packages.json`, `development/package-notices.json` and `build/*.log`. Generated build trees, package archives and executables stay private. [Native launcher](../../tools/rust-qa/portal-noble/run.py).
