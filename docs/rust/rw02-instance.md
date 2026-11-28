# Native old/new activation and writer locks

On Fedora 45 x86-64, two separate processes exchanged `SHOW_GUI` in both
directions. A Rust secondary activated the unmodified shipping .NET coordinator.
The shipping .NET secondary also recognized and activated a Rust primary.
The Rust endpoint verified the kernel's peer PID and effective UID against
the specific fixture child. The Linux coordinator's initial empty liveness
probe and its subsequent activation arrived over separate connections.
[Shipping source pins](../../tools/rust-qa/instance/legacy-inputs.json) and
[Linux peer credentials](https://man7.org/linux/man-pages/man7/unix.7.html).

A second Rust process received `WouldBlock` while the first held an exclusive
lock on the profile's persistent guard file. A replacement acquired the lock
after orderly release and again after the holder was killed. The original .NET
process could still become primary while that Rust lock was held. The installer
handover therefore needs independent proof that the old executable cannot
restart before Rust enables synchronization. Cross-session ownership, controlled
shutdown of actual workers, stale-endpoint recovery and installed handover remain
open. [Native lock contract](https://doc.rust-lang.org/std/fs/struct.File.html#method.try_lock)
and [migration requirements](../rust-rewrite-plan.md#data-compatibility-and-migration).

## Reproduction

Use the pinned native Rust compiler in `artifacts/rust/toolchain` and put the
matching .NET SDK on `PATH`. Each run creates a fresh private directory, an
empty guard file and a synthetic marker. The native activation listener is a
one-shot test with a parent-enforced process deadline. The .NET build restores
from the SDK's installed reference packs with package sources cleared. It stages
only the hash-checked platform coordinator and its required platform types.
The Rust probe uses the standard library and system calls.

```sh
python3 tools/rust-qa/instance/run.py x86_64-unknown-linux-gnu --output artifacts/rust/instance-native/test
```

The second Fedora run passed all six observations with Rust 1.100.0 and the
.NET 10.0.401 SDK, with zero compiler warnings. Its `result.json` SHA-256 was
`090f48beffc69f3a0bab629c19796c4a320fbdb24e689d9b4276e65f1f6ec86d`.
The receipt includes hashes for the native executable, development oracle and
source inputs. Both MSVC targets passed Clippy type checks on the Linux host.

The Windows fixture uses the real local-session legacy mutex and local named
pipe on the disposable rewrite runner. The receiving Rust process creates a
current-account DACL and checks the connecting PID. The sending process checks
the server PID. The oracle supplies the actual account SID.
[Microsoft mutex semantics](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw),
[named pipe access controls](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
and [pipe identity functions](https://learn.microsoft.com/en-us/windows/win32/ipc/pipe-functions).

## Native results on all four targets

At `5895c0b`, all four runners passed the same six observations, including
both directions of activation and recovery of the writer lock after process
exit. Each runner used a shipping coordinator compiled from the exact pinned
source. The Windows tests ran in a single logon session per runner. The archive
checksums matched GitHub's artifact digests and the ZIP integrity checks
passed. [Hosted native assessments](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264).

| Native target | SHA-256 of the instance result |
| --- | --- |
| Linux x64 | `2c9ef3aa065a30a09a62bf0117e89bbb5950a2aa1a9929980642dd5a53695c16` |
| Linux ARM64 | `4766c42832b9aa5f30f23fec388d69564f64518c3eb844a8d2cc2e19bd233524` |
| Windows x64 | `79e484606f12ed5858f7d0b36f796816e039f9073b477b5fb057faa3bcfbed54` |
| Windows ARM64 | `eafedcffe66eec0bbce23c62626de5c365c8b9a80d4b5b379a320b155ed2c048` |

The legacy writer ignored the new lock on every target. Cross-session ownership
for the same Windows SID and prevention of legacy restarts during installed
handover remain open.

### Ordinary launch of the installed Windows application with Rust running

The earlier native tests covered both message directions using the pinned
shipping coordinator. Separate trials exercised WPF-to-WPF and Rust-to-Rust
window activation. The original MSI install, repair and removal trials
kept the application stopped at their package checkpoints.
[Four-target coordinator](#native-results-on-all-four-targets) ·
[Ordinary WPF and Rust launches](#retained-windows-second-launches-at-989bb33) ·
[Original packages](rw01-installed-packages.md).

The Windows MSI comparison starts a private Rust build in one existing
session of the hosted installer account and then launches the installed
3.0.4 executable with no arguments. The installer requires an elevated
runner on both architectures.
The Rust primary uses the shipping single-instance names and authenticates
the second process. The observer follows the original hidden HWND, the
actual installed process, and the inventory worker through the reopen.
The watch directory is initially empty. The observer then makes a new
`.jpg` name visible and checks the same worker's subsequent file reads.
The installer must verify
and remove its own product on the disposable runner.
[Native x64 and ARM64 workflow](../../.github/workflows/rust-windows-msi-interop.yaml).

Detached replay uses Python and PowerShell 7 on `PATH`. It checks the
original installer logs against the recorded package identity and the
completed install and removal actions. This reader reproduced both
transactions from each architecture's original 3.0.4 package archive
at `5b6cebf`. The installed and repaired apphost digests matched on each
architecture. The local result at
`artifacts/rust/hosted-windows-msi-interop/first-shipping-log-replay.json`
has SHA-256 `b6b87b3c044c3824bef539e11b80cbdc85e723970c3b9939dc0ee98e35fdc3a3`.
[x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45871571606/artifacts/15141724559) ·
[ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45871571606/artifacts/15142827580).

### Installed Windows secondary at 1d3af9a

Both original 3.0.4 packages reopened the hidden Rust window at
`1d3af9af152c9ad82c4c2d21664464cd21d7312e`. The observer matched
the installed WPF process to the IPC connection. Its secondary process
exited zero without descendants. ETW then recorded the same Rust worker
reading the newly introduced file during two successive inventory passes.
The file was changed on pass 2 and stable on pass 3.

| Native host | Original HWND | WPF secondary / Rust primary PID | Worker PID | Reopen after resume | Time between file reads |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows x64 | 262530 | 980 / 5448 | 7344 | 93 ms | 5.001 s |
| Windows ARM64 | 262168 | 6300 / 5248 | 5544 | 437 ms | 5.009 s |

Both original windows became visible. Windows accepted the separate
foreground request on x64 and declined it on ARM64. Control-Q drained
the Rust job on both hosts. Both MSIs installed and uninstalled with
exit 0. The hosted scratch directories and synthetic profiles were removed.
Each archive contains 19 CRC-verified entries. Detached readback from the
measured commit verified the native compilation, installer logs, window,
process and kernel file observations.

| Native archive | ZIP SHA-256 |
| --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45893039720/artifacts/15153695057) | `c601576fdfc9e10ceb327b268185a9eef1093978094fe281698c63e1b100bdfc` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45893039720/artifacts/15153312140) | `57f7034e6d42c4503e445212a303a0305eb09903df7f7490d656f8c4167ad85d` |

### Rust second launch while the installed Windows application is running

The reverse trial starts the installed WPF GUI on a separate disposable
runner. After its original window hides, the Rust secondary opens the
existing session mutex and checks the server PID on its connected pipe
against the still-running installed process. It sends the shipping
`SHOW_GUI` message and exits. The observer checks the original WPF
window and the secondary's process job. Before starting WPF, it also
checks the private sender's behavior when no primary exists.

The recorder saves the activation observations before it asks the actual
WPF popup menu to quit. Its readback can report activation even when a
later shutdown step fails. The full trial also requires the process to exit
cleanly and its worker to log the shutdown signal or the start of flushing.
The shipping worker does not log when the flush completes. Cross-session writer exclusion
and an installed upgrade preventing an old worker from restarting remain
separate acceptance requirements.
[Native commands, evidence and quit behavior](../../tools/rust-qa/windows-msi-interop/reverse/README.md).

### Both installed Windows launch orders at ef28520

At `ef2852093abab540acc430d6099f9711bef0ef41` all four independent
hosted runs reopened the original hidden window. With WPF primary, Rust
sent eight bytes on the connected pipe owned by the original installed
process and exited zero with an empty job. On each host the original
WPF window became visible 16 ms after resume, on a distinct Windows
tick. The original worker had completed two scans of its empty synthetic
source. With Rust primary both full trials passed again, including the
original worker's reads of the new file.

| WPF primary | Rust PID | WPF PID | Original HWND | UI thread |
| --- | ---: | ---: | ---: | ---: |
| Windows x64 | 1732 | 2356 | 131448 | 2212 |
| Windows ARM64 | 6012 | 8444 | 196794 | 3924 |

Both WPF observers found the native menu. UI Automation failed the
check for the Quit item at its screen point. Both observers terminated
their owned WPF process and both MSIs uninstalled successfully. Detached
replay from the measured revision verified the four Actions digests,
both full Rust-primary trials and both WPF activations with
`--before-quit`. Both full WPF-primary readbacks failed. These trials
exercised one session on each disposable host. The next native run
uses the original upgrade test's menu helper to exercise normal Quit.

| Original archive | ZIP SHA-256 |
| --- | --- |
| [x64, Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45894171914/artifacts/15154041685) | `4b821c64ef788550db227e08412fb55c35810a5eec8c7658fe22e6243612546d` |
| [ARM64, Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45894171914/artifacts/15153921166) | `428cc410ffaf4af898961d52ebb3ece143046a6247ca0c929d20c0c140de3298` |
| [x64, WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45894171914/artifacts/15154385866) | `ffeb635f7b103c867fc3a8b1a91c14b7f50ede9ed2f62101caac6227d4d83868` |
| [ARM64, WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45894171914/artifacts/15153906608) | `4a733511b5336dc8849820e2dd337f960c3690c95ab8c8ed0c35f6be6e86cbc5` |

### Shipping Flatpak and Rust probe in two installed refs

On two private Fedora x64 X11 desktops the original, signature-verified
3.0.4 deployment ran alongside the compiled Rust writer-lock probe. The
probe ran its ordinary synthetic lock lifecycle. Its launcher observed
the application socket by file type and inode without connecting to it.
Both trials used separate per-user installations with no external route.

| Installed refs | Runtime directory and shipping socket | Process namespaces |
| --- | --- | --- |
| Shipping ID on branches `master` and `test` | Both saw runtime directory 96:47 and socket 96:72. | Outer PIDs 89 and 169 each had local PID 2 in a separate sibling PID namespace. |
| Shipping ID and a separate test ID | Runtime directories were 83:47 and 83:81. Only the original could see socket 83:72. | Outer PIDs 88 and 170 each had local PID 2 in a separate sibling PID namespace. |

The same-ID trial establishes that both branches can see the same socket
on this runtime. Neither process has a positive local PID for its sibling
under the observed namespace topology. The probe's existing activation
contract expects that PID. No trial queried socket peer credentials or
delivered an activation. In both cases the original application and Rust
probe exited zero and both test refs were removed. [Source-bound native
observer](../../tools/RustCompatibilityOracle/installed/interop/assess.py)
· [Peer identity check](../../tools/rust-qa/instance/unix.rs).

The same-ID and different-ID result SHA-256 values are
`baa881024dc808c1eca3f24faba0306f0622ee530b983e31895d48127345ddfd`
and `04caced3ba5601581fa2fa499e4e85245eea8dea55bc91e3545e32fc2979ade1`.
The archived inputs identify the native compiler, executable, original
release signature and both process lifetimes. The [two shipping launches](rw01-installed-packages.md#two-ordinary-launches-of-the-installed-linux-x64-reference)
and the Rust GUI's [filtered D-Bus trial](#second-launch-through-the-installed-flatpak)
have separate positive activation evidence. Installed old/new writer
handover remains open.

### Rust startup while the shipping Flatpak is running

On Fedora x64, the Rust GUI on branch `test` refused an ordinary start while
the signed 3.0.4 application on branch `master` owned the shipping socket.
Both branches used `io.github.voltkraft.immich-folder-watch` and the published
sandbox permissions. The original GUI kept PID 88, window 4194319 and socket
device/inode `96:73`. Both the ordinary start and a start requesting the optional
inventory worker exited 1 with the occupied-endpoint error. The candidate had
no bus name after either attempt. The private configuration and data contained
only the original startup marker, whose digest stayed the same.

After the original's normal tray Quit exited zero, the same Rust executable
opened window 4194306 as PID 198 and rendered through llvmpipe. It drained on
Quit and the two private application refs were removed. The positive run used
an unconfigured profile with the optional worker disabled. The original and
candidate executable SHA-256 values are recorded in the native result under
`artifacts/rust/shipping-flatpak-interop/same-id-2_rcoy7y/`. Its `result.json`
has SHA-256 `f9438bea3cdefd63334c3bbc424097d41babad94baa43e241c3eb75615940e71`.
[Native startup comparison](../../tools/RustCompatibilityOracle/installed/interop/gui_refusal.py).

At `0ccd036` the candidate reads the application ID from `/.flatpak-info`, checks the
private runtime directory's ownership and mode, and looks up the endpoint
through its open directory handle. It verifies that handle's device and inode
before accepting an absent name. Any existing entry blocks that startup. A
stale entry therefore also blocks startup. The candidate leaves the entry in
place and sends no activation. Its normal D-Bus election still covers the
lifetime of a running Rust primary through worker drain. The admission check
covers an entry already present in this runtime directory. An original
process that binds later, another session or runtime directory, and package
upgrade or rollback still require separate evidence.
[Linux admission check](../../tools/rust-qa/gui/src/linux_legacy.rs).

In the reverse-order test on the same Fedora x64 fixture, the Rust GUI
from `0ccd036` (PID 199) remained hidden while signed 3.0.4 (PID 272)
opened a separate window, XID 8388623. Both used an unconfigured profile.
After 3.0.4 quit, another ordinary Rust launch reopened the first Rust
window, XID 4194306. Both applications exited zero. The profile still
contained only the original startup marker. The native result under
`artifacts/rust/shipping-flatpak-interop/same-id-pnnphoi4/` has SHA-256
`fc0b9a168f6fb7dac2c4eda6bd55c1f88975910cd7163354a7bab82dcb578c80`.

### Shipping launch while the Rust Flatpak owns the endpoint

On the corrected Fedora x64 trial, an already running 3.0.4 again excluded
both Rust starts. After that process exited, Rust PID 209 became primary.
It published its already-listening Unix socket with a hard link that
requires the public name to be absent. The GUI retained the socket in the
supervisor alongside the D-Bus connection. A Rust secondary uses the bus.
The legacy listener accepts and closes connections without reading their
contents or requesting an action in the GUI.

While Rust was hidden, the later signed 3.0.4 process (PID 283) saw
the same private runtime directory and socket device/inode `97:104`.
It exited zero. The Rust window stayed hidden and the old tray name
remained unowned after exit. An ordinary Rust launch then reopened the
original window 4194306 with its original PID and bus owner. The listener
recorded two connections during the trial. After Rust quit, an independent
lookup through the pinned runtime directory found the socket absent.
The original version then started as PID 377, opened its own window and
quit normally. Both refs were removed. The sole original profile marker
retained its SHA-256 throughout. The result under
`artifacts/rust/shipping-flatpak-interop/same-id-4tmbpwku/` has SHA-256
`cbb85e6f7fd4ad554efa03db773c7cda2e14dac9e15fcca6a41d78e2b81efab9`.
[Installed observer](../../tools/RustCompatibilityOracle/installed/interop/gui_refusal.py)
· [Linux election](../../tools/rust-qa/gui/src/linux.rs).

All 27 local native GUI and tray tests passed, as did Clippy. In a separate
test a private D-Bus daemon exited while Rust held the socket. The listener
still accepted a connection after bus loss, and explicit supervisor shutdown
removed the socket. The offline GUI test launcher supplies a temporary
synthetic account entry for that private bus.

These installed trials use an unconfigured profile on a single private
desktop. The original process exits before Rust first claims the endpoint.
During shutdown the shipping coordinator disposes its bound socket and
then attempts another removal by name. The bundled .NET 10.0.12 runtime
also removes that name during socket disposal. Installing across an
overlapping old shutdown therefore still requires confirmation that the
original process has fully exited. Concurrent package changes, other
sessions, stale endpoints after abrupt exit and a handover with an active
sync engine remain open. [Shipping coordinator](../../src/ImmichFolderWatch.App.Linux/Platform/UnixSingleInstanceCoordinator.cs)
· [.NET 10.0.12 socket lifetime](https://github.com/dotnet/runtime/blob/v10.0.12/src/libraries/System.Net.Sockets/src/System/Net/Sockets/Socket.cs#L3184-L3193).

### Installed shipping launch during a Rust inventory

On Fedora x64, the corrected Rust Flatpak ran the source-pinned inventory worker
under the shipping application ID. The original signed 3.0.4 bundle and the
Rust test branch shared a private X11 desktop and the ordinary Flatpak profile.
Two launch-time read-only grants exposed a synthetic media directory and YAML
configuration to the Rust test branch. Only its worker launcher selected that
configuration through `XDG_CONFIG_HOME`. The worker used the GUI's filtered
`/run/flatpak/bus` via `unix:path=/tmp/session-bus`. Both the worker's startup
check and the observer encountered `ECONNREFUSED` at `127.0.0.1:9` in the
private network namespace. The signed application received neither input grant.

While the Rust GUI was hidden, the fixture created one JPEG filename before
the signed launch and a different one after its exit. Rust PID 213 and its
direct worker PID 224 retained their original start times and executable
identities at five observations, including one while the signed apphost was
present. Passes 2 and 3 found one and two files respectively, with one new
file per pass. For each discovery the observer held an open descriptor for
the same album inode and received a kernel `DN_ACCESS` event, after 4.44
and 4.51 seconds. The signed PID 289 saw the original socket and
exited zero. The listener counted two connections. The Rust window stayed
hidden until a further worker-enabled Rust launch reopened XID 4194306 on
the original primary. The original worker exited on GUI Quit. A subsequent
3.0.4 primary opened and quit normally, the shared profile retained its sole
startup marker, and the private installation was empty after uninstall.

Reproduce with `python3 -B tools/RustCompatibilityOracle/installed/interop/assess.py`
and arguments `--gui-build artifacts/rust/gui-dual-election-01`
and `--inventory-subject artifacts/rust/performance/subjects/linux-dual-election-8e1c5d7`.
The result at `artifacts/rust/shipping-flatpak-interop/same-id-imaf441q/result.json`
has SHA-256 `3ecf0a4abe209d3675aa2e519b16bfc9e58c1cc76a172450e043c03a57d046d1`.
Independent readback checked the detached signature, 26 evidence files, 64
archived source members and both synthetic inputs against the recorded sweeps.
The signed secondary's startup path returns before starting its in-process
services. This run covers an unconfigured shipping peer and a Rust inventory
that reads file metadata. Writer handover with a configured synchronization
engine remains open. [Installed observer](../../tools/RustCompatibilityOracle/installed/interop/gui_refusal.py)
· [Shipping startup](../../src/ImmichFolderWatch.App.Linux/App.axaml.cs).

### Restart and Quit from the installed Rust tray with live inventory

On Fedora x64, the installed Rust GUI (PID 212) retained its window and
first inventory worker through two ordinary secondary launches. The signed
3.0.4 secondary exited and the Rust secondary reopened XID 4194306. On
the private desktop bus, the observer then selected `Neustart` (menu ID 2)
and `Beenden` (ID 3) from that GUI's exported tray menu. Both clicks and
replies identified owner `:1.23` behind the original Flatpak proxy, PID
208. Their request serials were 157 and 163.

| Worker | Observer PID | Flatpak PID | Native observation |
| --- | ---: | ---: | --- |
| Original | 223 | 12 | Discovered both synthetic files during the ordinary launches. Restart produced a successful exit and the original pidfd became readable. |
| Replacement | 370 | 63 | The first sweep reported two files and two changes. The next reported two files and zero changes. Quit produced a successful exit on the second pidfd. |

Both workers were direct children of GUI PID 212. Both used the same
executable SHA-256, PID and mount namespaces, and device/inode pairs for
the original `/qa/files` and `/qa/worker-profile/config` read-only
mounts. The worker SHA-256 was
`1df5522e13556332eb87523337eb4178f28765e4caa67d5945c3a4b38d94f5b0`.
After Quit, the legacy socket disappeared, the signed 3.0.4 GUI reopened
as PID 387 with the same profile, and its own Quit left the private user
installation empty. The profile marker and synthetic configuration hashes
matched their original values.

Add `--tray-worker-restart` to the existing installed `--gui-build` and
`--inventory-subject` invocation. For the local run those inputs were
`artifacts/rust/interop-menu-noble-02` and
`artifacts/rust/performance/subjects/plasma-menu-noble-02`. The complete
`same-id-wb5pomgt/result.json` had SHA-256
`ae08a43ffaedecef66aca7e72e7536e3e28b568fa6170d68a7951cdfe80bda14`.
The observer archive matched `b1bfc59`; the three source archives retained
24 observer, 31 GUI and 16 worker/reference inputs. The 29-file evidence
manifest includes the four original D-Bus frames. Replay the archived
directory with the native GIO bindings.

```sh
python3 -B tools/RustCompatibilityOracle/installed/interop/tray_readback.py artifacts/rust/shipping-flatpak-interop/same-id-wb5pomgt
```

### Rust startup during a signed worker upload

At `f5e84bc` on Fedora x64, a configured, signed 3.0.4 Flatpak uploaded
a 69-byte synthetic PNG from its private data directory to an HTTP peer
on the isolated desktop's loopback interface. The peer received the named
multipart file and held its response. The signed apphost owned the matching
established TCP connection before and after a worker-enabled Rust launch.
The original log records an inotify registration error and the shipping
polling fallback discovering the image during `uploadAll` reconciliation.
Rust used the same two read-only inputs as its preceding successful inventory.
It exited 1 at the occupied activation socket. The original signed GUI,
socket and connection survived. No Rust bus owner or inventory worker
remained, and the upload row was still absent.

The peer then returned the synthetic asset ID. The shipping worker recorded
one synchronized upload with that ID, filename, source directory and size.
The row survived ordinary Quit and reopening a standalone SQLite backup.
The PNG and configuration retained their original bytes. The private
desktop released both bus names, the activation socket and all Flatpak
processes. Both installed application refs were removed. This qualifies a
live, configured **shipping** transfer in the same-session startup check.
Rust engine activity and installed product migration still require their
own tests.

Run the preceding Fedora command with the additional `--shipping-upload`
argument. Its evidence directory contains the signed build information,
original HTTP body, YAML, application log and SQLite snapshot. The
`same-id-xhk9fs1o/result.json` SHA-256 is
`7c678b23175ab205dae79b5f954238b8d281ec6500b4d1a4f6fb5c9ef4b7c518`.
Independent readback verified the signed commit, all 33 indexed files,
65 archived source members, the PNG's chunk checksums and the complete
SQLite row including the derived account scope. SQLite `quick_check`
returned `ok`. The Rust refusal took 81.32 ms inside the held request.
The report under `upload-readback-xhk9fs1o/readback.json` has SHA-256
`424f0c6619045441a8f962bd82e4bd47a8b5c68c8d4ad1dc5f902f8288e3c7a9`.
[Upload observer](../../tools/RustCompatibilityOracle/installed/interop/shipping_upload.py).

## Ordinary second launch of the Linux GUI

The shipping Flatpak starts its executable for each launch. When the Linux
coordinator finds a primary, it asks that process to show its window. On
Fedora 45 x64, starting the Rust GUI at `21e794f` again took the application
bus name away from the primary on both X11 and Wayland. On X11 the new
process opened a different window and started a second inventory worker.
The existing desktop and tray tests had sent activation messages directly
to the primary. [Flatpak entry](../../packaging/flatpak/io.github.voltkraft.immich-folder-watch.desktop) ·
[Shipping startup](../../src/ImmichFolderWatch.App.Linux/App.axaml.cs).

The pinned zbus 5.19.0 default allows an owner to be replaced and asks to
replace an existing owner. The GUI exports the application interface before
it requests the name with only `DoNotQueue`. It admits activation after
the primary has acquired any necessary legacy socket. A secondary resolves the owner's
unique bus name, sends it one `Activate` request and checks the reply before
exiting. The primary acknowledges an accepted command and rejects a full
queue or a request received during shutdown. Election precedes appearance
monitoring, graphics and worker startup. [Linux adapter](../../tools/rust-qa/gui/src/linux.rs) ·
[Startup order](../../tools/rust-qa/gui/src/main.rs).

| Fedora x64, private X11 | Original | Corrected |
| --- | --- | --- |
| Normal second launch | Owner moved from PID 9 to 67. Workers 16 and 73 were live together. The secondary remained running after eight seconds. | The secondary exited successfully in 27 ms. Primary 9 retained its name, window 4194306 and worker 16. |
| Second launch with `--background` | The normal launch had already failed. | The secondary exited successfully in 30 ms and reopened the same window. |
| Inventory and Quit | The fixture stopped the failed secondary and its worker. The original drained on Quit. | Worker 16 found the new synthetic file in 4.753 s. The observer independently verified that the access time advanced on the same directory inode. Both process handles reported exit on Quit. |

Both runs used worker SHA-256
`1df5522e13556332eb87523337eb4178f28765e4caa67d5945c3a4b38d94f5b0`.
The GUI compiler receipts differ only in the two startup source files and
the executable digest. The paired worker reports have SHA-256
`cb5ef33ecaf3e5d1445b22d9e36dfaa213217732a82843231148a96e172603c7`
and `55a881867816cbbb773936bfb89a888e881061c5ec571d1000843415f8077d4d`
respectively. A separate X11 and Wayland lifecycle run confirmed that the
corrected GUI retained its original owner after ordinary launch and drained
on Quit. X11 remapped its existing window. Wayland presented a new surface
from the original process. These tests cover one Linux desktop session.
Installed old/new handover and Windows cross-session writer exclusion have
separate acceptance requirements. [Worker observer](../../tools/rust-qa/performance/worker/second_launch.py) ·
[Native desktop observers](../../tools/rust-qa/gui/native.py).

At `8e1c5d7` the same executable as the signed-package pairing passed
both ordinary and background second launches with an active synthetic
inventory worker on a separate Fedora x64 desktop. Both secondaries exited
zero. The primary (PID 9), worker (PID 16) and XID 4194306 survived.
The original worker discovered a file added after both launches in 4.6592 s
and drained on Quit. The report SHA-256 is
`c3dc6df1d1d1cb9b0b4711444c723bed61b229ad75cc07d8f422fb7c2cdbf31e`.
Separate native X11 and Wayland runs retained their original D-Bus owners
through ordinary second launch, exercised keyboard input and drained on
Quit. Their result SHA-256 values are
`c1ef41f16778eaca4a12bcb7b7cdd14577db501cd55d2e7047d2cf9d208d620b`
and `da3612d04f5c811fb6a1e1c43a1720add41acce2c85b41b1d19d22432b36327f`.

### Second launch through the installed Flatpak

A native x64 X11 trial installed the same corrected executable in an offline
test ref with its own application ID. It used the existing, read-only
freedesktop 26.08 Platform and Mesa GL extension. The private installation
granted X11, shared IPC and access to the tray watcher. The fixture mapped
the application's filtered D-Bus socket to the name expected by the QA
binary. The bus reported the proxy's PID 52. The GUI itself was PID 56
in the test desktop and PID 2 inside the Flatpak. Its executable hash,
process ancestry, instance ID and original X window identified the primary.
[Installed-app runner](../../tools/rust-qa/gui/flatpak/run.py) ·
[Native process observation](../../tools/rust-qa/gui/flatpak/observe.py).

A normal secondary and a separate `--background` secondary both exited
zero and reopened XID 4194306. The original rendered ten passes using
Vulkan llvmpipe and drained on Quit. The GUI, both original sandbox
wrappers and the original bus proxy exited. The private installation
contained no app after uninstall. This run used the GUI only. The
preceding X11 worker trial covers inventory continuity. The installed
trial's `result.json` SHA-256 is
`794b329ef194c1337629212887997b2a2830eb16e60a9aa91902094593405b2b`.
The SHA-256 of its evidence manifest is
`c64925dbff10da16381195bca07499c2b4336ed3b164d9dca838953d71c955bb`.

### Tray watcher replacement and menu delivery through the installed Flatpak

The optional menu trial runs after the two installed second launches. It
closes the original X11 window again, waits for the original watcher to exit
and starts a new watcher process on the same private session bus. A separate
protocol peer reads the installed item's `Menu` property and requests
`GetLayout`. It sends Open and Quit to the normal application bus name. The
monitor matches the requests and replies by sender, destination and serial.
The app uses the same X11, shared IPC and watcher permissions as the preceding
trial. [Installed menu observer](../../tools/rust-qa/gui/flatpak/tray_menu.py).

```sh
python3 -B tools/rust-qa/gui/flatpak/run.py plasma-menu-noble-02 --tray-menu
```

On native x64 the executable built from the sources at `9487dbe` had SHA-256
`8c8bfba1496d0b74424e6c316de6f8d58a488e6ebec6e89643384de88aecfb12`.
The original proxy (PID 53, `:1.6`) registered the same item with watchers
`:1.2` and `:1.17` while the original window remained hidden during handover.
The menu advertised “GUI öffnen”, “Neustart” and “Beenden” with IDs 1–3.
From peer `:1.0`, `Event(1, "clicked")` reopened XID 4194306 on the original
Flatpak instance 3343806487. `Event(3, "clicked")` drained GUI PID 57, its
two wrappers and its bus proxy. The private user installation was empty after
uninstall. The result SHA-256 is
`75234d6975f3da072244bf2549d595deaf32e5944be91c39a8b197a045b1687c` and the
evidence manifest SHA-256 is
`a6db24a2199c8669fa483aa0c55c4a363e78c283b628464b1a0ec7622c92a6d9`.
The ordinary mode passed independently with result SHA-256
`abffbda3b86fc8d82c6e25b7faada2848290b5aa7d040cf8260cc91ee0783718`.
The installed test exercises GUI-only protocol delivery. The physical panel
and worker restart use the [separate Plasma trial](rw02-plasma.md#open-restart-and-quit-from-the-plasma-menu).

On a native x64 or ARM64 rewrite runner, pass the signed Platform deployment
after preparing its matching GL.default extension. The fixture copies the two
original signature transcripts, acquisition receipts and deployment metadata
into its evidence directory. It checks the native ELF machine for the GUI
and Mesa library, follows the Platform's GL mount to the Vulkan ICD, and hashes
that ICD and the library mapped by the running GUI. The earlier installed ARM64
shipping trial recorded `lib/aarch64-linux-gnu/GL` with the Vulkan ICD merge
directory and GL commit `ab6ebce8bf5a62d9393fca493a08c45fe669a8f73527bccec6ad3dbf62748b41`.
[Signed deployment pins](../../tools/RustCompatibilityOracle/installed/launch/graphics.py) ·
[Native shipping launch evidence](rw01-installed-packages.md#signed-native-launch-inputs-on-ubuntu-x64-and-arm64).

```sh
python3 -B tools/rust-qa/gui/flatpak/run.py plasma-native --hosted-runtime "$PLATFORM_DEPLOYMENT" --tray-menu
```

The architecture-aware runner passed locally on x64 with result SHA-256
`fb74331a74bd6e6f694eca20c181f1a729772931dec80a97133edc9b8c12aea1`.
Its evidence manifest SHA-256 is
`c32414feb0c8daad09976bfd92b87b0052d9c8410c752f157fbccee91531330d`.

## Ordinary second launch of the Windows GUI

The shipping desktop shortcut starts the executable without arguments. A second
launch sends `SHOW_GUI` to the primary and exits. The WPF dispatcher shows and
activates the existing window. The Startup shortcut uses `--autostart` to
request a hidden first start. The coordinator tests above verified the pipe
exchange. The earlier Rust GUI observations reopened a window through the test
process's standard input. [Desktop shortcut](../../packaging/windows/Installer.wxs) ·
[Windows startup](../../src/ImmichFolderWatch.App/Program.cs) ·
[WPF dispatcher](../../src/ImmichFolderWatch.App/App.xaml.cs).

The canonical Rust feasibility GUI now uses the same local mutex election and
`SHOW_GUI` byte protocol when the observer explicitly enables its marked
synthetic profile. The mutex and pipe names include the test account SID and
a fresh profile identifier. The first process restricts the pipe to that
account and local clients. The second process checks the pipe server's kernel
PID against the primary's pinned profile record before sending. The primary
queues the request through its ordinary window supervisor. [Local Windows IPC](../../tools/rust-qa/gui/src/win32_instance.rs) ·
[GUI launcher adapter](../../tools/rust-qa/gui/src/windows_launcher.rs).

If all eight UI command slots are occupied, the listener keeps the pending
activation and retries when capacity becomes available. Earlier queued
commands keep their order. When the UI exits, it stops the listener before
draining the worker and keeps the primary mutex through that drain. Shutdown
wakes a listener waiting for a queue slot. The secondary records a completed pipe write.
The primary emits `LAUNCHER_OPEN` only after it queues the command and wakes
the supervisor. The observer verifies the resulting HWND separately. The
portable Rust tests exercise queue saturation, shutdown and a closed receiver.
[Queue delivery](../../tools/rust-qa/gui/src/launcher_delivery.rs) ·
[Bounded-channel tests](../../tools/rust-qa/gui/tests/launcher_delivery.rs).

```sh
cargo test --frozen --manifest-path tools/rust-qa/gui/Cargo.toml --test launcher_delivery
```

After the canonical GUI build and filtered YAML worker bundle are available in
the native Windows toolchain environment, run the observer separately on x64
and ARM64.

```powershell
python tools/rust-qa/windows-launcher/observe.py $env:NATIVE_TARGET
```

The observer creates a non-input desktop, verifies the absence of the Shell
notification area, and launches the primary with `--autostart`. It checks the
visible fallback, closes its HWND and verifies that it disappears. A second
copy of the same executable then runs without arguments. Its job must contain
exactly one process over its entire lifetime and drain with exit code zero.
The observer independently checks the reopened window's owning process and
desktop, and the original inventory worker's PID and creation time. Before
close and after reopen it enumerates the primary job and checks its open
process handles. It accepts the two staged executables and an optional native
system-directory `conhost.exe` directly under each. The receipt records the
observed PIDs, parents, executable names and creation times as the checks run.
It also records whether the reopened window obtained the foreground. Quit
must drain the primary and worker, and a fresh launch must become primary in
the same test profile. The logs and receipt are under
`artifacts/rust/windows-launcher/<target>/`.
[Native observer](../../tools/rust-qa/windows-launcher/observe.py) ·
[Launcher evidence controls](../../tools/rust-qa/windows-launcher/test_launcher.py).

All 54 earlier Rust idle measurements across three runs recorded
`conhost.exe` in the GUI's process tree. In all six canonical trials at
`7517e3b` the console host was a direct child of the inventory worker.
These observations motivated the per-member identity check.
[Earlier native measurements](rw02-windows-window.md#repeat-measurements-before-the-dispatch-trace).

### Native first-window timeout at `8091469`

Both Windows jobs timed out waiting for the first visible primary on their private
desktop. Each primary reported `READY Visible Unavailable`, initialized its first
graphics generation on the Microsoft Basic Render Driver and completed eight
empty inventory passes. Neither job reached the second launch. The x64 action
trace records the timeout followed by Win32 error 170 from `CloseDesktop`.
Its JSON retained only the cleanup error. The ARM64 JSON retained the timeout.
[Windows x64 action](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343500/job/137346335384) ·
[Windows ARM64 action](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343500/job/137346335340).

| Target | Primary / worker PID | SHA-256 of activation-primary.log | SHA-256 of result.json |
| --- | --- | --- | --- |
| Windows x64 | 3604 / 8472 | `1f77103b4794d6e6ab64a0e735e58b110dd12435415fa1a25d6d308ded5b6603` | `b51b58091e30af7ce7c8c7df0ecf384cb7264674db8ebe04ed1ea14108b514c8` |
| Windows ARM64 | 8700 / 9312 | `dfe7da6799ed735c212ea22fa710a9643448b59b4ce3d4610b39f50744ccac0b` | `484833f58c6ad9ae8b2ce8859adbb88e0bf58fe1b6060c16dc709f89b5a94939` |

The GUI emits its adapter marker during application creation. The pinned
eframe 0.37.0 backend creates a hidden root and shows it after the first frame.
The archived logs leave that first paint, the HWND's actual desktop and its
visibility unresolved. Both native receipts identify the CRLF checkout of the
historical launcher observer by SHA-256
`65b501a930d46c6b9dd9511ed3a65cdcc772f139c5bcac68a2bbdd5b3176415e`.
[GUI app creation](../../tools/rust-qa/gui/src/main.rs) ·
[eframe window creation](https://github.com/emilk/egui/blob/3c6eb8261c3293ad9c7ea1ed58487e038860ebef/crates/eframe/src/native/wgpu_integration.rs#L1177) ·
[eframe first show](https://github.com/emilk/egui/blob/3c6eb8261c3293ad9c7ea1ed58487e038860ebef/crates/eframe/src/native/epi_integration.rs#L448).

### Independent desktop observations

The private desktop's creator now restores its own original thread desktop
after releasing its hooks and windows. The supervisor joins that thread before
closing the private desktop handle. The receipt retains observation and cleanup
failures in order. A private observer-owned window records whether a hidden
and a shown window receive the same internal paint request used by winit.
The control also reads back its own visibility after show and hide. At GUI
startup, adapter initialization, first visibility, close and reopen, the observer
enumerates the primary's top-level HWNDs. It records up to 32 entries with
their Unicode captions, classes, PIDs, thread desktops, visibility and minimized state, together
with the primary's creation time. If the initial thread chose another desktop,
the observer also enumerates that desktop for windows owned by the primary.
[Window readback](../../tools/rust-qa/windows-launcher/window_readback.py) ·
[Desktop handle lifetime](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-closedesktop) ·
[Thread desktop assignment](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddesktop).

The ordinary foreground-first launch uses an isolated profile on the
runner's existing unlocked Default desktop. Commit `68f68c0` runs it
first, then starts the private desktop case after verified cleanup.
Both invocations use the canonical GUI executable without arguments. The
first launch must show its own titled window, close it, accept the second
process's request, show its window again and retain the same inventory worker
through Quit. The profile uses the preceding native Shell result as its initial
tray input when available. If that result is unavailable, the receipt identifies
the synthetic unavailable-tray input. Foreground startup requests a visible
window with either value. The foreground result is recorded separately even
when private fallback fails after verified cleanup. An unconfirmed cleanup
prevents the next launch. Both Windows architectures still require a fresh
native run of the private fallback, restart and foreground trials.
[Launcher controls](../../tools/rust-qa/windows-launcher/test_launcher.py) ·
[Desktop and cleanup controls](../../tools/rust-qa/windows-launcher/test_desktops.py).

### Native desktop selection and ordinary reopening at `0a2b5ca`

On both private desktops, the observer's own window received paint only
after being shown. Its enumeration saw zero primary windows. Inspecting the
primary's initial thread located the missing visible window on `Default`
on both architectures. The actual DX12 window belonged to the expected
process. Both primaries quit and both private desktops were released.

On each runner's original desktop the ordinary second launch delivered one
request to the elected primary. The primary reopened a new HWND, retained
the same worker PID and creation time, and drained on Quit. The x64 HWND
was foreground at the observer's sample. The ARM64 HWND was visible and
did not hold foreground at that sample. Each secondary exited successfully
and emptied its job. Both jobs had counted two processes over their lifetime.
The receipt identifies the system console hosts in the primary job. The
secondary job's second process remains unidentified. Both complete launcher
results therefore failed. The revised starter at `3dbc123` supplies the
checked desktop name in `STARTUPINFOEXW`, passes only the standard-stream
handles and starts the ordinary secondary detached from the console.
The observer still requires exactly one process in that secondary's job.
[Native process starter](../../tools/rust-qa/windows-launcher/named_process.py)
· [Windows desktop assignment](https://learn.microsoft.com/en-us/windows/win32/winstation/thread-connection-to-a-desktop)
· [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags).

| Target | Original desktop primary / worker | Secondary | Archive SHA-256 |
| --- | --- | ---: | --- |
| Windows x64 | 8800 / 6484 | 7496 | `24507cdc2e539eaa9a376f96d2a425d053046b94e9702d4fa2a588dae72e69e3` |
| Windows ARM64 | 1468 / 10276 | 10216 | `3361417e35cc4026af4e9ca67386ae8c1631b0ed0f90c8745ce0fb32ab3b7bdf` |

The archive readback matched each primary and secondary log and all seven
observer sources to that checkout, accounting for the Windows checkout's
line endings. The compact readback SHA-256 is
`108ea8d33d6a09035b1e77958abf6c38ee0d6ae97bd7b4b230b7300922f74c41`.
[Native workflow](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235).

### Ordinary second launch and private desktop at 93ecc35

On both original console desktops a normal second invocation reopened the
canonical GUI. The first window closed, the authenticated pipe delivered
one Open, and the same primary and inventory worker survived the round trip.
Each secondary job contained exactly one process and drained with exit zero.
The primary and worker then quit. The foreground observations differed.
[Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275435)
· [Windows ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275454).

| Target | Primary / worker / secondary PID | Foreground on reopened HWND | Launcher artifact |
| --- | --- | --- | --- |
| Windows x64 | 5356 / 5300 / 8436 | Yes at the first sample | `14778744916` |
| Windows ARM64 | 4520 / 5468 / 10472 | Visible throughout 41 samples in 2,042 ms. None showed foreground. | `14778984921` |

The private non-input desktop on both hosts enumerated its hidden witness,
a native show event and the visible `Desktop input probe` window in class
`Window Class`. The observed HWND/PID/TID triples were 524582/8292/2644 on
x64 and 197104/4312/2436 on ARM64. The additional foreign-thread desktop
name query returned Win32 error 5. Both private trials stopped at that
check before the second launch. The observer restored its original desktop,
closed its handle and drained the GUI. The complete private restart and
retained-window activation still need native receipts.

Readback checked all six launcher, integrated tray and separate Shell ZIPs
against GitHub's digests. On each architecture it compared 31 distinct
observer and worker input files with the exact Git checkout and reconciled
the raw process logs with the visibility, worker and cleanup records.
The readback SHA-256 is
`c1f17ca8f95defa38ed4639f5d90746da72ced35a564e33605d2d8b573e626d0`.
[Integrated Shell results](rw02-windows-services.md#original-explorer-and-the-primary-gui-at-93ecc35).

### Explicit Windows foreground requests

The canonical supervisor used to consume an explicit Open before the recreated
root had a visible HWND. Commit `648501a` keeps the request until the owning UI
thread has a visible root and consumes it once. The retained root uses the same
request after showing its existing HWND. A normal second launch on the input
desktop can offer the foreground right to the connected pipe server. It first
checks the server PID, process creation time and live process handle. An
unavailable or denied grant still allows the ordinary activation message to
reach the primary. The primary calls `SetForegroundWindow` on its own visible
root and records the return value. Automatic startup requests no grant.
[Windows foreground grant](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-allowsetforegroundwindow)
· [Windows foreground request](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)
· [Application launcher](../../tools/rust-qa/gui/src/windows_launcher.rs)
· [Pending activation](../../tools/rust-qa/gui/src/foreground_request.rs).

The secondary log records its grant result. The primary log names the exact
HWND and result of its request. The desktop observer samples actual foreground
ownership and, on the retained input desktop, keyboard focus. A retained focus
timeout leaves both process logs available for diagnosis. Independent source
review reproduced the retained patch and checked the first synchronous eframe
paint and the ordinary reopen. Native Windows results for this change belong
to the [assessment at `1e58541`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708).

### Native Windows launcher at 1e58541

Windows x64 completed the ordinary second launch and restart on the private
desktop and the ordinary launch on the original input desktop in both
variants. The retained build reopened the same HWND with the original worker.
The observer confirmed both foreground and keyboard focus.
[Canonical x64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14795074825)
· [Retained x64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14795414801).

On ARM64 the canonical private launch and restart both drained their jobs.
When cleanup opened a fixture entry for deletion, Windows returned sharing
violation 32. The original log identifies the operation but omits the name.
The canonical Default-desktop trial therefore did not start in that run.
Commit `68f68c0` records the failing relative path and preserves the busy
entry. The retained private trial passed. On Default, secondary PID 2128
granted foreground access to PID 5780. The same HWND 1376862 became visible
with worker PID 1780. Its UI thread's `SetForegroundWindow` returned false.
All 41 foreground samples over 2,022 ms and all 41 keyboard-focus samples
were negative. The primary and secondary jobs drained normally. This was a
no-argument launch by the native observer. An interactive launch through
Explorer still needs direct observation.
[Canonical ARM64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14796192246)
· [Retained ARM64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14796579708).

### Native Windows launcher at 6af7100

Both canonical launchers completed the original input desktop, the private
desktop and the private restart. Each no-argument secondary sent one Open to
the original primary and exited. On both original desktops the primary
recreated its DX12 window, retained the worker and drained normally at Quit.
Each secondary granted foreground access to the original primary.

| Original desktop | Primary / worker / secondary PID | Recreated HWND | Observed foreground |
| --- | --- | --- | --- |
| Windows x64 | 3276 / 8756 / 2828 | 1704040 | Windows accepted the request. The HWND owned the foreground on the first sample. |
| Windows ARM64 | 1272 / 1556 / 6896 | 590404 | Windows declined the request. The HWND was visible during all 41 samples over 2,044 ms and stayed in the background. |

The canonical fixture's overall pass covers IPC, visible reopening and
cleanup. Foreground ownership has its own measurement. These secondary
launches came from the observer's `CreateProcessW` call. An ordinary
interactive Explorer launch still needs its own observation. Independent
readback matched seven archived file hashes and 30 source hashes on each
target, including the native grant, primary request and process identities.
[Canonical x64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14805400187)
· [Canonical ARM64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14805481046).

### Private launcher cleanup at 8566f81

Both native launchers reopened the canonical GUI on the original Default
desktop and retained the initial worker. Windows x64 granted foreground
on the first sample. ARM64 kept the reopened HWND in the background in all
40 samples over 2,005 ms. Seven archived logs and 30 source hashes per
target matched the Git revision and recorded PIDs. The combined readback
SHA-256 is `0cd15b0537fea9b1305aba8d2bf6a21f605277a2d17becc79dbc516eab5d850c`.
[x64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14810329735) · [ARM64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14810518540).

The private ARM64 activation and restart drained both jobs and restored
the original desktop. Subsequent profile cleanup received Win32 error 145
for a nonempty directory. The receipt did not identify the remaining
entry. Commit `579fbcc` records the first error, relative directory and
volume/file ID. It allows up to five seconds for previously requested
deletions to take effect and checks the identity and type of the held
directory before each retry. A persistent entry or a changed error fails
cleanup. The independent review and portable controls passed. The new
native control holds a synthetic child across the first real disposition
attempt, then releases it through the original handle.
[Cleanup implementation](../../tools/rust-qa/windows-performance/native.py) · [Native control](../../tools/rust-qa/windows-performance/test_owned_subject.py).

The ordinary retained launcher gave the window foreground on the first x64
sample. On ARM64 the reopened window remained in the background throughout
41 samples. Both separate private retained-launcher restarts passed. In
the retained tray fixture, the x64 private cleanup also encountered error
145, so neither original-desktop tray attempt ran.
[x64 retained tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14814786519) · [Windows Shell observations](rw02-windows-services.md#original-desktop-at-8566f81).

## Launcher cleanup and foreground at 549066f and ba02f8b

Across the two revisions, eight private restart trials ran on Windows x64
and ARM64. All 24 primary processes drained and exited zero.
All 16 ordinary second launches exited with the original worker still
running in the primary process tree. Its PID and native creation time
matched before and after the second launch.
All 36 separate test profiles were removed. None of the launcher profiles
needed to retry directory removal. In the separate retained tray case
at `ba02f8b`, both private profiles did encounter Windows error 145.
The original directory handle accepted disposition after five retries on
x64 and sixteen on ARM64. The evidence does not identify which child
entry had delayed either removal.
[x64 tray and launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14825115763) · [ARM64 tray and launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14826595019).

On ARM64 the original desktop reopened the visible canonical and retained
windows at both revisions and kept them in the background for every
sample across two seconds. The canonical process recreated its HWND. The
retained process recovered its original HWND. Ordinary foreground keyboard
handover on ARM64 remains open.
[First ARM64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471/artifacts/14819371268) · [Second ARM64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14824351734).

### Ordinary second launch at 653f255

Both parameterless second processes exited successfully. Each reopened
the original HWND with the same worker, DX12 device and renderer
generation. On x64, HWND 2031726 received foreground and keyboard focus
on the first sample. On ARM64, HWND 1835364 became visible and all 41
samples over 2,023 ms showed it without foreground or keyboard focus.
Each separate shell-less control restarted with a new primary and worker
and exited with an empty job.

The integrated x64 Shell registered the version 4 icon. Its observer
could not identify the overflow button and recorded zero activation
markers. The ARM64 Shell refused the initial registration and both
automatic retries. Neither job established an actual Shell click.
The seven launcher logs per host and the corresponding eight x64 and six
ARM64 tray logs matched their original receipts. The build and observer
sources matched the exact Git revision.
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14847493064) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14847852603).

### Ordinary second launch at 1904be7

On x64 the ordinary second launch returned HWND 2621908 to the foreground
with keyboard focus on the first sample. PID 5000 retained worker 8952.
On ARM64, PID 3540 retained HWND 1966220 and worker 2556. Windows refused
the primary's foreground request despite the secondary's successful grant.
All 41 samples over 2,020 ms showed the same visible HWND in the background.
Both hosts kept DX12 generation 1 and drained their primary and secondary
jobs. Both separate private restart cases passed.

In both x64 tray trials Explorer acknowledged the version 4 icon. Its
reported center showed `eeeeee` and the four overflow-button queries had
zero matches. In both ARM64 trials Explorer refused the initial add and the
two scheduled retries. No trial produced a Shell Open callback. On each
host the native launcher and tray logs matched the archived receipts and
34 source files matched the Git revision. The combined readback SHA-256 is
`1ec9fd1fa5f2bba87b45b983bdc8ff2ca110202e1cf66d312654a418f148bb1f`.
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14854302616) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14854152253).

### Staged executable cleanup at 21e794f

On Windows x64 the ordinary secondary returned zero. The original GUI
(PID 7132) showed HWND 2031982 in the foreground and retained worker 5184.
Its log recorded nine completed passes at shutdown. Both process jobs
were empty. Windows then refused the DELETE handle for
`subject/native-gui-assessment.exe` with sharing violation 32. The
foreground trial retained its failure and the private-desktop trial was
skipped. On ARM64, both launcher trials completed and removed their
profiles. The original GUI (PID 5208) retained worker 1624 and reopened
HWND 327924. All 41 samples over 2.016 seconds found the same visible
window. None recorded it in the foreground.
[Native launcher run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661).

The two original receipts have SHA-256
`e4232da904523e1f9f1d3eff57fc3701ff1c71c7cb73f633b65c332d4eabe54d`
and `2ae35a8dfbabfc18a6c1f2f802cb5100ab9d19c0fb9d3a6b87e4f38b6af6f9da`
for x64 and ARM64 respectively. Archive readback matched the four x64
logs and seven ARM64 logs to their receipts. On each target all 13
observer inputs matched the Git sources with the runner's line endings.

The launcher observer now hashes each staged executable under its
deny-write, deny-delete handle. A second handle keeps the original
volume and file ID live and continues to deny writes as cleanup opens
the DELETE handle. Only a sharing violation on that open permits a retry,
for up to five seconds per executable. The observer compares the new
handle's identity, requests disposition on that handle and confirms that
opening the original name returns file-not-found. The subject directory
stays pinned until both names are gone. An uncertain job exit preserves
the profile. The executable receipts record their digest, identity,
attempt count and any initial sharing refusal.
[Launcher observer](../../tools/rust-qa/windows-launcher/observe.py).

The Windows control holds a real deny-delete handle on the staged GUI
copy until it observes the first native sharing violation. It then
checks both executable dispositions and removal of the two fixture
directories. Run the focused controls from the project root with
`python -B -m unittest discover -s tools/rust-qa/windows-launcher -p test_staged_images.py`.
The hosted control writes its source hashes and observations to
`artifacts/rust/windows-launcher-staging/<target>/result.json`.
Native results for the revised cleanup are pending.
[Staged-image controls](../../tools/rust-qa/windows-launcher/test_staged_images.py).

### Retained windows on the original desktop at 21e794f

The two normal no-argument launches reached the original retained window.
On x64 the secondary gave primary PID 7468 foreground permission. The
same HWND 1245536 acquired foreground and keyboard focus. Inventory
worker PID 6036 remained alive. On ARM64 the secondary granted permission
to primary PID 5264, whose request for HWND 2032280 returned false. The
window was visible with its original worker PID 5192. All 41 foreground
samples over 2.017 seconds were negative and the keyboard check found no
focus. The ordinary private-desktop restart passed on both architectures.

The same retained binaries also ran the integrated tray trial. The x64
Shell registered the icon, but the observer could not identify the
hidden-icons control. The ARM64 Shell refused the initial registration
and both retries. Neither original desktop delivered a verified activation
from the Shell. Both private Shell-less fallback trials passed.
[Windows x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14960630023)
· [Windows ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14958668144).

Detached readback verified each archive's Actions digest, 13 ordinary
launcher inputs, 19 integrated tray inputs, all indexed process logs and
the shared retained build receipt on each architecture. Its SHA-256 is
`46dd9dd80047e959e0743cd913672a833d149e2f4d30a286a8baf7cf595c2bbb`.

On the dedicated keyboard desktop the foreground launcher's F24 key-up
started an ordinary secondary on both Windows architectures. On x64,
secondary PID 1740 returned the foreground to primary PID 10092, HWND
5898592, with inventory worker 4084. On ARM64 the corresponding identities
were secondary 8500, primary 2924, HWND 1442392 and worker 2460. Each first
sample found the original window visible, active and keyboard-focused.
Both primary and secondary processes exited zero. Both supervisors restored
Default. For each architecture detached readback matched all 17 observer
sources and the six indexed files, including the two process logs and
the native keyboard record. [x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14963163292)
· [ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14962421675).

The WPF timing reference reopens its window for the measured cycles by
signaling the shipping coordinator directly. A separate reference now
starts the original WPF executable a second time without arguments after
the final WPF idle trial has recorded its metrics. On the same disposable
desktop it checks that the original primary remains hidden while the
secondary is suspended, then observes the original HWND, its native show
event, and foreground ownership after the secondary exits. An event on the
same Windows uptime tick as the return from resume leaves its order
inconclusive. The original WPF secondary can exit zero even when its
signal fails. The native result will be recorded beside the final WPF
trial as `wpf-3.second-launch.json`.
[Shipping entry point](../../src/ImmichFolderWatch.App/Program.cs) ·
[Native observer](../../tools/rust-qa/windows-performance/run.py).

## Second launch from a foreground test window

The ordinary launcher trial starts the secondary process directly from
its observer. The keyboard trial exercises a different condition in the
Windows foreground rules. A process started by the foreground process
can be eligible to request foreground access. Windows decides whether
the reopened primary actually receives it.
[Microsoft's foreground-window rules](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow).

On a disposable native Windows runner, the supervisor creates a temporary
input desktop and checks the retained GUI against the build used in the
ordinary launch. After the original GUI hides, the fixture shows its own
launch window. It checks the input desktop, the window owner, foreground,
keyboard focus and center hit before sending one tagged F24 keystroke.
The fixture's native message loop receives the tagged key-up and starts
the same GUI without arguments. The observation
records the parent and child process identities, the primary's foreground
request, the original window and worker, and the actual foreground and
keyboard focus after reopening. The supervisor restores the runner's
original desktop. Explorer icon activation has its own trial.

From the native build environment, after the ordinary retained launcher,
run the following command. The original logs and result are in
`artifacts/rust/windows-launcher-input/<target>/` in the final desktop
archive. The recorded status distinguishes observed focus, a failed
handoff, and an unavailable input desktop or test window.

```powershell
python -B tools/rust-qa/windows-launcher/input_launch.py $env:NATIVE_TARGET
```

[Keyboard trial](../../tools/rust-qa/windows-launcher/input_launch.py)
· [Native input and handler](../../tools/rust-qa/windows-launcher/input_gesture.py).

### Named input desktop at e796d30

On Windows x64 and ARM64 the retained GUI started in session 2 on the
fixture's own input desktop. Both primary processes exposed their original
window, selected the DX12 Microsoft Basic Render Driver, presented with
Mailbox at one-frame latency and logged both empty inventory passes. Before
the observer could request close, the x64 primary exited with
`0xC0000005` and the ARM64 primary with `0xC000041D`. Neither trial
reached the keystroke or started a secondary process. Each supervisor closed
its worker job, removed its synthetic profile and restored the original Default
desktop. The original archives identify the exit codes and stage. They contain
no faulting module or stack. Detached readback matched all 17 observer inputs
and the ordinary-launcher receipt for each architecture. Its SHA-256 is
`99280ab4b7c80853d75e35243070f5275523ced8fa6b03ee5c1f1a68b7d89e34`.
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14874798632) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14873982830).

### WPF and retained Rust second launches at 4e3dbc4

On Windows x64 an ordinary second launch reopened the original WPF HWND
1901124 and it held foreground at the first sample. The second process
exited successfully. The retained Rust window held foreground and keyboard
focus at the first sample in both its ordinary and its F24 keyboard trial.
The first trial retained worker 2948 and the second retained worker 8012.
WPF's three lookups of its tray icon returned the same rectangle as the
separate Rust trial. The rectangle by itself established no activation.
[x64 native WPF and Rust records](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14979507507).

On Windows ARM64 the original WPF 3.0.4 sources and the retained Rust
GUI both reopened their original HWND on an ordinary second launch.
The WPF window appeared 63 ms after resume. All 41 subsequent foreground
samples over 2.019 seconds showed it in the background. The retained Rust
window also remained in the background across its 41 samples.

On the private input desktop, a foreground window receiving F24 launched
the same retained Rust executable. Its original HWND 4326006 had foreground,
active-window state and keyboard focus at the first independent observation.
Worker PID 1464 survived the reopen. The processes exited successfully
and the host restored the Default desktop.
[ARM64 native WPF and Rust records](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14978878237) · [Ordinary retained Rust HWNDs](rw02-windows-services.md#corrected-canonical-windows-launcher-at-4e3dbc4).

### Retained Windows second launches at 989bb33

On x64 the ordinary second launch brought the original HWND 3015190
to the foreground with keyboard focus at the first sample. Worker 884
survived and the secondary exited successfully. Two separate Shell
preflights drained their process jobs and Windows accepted disposition on
each original staged GUI executable. After the fixture released its last
file handle, its first read of each filename returned Win32 error 5.
Cleanup remained unconfirmed and both subsequent retained Shell attempts
were skipped. The earlier successful ordinary launch removed its copy
of the same executable. [Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14981932344).

On ARM64 the original HWND 1966576 reopened and worker 7216 survived.
All 41 observations over 2.019 seconds found the window in the background.
Explorer declined registration on both retained Shell attempts, and both
profiles passed cleanup. [Original ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14981947506).

Windows can return access denied for a name pending deletion. The x64
archive did not identify a remaining handle. The revised observer retries
only that read, under the pinned parent, for up to five seconds after
disposition and witness release. It records the attempt count and first
and last Win32 errors separately from the original DELETE open. Only
file-not-found confirms absence. An open name, a different error or
expiry stops cleanup. The native control holds one additional read
handle sharing deletion until the first refused read, then requires a
successful absence check.
[Windows file open semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) · [Windows disposition flags](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_file_disposition_information_ex) · [Staged image control](../../tools/rust-qa/windows-launcher/test_staged_images.py).

### Native staged image readback at f155b65

On Windows x64 the normal GUI tray preflight encountered the same
access-denied read after Windows accepted disposition on the original
staged GUI file, ID 844424930195012. No test handle was deliberately held
open in this preflight. The eighth read returned file-not-found. The worker
image and both images in the Default-desktop trial returned file-not-found
at the first read. The recorder confirmed cleanup in both profiles. The
independent ordinary launcher also confirmed all four names absent at the
first read. [Native tray and staging record](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14987084653) ·
[Ordinary launcher record](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14986709542).

The retained x64 GUI also encountered access denied on the original
staged name and confirmed absence on its seventh read. The other nine
GUI and worker names were absent at the first read. Both retained Shell
attempts then ran on the original desktop. In each trial Explorer accepted
registration, but none of the 256 sampled points in its reported rectangle
showed the corresponding test color. The ordinary second launch reopened
HWND 5111934 with foreground and keyboard focus and kept worker 5720.
On ARM64 all ten names were absent at the first read. The ordinary second
launch reopened HWND 2163306, kept worker 6136 and stayed in the
background for 41 observations over 2.020 seconds. Explorer declined
registration in both retained Shell attempts. All profiles passed cleanup.
[Retained x64 trials](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14988197453) ·
[Retained ARM64 trials](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14987583680).

In the separate controlled trial, both architectures observed Windows
error 32 on the initial delete-open of the deliberately held GUI image.
After Windows accepted disposition, the first name check returned error
5. Releasing the final sharing handle allowed the second check to confirm
error 2. Both workers disappeared at the first check. In the independent
foreground trials, a real F24 launch focused the same retained HWND on
both hosts and preserved the original worker.
[x64 controls](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14991846627) · [ARM64 controls](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14990910738).

At `5efe1f1` the x64 F24 observer received the marked key events,
the primary reported the secondary's PID in its open request, and the
original HWND had focus on the first independent sample. It kept the
same worker and both GUI processes exited cleanly. Windows timestamped
the secondary's resume and the original window's show event at the same
millisecond. The first sample after the trigger already showed a visible
window. The observer returned unavailable for their ordering. Those two
timestamps had been 16 ms apart in the successful `f155b65` trial.
[x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996554328).

### Ordering a fast foreground keyboard launch

At `ead9fb3` the Windows x64 F24 trial reopened HWND 8454480 with
keyboard focus and retained the worker. The primary accepted the correct secondary
PID. Its SHOW and the recorded secondary resume both fell in uptime
millisecond 7,428,421. The first post-IPC sample already saw the window.
The native ordering outcome remains unavailable for this run.
[Original x64 foreground keyboard records](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45865602688/artifacts/15147426906).

The keyboard-launch observer samples the original root’s `WS_VISIBLE`
state immediately after the suspended secondary resumes and before the
observer pumps queued events. A hidden sample followed by exactly one
SHOW on the same live root can resolve a tied timestamp. The observer
records the process creation times, window thread and the sample’s
performance-counter interval. An already visible sample leaves the
existing ordering checks in effect.
[Native keyboard recorder](../../tools/rust-qa/windows-launcher/observe.py) ·
[Windows visibility query](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-iswindowvisible) ·
[Windows event timestamp](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nc-winuser-wineventproc).

Detached replay of six archived trials preserved four ordered successes
and both unresolved x64 ties. The replay report in
`artifacts/rust/windows-launcher-input/keyboard-resume-controls/original-orders.json`
has SHA-256 `8ffa18aea8bb5963ec8d007249a71ace51728071597409061875b36ca10351b0`.
A separate review also reproduced the x64 success at `0bb39bf`. All
28 targeted tests passed. The full launcher suite passed 107 tests on
Linux and skipped three native cases.

On Windows x64 at `de3eec4`, both secondary resume and SHOW fell in
uptime millisecond 7,585,140. After resume the observer found the original
HWND 4391472 (PID 7336, UI thread 8828) still hidden. The event count
was two on both sides of this query. The third event was a SHOW on the
same HWND. Its first foreground and focus samples then found the original
window active with keyboard focus. The F24 launcher (PID 4820) had
started secondary PID 1260, which the primary identified in its IPC log.
The original inventory worker (PID 6396) survived the close and reopen.
[Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45885538660/artifacts/15161077395).

On ARM64 the original HWND 655392 (PID 7152, UI thread 10740) was also
hidden immediately after resume. Windows recorded resume at 5,317,437 ms
and SHOW at 5,317,453 ms. The original window held keyboard focus on
the first sample and inventory worker PID 6348 survived. On both hosts
the primary and secondary exited zero, both process jobs emptied, the
temporary profile was removed and the supervisor restored the original
`Default` input desktop. Both keyboard steps passed. Separate checks
failed in each desktop job. These observations cover an F24 launch
from a foreground test window on a private desktop. Explorer activation
remains open.
[Original ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45885538660/artifacts/15156702599) ·
[Desktop jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45885538660).

## Both installed Windows launch orders at 2dd5f93

On x64, Rust activated the original WPF window (HWND 262256, PID 5104,
UI thread 6056) and exited zero. The shipping helper selected Quit on
popup 196986. WPF exited zero, its job emptied and its logs recorded the
shutdown signal and start of flushing. The ARM64 WPF window also
reopened (HWND 262434, PID 4352, thread 8740). The native helper
declined to click the covered menu entry and the observer reaped its
owned process. Independent replay established activation on both hosts
and orderly WPF shutdown on x64.

The ARM64 Rust primary passed both file observations, activation and
shutdown. On x64 the original Rust worker completed both inventory
cycles, but ETW reported 134 lost events. Independent replay could
not verify that file trace or the scratch-directory cleanup. All four
MSIs installed and uninstalled with exit zero. The post-uninstall checks
found no installed application process, package registration or payload.

| Native original | ZIP SHA-256 |
| --- | --- |
| [x64 WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825893/artifacts/15155176905) | `e3a49cd76cd9325cf9385ad234b497ab49cbd315d13279f4bdcfec01ece7e19e` |
| [ARM64 WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825893/artifacts/15155431066) | `5799dfb0026c5483a87135e0e418ddb83d8c49ed14bc859186cb7e43fad6975d` |
| [x64 Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825893/artifacts/15154599378) | `abf53ba873af848b4c89b21dc34454e23c8fd3375222080cfb451828a20844d9` |
| [ARM64 Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825893/artifacts/15155376181) | `ab6ffed21def514155262ec1ec7f522157d19d85cd27780895a01b81dd21c230` |

## Installed Windows activation at f8cf6b1

The x64 WPF primary reopened its original window (HWND 589850, PID
9720, thread 9884) and exited zero after the shipping helper selected
Quit. The Rust secondary (PID 9504) exited zero. The original worker
logged the shutdown signal and the start of flushing. The ARM64 WPF
primary (HWND 459236, PID 1208, thread 8000) also reopened. The test
stopped before moving the cursor because its planned Quit point belonged
to a different foreground process. The separate replay confirmed
activation on both hosts.

With Rust primary, the ARM64 original worker completed both observed
file queries. WPF exited after its second launch, Rust quit normally
and the job emptied. On x64 the application recorded both inventories
but the kernel tracer reported 1,273 lost events. The independent file
and full-cleanup proof for that run is incomplete. The four original
MSI install and uninstall transactions all returned zero.

| Original native archive | ZIP SHA-256 |
| --- | --- |
| [x64 WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285022/artifacts/15155267748) | `c032cdb25a97f4276359924d46b1200c11ec7a511a275e41b6195d2f203cfc42` |
| [ARM64 WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285022/artifacts/15155143034) | `d09885f560b4405b404842f52225c67feb57e7ba2471484ea7e41a181261e41b` |
| [x64 Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285022/artifacts/15156305512) | `8c41c642e85c88cf1592de5a126bd957e3e5298e96170d9de46973bb2244d8f8` |
| [ARM64 Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285022/artifacts/15155987051) | `627b11ef91e997760e8387c0f2fe97b273d1e1f0432121e81fdc6db9fcb8b30a` |

## Installed Windows activation at d7c084c

Both native Rust-primary trials passed. With the original recorder the x64
worker (PID 4208) and ARM64 worker (PID 11172) each made the two required
kernel-observed file queries. Window reactivation, orderly Quit, job
drain and cleanup also passed. This x64 run predates the independent ETW
session at `69b3ddd`. The two earlier loss reports remain valid.

With WPF primary, both argument-free Rust launches reopened the original
window on distinct native ticks and exited zero. On x64 the ordinary
menu Quit completed. On ARM64 each of 16 interior points belonged to
foreground HWND 66052 (PID 8284, thread 8480). The observer stopped
before moving the cursor. The partial activation replay passed, and the
full orderly shutdown comparison failed. All four original MSIs were
removed.

| Original native archive | ZIP SHA-256 |
| --- | --- |
| [x64 Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45900725255/artifacts/15155259912) | `028604d5ff45eabcb630d7103e3998021a055d919f95a2df3feb613132fa1b2b` |
| [ARM64 Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45900725255/artifacts/15155698711) | `b3a875a8fb39b91a63054c00af9ec913fe993b135636ec5b15d261e96a5fe3a1` |
| [x64 WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45900725255/artifacts/15156502752) | `d8b39527024d17af2c128020ff495f209acba4cab74f468ef7663888e44a5bbe` |
| [ARM64 WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45900725255/artifacts/15155494029) | `b82106dff6674e9ad95dd5ae85b3cb53790418f72a48d0c7e6e0e5bb548ff56b` |

## Installed ARM64 WPF activation and Quit at 972adc6

On a private input desktop in session 2, the original installed 3.0.4
WPF process (PID 11120, UI thread 960) retained HWND 197088. The
argument-free Rust secondary (PID 1684) activated that same window and
exited zero. The observer saw the original window still hidden after
resuming Rust and visible after the request. Both Windows events had the
same millisecond timestamp. The hidden sample ended at QPC 20720725870,
before the visible sample at 20720952002. The shipping menu helper
(PID 8640) selected Quit on the same desktop. WPF logged the worker
shutdown signal and start of flushing, exited zero and left its job empty.
The observer exited zero. The supervisor restored the original Default
input desktop and released both handles. WPF's log does not record
flush completion.

On the separate ARM64 Default desktop, Rust PID 4312 reactivated the
original HWND 131710 of WPF PID 6260. All 16 sampled Quit points hit
HWND 66052 of a different process (PID 9036). The observer
stopped before moving the cursor. Both runners removed the original
MSI. Detached replay passed both checks for the private trial and only
the activation check for Default. These trials exercise same-session activation. Standard-user
cross-session writer exclusion and visible Explorer activation remain open.

| Original archive | ZIP SHA-256 |
| --- | --- |
| [ARM64 private input](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45905250552/artifacts/15157584251) | `e99177b32271f68b12ecbc3c85239ecebbd9ebe0ac917ca3164d6dc4169d964e` |
| [ARM64 Default](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45905250552/artifacts/15156964970) | `ba1744ebefc2e5ba60b4c50d20c2aad5e40291be0f72e7403004e282abb8acbf` |

At `1910195` the separate Rust-primary ARM64 job retained the original
window and observed two directory/file queries from the same worker.
With WPF primary on its private desktop, Rust reopened the original
window, WPF exited zero through its Quit menu and the supervisor restored
Default. With WPF primary on Default, Rust also reopened the original
HWND 655418. The 16 Quit points all hit the foreground window of another
process. The passive observer could establish neither its class nor its
executable at startup, after reactivation or before Quit. Detached replay
of the three original archives passed the two complete cases and the
pre-Quit activation on Default.
[Rust primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46098223502/artifacts/15244303161) ·
[Private WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46098223502/artifacts/15244522728) ·
[Default WPF primary](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46098223502/artifacts/15244439309).
