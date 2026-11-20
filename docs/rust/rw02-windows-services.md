# RW-02 Windows desktop services

The [native assessment](../../tools/rust-qa/windows-services/run.py) exercises the
Windows notification area and per-user startup shortcuts on disposable Windows
x64 and ARM64 profiles. The executable uses the Microsoft Rust bindings and has
no Immich configuration, network client, installed product path or sync worker.
The reference product uses Shell_NotifyIconW and writes a per-user shortcut with
the executable, working directory, icon and `--autostart` argument. [Shipping tray](../../src/ImmichFolderWatch.App/Services/TrayIconHost.cs)
and [shipping autostart](../../src/ImmichFolderWatch.App/Services/AutostartManager.cs).

## Native invocation

Use Python 3.11 or newer, the pinned native Rust 1.100.0 compiler with Cargo,
Clippy and rustfmt, native MSVC tools and Windows PowerShell. On a GitHub-hosted
Windows runner, run from the repository root with the matching target.

```powershell
python tools/rust-qa/windows-services/run.py x86_64-pc-windows-msvc --hosted-startup --output artifacts/rust/windows-services/native-x64
python tools/rust-qa/windows-services/run.py aarch64-pc-windows-msvc --hosted-startup --output artifacts/rust/windows-services/native-arm64
```

Use an empty output directory. The default Cargo cache is
`artifacts/rust/windows-services/cargo-home`. The optional `--cargo-home DIR`
and `--offline` select an existing populated cache. On another disposable Windows
test account, `--isolated-session` enables the fixture with a private temporary
Startup directory. `--hosted-startup` additionally enables a real known-folder
registration on a GitHub-hosted Windows machine. The launcher and native process
both check GitHub's runner environment for that operation. [Runner environment](https://docs.github.com/en/actions/reference/workflows-and-actions/variables).

## What the probes measure

| Capability | Native action and observation |
| --- | --- |
| Shell and taskbar availability | The probe records the process session, window-station visibility, shell HWND availability and taskbar PID/visibility. It creates a hidden top-level tool window so that it can receive the registered TaskbarCreated broadcast. |
| Tray service | Its own icon receives NIM_ADD, NIM_SETVERSION for version 4, NIM_MODIFY, a rectangle query and NIM_DELETE. Each BOOL and the immediately captured raw last-error value is retained. The API specifies its BOOL result. The last-error value is diagnostic. |
| Notifications | The probe requests a quiet-time-respecting, silent notification with a fresh synthetic title. The request result, Windows notification state and shell callbacks for show, hide, timeout and click are recorded separately. The UI Automation observer also searches shell-owned surfaces for the exact notification title. |
| Activation and accessibility | The observer seeks only the exact unique tray tooltip in the taskbar and overflow roots. It records enabled/offscreen state and can invoke that element's accessibility provider. The native probe records shell-delivered activation separately from the private message it posts to test its own receiver. |
| Re-registration | The probe removes its own icon, sends the registered TaskbarCreated message only to its own HWND with a synthetic marker, and attempts real add/version registration again. Unmarked OS messages have independent counters. Other icons and Explorer continue running. |
| Missing host | A fresh thread creates and joins a separate, non-input desktop. It looks for a taskbar, attempts registration, and, on refusal, presents an actual nonactivating fallback HWND on that private desktop. Native visibility, restoration of the borrowed thread desktop and cleanup are observed. No global desktop switch is made. |
| Autostart | Rust creates a new, unique `.lnk` via IShellLinkW/IPersistFile. A fresh COM instance loads and resolves it without search, tracking, UI or update. The target, argument, working directory, description and icon are checked. Windows Script Host independently reopens the existing link and checks all five fields, then Rust disables it and verifies absence. The shortcut's target is the harmless probe and is never launched. |

