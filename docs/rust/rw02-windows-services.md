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
python tools/rust-qa/windows-services/run.py $env:NATIVE_TARGET --hosted-startup --output "artifacts/rust/windows-services/native-$env:NATIVE_TARGET"
python tools/rust-qa/windows-services/activation.py $env:NATIVE_TARGET
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

At `8a8adaa`, Explorer on x64 registered the icon, returned a nonempty icon
rectangle and reported displaying its notification. UI Automation saw one
Shell root and could not find the fixture's tooltip. ARM64 Explorer declined
registration. The follow-up first checks the exact test tooltip through the
accessible name and help text. After confirmed registration it can open the
same-session Explorer button for hidden icons, inspect the temporary flyout
and invoke the exact test icon through its provider. It records the native
activation callback independently and restores the flyout if the test opened
it. Four deterministic controls cover cleanup and an Explorer process change.
The native observations from the later run follow below. [Explorer observer](../../tools/rust-qa/windows-services/tray-overflow.ps1)
and [Microsoft notification area guidance](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area).

## Same-session controls at d403fee

Run 44953046306 used the system's shared `IDI_APPLICATION` icon for these
controls. Both targets reported session 2, a visible taskbar, a Shell window
and notification state 6, which Microsoft calls `QUNS_QUIET_TIME`. The
observer saw one Shell accessibility root on each. Neither root exposed the
unique tooltip or generated an activation. The earlier probe retained only
the nonempty-rectangle flag. Its coordinates cannot be reconstructed.
[Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306)
and [Microsoft notification states](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ne-shellapi-query_user_notification_state).

| Native observation | Windows x64 | Windows ARM64 |
| --- | --- | --- |
| Explorer taskbar PID | 3012 | 4176 |
| Add, version 4, rectangle | All accepted, nonempty rectangle | Add refused, raw last-error `0x80004005`. Rectangle HRESULT `0x80004005` |
| Notification and activation | Request accepted, one balloon-show callback, zero shell-open callbacks | Request refused, zero balloon-show and shell-open callbacks |
| Shell-less non-input desktop | Registration refused, fallback visible | Registration refused, fallback visible |
| SHA-256 of native control result | `fb895481c4d6d5fa46aaaf499d2be7acc44718bd82ae429a7fe4f870d6424559` | `fcc61056605b9b546ab1bff9b83651025aacb1c516928878ff55b9de0b117859` |

Every indexed service artifact in both ZIPs matched its digest. The
hosted ZIP SHA-256 values were
`6e4391e0eebe43292f538115201178642a8395fba1aaece3900733fa20387c17`
on x64 and `454cf16b2d6a637d0fcce5b20c9bb082bd3e7fcc68c052e2f951bd46be9455ca`
on ARM64. A balloon-show callback records what the shell reported.

## Private input desktop and notification-area activation

The second command above requires a disposable GitHub-hosted Windows runner,
its active unlocked `WinSta0\Default` console and the first command's result
for the same target, binary, sources and workflow run. It creates
`artifacts/rust/windows-services/native-<target>/activation/result.json`.
The private worker writes `worker.json` and, when a verified shell can host
the Rust receiver, `native.txt`. Exit 0 requires native activation and
cleanup. Exit 2 records an unavailable capability. Exit 1 records a failed
control or cleanup. [Launcher](../../tools/rust-qa/windows-services/activation.py).

