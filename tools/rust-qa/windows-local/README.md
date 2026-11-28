# Windows x64 tests on the local VM

For `rewrite/rust` and its draft PR, run Windows x64 tests in a disposable
copy of the local Windows Server 2025 Desktop Experience guest. Use the
configured display snapshot and a synthetic user profile. GitHub compiles
the x64 inputs. Native Windows ARM64 and both Linux suites run in Actions.
Retain the full source revision, original input ZIP, its Actions SHA-256,
guest result and logs together. Use a fresh output directory for each trial.

Run one local Windows guest at a time. Allocate at most 3 GiB (`-m 3072M`)
to the desktop and every disposable overlay, including the workspace,
MSI, tray and proxy trials. The local starters share the [host launch
helper](guest_slot.py). It checks the RAM argument and reserves the same
slot for the lifetime of QEMU, including daemonized guests.
When adapting an old launcher, set its RAM limit and route its QEMU call
through the installed helper. On a new QA host, copy `guest_slot.py` to
the existing private VM directory before using the launcher.

```python
import runpy
from pathlib import Path

vm_dir = Path.home() / ".local/share/ifw-qa/server2025-x64"
run_guest = runpy.run_path(str(vm_dir / "guest_slot.py"))["run"]
run_guest(args, cwd=work, check=True)
```

Stage new DVDs, result disks and writable guest overlays on the local SSD.
On this test host `/tmp` is a RAM-backed filesystem.

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

### Workspace, Realtime and Combined on the same Server 2025 guest

On November 28, 2026, the native x64 guest ran the following compiler
archives offline in console session 1 as its dedicated standard user.

| Original compiler input | Local result |
| --- | --- |
| [Workspace at `a2e54f5`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103806236/artifacts/15246667821) | Nine harnesses, 35 tests passed, zero failed or ignored. |
| [Realtime at `a2e54f5`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103806236/artifacts/15246019059) | 18 unit tests, 49 wire cases and 16 Windows system proxy cases passed. The fixture and its supervisor both confirmed restoration. |
| [Combined at `6c4a364`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103222392/artifacts/15246850971) | The native smoke test and all five held-file upload retries passed after the original paths were replaced. |

For Realtime, restore the checkout with `core.autocrlf=true` and its
checked-in attributes to reproduce all 35 compiler source digests. Run
the command above with `--system-proxy` in the disposable account. Put the
offline OpenSSL CLI on `PATH` for the loopback peers' temporary certificates.
With embedded Python, add the checkout's `tools/rust-qa/realtime` directory
to a private copy of its `python*._pth` file so child interpreters can load
the fixture's sibling modules. The first run lacked OpenSSL on `PATH`.
The repeat used OpenSSL 3.5.9 and exited zero for all four driver steps.

The guest generated the Combined SPDX inventory from 250 compiled packages
in 281 compiler units. Independent host generation produced the same bytes
and validated 258 SPDX packages and 615 relationships against the pinned
schema. Its SHA-256 was
`2b2c737909bed78f8cb40195ac52a8e05fa7c56e103e83247ed7496d3df26591`.
The 47 original result files, the 667,721-byte ZIP, and the independent
replay are under
`artifacts/rust/local-windows-server-2025-x64/20261128/local-suite-a2e54f5/attempt-2/`.
The ZIP matched the guest's serial SHA-256
`eedd46bbedb9a333e3723008a7ed27fdfd2d0b37c46d635e2fbaf8b157531e05`.

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

### GUI worker Quit during restart at 02d4460

On the 4 GiB Server 2025 VM, the five native test executables at
`02d4460` passed 27 of 28 cases. The ordinary worker restart and recovery
after an unsuccessful child exit passed. The Quit-during-restart test
received Winsock error 10035 within 0.05 seconds. Its listener was in
nonblocking mode. The early return left the test image in use during
cleanup. All 11 tray delivery cases passed separately.

The corrected observer explicitly restores blocking mode on the accepted
test socket before its bounded reads. Dropping the tray owner also waits
for its thread while other senders are still alive.
The original [compiler archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46112078964/artifacts/15249986728)
has SHA-256 `24b045b356a44d39390ef27c8579dfeabf3c81fe6154af3741355fce6b1e63da`.
The original guest ZIP under
`artifacts/rust/local-windows-server-2025-x64/20261128/gui-02d4460/`
has SHA-256 `e56cf7779fd1222c841b18c7d3d5c606dd1be680f05b0849fac6b24ec9ee23cf`.

On the local Server 2025 x64 guest at `cdb69d4`, all 29 tests in five
native executables passed. The previously failing case completed its
worker drain. The new test also observed the owner thread exiting while
a command sender survived. QEMU reported 4 GiB of base memory. The host
reader verified each original test log and the serial transfer. The
first successful execution exposed an empty-output handling issue in the
host export script. The complete archived repeat also exited zero.
[Original compiler artifact](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46113325781/artifacts/15250224209).

