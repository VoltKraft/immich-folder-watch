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
desktop, and the original inventory worker's PID and creation time. It records
whether the reopened window obtained the foreground. Quit must drain the
primary and worker, and a fresh launch must become primary in the same test
profile. The logs and receipt are under
`artifacts/rust/windows-launcher/<target>/`. Both native launcher observations
are pending. [Native observer](../../tools/rust-qa/windows-launcher/observe.py) ·
[Launcher evidence controls](../../tools/rust-qa/windows-launcher/test_launcher.py).
