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
the server PID. The oracle supplies the actual account SID. Native results and
same-SID tests in two separate Windows sessions remain pending.
[Microsoft mutex semantics](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw),
[named pipe access controls](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
and [pipe identity functions](https://learn.microsoft.com/en-us/windows/win32/ipc/pipe-functions).
