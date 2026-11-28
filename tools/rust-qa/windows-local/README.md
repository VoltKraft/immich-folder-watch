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

## Ordinary GUI and native GUI test executables

The [x64 GUI compiler](../../../.github/workflows/rust-windows-x64-gui-build.yaml)
uses the reviewed GUI lockfile, reconstructed source trees and fonts. It
builds the ordinary GUI and all Cargo test executables for the library,
application and integration targets. Download both original ZIPs for the
same revision and check their Actions digests. The
`rust-gui-tests-windows-x64-` archive is the input to this guest command.

```powershell
python -B tools/rust-qa/windows-local/workspace.py run C:\QA\gui-tests.zip $digest C:\QA\results\gui --suite gui
```

The guest compares its checked-out revision and GUI lockfile with the
compiler receipt, checks all executable digests and runs each harness
sequentially. For an interactive assessment, the separate
`rust-gui-windows-x64-` archive contains the ordinary executable,
native dependency graph and build receipt. Its `testHarnessReceiptSha256`
identifies the companion test kit. The retained-window and CPU-renderer
comparisons use their own executables and measurements.

### GUI tests on Server 2025 at 1660aeb

The offline 4 GiB VM ran all five original x64 test executables from
[`1660aeb` compiler run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46099044960).
The foreground-request tests passed 2 cases, the GUI library 3, the
Windows tray 8, launcher delivery 4 and the GUI application 3. All
twenty cases passed, with zero ignored or filtered. Each original test
log matched the guest report. Real Explorer interactions have separate
[desktop observations](../../../docs/rust/rw02-windows-services.md).

| Original archive | SHA-256 |
| --- | --- |
| [Five test executables and compiler stream](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46099044960/artifacts/15244223677) | `22dbf4faaada4456a20d18752bae854545745363007478ae650949e6e4190d04` |
| [Ordinary GUI and compiler receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46099044960/artifacts/15244358084) | `f6d7f5e21b9b723f5582ebb5a131356dbeeacb5bb463401da467c448e865021d` |
| Guest output in `artifacts/rust/local-windows-server-2025-x64/20261128/gui-1660aeb/original-guest-results.zip` | `c14401996f4afb3af1c7b13120e18e46089e194a57229ce818b77f31b69b49d0` |

## Combined native profile

The [x64 profile compiler](../../../.github/workflows/rust-windows-x64-combined-build.yaml)
reconstructs the locked sources, links the executable, captures the compiler
units, and records the Clippy diagnostics and native imports. It saves these
with `compiler.json` in `rust-combined-windows-x64-<revision>`. Check out
that revision in the local guest and supply the original Actions ZIP and
its SHA-256. Choose a new output directory.

```powershell
python -B tools/rust-qa/windows-local/combined.py C:\QA\combined.zip $digest C:\QA\results\combined
```

The guest checks the original compiler inputs and executable, then exercises
the SQLite, YAML, GUI mesh, Shell and WebSocket paths and all five legacy
upload cases. The guest report binds these observations to the original
compiler archive. The same report directory is an input to
[`sbom.py`](../combined-profile/sbom.py) for the Windows x64 target.

## Shipping .NET solution and installer checks

In a fresh guest checkout, select the x64 SDK from `global.json`, Git for
Windows with `bin/bash.exe`, Python and PowerShell 7.3 or later. Stage the locked Avalonia
source and upstream inputs in `artifacts/reduced-avalonia/inputs`.
Pass the guest path of the offline public NuGet feed. The launcher keeps the
private Avalonia packages mapped to the feed it builds from the pinned sources.

```powershell
./tools/rust-qa/windows-local/dotnet.ps1 -OfflineNugetFeed D:\public-packages
```

The launcher runs the PowerShell and installer regression tests, builds the
solution, verifies package provenance and writes the .NET test logs under
`artifacts/rust/local-dotnet/<revision>/`. Select `-BuildInstallers` with the
WiX and runtime pack inputs staged when candidate packages are needed. To
exercise the installed upgrade on a clean, elevated guest desktop, supply
the published 3.0.3 MSI. The test checks its pinned hash before installation.

```powershell
./packaging/windows/Test-InstalledUpgrade.ps1 -LocalQaVm `
    -BaselinePackage D:\immich-folder-watch-3.0.3-win-x64.msi `
    -CandidateMsi artifacts/windows/msi/immich-folder-watch-3.0.4-win-x64.msi `
    -CandidatePublishDirectory artifacts/windows/msi/publish/win-x64 `
    -EvidenceDirectory artifacts/windows/upgrade-evidence
```

### Local shipping reference at `343ebd3`