The compiler archive has SHA-256
`0735d389e814ebf1fed674a24cd0a97ad06b5a0bacfa723d65eab8efab132fd5`.
The original guest ZIP in
`artifacts/rust/local-windows-server-2025-x64/20261128/gui-cdb69d4/`
has SHA-256 `190ccc11c3de3dacd4cf94aab9d202a1837645beeac2d021d2e348960b15c6f8`.

### GUI tests and focused filename edits at 03b0b8e

The local Server 2025 x64 guest ran both original compiler outputs from
`03b0b8ea10a27434fbe8ea1376b277ed2c9258d5`. The host checked the original
ZIP sizes, Actions digests, binary and compiler receipts, dependency graph
and Git source digests. The ordinary GUI receipt identified its companion
test kit. [Original compiler run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46117148186).

| Original input | SHA-256 |
| --- | --- |
| [Five Cargo test executables](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46117148186/artifacts/15252353325) | `8a495982b451398905377621504f955e93e617ad985e6f6ceeccceeaa9eddcd8` |
| [Ordinary GUI archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46117148186/artifacts/15252213846) | `25f34748b164edaf09cabe13021b6bce80e0ac9487c34d1a99e5de692956549c` |

The standard user ran 29 passing cases in the offline 3072 MiB guest.
The Windows tray contributed 11, the foreground-request controller 2,
the GUI library 5, launcher delivery 4 and the application 7. The host
checked all five original logs. The two foreground-request cases exercise
the controller's decision to request focus. The separate
[editor observation](../windows-text/run.py) started the ordinary
`native-gui-assessment.exe` and measured its actual foreground window.
The initial observer launch stopped during Python import. A repeat on the
same desktop supplied the observer directory to the embedded interpreter.

UI Automation confirmed keyboard focus in the ordinary German filename
editor of PID 952, HWND `0x70212`, on the unlocked Default console
desktop in session 1. The physical field contained eight distinct glyph
masks. Native cursor movement, selection and deletion passed for `界` in
`あ界⬟.jpg`, `ث` in `L-بتث-R.jpg` and `ت` in `L-ب12ت-R.jpg`. Both
UI Automation text interfaces returned the expected filename after each
deletion. The host independently checked the PNG and its raw pixels,
the three edit records and the original window and executable identities.
These measurements cover the visible window before shutdown. Selection
restoration across a close and reopen remains unmeasured in this trial.

The evidence is under
`artifacts/rust/local-windows-server-2025-x64/20261128/gui-03b0b8e/`.
The Cargo results in `original-guest-results.zip` have SHA-256
`a14699d32cf9813d01f59e85d6878e9c77186ce0c31b709d129255a56443c95d`.
The separate editor results in `ifw-text2/original.zip` have SHA-256
`f776bcdd0e9cbe9792264a79d8bffb819c6bb09ce7cd6a3a476f7a7479e930f5`.
QMP reported 3,221,225,472 bytes of base memory and zero hot-plugged
bytes. Windows shut down through ACPI, the QEMU process exited and the
host released the temporary SSD layers.

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

### Combined profile on Server 2025 at 36190f1

The standard user on the offline 4 GiB Windows Server 2025 VM ran
`36190f153aa8aee50ec1d9b471cd3b44df5f0522` in console session 1.
The compiler ZIP matched its published SHA-256
`a7a5b052b65fbbc0d87e38d59adf2594047907ad304edcfe5dc9c299a6c746ac`.
The guest restored the same Git revision from the read-only input DVD and
verified the 82 source witnesses, lockfile and native executable. The executable
SHA-256 was `dec5ce6416b1513077738a2b69f3973c70d5b1eb70ce85b903788034fe4eb253`.
[Original x64 compiler artifact](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46101078394/artifacts/15245916256).

The smoke test read back the pinned SQLite source with extension loading
omitted, the YAML timestamp including its seventh fractional digit, one
tessellated GUI primitive and the WebSocket ping payload. It also resolved
the native eframe entry point and checked the Windows Shell notification
icon layout. In all five shipping upload cases, Windows permitted a rename
and a replacement at the original path. Each retry started at byte zero and
returned the original held file's identity and body digest.

The guest generated an SPDX 2.3 inventory covering 250 compiled Cargo
packages in 281 compiler units. Its 258 SPDX packages and 615 relationships
passed the pinned SPDX schema and target-specific checks on the host. A
second generation from the restored source and original guest files
produced identical bytes, SHA-256
`13319a30cd53aee23cc4b6fb5c6e11518587fa6ed7912eb1445f14c834cec777`.
The guest exited zero and shut down normally. Its 653,680-byte original
result ZIP matched the serial SHA-256
`75d63e781abe2b2d080c4de415f75048d8afa3e2cce26a046e3a1081da0f4888`.
All 28 member CRCs and all 23 output digests passed readback. The original
compiler ZIP, guest archive, native logs, SPDX documents and readback
receipt are retained in
`artifacts/rust/local-windows-server-2025-x64/20261128/combined-36190f1/`.

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
