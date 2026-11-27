# Windows x64 tests on the local VM

For `rewrite/rust` and its draft PR, run Windows x64 tests in a disposable
copy of the local Windows Server 2025 Desktop Experience guest. Use the
configured display snapshot and a synthetic user profile. GitHub compiles
the x64 inputs. Native Windows ARM64 and both Linux suites run in Actions.
Retain the full source revision, original input ZIP, its Actions SHA-256,
guest result and logs together. Use a fresh output directory for each trial.

## Workspace and network

Download the original artifact ZIP without extracting or repacking it.
Take the digest from the artifact metadata for the same run and revision.
Check out that revision in the guest. The [build workflow](../../../.github/workflows/rust-windows-x64-build.yaml)
produces the following inputs. Run these commands inside the guest.

| Artifact prefix | Guest command |
| --- | --- |
| `rust-workspace-windows-x64-` | `python -B tools/rust-qa/windows-local/workspace.py run C:\QA\workspace.zip $digest C:\QA\results\workspace` |
| `rust-realtime-build-x86_64-pc-windows-msvc-` | `python -B tools/rust-qa/realtime/guest.py --archive C:\QA\realtime.zip --archive-sha256 $digest --head $revision --source-root . --output C:\QA\results\realtime` |
| `rust-msi-session-endpoint-x86_64-pc-windows-msvc-` | Use the [installed MSI session fixture](../instance/cross-session/msi_sessions.py) in two active logons of the same synthetic standard user. |

The workspace runner enumerates test executables from Cargo's original
compiler messages, checks each digest and records each process exit and
output. The network fixture uses private loopback endpoints. A compiler
receipt and a guest result identify different events.

## Other native suites

| Scope | Local execution and evidence |
| --- | --- |
| RDP and mixed DPI | From the Linux host, run the VM's provisioned `tests.py`. Its two RDP monitors use 96 and 192 DPI. Retain both observations from the actual guest. [Display procedure](../../../docs/rust/rw02-windows-display.md#local-windows-server-2025-x64-display-trial) |
| Console appearance, notifications, Shell, tray and text | Use the original guest desktop and standard user. Retain the HWND, observed pixels, callback or visible text required by each test. [Contrast](../../../docs/rust/rw02-appearance.md) · [Toast sender and observer](../windows-services/toast-history.md#original-sender-on-a-disposable-windows-x64-vm) · [Tray](../../../docs/rust/rw02-windows-services.md) · [Text](../../../docs/rust/rw02-windows-text.md) |
| File guard and installed launch order | Use the console and RDP under the same standard account for the guard. Use separate overlays for the two installed start orders. [Cross-session instructions](../../../docs/rust/rw02-cross-session.md) · [Installed WPF primary](../windows-msi-interop/reverse/README.md) |
| Graphics, accessibility and same-host resource budgets | Run the WPF reference and native GUI on the same guest, collecting the window, file-worker and frame evidence. [Measurement procedure](../../../docs/rust/rw02-windows-window.md) · [Transition comparison](../windows-warm-window/dwm-transitions.md) |
| Native feasibility, storage and reference compatibility | Use synthetic legacy fixtures, an owned guest volume for VHD/FAT recovery and the original offline backups. [Native commands](../../../docs/development.md#rust-feasibility-workspace) · [Storage faults](../../../docs/rust/rw02-storage-faults.md) · [Reference corpus](../../../docs/development.md#rust-rewrite-reference-corpus) |
| .NET, installed worker, MSI and upgrade | Use an isolated overlay for each install and the original hash-pinned package. Retain the installed payload, backup/rollback observations and uninstall logs. [Windows build and upgrade](../../../packaging/windows/README.md#upgrade-process-safety) · [Installed worker backup](../../../docs/development.md#installed-windows-worker-backup) |

Some older entry points require a GitHub-hosted machine. Their x64
acceptance checks stay open until a guest-capable entry point produces the
required evidence. Preserve the original fixture preconditions and identify
the host truthfully. Previously captured hosted runs remain historical evidence.