1. The supervisor creates and selects a fresh named desktop. The worker
   checks that the desktop has no notification-area host, starts the OS copy
   of Explorer suspended with that explicit desktop, assigns it to a verified
   empty kill-on-close job, and resumes it. The worker pins the actual
   taskbar process, verifies its full image, session, thread desktop and
   membership in the same job. The Rust receiver and optional accessibility
   observer inherit a handle to the exact private desktop. A launch that delegates to another Explorer
   cannot qualify. [Desktop startup](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-startupinfow),
   [desktop inheritance](https://learn.microsoft.com/en-us/windows/win32/winstation/thread-connection-to-a-desktop)
   and [job membership](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob).
2. The hidden Rust receiver registers a version-4 icon identified by its HWND
   and numeric ID 23. It uses the first-party 32-pixel tray image with a
   fixture-specific opaque center. Its source asset SHA-256 is
   `402073a5d81779a92c54629de7fb16a511c0764391bcdec060095c691b3d0a31`.
   The independently running worker queries that exact identifier and samples
   one screen pixel at the center of the returned rectangle. It requires the
   point to hit the private Explorer taskbar or overflow. If necessary, the
   exact private Explorer accessibility button may temporarily expose the
   hidden icons. Rust updates only its own icon to a second, contrasting
   center color. The worker must see both colors within eight levels per RGB
   channel at the same HWND, bounds and hit target. The Rust process must
   confirm the same bounds before input. [Source tray image](../../tools/rust-qa/gui/src/tray-icon.argb),
   [Shell rectangle](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shell_notifyicongetrect)
   and [screen pixel observation](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getpixel).
3. Before each pointer gesture, every visible window on the active fixture
   desktop must belong to the subject or the private Explorer job. The worker
   rechecks the color, geometry, cursor position and HWND owners. It queues
   one left-button down/up pair, with an optional second independently guarded
   pair inside the system double-click interval. Rust must receive
   `NIN_SELECT` or `WM_LBUTTONDBLCLK` with the correct version-4 icon ID. Rust
   binds `MSG.time` to the exact HWND, code and parameters being dispatched
   from its message queue. A synchronous sent callback can carry the thread's
   previous `GetMessageTime` value and is recorded as a callback without a
   qualifying queue time. The observer extends the message's 32-bit timestamp
   within the bounded 64-bit uptime interval. The queue tick must follow the
   completed first `SendInput`, and for double clicks it must follow the
   completed second call. It can equal the dispatch tick. An equal lower tick
   is ambiguous at Windows' clock resolution. Messages already queued before
   the gesture fail even when the procedure runs later. The receiver has a zero
   activation baseline and its private mode sends no test messages to the
   callback HWND. [Version-4 notifications](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-notifyicondataw),
   [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
   [message queue timestamp](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msg),
   [GetMessageTime semantics](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmessagetime)
   and [shared system clock](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-gettickcount64).
4. Cleanup removes the fixture icon, closes the owned Explorer job after
   readback of zero active processes, removes the marked temporary directory
   by identity and restores the original input desktop. A used overflow helper
   must acknowledge readiness, exit successfully and return a complete result.
   If it opened the flyout, it must receive the release marker and confirm closure
   while the private Explorer still owns the input desktop. A timeout, provider
   error or failed restore makes the trial fail even after a qualifying callback.
   A partially queued input pair also fails. For an isolated left-button down,
   a single corrective release requires a fresh check of the live desktop,
   visible process-tree ownership, callback and taskbar HWNDs, hit target, color,
   actual cursor coordinates and pressed left button. Uncertain ownership
   withholds the release. Further cursor movement is suppressed after a partial
   pair. [Private observer](../../tools/rust-qa/windows-services/activation_worker.py)
   and [input qualification](../../tools/rust-qa/windows-services/test_activation.py).

The Linux host ran the 21 Python controls, the six PowerShell tray cleanup
controls, the PowerShell parser and the embedded observer's C# compiler. Rustfmt
and warnings-denied offline Clippy passed for both pinned MSVC targets. A fresh
audit verified the unpacked dependencies against their archives and reproduced
both pinned target graph hashes. The new Win32 calls use the
system's User32, Shell32, Gdi32 and Kernel32 libraries.

At `3b4854d` both Windows targets observed a visible taskbar owned by their
fresh private Explorer. Each Shell refused the receiver's initial icon
registration. The rectangle query returned `0x80004005` and empty bounds.
Both fixtures stopped before pointer input and recorded zero activations.
Both removed the temporary directory, closed the empty Explorer job and
restored the original input desktop. In the separate original-desktop
control, x64 registered and removed the icon and recorded a balloon callback.
ARM64 declined registration there. The two private activation receipts have
SHA-256 `13037d65b9fbd331fb606d204a327c07327760bac2d64d6587f81c0829da6a95`
(x64) and `e4d5e5168962e858d25728455cba6717c9eeb93722a0cdc4b25ea2f32c33c14b`
(ARM64). [Four native archives](rw02-native-gui.md#native-follow-up-at-3b4854d).

The follow-up gives the newly started Shell one more opportunity to register
the application's icon. After an initial refusal, the Rust receiver processes
its own messages until `TaskbarCreated` or a three-second deadline. It retries
once if the visible taskbar still has the original HWND, process, thread and
desktop. A successful first registration skips the retry. The receipt retains
each Shell response and requires successful removal of any registered icon.
Rustfmt, offline Clippy on both Windows targets and 22 portable observer
tests passed. Native activation, Explorer restart, visible notification
presentation and opening the product GUI still need direct observation.
[Shell registration](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shell_notifyiconw)
· [Taskbar creation notification](https://learn.microsoft.com/en-us/windows/win32/shell/taskbar).

At `7517e3b` the x64 trial saw the private Explorer's taskbar and then lost
that window before it could launch the receiver. On ARM64, the same visible
taskbar remained available for 3,060 ms. Both registration attempts failed,
the rectangle was empty, and the receiver counted zero `TaskbarCreated`
notifications and zero activations. Both fixtures restored the original
desktop and removed their temporary directories. On the original x64
desktop the Shell accepted and removed the icon and reported that the
balloon was shown. The ARM64 Shell declined registration. A real user
activation and independent notification-area observation are still needed.
The private trial result hashes are
`4853a03925bcf221d850fa971a43197644b1484ba6939729f129aacc9c71a6a0`
(x64) and `686cd35dcbc7b31881668db6a6e70cb3cabad7559f2e770cc154eec25789da94`
(ARM64). [Desktop assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460092).

## Primary GUI and Shell callback

The elected GUI owns a hidden top-level Shell receiver throughout the
inventory worker's lifetime. It obtains the initial tray state from
`Shell_NotifyIconW` and passes it to the desktop lifecycle. The receiver
reports a new Shell and retries registration. A Shell activation enters the
primary's bounded command channel and wakes the window. The receiver stops
before worker drain and release of the primary election. The standalone
service assessment uses the same native receiver and icon implementation.
[GUI adapter](../../tools/rust-qa/gui/src/windows_tray.rs)
· [Shared receiver](../../tools/rust-qa/gui/src/windows_tray_shell.rs).

On the private desktop with no Shell, the observer starts the worker and
checks the fallback window and its ordinary secondary launch. On the
runner's original desktop it starts the primary with `--autostart`. For
an acknowledged icon, it checks the receiver's PID, the rectangle from the
Shell, two successive marker colors at the same screen position and the
Explorer provider's exact per-run tooltip. It invokes the identified item
through UI Automation. A passing result requires the matching native
callback after the provider's invocation start, an admitted GUI command,
a primary window intersecting an actual monitor, at least one UI pass and
confirmed process and icon cleanup. A missing icon or provider is recorded
as unavailable. Each architecture has its own result archive.
[Hosted observer](../../tools/rust-qa/windows-launcher/native_tray.py)
· [Explorer provider](../../tools/rust-qa/windows-launcher/tray_provider.ps1).

The receiver retries a refused real host after 3, 6, 12 and 24 seconds,
then at most once every 30 seconds. A new host starts a fresh retry schedule.
Success or host loss cancels the pending attempt. A marked test message
does not start a retry. The five portable state tests cover delayed
registration, host replacement, host absence and a full or disconnected
GUI queue. [Retry and delivery tests](../../tools/rust-qa/gui/tests/windows_tray.rs).

At `a4d951d` the independent observer holds a synchronization handle to
the original Explorer before the registration barrier. It confirms that
process at registration, marker change, provider invocation and shutdown.
A stable activation requires the ordered Shell receipts for the same
receiver and icon. A prior successful withdrawal can confirm cleanup when
a later registration is refused. If the owner disappears and the final
delete fails, retirement additionally requires the original process handle
to be signalled, no Shell or taskbar before and after the icon rectangle
query, and the exact icon to be absent. The receipt preserves the failed
delete. That host change prevents a stable activation pass. Independent
review reproduced 35 portable tests and 77 source-reachable operation
sequences. Native execution of the combined observer is pending.
[Shell lifetime and cleanup](../../tools/rust-qa/windows-launcher/native_tray.py)
· [Observer regression cases](../../tools/rust-qa/windows-launcher/test_native_tray_lifetime.py).