The runner reserves the unique link name with exclusive creation before writing
a recovery marker. It compares the exact saved fixture bytes during normal
cleanup or after an interrupted native process. Existing shortcut names and
changed contents do not authorize cleanup. The test does not restart Explorer,
alter startup registry entries or simulate a new login. [Native shortcut](../../tools/rust-qa/windows-services/src/shortcuts.rs),
[native tray](../../tools/rust-qa/windows-services/src/tray.rs),
[independent observer](../../tools/rust-qa/windows-services/observe.ps1),
[Microsoft notification area guidance](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area)
and [Microsoft Shell links](https://learn.microsoft.com/en-us/windows/win32/shell/links).

`result.json` binds the source, native compiler, Git revision, executable SHA-256,
reviewed dependency graph, checks and individual capability outcomes.
`native.txt` retains raw calls and callbacks. `observer.json` retains the
independent Windows Script Host and UI Automation observations. Missing
notification presentation, absent Explorer or unavailable accessibility remain
visible in their own fields. `probeCompleted` records completion of the
assessment. Interactive notification presentation, accessibility invocation and
an actual OS TaskbarCreated event require their own positive observations.

## Native observations on both Windows architectures

At `49617467a73901fb10b9735dcf7bf727e6d0b2d1`, both Windows hosts
created their hidden message receiver, processed the targeted callbacks,
showed a fallback HWND on a shell-less private desktop and removed their
test-owned shortcuts. Each native COM reader recovered the recorded target,
arguments, working directory, description and icon for both shortcuts.
[Native runs and artifacts](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44820760903).

| Observation | Windows Server 2025 x64 | Windows 11 ARM64 |
| --- | --- | --- |
| Independent Windows Script Host readback in the synthetic and known Startup folders | Both passed | Both observer processes timed out |
| Notification area and notification request | Shell accepted add, version, modification, request and removal, and sent a balloon-show callback | Taskbar present. Initial add returned false with raw last error `0x80004005` |
| Re-registration after a targeted TaskbarCreated message | Shell accepted the new icon and version | Receiver handled the message. Re-registration was refused |
| Independent UI Automation element, invocation and resulting native activation | No matching element or activation observed | Observer timed out |

Neither host observed an unsolicited Explorer restart. The downloaded ZIPs
matched SHA-256 `dbe54a2c4ec3099a1f342b3be1aaa782fef17722ed20e4967e671f8c489b5759`
(x64) and `6274152bf583a3eda740ab17b538c8cd8800f50075eaff49bc1ec61161400387`
(ARM64). All files indexed by each native report matched their SHA-256 values.
For follow-up runs, the launcher probes WScript and UI Automation separately
with each available PowerShell host, records its version or failure, and
records the last completed observer phase on timeout. The input fixture uses
the same UI Automation host selection. Interactive notification and activation
remain open on both targets.

At `11e4e6f` the ARM64 launcher measured the Windows PowerShell 5.1 WScript
startup timeout, then successfully instantiated WScript with PowerShell
7.6.10. Both independent shortcut readbacks passed. Windows PowerShell 5.1
loaded the ARM64 UI Automation assemblies in 23.429 seconds. Both service
jobs completed and showed the fallback on the private shell-less desktop.
ARM64 Explorer still declined the tray icon. The x64 shell again registered
and removed it and delivered a balloon-show callback. All indexed service
files matched their hashes after download. [Artifacts for both Windows targets](rw02-yaml.md#reviewed-inputs-and-corresponding-sources).

## Dependency review and local evidence

The standalone lock SHA-256 is
`fd6ecf8c53e8fcbc463972c49c9ecf7f3c80e5c91a76655f5043f3b391e2d38a`.
Both target profiles selected 15 registry packages and one first-party binary.
All original archives and unpacked source bytes matched, including 31 notice
files. The selected archives contained no native objects, shaders or fonts. The
bindings call the system Shell, User, COM and Kernel APIs. The PowerShell
observer uses system-provided WScript and UI Automation services.
[Exact inputs](../../tools/rust-qa/windows-services/inputs.json) and
[feature selection](../../tools/rust-qa/windows-services/Cargo.toml).

Microsoft windows 0.62.2 supplies typed COM and desktop APIs. Its resolved
support crates include windows-link 0.2.1 and the interface and implementation
macros. Select the MIT option for the dual-licensed packages, retaining all
attribution, and the additional Unicode-3.0 notice for unicode-ident. The
shipping combined graph and notices require their own release review.
[`windows` source archive](https://static.crates.io/crates/windows/windows-0.62.2.crate)
and [Microsoft windows-rs](https://github.com/microsoft/windows-rs).

On 2026-11-20 the Linux host verified the two official, repository-pinned
Windows standard-library component checksums, type-checked both actual MSVC
ABIs with Clippy warnings denied, and passed rustfmt and three isolated shortcut
recovery tests. Native status comes from the two Windows runs. A shell-less
runner can supply shortcut, hidden-window and private-desktop observations while
interactive notification-area evidence remains open. [Acceptance record](acceptance.md).
