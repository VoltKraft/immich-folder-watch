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

After verified cleanup, a second isolated profile exercises an ordinary
foreground-first launch on the runner's existing unlocked Default desktop.
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