On 2026-11-28, the standard user in the offline 4 GiB Windows Server 2025
x64 guest ran the solution at `343ebd315d92699d00443d52fb09bc18b214b27b`.
The fixture checked SHA-512 for 127 input files, including 120 public NuGet
packages and the four upstream Avalonia inputs. The guest used .NET SDK
10.0.401, PowerShell 7.7.0, Python 3.13.17 and Git for Windows 2.56.1.
Its private embedded Python path file included the checkout's `tools`
directory for sibling module imports. A short physical checkout at
`C:\Users\ifw-test\i\r` kept the longest extracted framework path below
the guest's 260-character limit. Python resolves substituted drive letters
to their physical locations during that extraction.

All 39 workflow and installer regression cases passed. The guest rebuilt
both private Avalonia packages, restored and built the Release solution,
verified the assemblies' provenance and produced three original TRX files.

| Test assembly | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: |
| ImmichFolderWatch.Tests | 36 | 0 | 0 |
| ImmichFolderWatch.Tests.Core | 564 | 9 | 0 |
| ImmichFolderWatch.Tests.Linux | 46 | 19 | 0 |
| **Total** | **646** | **28** | **0** |

The skipped rows identify 27 Linux D-Bus cases and one Unix file-mode case.
The separate installed MSI upgrade has its own guest procedure above.
The original transcript, standard output and errors, three TRX files, guest
receipt and independent per-row readback are under
`artifacts/rust/local-windows-server-2025-x64/20261127/dotnet-343ebd3/attempt-3/`.
The guest returned exit code zero. Its archived results have SHA-256
`23e3b24f55a92aad19fd21b750e41aa4311e9af9451475502557cd5393650752`.

## Other native suites

| Scope | Local execution and evidence |
| --- | --- |
| RDP and mixed DPI | From the Linux host, run the VM's provisioned `tests.py`. Its two RDP monitors use 96 and 192 DPI. Retain both observations from the actual guest. [Display procedure](../../../docs/rust/rw02-windows-display.md#local-windows-server-2025-x64-display-trial) |
| Console appearance, notifications, Shell, tray and text | Use the original guest desktop and standard user. Retain the HWND, observed pixels, callback or visible text required by each test. [Contrast](../../../docs/rust/rw02-appearance.md) · [Toast sender and observer](../windows-services/toast-history.md#original-sender-on-a-disposable-windows-x64-vm) · [Tray](../../../docs/rust/rw02-windows-services.md) · [Text](../../../docs/rust/rw02-windows-text.md) |
| File guard and installed launch order | Use the console and RDP under the same standard account for the guard. Use separate overlays for the two installed start orders. [Cross-session instructions](../../../docs/rust/rw02-cross-session.md) · [Installed WPF primary](../windows-msi-interop/reverse/README.md) |
| Graphics, accessibility and same-host resource budgets | Run the WPF reference and native GUI on the same guest, collecting the window, file-worker and frame evidence. [Measurement procedure](../../../docs/rust/rw02-windows-window.md) · [Transition comparison](../windows-warm-window/dwm-transitions.md) |
| Native feasibility, storage and reference compatibility | Use synthetic legacy fixtures, an owned guest volume for VHD/FAT recovery and the original offline backups. [Native commands](../../../docs/development.md#rust-feasibility-workspace) · [Local VHD command](../storage-faults/README.md#local-windows-x64-vhd-trials) · [Reference corpus](../../../docs/development.md#rust-rewrite-reference-corpus) |
| .NET, installed worker, MSI and upgrade | Use an isolated overlay for each install and the original hash-pinned package. Retain the installed payload, backup/rollback observations and uninstall logs. [Windows build and upgrade](../../../packaging/windows/README.md#upgrade-process-safety) · [Installed worker backup](../../../docs/development.md#installed-windows-worker-backup) |

Some older entry points require a GitHub-hosted machine. Their x64
acceptance checks stay open until a guest-capable entry point produces the
required evidence. Preserve the original fixture preconditions and identify
the host truthfully. Previously captured hosted runs remain historical evidence.

## Workspace execution on Server 2025 at 30e2a9c

The dedicated standard account ran all nine original Windows x64 test
executables from [artifact 15230663783](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46066266349/artifacts/15230663783)
in an offline copy of the Windows Server 2025 VM. The artifact SHA-256 was
`2a778d9090ea4829975bd3ea473f36bbb91acb0df073dd097f7456e67422ae45`.
All processes exited with zero. The six harnesses containing tests passed
35 cases, with zero failed, ignored or filtered. This covered 11 handle
integration cases, 11 legacy cases, five safe filesystem cases, three
Immich cases, three platform logging cases and two desktop lifecycle
cases. The two examples and the legacy probe executable contained zero
tests. The Windows short-name requirement was enabled for the run.

The original Cargo compiler JSON stream, binary hashes, artifact metadata,
guest execution receipt, nine test logs and independently counted results
are retained under
`artifacts/rust/local-windows-server-2025-x64/20261127/workspace-30e2a9c/`.
The measured guest had Python 3.13.17, Git 2.56.1 and VC++ x64 runtime
14.52.37029.0. Its pre-test inventory found no installed Rust or .NET SDK,
Visual Studio C++ tools or Windows SDK.
