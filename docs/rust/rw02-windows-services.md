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

### Private Explorer startup at 21e794f

Both native hosts found an Explorer taskbar on the owned desktop in
session 2. On x64 its first rectangle was `[0, 0, 0, 0]`. ARM64
reported `[0, 720, 1024, 768]`. Both failed the subsequent visible
window and owner check before launching the Rust icon receiver. The
original observer returned one error for all four conditions, so the
ARM64 record does not identify which condition failed. Both Explorer
jobs emptied, their temporary directories were removed and the original
`Default` input desktops were restored.
[Windows x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14956742379) ·
[Windows ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14958032495).

The observer now waits within the original 18-second startup limit for a
visible taskbar with nonempty bounds. It retains the first and last
samples, pins the process and verifies the Explorer job, session and desktop
before the receiver can start. Subsequent checks identify changes in HWND,
visibility, PID or desktop. The portable controls cover an empty rectangle,
a still-hidden taskbar with full bounds and a taskbar that never becomes
ready. Pointer activation still requires a real fixture pixel and the
matching native Shell callback. [Private Explorer observer](../../tools/rust-qa/windows-services/activation_native.py).

## Late notification on the original desktop

The Windows desktop assessment reuses the native service executable after
the GUI measurements. The observer verifies its PE architecture, the early
build receipt, compiler, dependency graph and source digests. Before Rust
sends the single silent notification, a separate UI Automation observer
starts on the original input desktop. The result records the Windows
notification policy, Shell registration and version, request result, and
callbacks for the fixture's own icon. Independent presentation requires
separate physical hits for the unique title and body on the notification
surface. The armed observer reads the baseline before the request. Native
and independent observers check the same original Explorer window, process,
thread and creation time. The Rust observer tests that process with a
zero-timeout wait on its held handle. The exit-time field is undefined
while a process is running. [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)
· [WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject).

The probe also records cleanup and preserves the original desktop settings.
The early and late receipts can show how the same host behaved at the two
times. [Native observer](../../tools/rust-qa/windows-services/notification.py)
· [On-screen checks](../../tools/rust-qa/windows-services/notification.ps1)
· [Native invocation](../development.md#rust-feasibility-workspace).

At `1e58541`, both late probes reached the original unlocked Default desktop.
The shared directory creator then rejected the notification fixture's
`ifw-shell-<token>` name before either process started. That prefix was
already required by the Rust service and the PowerShell observer. The
directory creator now accepts it with exactly 32 lowercase hex digits.
The regression follows the actual notification entry into the native create
call with its pinned parent and rejects truncated, uppercase and nested names.
The late presentation still requires a native rerun.
[x64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14797293565)
· [ARM64 receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14798618399).

The two receipts match their copies in the full desktop archives, their
37 source inputs per host and their original early measurements. Both hosts
reported quiet time early. x64 registered and received one balloon-show
callback. ARM64 refused registration. The independent readback has SHA-256
`959a289ba23d6ffb08ec0340037e54e663ed5429bd221206bdaa82c1e2c66f01`.

### Late notification at 6af7100

The corrected fixture reached the single notification trial on both original
desktops in unlocked session 2. On x64 the early state was quiet time (6)
and the late state was accepts notifications (5). Explorer accepted the
version-4 icon and the silent request. The receiver counted one show and
two timeout callbacks. The independent observer sampled one known Shell root
80 times with zero provider errors. It never identified the unique title
and body together. On ARM64 the late state was app (7). Explorer declined
the icon registration with `0x80004005`, so the fixture issued no request.
Its 90 samples covered two known roots and recorded zero provider errors.
The reported policy state does not identify the cause of the registration
failure. [State definitions](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ne-shellapi-query_user_notification_state).

Both subjects exited with zero, the observers exited with their unavailable
status, all process jobs drained and the profiles were removed. The two
small archives matched their copies inside the full desktop ZIPs, the early
receipts, and 37 source files per target after Windows checkout conversion.
The x64 and ARM64 result SHA-256 values are
`95e394f6e6c2e325580d6ec157f098cc12c29e9390b71f18c5cea6ad32c7cea2` and
`d8966b54f09d475a924ebe2a542bea041bf2b56e7952782a23fd6e1cc11c1305`.
At this revision the observer checked its baseline before release and began
repeated sampling after the synchronous Shell request returned. A
presentation during the call remains unobserved.
[x64 notification archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14808178866) · [ARM64 notification archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14807909745).

### Original desktop at 8566f81

On x64 the original Explorer accepted the notification, then reported one
show and one timeout callback. The independent observer made 80 UIA queries
on one Shell root and found no matching title and body. ARM64 Explorer
refused icon registration with `0x80004005`. The Rust sender issued no
notification. Ninety queries on two Shell roots found no matching pair.
Both observers reported zero provider errors. Sampling during the synchronous
request starts with the later change described below.
[x64 notification](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14817856976) · [ARM64 notification](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14817356380).

The canonical x64 tray icon had a Shell rectangle, but its center pixel was
`eeeeee` instead of the icon marker `2ec140`. The independent observer
found no overflow button and did not click. The separate x64 retained tray
test stopped during private profile cleanup with error 145 before either
original-desktop attempt. ARM64 Explorer refused all nine initial and retry
registrations across the canonical and two retained cases.
[x64 tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14810414710) · [x64 retained tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14814786519) · [ARM64 retained tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14815025387).

### Sampling across the Shell request

At `effae21` the observer begins reading the notification surface before
the supervisor releases the sender. A complete baseline sweep must find
the fresh title and body absent. The Rust sender records the start and
return of its single synchronous `NIM_MODIFY` using the same Windows
performance counter as the supervisor and the independent UIA observer.
The observer records each sweep and continues for ten seconds after
acknowledgement, including when it has already found both strings.
[Native sender](../../tools/rust-qa/windows-services/src/tray.rs) · [UIA sweeps](../../tools/rust-qa/windows-services/notification.ps1).

The readback requires a new sweep after the request began for a positive
observation. It records whether the title and body were verified during
the call, across its return, or later. If a fast call falls between two
sweeps, a subsequent physical match retains its own time. A post-request
sweep or interval between sweep starts longer than one second marks
the sampling interval incomplete. Any valid physical match stays in the
report. Independent review exercised all four timing corrections. The 41
Python tests and the PowerShell pixel and timing controls passed. Native
Windows presentation with this observer awaits results.
[Evidence readback](../../tools/rust-qa/windows-services/notification_probe.py) · [Timing controls](../../tools/rust-qa/windows-services/test_notification.py).

At `549066f` and `ba02f8b`, x64 Explorer registered the synthetic icon,
accepted its notification request and sent one show callback in each trial.
One independent UIA sample overlapped the 19.29 ms and 19.18 ms synchronous
requests respectively. Across 91 and 97 sweeps, including more than ten
seconds after each request, the observer found no matching visible title
and body. ARM64 Explorer refused icon registration in both trials. The Rust
sender consequently made no notification request. Its two observers
completed 109 and 108 sweeps. All four reported zero provider errors.
Readback matched the two original source revisions, all 37 observer inputs
per target and the small archives to their copies in the full desktop
archives. Windows notification presentation remains open.
[First x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471/artifacts/14822014126) · [First ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471/artifacts/14822831355) · [Second x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14826514476) · [Second ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14828277542).

## Windows notification history

The [Server 2022 x64 comparison](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-notification-2022.yaml)
uses the same Rust sender, classic Shell observer and WinRT history reader
on a disposable desktop. A separate check replays the normal sender's
timed call and the Shell's visible title and body. A history entry alone
leaves presentation open. The archive retains the original executable,
host build and both readers' evidence.

At `1b95ba0`, Explorer on Windows x64 accepted the ordinary Shell
notification and reported a show callback. Across 86 samples the
independent screen observer could not identify its exact title and body.
The native receiver recorded zero clicks. ARM64 refused initial icon registration and issued no
notification request. The late observer took 112 samples. Both observers
recorded zero provider errors. Detached replay matched the sender output,
observer log and recorder sources, SHA-256
`4918ea23985230b6e49db9fae4d33010f9b9e0e179a4e19d577a5b54d3afaa31`.
[x64 Shell archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14845265609) · [ARM64 Shell archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14843191637).

The separate inbox WinRT trial registers a per-run shortcut under a disposable
runner's Programs folder and sends two uniquely tagged notifications under its
own app identity. One requests ordinary delivery and the other suppresses the
popup. Each independent reader checks the original title and body in Windows
notification history. The trial removes one entry, checks that the other
survived, then removes it and verifies the empty history. The shortcut uses
Microsoft's stub CLSID convention. A visible banner and user activation
still need their own interactive observations.
[Trial, native commands and archive replay](../../tools/rust-qa/windows-services/toast-history.md).

The pinned 0.62.2 Windows bindings supply the additional WinRT and Shell
interfaces. Archive and license review covered the same 15 registry packages
and 31 notices on each Windows target. The combined development dependency
profile retained its four previously qualified graphs. Both Windows targets
passed the frozen cross-Clippy check. Fifty-one portable controls passed,
including refusals for incomplete import evidence, an incorrect input desktop
and a missing native history read. Independent review cleared the corrected
archive replay. The local receipt under
`artifacts/rust/windows-toast-history/reviewed-cross-check/` has SHA-256
`2a4540e190a94f3a6024c72695cc1e43ca7808cc320c1e7227020da41d912d72`.
Native x64 and ARM64 delivery remains to be observed.

### Native WinRT startup at 653f255

Both original Windows jobs verified an active, unlocked Default desktop
in session 2. The first ordinary launcher call stopped before
`CreateProcessW`. The observer had pinned its new synthetic profile
marker, but passed only the toast-specific flag in the child environment.
The shared launcher also requires that marker's token and the isolation
flag. Each archive records one planned `prepare` operation with an empty
Windows job and no child PID. Shortcut registration and history delivery
remain unobserved.
[Windows x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14849784690) · [Windows ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14851117029).

The corrected observer passes the two required values from the same
newly pinned test profile and points the child's temporary directories
there. It keeps the original user profile and Default input desktop.
Running the added test against the original sources reached the same
refusal on both target configurations. The corrected test crosses the
shared launcher's validation and stops at the native process-creation
boundary. The 53 Windows service tests passed locally. A native sender,
independent history reader and verified cleanup are still required on
each Windows target. [Fixture](../../tools/rust-qa/windows-services/toast_history.py) · [Regression control](../../tools/rust-qa/windows-services/test_toast_history.py).

### Native WinRT senders at 6084b23

On Windows x64 six separate native processes ran on the original Default
desktop in session 2. The installed shortcut had the expected target,
arguments, app ID and stub CLSID. A fresh reader found zero entries for
that ID. The quiet and ordinary senders started 77 and 130 ms after the
registration process started. Both reported `0x80070490` during notifier
setup, before either called `Show`. The original log grouped
`CreateToastNotifierWithId` and the subsequent `Setting` query in that
phase. A final reader found zero entries. The shortcut, its owned folder
and the temporary profile were removed.
[Original Windows x64 history archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14864372145).

Windows ARM64 also verified the shortcut, read an empty history and
launched both native senders in session 2. They started 166 and 264 ms
after the registrar and both returned `0x80070490` before `Show`.
The final history was empty and cleanup removed both the shortcut folder
and the synthetic profile. Detached readback checked 42 source inputs
for each architecture, both original PE import receipts and all twelve
native process records. Its SHA-256 is
`6da0d8f9dc1ff8c6a4cac532d92c61c97795c465e06a13e1152490fa8cfe55ce`.
Both native runs leave delivery unobserved.
[Original Windows ARM64 history archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14864247676).

The revised sender records the separate HRESULTs from the two read-only
calls and waits only for a newly registered app identity that Windows
reports as missing. Policy and permission outcomes end the lookup. The
normal and quiet sends still each issue at most one `Show`. The source
passed frozen Clippy checks for both Windows targets. Two Rust tests
exercised the wait and 55 service tests passed locally. The source-bound
local readback SHA-256 was
`554c54d034acaafc8ade7280a49cfa5b53599e89e10cc7396da2eb47422e4531`.
The next native run identified the failing call on both architectures.
[Native trial and archive replay](../../tools/rust-qa/windows-services/toast-history.md).

### Native notification setting at e796d30

Four native senders on Windows x64 and ARM64 verified their installed
shortcut and queried their own notification identity 16 times each.
All 64 notifier creations succeeded. Every following `Setting` query
returned `0x80070490`. All four senders ended before `Show`. On each
host, separate processes read empty history before and after the senders,
and cleanup removed the shortcut folder and synthetic profile. All twelve
processes ran elevated on the original Default desktop in session 2.
Detached readback matched six process logs, the PE import table and
43 source files on each host against the native build. Its SHA-256 is
`82e3ce74f5d039817c4acdbac064a3be1ecb2267a68ca2bbebbb0564d65fd607`.
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14875525894) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14874246937).

The follow-up trial compares the terminal shortcut-only result with
a per-user display name for the same notification identity, using the
same installed shortcut and Rust executable throughout. The Windows
notification setting, selective history readback and cleanup criteria
apply after registration. Native results for the comparison are pending.
[Procedure and ownership](../../tools/rust-qa/windows-services/toast-history.md#per-user-display-name-comparison).

### Fresh Windows user profile at 21e794f

On ARM64 the ordinary and quiet senders each created a notifier 16 times.
Every query of the notification setting returned `0x80070490`. A separate
reader found an empty history before and after both senders. Neither sender
called `Show`. The display-name comparison then stopped because the fresh
user profile lacked `HKCU\Software\Classes\AppUserModelId`. The observer
removed its shortcut, owned folder and synthetic profile. In the independent
classic tray trial Explorer declined to add the icon, so the receiver issued
no balloon request. [WinRT archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14963030294) · [Classic notification archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14961599872).

On x64 the existing per-user namespace allowed both WinRT comparisons.
The first quiet and ordinary senders used the registered shortcut alone.
The next pair ran with its separately verified temporary display name.
Each of the four senders created its notifier 16 times. Every setting
query returned `0x80070490` before `Show`. Four separate history readers
found zero entries before and after the two exchanges. All ten process
jobs emptied. The observer removed the UUID leaf, shortcut, owned folder
and synthetic profile. The original result SHA-256 is
`23c1d7d2f64ee14eb6f1a66a4c89192895ad1210e7be83a8f0be07766a72f05e`.
[Original x64 WinRT archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14963453121).

In the separate classic trial the x64 Explorer accepted the icon, version 4
and balloon request. Receiver HWND 393756 (PID 5520) recorded one show and
two timeout callbacks. The UI Automation observer sampled 88 times on the
original Default desktop with zero provider errors and found no exact
visible title and body. The icon was removed, the receiver closed, both jobs
emptied and the profile was removed. The result SHA-256 is
`ef304a5c7d01936a1916d3528f17f5594755adaf0f92bceaeadd466ec0acb412`.
[Original x64 classic notification archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14963507991).

The revised hosted comparison can create the missing standard container
in the existing user's Classes hive. The observer records the disposition
and removes its own temporary identity by handle. Its 63 local service
checks passed. Native delivery and visible presentation remain open.
[Registry scope and reproduction](../../tools/rust-qa/windows-services/toast-history.md#per-user-display-name-comparison).

The six senders in the original `21e794f` archives all reported elevated
tokens. The revised WinRT trial follows Microsoft's classic desktop send
sequence when the last notifier was created but its setting alone remains
unavailable with `0x80070490` after the bounded wait. It uses that notifier
once and records the signed `Show` HRESULT. A disabled setting or access
denial still ends the attempt. History delivery requires two independent
content matches and selective removal. A native result for the revised
sender and a direct observation of banner presentation remain open.
[Microsoft's desktop send example](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/legacy/hh802768%28v%3Dvs.85%29) · [Recorder and replay](../../tools/rust-qa/windows-services/toast-history.md).

At `13e4af8` the four x64 and two ARM64 WinRT senders repeated the 16
successful notifier creations and `0x80070490` setting responses per
sender, with zero calls to Show and empty history. The separate classic
receiver on x64 saw one Shell show callback and two timeouts. All 87 UI
Automation sweeps finished without a provider error and found no visible
matching title and body. The ARM64 Shell declined icon registration and
the classic receiver did not request a balloon. The direct-Show change
postdates this source.
[x64 WinRT](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14972183094) ·
[x64 classic](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14973117325) ·
[ARM64 WinRT](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14970553191) ·
[ARM64 classic](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14969828998).

### WinRT history and classic Shell delivery at 4e3dbc4

Both native Windows architectures passed the WinRT history trial. On each
host, the quiet sender's optional setting query returned `0x80070490` on
all sixteen attempts. The ordinary sender observed the enabled setting on
its first attempt. Both calls to `Show` returned `S_OK`. Independent native
processes read each exact title, body, tag and group. Removing the ordinary
entry left the quiet entry in history. Two final reads found the history
empty. All twelve processes on each host exited successfully and cleanup
removed the shortcut and synthetic profile. An on-screen banner still
needs a visible title and body.
[Original x64 WinRT archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14979881380) · [Original ARM64 WinRT archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14978463516).

In the separate classic ARM64 trial, Explorer declined initial registration.
The receiver made no balloon request. The observer completed 112 UI
Automation sweeps without a provider error and found no matching banner.
On x64 Explorer accepted registration and the request. The receiver recorded
one show and two timeout callbacks. All 86 UI Automation sweeps completed
without a provider error. None found the visible title and body.
[Original x64 classic archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14979736952) · [Original ARM64 classic archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14979421612).

The new WinRT observer arms before the ordinary sender and compares the
actual `Show` interval with an independent UI Automation observer's clock.
It looks for both synthetic strings on the visible Shell popup and checks
the two physical points against the original Shell window. History readback
and selective cleanup still run when a popup cannot be identified.
Both original history-only archives above passed replay. Native evidence
from this new observer is pending.
[Popup observation and raw records](../../tools/rust-qa/windows-services/toast-history.md#visible-normal-winrt-popup).

### Classic and WinRT notifications on Windows Server 2022 at db1d33a

On the original x64 desktop, the notification state was `QUNS_QUIET_TIME`
both before registration and at the late classic notification request.
Explorer accepted the request and sent one show and one timeout callback.
Across 97 UI Automation samples the observer found no visible match for
the exact title and body. All samples completed without a provider error.

The quiet WinRT sender received `0x80070490` on all 16 optional setting
queries. Its `Show` succeeded and the tagged notification entered history.
The ordinary sender observed the enabled setting. Its successful 4.15 ms
`Show` fell between two samples. Across 93 samples one Shell root was
observed, with zero provider errors and no matching visible title and
body. Independent reads found the quiet entry, then both entries. Removing
the ordinary entry preserved the quiet one. Removing the quiet entry
emptied history. The job drained and the shortcut and profile were removed.
Desktop presentation remains open for both senders.

Independent replay matched 46 source inputs, 17 native service outputs,
two classic observation files and 19 WinRT observation files. The archive
has SHA-256 `d1337be9f94bb3a1d9d0788dfc6a88e5cea73819ad76288bd5ce42c1ec0e839f`.
[Original notification archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46031319750/artifacts/15215136049).

The dedicated repeat samples the notification state every 30 seconds
while the original Explorer reports quiet time, for up to 65 minutes.
Each sample checks the same desktop, session and Explorer before and
after the native query. The late senders then perform their own original
presentation checks. The archived `notification-state.json` records the
actual policy history and the reason observation ended.
[Focused workflow](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-notification-2022.yaml) ·
[Windows notification states](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ne-shellapi-query_user_notification_state).

### After quiet time on Windows Server 2022 at 20dfb10

On the repeat run's original unlocked x64 desktop, Explorer reported `QUNS_QUIET_TIME`
in 96 consecutive samples taken 30 seconds apart. The next sample,
48 minutes after observation began, reported `QUNS_ACCEPTS_NOTIFICATIONS`.
The Explorer process and taskbar window remained the same. At the classic
request the Shell still reported that it accepted notifications and sent
one show and one timeout callback. Across 96 UI Automation samples,
including one during the request, none found the exact visible title and body.

WinRT accepted the ordinary and quiet sends. An independent history reader
matched each entry's title, body, tag and group and verified selective removal.
The separate ordinary popup request returned success in 4.13 ms between
two samples. Across all 93 samples the observer found no exact title and
body on the Shell. Both observers completed without provider errors.
Visible presentation remains open for both notification paths. The job
finished with a failure after 54 minutes 57 seconds. The original archive
has SHA-256 `f1f2ee67fb51580110f70b6378e16d1a9e658f5ab7c6910bd7ec2274078e56c7`.
[Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46034955133/job/140627892360) ·
[Original state, callbacks, history and popup observations](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46034955133/artifacts/15221500889).

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
sequences. The first combined native observations are recorded below.
[Shell lifetime and cleanup](../../tools/rust-qa/windows-launcher/native_tray.py)
· [Observer regression cases](../../tools/rust-qa/windows-launcher/test_native_tray_lifetime.py).

### Partial Windows tray registration

A background start also needs an ordinary way to quit when the Shell refuses
the initial icon. The canonical editor exposes **Beenden** (German) or **Quit**
(English) while the tray is unavailable. The button uses the existing owner
shutdown path. The native Windows observer starts the paired editor and worker
on a private input desktop, waits for two inventory passes and locates the
visible German button on the primary window using UI Automation. It invokes
that button with the launcher's command pipe still open and verifies the
original worker exit, primary drain, profile cleanup and return to the
original console. The observer requires the real Shell refusal, including its
receiver and registration token. [Native observer](../../tools/rust-qa/windows-launcher/window_quit.py)
· [UI Automation action](../../tools/rust-qa/windows-launcher/window-quit.ps1).

At `07c0d70` the native ARM64 editor (PID 11180) opened HWND 328388
after the Shell refused its initial tray add. The original ARM64 worker
(PID 4860) completed two passes over the synthetic file. UI Automation
invoked the enabled, visible 70 × 22 **Beenden** button on that HWND.
The worker exited successfully, the GUI cleaned up the tray receiver and
stopped its control reader, then recorded `DRAINED passes=11` and exited
with status zero. The supervisor confirmed profile cleanup and restored
the unlocked `Default` input desktop in the original console session 2.
Both PE headers and image hashes matched their native compiler receipts.
The original ZIP matched the Actions SHA-256
`d9d80b40e752bfca1b8c3b0add67634a9517226e686f669eb29ba414672d02e2`.
[ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46128570840/job/140928524047)
· [Original archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46128570840/artifacts/15256159953).

The earlier `245a921` verifier rejected the same shutdown order for worker
8212 because it required tray cleanup to precede worker exit. Replaying
that archive reproduces the original error and confirms both events before
the control reader stopped. In the `07c0d70` run both separate source-frame
checks on `Default` failed because the field center still belonged to a
different HWND after the editor was raised. Both private-desktop frame
checks passed. The console had one 96-DPI monitor. Mixed-DPI and native
RDP rendering on ARM64 remain open. [Earlier job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46127111222)
· [Display criteria](rw02-windows-display.md#required-observations-on-a-disposable-native-desktop).

Explorer can accept the icon before the separate version-4 handshake
finishes. An isolated API model returned success for `NIM_ADD`, failure
for `NIM_SETVERSION` and failure for the attempted `NIM_DELETE`. With
these three replies, the registration method at `6a322bd` returned an
error before the GUI received its initial tray state. The same error on
re-registration could terminate the tray thread.

The adapter now reports the tray unavailable and retains responsibility
for the possibly outstanding icon. A background start receives the normal
visible-window fallback. The existing retry timer probes the same icon's
version again, and Quit still needs either an acknowledged final deletion
or the existing proof that the original, independently identified Shell
exited and its icon disappeared. A failed withdrawal is recorded in the
original Shell operation stream. The shutdown observer rejects a
`neverAdded` result after a successful add.

The regression cases exercise these API replies, the actual lifecycle's
initial show command, the retry deadline, recovery and final ownership
readback. The ARM64 desktop recorded below refused the initial add itself
and showed the real fallback window. A native Shell returning the three
partial-registration replies remains unobserved.
[Adapter](../../tools/rust-qa/gui/src/windows_tray.rs) ·
[State and lifecycle tests](../../tools/rust-qa/gui/tests/windows_tray.rs) ·
[Cleanup replay](../../tools/rust-qa/windows-launcher/test_native_tray_lifetime.py).

### Original Explorer and the primary GUI at 93ecc35

On Windows x64 the integrated primary registered its own icon with the
original Explorer, set version 4 and remained hidden with the worker alive.
The GUI and the independent observer both obtained the rectangle
`[790, 720, 822, 768]`. At its center `[806, 744]` the screen showed RGB
`eeeeee`. The GUI's first marker was `33c76b`. The observer stopped before
the color challenge or provider invocation. The primary then deleted the
icon, exited normally and drained its job. The exact receiver and icon were
absent after Quit. [Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275435).

On Windows ARM64 the original Shell refused the first add. The integrated
primary reported raw error `0x80004005`, opened its visible DX12 fallback,
ran the worker and quit. The independent observer confirmed the receiver
and icon were absent after exit. In the separate named-desktop test the
private Explorer declined the initial add and the retry on both
architectures. Both restored the original input desktop. The integrated
activation remains open on both architectures.
[Windows ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275454).

The integrated GUI artifacts are `14778803163` for x64 and `14780060057`
for ARM64. The separate Shell artifacts are `14778862212` and
`14779213755` respectively. The private GUI receiver additionally reported
Win32 error 5 for the thread desktop name on both hosts.
[Source-bound archive readback](rw02-instance.md#ordinary-second-launch-and-private-desktop-at-93ecc35).

For an acknowledged icon whose first marker is hidden, the observer can
temporarily expand the original Explorer's verified *Show hidden icons*
button on the disposable runner. It queries the application's current icon
rectangle again after opening the flyout. Both color samples and the exact
tooltip provider must agree with that visible rectangle through invocation.
The helper records the exact original provider before requesting the change
and confirms closure of a flyout that it opened. A flyout already open at
startup retains its previous state. [Original Explorer observer](../../tools/rust-qa/windows-launcher/tray_provider.ps1).

After an initially refused add, the observer leaves the live application
running for its own first two scheduled retries, up to 15 seconds. It
records the receiver, Shell return values and independent icon rectangles
while holding the original Explorer process. The initial registration and
activation results retain their original outcome. [Passive retry observation](../../tools/rust-qa/windows-launcher/tray_retry.py).

Commit `1e58541` binds each marker read and invocation to the original popup's
HWND, PID, thread and class. Cleanup reads DWM visibility and observes the
popup's absence for at least 750 ms. Independent replay rejected a reused HWND
on a different thread. A popup already hidden by Explorer and an effective
invocation followed by a COM error each caused zero additional invocations.
Seven PowerShell controls also passed. The corrected path is included in the
[native Windows run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708).

At `1e58541` all four integrated shell-less cases passed. On the original
x64 desktop all three GUI trials registered version 4 and removed their
icons at exit. Each rectangle pointed at the same screen pixel, RGB
`eeeeee`. The observer could not identify an eligible overflow provider
and issued no invocation. On ARM64 the original Explorer remained in place
and returned `E_FAIL` on all nine adds, including the application's two
scheduled retries per trial. It returned no icon rectangle. Neither host
produced an integrated Open callback. On the separate private x64 desktop,
registration succeeded after 49 ms, with the marker still unobserved.
[x64 integrated tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14796080786)
· [ARM64 integrated tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14796372328)
· [Original and retained launcher observations](rw02-instance.md#native-windows-launcher-at-1e58541).

Commit `1f26816` records each of the four named UI Automation queries
when the original Explorer has no eligible overflow button. It flushes the
query results before collecting a bounded, read-only sample at the hint
point. The observer still requires an identified button and the private
icon marker for an actual activation. The additional diagnostic has passed
its isolated PowerShell selection and point checks. A native result with
an actual provider remains open. Commit `00db89c` also records when the
element at that point changes owner during the query. [Original Explorer selection](../../tools/rust-qa/windows-launcher/tray_provider.ps1) · [Selection controls](../../tools/rust-qa/windows-launcher/test_chevron.ps1).

### Original and private Explorer at 6af7100

In run `45144662858`, the separate pointer fixture started an Explorer on
each owned input desktop. Both private taskbars were visible in session 2.
The x64 Explorer (PID 9016, taskbar thread 6932) and the ARM64 Explorer
(PID 9996, taskbar thread 1292) both declined the initial `NIM_ADD` and
one retry. The pre-retry waits were 3,036 ms on x64 and 3,168 ms on ARM64.
Both receivers logged raw last-error `0x80004005`, and both independent rectangle
queries returned that HRESULT with empty bounds.
The fixtures issued no pointer input. Both confirmed an empty Explorer job,
removed the temporary directory and restored the original `Default` desktop.
[x64 private Shell receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14804447428)
· [ARM64 private Shell receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14803804924).

On the original x64 desktop, Explorer PID 6152 owned taskbar HWND 393238,
thread 7816. It acknowledged the canonical GUI's version-4 icon at receiver
HWND 328188, ID 23. The GUI reported its marker as `39cc65` in screen
rectangle `[790,720,822,768]`. At the center, `[806,744]`, the observer
read `eeeeee` on child HWND 131208. Each of the four exact overflow-button
name queries returned zero matches. A separate UI Automation hit at that
point returned the taskbar root itself. The helper opened no flyout and
issued no invocation. The cursor remained at `[512,384]`. The GUI deleted
the icon at Quit, and the observer confirmed that the receiver and icon
rectangle were gone and the job was empty.
[x64 integrated GUI receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14803949483).

On the original ARM64 desktop, Explorer PID 7652 retained taskbar HWND
65846, thread 2240. The canonical GUI's initial add and two automatic retries
all returned false with raw last-error `0x80004005`. The independent observer
still held the same live Explorer at 3,124 and 9,170 ms and obtained no icon
rectangle. The GUI drained and its process job emptied. The separate GUI
scenarios on private desktops without a Shell passed on both architectures.
All 19 observer input hashes in each canonical archive matched the source
revision with Windows checkout line endings.
[ARM64 integrated GUI receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14804324249).

The retained GUI also tested hidden startup and reopening after a close.
On x64 both version-4 registrations returned the same taskbar rectangle.
Both independent observers read `eeeeee`, found zero matches for all four
overflow-button names and recorded no icon invocation. The GUI deleted
both registrations at Quit. On ARM64, both initial registrations and their
four retries failed. All four GUI processes drained, and both private
shell-less scenarios passed. The archived logs and 34 distinct source hashes
per architecture matched during independent readback. The combined launcher
and Shell readback SHA-256 is
`711da3aa0f4dd89519a34f3cb9de8c98f6600ab8e54b99ee97adb73807cbdf85`.
[x64 retained GUI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14806170882) · [ARM64 retained GUI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14805618878).

### Native notification-area menu

The Rust tray receiver uses the version 4 `WM_CONTEXTMENU` callback for its
own icon to open the standard Windows popup. Its three commands follow the
installed WPF application's order and German or English labels. Open uses
the elected GUI. Restart drains the current inventory worker before the
replacement starts. Quit requests shutdown through the GUI supervisor.
[WPF tray implementation](../../src/ImmichFolderWatch.App/Services/TrayIconHost.cs) ·
[Native menu](../../tools/rust-qa/gui/src/windows_tray_menu.rs).

The portable delivery tests cover a full command queue, command order and
both sets of labels. To establish desktop behavior, open the menu at the
verified Explorer icon for each selection, inspect the visible menu rows
and click their screen coordinates. Observe the original GUI window and
worker handles across all three selections. Keep the GUI's control pipe
open until it exits through Quit.
[Local Explorer test and replay](../../tools/rust-qa/windows-launcher/tray-menu.md) ·
[Delivery tests](../../tools/rust-qa/gui/tests/windows_tray.rs).

The local Server 2025 x64 console passed all three physical selections
with the original executable from `56b7ae8`. Open focused the original
editor, Restart replaced its worker after the first process exited, and
Quit drained both the GUI and its replacement worker. Explorer removed
the icon. The offline observer reproduced the results from the guest logs.
[Original process and window observations](../../tools/rust-qa/windows-launcher/tray-menu.md#local-server-2025-result-at-56b7ae8).

## Canonical GUI startup on the staged Windows desktop at 13e4af8

On x64 and ARM64 the ordinary launcher primary on Default, the launcher
primary on its private desktop and the integrated tray primary on its private
desktop each reported primary election, then exited with Windows sharing
violation 32. All six exited before creating the inventory worker or
reporting a window. Both integrated tray observers recorded an empty process
job but lacked their normal drain marker and skipped the input-desktop phase.
The two canonical launcher archives and both integrated tray archives matched
their Actions SHA-256 values, all fourteen indexed logs and their observer
sources. [x64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14965252875)
· [ARM64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14965748407)
· [x64 GUI tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14966021136)
· [ARM64 GUI tray](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14965378920).

The fixture held DELETE access to the staged executable directory while
the Rust supervisor opened that directory for reading with
`FILE_SHARE_READ | FILE_SHARE_WRITE`. Those sharing modes conflict.
The corrected fixture holds a read-only directory handle throughout the
trial and the two executable removals. It then opens an identity witness
that permits deletion, releases the running-phase handle and opens a
disposition handle. Both handles must match the original volume and file
ID. The fixture removes the empty directory and verifies its absence.
The native control first reproduces the original handles on a separate
empty directory and requires error 32 on the worker open. It then checks
that the same worker access succeeds in the corrected stage. After that
worker handle closes, a separate DELETE request must still fail against
the fixture's running-phase pin. The next native execution will verify
both observations. [Worker directory open](../../tools/rust-qa/gui/src/windows_worker.rs)
· [Launcher fixture](../../tools/rust-qa/windows-launcher/observe.py)
· [Native control](../../tools/rust-qa/windows-launcher/test_staged_images.py).

The retained-window launcher and tray observers used the same staging
helper at this revision. All six of their primary process logs also record
election followed by error 32. None reached inventory or activation.
Detached replay of both archives matched each observer source and indexed
log. Its SHA-256 is
`e30c504320b897a4ede58a0d7e8dad09fa17daeb3963f36345fabbc1c6b86ca7`.
[x64 retained archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14966273317) ·
[ARM64 retained archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14967851248).

### Corrected canonical Windows launcher at 4e3dbc4

On Default and the private desktop, both native architectures started their
worker. The observer verified the original directory identities and removed
the staged executables and directories after drain. On x64 the Default
primary retained worker PID 3572, reopened its window and obtained the
foreground. On ARM64 the Default primary retained worker PID 2616 and
reopened a visible window. All 41 foreground samples over 2.037 seconds
found it in the background. These canonical GUIs recreated their HWND on
reopen. The retained-window trial uses a separate executable.
[x64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14975080953) ·
[ARM64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14975106072).

The x64 primary also registered a v4 notification icon with the original
Explorer. Its rectangle was `[790,720,822,768]`. On the original taskbar,
the last read at its center was RGB `eeeeee`. The expected marker was
`1fc653`. The observer obtained neither the marker nor a visible
hidden-icons button. It sent no activation. The Shell-less run kept its
worker and passed. [Original x64 tray archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14973991781).

On ARM64 the Default receiver was created by PID 9436. Explorer declined
the icon add and v4 registration. The independent rectangle query returned
`E_FAIL`. The receiver exited, its job drained, and the Shell-less run
retained its own worker. This host supplied no icon to activate.
[Original ARM64 tray archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14974376768).

The retained variant kept its original HWND and worker across the ordinary
second launch on both architectures. On x64 the first independent sample
found HWND 2359632 visible, foreground, active and focused. Worker 2948
stayed with primary 5684. On ARM64 Windows declined the foreground
request after the secondary granted permission. HWND 2097612 was visible
and retained worker 1696, but none of 41 samples over 2.021 seconds found
foreground. The last focus sample found an active window without focus.
Both private-desktop restart controls passed. Neither architecture
demonstrated a retained-window Shell click.
[Retained x64 observations](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14975353233) ·
[Retained ARM64 observations](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14976386454).

The follow-up observer at `236c852` samples up to 16 by 16 points inside that same
rectangle when the center misses the first marker. Each eligible point
must still lie on the original Explorer surface and monitor. The report
contains counts, the bounds of matching sample points and the number of
adjacent two-by-two matching squares. Positions on another window or
without a valid read are counted separately. The raster is a passive
observation. The original two-color and provider checks still govern
activation. The native `4e3dbc4` result contains the earlier center observations.

### Sampling the Explorer tray rectangle at 989bb33

On x64 the original Explorer registered the canonical Rust icon and returned
`[790,720,822,768]` for it. The center was RGB `eeeeee`. The independent
observer read 256 points in a 16 × 16 grid on the same monitored Explorer
surface. All reads succeeded. None matched the icon's `33c733` marker.
UI Automation also found no identified hidden-icons button or matching item
at the center. The observer sent no activation input. Worker 5668 survived
until Quit, the receiver removed its icon and the test profile was cleaned up.
[Original x64 tray archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14981286389).

On ARM64 Explorer declined the initial add and two registration retries.
The rectangle lookup returned `E_FAIL`. With no rectangle to sample, the
observer finished after confirming receiver shutdown and job cleanup.
The ordinary launcher still reopened the canonical GUI and retained worker
10400. Its visible window stayed in the background for all 40 samples
over 2.008 seconds. The ordinary x64 launcher retained worker 8528 and
obtained foreground on its first sample.
[Original ARM64 tray archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14980322661) ·
[ARM64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14981825678) · [x64 launcher](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14979924686).

The producer control at `bfe10f5` checks an earlier point in delivery.
It draws the actual HICON returned by the shared Rust implementation into a
private bitmap, using each of the two archived x64 marker colors at 32 × 32
and the native small-icon size. It keeps the complete pixels from black and
white backgrounds. Independent readback checks the interior RGB, transparent
source corners and confirmed handle cleanup. The native service archive
retains the output in `tray-image.txt` and its result in `trayImage`.
Real Shell registrations and clicks have their own outcomes. The producer
control passed cross-compilation checks and awaits native execution.
[Native HICON control](../../tools/rust-qa/windows-services/src/tray_image_test.rs) · [Recorder and pixel verification](../../tools/rust-qa/windows-services/run.py) · [Windows icon drawing](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-drawiconex).

In the late notification trial on that revision, each Windows host again
posted the ordinary and quiet WinRT notices, read their exact contents
and verified selective removal. The classic x64 icon received one show
and two timeout callbacks. None of 87 Shell observations saw the required
title and body on screen. On ARM64 registration failed, and none of 117
observations found that pair. The timed WinRT popup observer first runs
in the following desktop matrix.
[x64 WinRT](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14987305015) · [ARM64 WinRT](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14984226649) · [x64 Shell](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14986431031) · [ARM64 Shell](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14984431074).

### Native icon pixels and WinRT popup at f155b65

On both Windows architectures the bitmap control drew both archived marker colors
from the real HICONs on black and white backgrounds. All 484 checked
interior pixels at 32 × 32 and all 64 at 16 × 16 matched each marker.
The original corners were transparent and both icons were destroyed.
On ARM64 Explorer declined registration for the canonical and retained GUI icons.
[x64 icon and desktop archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14991846627) ·
[ARM64 icon and desktop archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14990910738) ·
[Retained Shell trials](rw02-instance.md#native-staged-image-readback-at-f155b65).

The ordinary ARM64 WinRT send returned `S_OK` in 5.91 ms. The popup
observer made 92 sweeps on the original desktop, continued after the
send, and encountered no provider error. No sweep attributed a visible
title and body to the test notification. The independent history reader
found both exact entries, removed each selectively and verified empty
history twice. The classic Shell trial made 110 observations after
Explorer declined registration. [ARM64 WinRT and popup](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14989564512) · [ARM64 classic Shell](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14990122838).

On x64 the ordinary WinRT notifier reported enabled on its first query.
Its single send returned `S_OK` in 3.06 ms. Over the ten-second
observation window the independent reader made 82 sweeps and encountered
no provider errors. None showed the test title and body together. The
history reader found both entries and verified selective removal through
an empty history. In the separate classic Shell trial, Explorer accepted
registration and returned a show callback. The 86 independent observations
found no matching visible title and body.
[x64 WinRT and popup](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14991333500) · [x64 classic Shell](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14991363312).

### Native notification observations at 5efe1f1

Windows again stored both WinRT notices in the test app's
history and accepted their selective removal on both architectures. The
ordinary send returned `S_OK` in 2.44 ms on x64 and 6.36 ms on ARM64.
Across 84 x64 and 92 ARM64 sweeps the independent popup reader found
no matching visible pair and recorded no provider errors. Each observation
continued for ten seconds after the send. The separate x64 classic Shell
trial received a show callback. Its 91 sweeps found no visible pair.
ARM64 Explorer refused the classic registration.
[x64 WinRT](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14997780160) · [ARM64 WinRT](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996411832) · [x64 classic Shell](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996548148) · [ARM64 classic Shell](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14997195340).

### Comparing marker colors across the original x64 taskbar

In the x64 retained-window trial, Explorer can acknowledge the native icon
and return a rectangle whose pixels do not contain the marker. The normal
activation trial first looks for that marker and an identifiable Shell
provider. If the close/reopen case finds neither the expected marker nor a
verified hidden-icons button, the observer compares a grid across the same
visible taskbar. It samples up to 1,536 points twice before and twice after
the original receiver successfully changes its HICON to the complementary
color through `NIM_MODIFY`.

Each counted transition must have the original and complementary colors at
the same physical point in both observations of each phase. All four reads
must resolve to the same Explorer-owned window. The observer retains counts,
coordinate bounds and timings. A transition outside the supplied rectangle
can locate the marker for further investigation. Activation still requires
the accessible item, its callback and the reopened original window with its
worker. A run with no eligible provider records activation as unavailable.
[Native observer](../../tools/rust-qa/windows-launcher/native_tray.py) ·
[Shell sampling](../../tools/rust-qa/windows-launcher/tray_provider.ps1).

The Server 2022 x64 comparison runs the same source-built observer, retained
GUI and inventory worker on another standard hosted Windows image. It
records the OS build, runner image version and Explorer version, along
with the original process and window evidence. The contrast trial on this
host retains its existing named-scheme requirement before changing the
palette. The regular Server 2025 and Windows 11 ARM64 trials continue to
measure their own desktops.
[Server 2022 comparison](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-shell-2022.yaml) ·
[GitHub runner images](https://github.com/actions/runner-images) ·
[Contrast observation](rw02-appearance.md#windows-contrast-baseline-and-restoration-at-f155b65).

### Visible background-start icon on Windows Server 2022 at 47fe26d

On hosted image `win22/20261123.376.1` (Explorer 10.0.20348.1), the
background-start Rust primary registered icon 23 with version 4. Explorer
returned the physical rectangle (835, 728)–(859, 768). The observer saw
`33ca56` at (847, 748), then `cc35a9` at the same point after the original
receiver acknowledged its HICON change. The Explorer process (6236), child
window (65770) and taskbar (524458) matched across observations. This
confirms visible rendering of the registered Rust icon on this x64 desktop.
The accessibility lookup found zero eligible items at that point. The
observer issued no invocation. The primary recorded no Shell activation
callback. Its original worker completed four inventories and exited cleanly.

In the separate ordinary-close trial, the original HWND 262596 was still
present and hidden. Explorer returned `S_FALSE` for the subsequent
rectangle query. The worker completed two inventories, and both trial
icons were removed on shutdown. The contrast observer captured the
original field twice. Windows returned an unnamed current scheme, so the
reversible palette change remains untested on this desktop.

The original ZIP (SHA-256
`e6b7fef62d424255b5635a37815ef76b13fec7731ee162f3faef694e27e98401`)
contains both native executables, the retained source archive and compiler
receipt. Its upload glob missed the eframe and winit library and metadata
files. The workflow at `bfc6408` reads all four paths from that receipt and
checks their hashes before upload. A native archive with those files is pending.
[Original observations and builds](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46025437427/artifacts/15212996332) ·
[Windows Shell run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46025437427).

### Identifying a classic notification toolbar button

The retained x64 GUI observer tries Microsoft Active Accessibility when UI
Automation finds zero visible items with the per-run name on the original
taskbar. It requires both observed icon colors, the original Explorer
process and toolbar HWND, and a single visible, enabled push button with
the exact name and a default action. Both the physical-point lookup and the
toolbar's own hit test must identify that button inside the registered
icon rectangle. An overflow pane or a changed hit ends this route.

Immediately before invoking the default action, the helper checks the
button and samples the marker again. The primary must then receive its
matching native Shell callback and show the window while its original
worker stays alive. The observer records the method and invocation time.
[Observer](../../tools/rust-qa/windows-launcher/native_tray.py) ·
[Classic toolbar adapter](../../tools/rust-qa/windows-launcher/tray_msaa.cs) ·
[Microsoft physical-point lookup](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfrompoint) ·
[Microsoft toolbar accessibility](https://learn.microsoft.com/en-us/windows/win32/winauto/toolbar-control).

### Explorer activation after a hidden start at 3c4d62c

On Windows Server 2022 x64, the retained GUI started in the background
and registered icon 23. Explorer PID 5572 painted its two marker colors
at (847, 748) inside rectangle (835, 728)–(859, 768). The accessibility
point lookup, toolbar hit test and enumeration identified button 1 on
toolbar HWND 65758. Its default action started at system tick 941906.
At tick 941921 the original Rust receiver handled one `NIN_KEYSELECT`
for icon 23 and issued one GUI Open. On the first observation, the shown
window (HWND 197214) was active, in the foreground and had keyboard focus.
Worker PID 7208 retained its original creation time. The GUI then quit,
drained the job and removed the icon.

In the separate run starting visibly, the parent received `S_FALSE` for the
icon's rectangle before the close. After the original HWND 459254 was hidden,
the repeated rectangle check still received `S_FALSE`. No eligible overflow
button was found. Opening the original window from this state remains open.
The Shell-less control passed. The contrast trial again captured the baseline
on a desktop with an unnamed scheme.

The archive (SHA-256
`2cd53333ceca88c032b9a43b043972f178ac9bb15043f342fa95c506a13d9834`)
contains the four original eframe and winit library and metadata files.
Their paths and hashes match the native compiler stream and receipts. The
retained executable has SHA-256
`b7d57b79d45466863a9923612277a2bab4b4dab86c130fbe5ad4adf504bb607e`.
[Original observations and native compiler outputs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46029732858/artifacts/15214951547).

In both background-first runs the independent rectangle query for the
visible-start GUI had already returned `S_FALSE` at registration, before
the first window close. Both runs started it second on the same Explorer.
The dedicated Server 2022 comparison now starts the visible-close trial
first after the Shell-less control. It records the planned and executed
case order, the original handles and cleanup before starting the next GUI.
[Native case order](../../tools/rust-qa/windows-launcher/native_tray.py) ·
[Server 2022 comparison](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-shell-2022.yaml).

### Visible start first on Windows Server 2022 at f148e30

On a fresh original Explorer the visible-start GUI ran first. After the
user-window close, Explorer supplied the registered icon rectangle
(835, 728)–(859, 768). Activating the visible icon reached the original
GUI (PID 4620) and the original worker (PID 5276) survived the reopen.
The callback and the native window SHOW fell within the same Windows timer
tick. The observer could not establish their order. In the second,
background-start case, Explorer returned `S_FALSE` for the icon rectangle
and exposed no eligible overflow provider. Both cases cleaned up. The
earlier background-first run qualified that startup on its own desktop.
[Original visible-first archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46033236196/artifacts/15215852607).

The repeat observes the original window on its own UI thread when it
consumes that specific Shell Open. Before calling its normal activation
handler the GUI records its HWND, PID, thread, callback ordinal and native
visibility. A tied timestamp qualifies only if the root was still hidden
at that point and the independent WinEvent stream then shows exactly one
matching root SHOW.
[Native launcher](../../tools/rust-qa/windows-launcher/native_tray.py) ·
[Offscreen editor comparison](../../tools/rust-qa/windows-cpu-paint/headless/README.md).

### Explorer reopened the original closed window at 29ce1c0

On Windows Server 2022 x64, Explorer displayed both marker colors on the
first GUI's icon. Its accessibility default action delivered `NIN_KEYSELECT`
for icon 23 to receiver HWND 524654 in PID 5944. The GUI thread (6564)
consumed callback 1 while its original root HWND 458906 was still hidden.
The independent root SHOW was at the same native tick, 1489328. The first
focus sample found the reopened window active, foreground and focused.
Worker PID 5156 and its creation time matched before and after. Quit
removed the icon, drained nine inventory passes and left the job empty.

For the second GUI, which started hidden, Explorer returned `S_FALSE` for
its icon rectangle and exposed no eligible overflow provider. This case
ended without a callback. The hidden-start case passed when run first at
`3c4d62c`. In the paired runs both processes registered version 4 and
successfully removed their own HWND/icon ID on Quit. The Rust registration
log reports the result of the add/version calls. For rectangle availability,
the independent observer preserves the Shell's exact HRESULT, including
`S_FALSE`. The icon's location in the second case remains unknown.
The contrast observer recorded an unnamed original scheme and
made no change. The archive SHA-256 is
`c3bd6532972befc11294b0fa907fa2fd486ddc291b7b9052e87981ea743de714`.
[Original Windows desktop and GUI logs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46037576951/artifacts/15219980415).

### Ordinary launch when the registered icon has no rectangle

The second, hidden GUI on the desktop at `29ce1c0` exited at Quit before
any ordinary second launch. The launcher observer now starts the same
executable with no arguments while that original primary is still running.
It requires the original receiver and an independent `S_FALSE` readback
immediately before the second process resumes. It observes the primary's
window SHOW, the secondary's IPC request and exit, and the original
worker through normal Quit. For an initially visible GUI it requires
the same HWND that was closed. For an initially hidden GUI it observes
the primary's first window. The observer compares the original SHOW
timestamp with the second process's release and samples actual foreground,
active window and keyboard focus. A delayed hook event alone cannot
establish that the launch opened the window. The ordinary launch is
recorded separately from Shell activation.
[Launcher observer](../../tools/rust-qa/windows-launcher/native_tray.py).

At `3d55500` the background-start primary (PID 7928) had no usable icon
rectangle on the original Windows Server 2022 x64 desktop. A second launch
of the same executable (PID 3136) sent the ordinary IPC request and exited
zero. Windows reported the primary's first window (HWND 720948) shown
171 ms after the observer released the second process. The first sample
found foreground, active window and keyboard focus on the primary. The
original inventory worker (PID 5924, same creation time) survived until Quit.

The visible-start case on that host obtained a usable icon rectangle and
received a Shell callback. Its provider call and callback had the same
Windows tick, so that trial did not establish their order. The contrast
baseline remained unnamed. The job finished with a failure. The workflow
now defaults to starting the background GUI first; the dispatch input can
also select the visible-first order. This exercises the ordinary launch
against a previously closed window if Explorer again gives its second GUI
no usable icon rectangle.
[Original executables, observations and compiler records](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46043105453/artifacts/15222710202) ·
[Native start-order selection](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-shell-2022.yaml).

At `db1f126` the background-start case ran first on Windows Server 2022
x64. Its accessibility action and callback shared a Windows tick, so
their order remains unresolved. The second GUI started visible and closed
to the tray. Immediately before its ordinary second launch, the Shell
returned `S_FALSE` for the icon rectangle. Windows showed the original
hidden HWND 458882 at uptime 949750 ms, 16 ms after the observer released
the secondary process. The first focus sample found the original window
foreground, active and focused. The secondary exited zero and the same
inventory worker (PID 980 and identical creation time) continued through
the reopen. The ordinary-launch checks have now passed for both initial
window states across the two desktops. The Shell activation check on
this run remained unavailable. The original ZIP has SHA-256
`65274e9dd39e14bc8b3350aa8f02b8913e7b51886584ccd11979598b607091c7`.
[Native background-first run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46045729761).

The provider now records its performance counter immediately before and
after the accessibility action. The receiver records the same Windows
counter when it handles the matching callback. The observer compares the
two start and dispatch samples even when Windows reports the same uptime
millisecond. It requires more than one counter tick between the samples,
checks the provider's counter frequency against the observer's and keeps
the original message-queue bounds for queued callbacks. A posted message
with an indistinguishable queue time still has an unresolved order.
[Windows performance-counter ordering](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps).

### Retained Explorer activation on the local Windows x64 VM

The [tray compiler](../../.github/workflows/rust-windows-x64-tray-build.yaml)
packages the canonical and retained GUI, both retained library units and
their compiler stream, plus the matching inventory worker. Copy the original
`rust-tray-windows-x64-<revision>` ZIP and its Actions SHA-256 to the
disposable Server 2025 x64 guest. Use a checkout with the recorded compiler
sources and an empty output directory location. On the active, unlocked
console, run this command as the dedicated standard user.

```powershell
python -B tools/rust-qa/windows-launcher/native_tray.py x86_64-pc-windows-msvc --subject retained --reopen-first --local-archive D:\tray.zip --archive-sha256 $digest
```

The observer authenticates the local host, account, console and hypervisor.
It verifies the archive digest before reading either executable, replays
the compiler records for the application and both libraries, verifies the
source and graph checksums, and stages the GUI and worker in each new
token-owned profile. After the private desktop control, it measures first
the visible start and close, then the background start. Preserve the
original logs and `result.json` under
`artifacts/rust/windows-gui-tray-retained/x86_64-pc-windows-msvc/`.
Each Shell result reports its own provider, callback, window and worker
observations, including any ordinary-launch fallback.

#### Both Explorer starts on Windows Server 2025

The local Server 2025 x64 console ran the retained GUI and inventory worker
from `87491b0` as the standard user in session 1. The original Actions ZIP
has SHA-256 `156bbb1a6af1a41ca4edc9c002ba7f79ad89bc142953f4b4579de5eae60b7aeb`.
Observer `aa403da` opened Explorer's hidden-icons flyout through its taskbar
button. At pixel (1283, 815), UI Automation returned the flyout root.
Explorer exposed one enabled child button bearing the GUI's exact
token-specific name. Its bounds matched the icon rectangle, and its runtime
ID differed from the root's. In each trial, the sampled pixel changed to
the requested complementary color before the observer invoked that child.
[Original compiler archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46102133752/artifacts/15246502882).

| Start and Shell action | GUI PID | Visible root HWND | Worker PID | Sampled RGB sequence | Invoke to callback |
| --- | ---: | ---: | ---: | --- | ---: |
| Visible start, close, then reopen through Explorer | 4544 | 262520 | 3152 | `20e033` → `df1fcc` | 2.7646 ms |
| Background start, then first show through Explorer | 5100 | 327704 | 656 | `4cc963` → `b3369c` | 4.5330 ms |

Both registered receivers delivered one `NIN_SELECT` for icon 23 before
the Explorer invocation returned. The first GUI thread recorded the original
HWND as hidden during the callback. Its next root SHOW reopened that HWND.
The background process created its first editor root after the callback.
Both windows acquired keyboard focus and foreground ownership. Each worker
kept its original PID and creation time. Ordinary Quit removed each icon,
and both process jobs drained. Explorer's flyout returned to its original
closed state for 774 ms and 759 ms respectively, with the pointer restored.
The separate private-desktop control recorded a failed icon registration
and a successful ordinary second launch of the same retained window.

The private results are under
`artifacts/rust/local-windows-server-2025-x64/20261128/tray-87491b0/attempt-3/`.
The guest ZIP has SHA-256
`2fc908ef58c61a39a8e192d50fc2ef8c4f33000a32c42956aa610faa406d37b3`.
The independent host replay checked the 42 compiler-manifest entries, ten
observer sources and ten guest files, then reconstructed both activations
from the provider records, GUI logs and native window and job samples.

## Shipping WPF tray lookup

The shipping WPF application creates a message-only window named
`ImmichFolderWatchTrayReceiver` and registers numeric icon ID 1. Its registration
uses the window and ID. After each WPF idle trial has finished timing and
stopped its ETW trace, the observer searches only the message-only windows
with that name. It requires a unique receiver owned by the original live WPF
process, queries its Shell rectangle with a zero GUID and checks the receiver,
thread and process again. The raw HRESULT, rectangle and both QPC ticks appear
in `trials.wpf[].controls.shippingTrayLookup` in the Windows performance report.
[Shipping receiver](../../src/ImmichFolderWatch.App/Services/TrayIconHost.cs) · [Observer](../../tools/rust-qa/windows-performance/native.py) · [Window lookup](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-findwindowexw) · [Shell identifier](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-notifyiconidentifier).

This comparison asks whether the Shell on the original desktop of the same
hosted runner can locate the shipping application's icon. A stable receiver,
`S_OK` and a positive-area
rectangle establish that result. The Shell add return value belongs to the
WPF process and the source records no return receipt. Visible presentation,
pointer activation and focus each require their own observations.
[Rectangle result](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shell_notifyicongetrect).

Across the same two runs, the shipping WPF receiver returned a visible-area
Shell rectangle on all six x64 idle trials. All six ARM64 trials found the
WPF receiver but returned `E_FAIL` for its icon rectangle.
[Same-host renderer and Shell results](rw02-windows-window.md#visible-gdi-and-retained-egui-under-the-same-inventory).

### Visible WinRT banner on the local Windows Server 2025 x64 console

The native sender built at `672d896` ran in console session 1 as the
non-elevated `ifw-test` account on Windows Server 2025 Standard Evaluation.
With Windows' **Do not disturb** switch on, both sends returned `S_OK` and
both history entries could be read and removed. Seventy-eight Shell sampling
sweeps found no banner. Windows Settings reported notifications enabled.
After switching Do not disturb off in that same account, the normal banner
appeared with both complete texts. A first full-screen capture showed the
unique token `094d5024f02a4a328817fa883f5a4219`. The Shell state still
reported `QUNS_QUIET_TIME` during this visible send.

In a fresh repeat with Shell state `QUNS_ACCEPTS_NOTIFICATIONS`, the original
sender (PID 6732) issued its successful ordinary `Show` with
`SuppressPopup=false`. The physical observer sampled the visible banner
133.007 ms after that call returned. Both label centers identified HWND
131386 in `Windows.UI.Core.CoreWindow`, owned by the session's
`ShellExperienceHost.exe` (PID 4148). UI Automation on that HWND returned
the full title and body in two distinct on-screen rectangles. The screen
crop shows both strings with token `4353d463f95f49a0ad72c56f53c7176d`.
Its SHA-256 is `25b077015215c6ec99728ebcda7fb1d3a850e70665705eec4940c9cb218eb64f`.
Independent reads verified selective removal and an empty history. The
standard account's original Do not disturb setting was restored.

The original generic UIA sampler reported no visible match on these desktops.
In the diagnostic repeat, UIA's global point query returned the background
Terminal while Win32 hit testing returned the Shell toast HWND at the same
pixel. The [local physical observer](../../tools/rust-qa/windows-services/toast_console.ps1)
queries that HWND directly and captures its label rectangles from the screen.
The result pertains to x64 on this native Server 2025 console. Windows ARM64
presentation has its own evidence requirement.

To reproduce with this archived sender, use a fresh checkout of `672d896`
for `toast_history.py` and the local physical observer from a separate
checkout. Start the following in two ordinary x64 shells in the same test
account. Set `$native` to the sender checkout's future
`artifacts/rust/windows-services/toast-history-x86_64-pc-windows-msvc`
directory and `$frames` to a fresh path. Keep Do not disturb off for the
capture, then restore the test account's previous setting.

```powershell
# Start the point observer before starting the sender.
.\tools\rust-qa\windows-services\toast_console.ps1 -IsolatedVm -NativeDirectory $native -OutputDirectory $frames
# Run from the original sender checkout in the second shell.
python -B tools/rust-qa/windows-services/toast_history.py x86_64-pc-windows-msvc --isolated-vm $senderZip --archive-sha256 37ca6c25cb623f638c1f53640627a8edfffecad3d99a15cfe66d44ff6c62f7ff
# Replay from the physical observer checkout after both have exited.
python -B tools/rust-qa/windows-services/toast_console.py $native $frames
```

The immutable compiler ZIP is [artifact 15229643760](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46063786416/artifacts/15229643760).
The local original ZIP, Actions digest, receipt, sender logs, screenshots,
physical observations, replay and setting readbacks are retained under
`artifacts/rust/local-windows-server-2025-x64/20261127/toast/`.

## Keyboard activation of the visible Windows ARM64 Quit button

The native ARM64 observer has a separate keyboard case for the visible
fallback after Explorer declines the tray icon. It starts a fresh canonical
GUI and worker and waits for two scans. UI Automation sets the initial focus
on the owned filename field. Three native Tab presses must then move focus
through `Kennwort`, `English` and `Beenden` on the same HWND. The observer
checks the actual focused UIA element, native foreground and keyboard owner
before each gesture. It sends one Space press on the identified button.
The record includes the four runtime IDs and input counts. It reads no
password contents. The command pipe stays open while both processes exit.
[Keyboard observer](../../tools/rust-qa/windows-launcher/window-quit-keys.ps1) · [Native key events](../../tools/rust-qa/windows-reader/Keyboard.cs).

Run `python -B tools/rust-qa/windows-launcher/window_quit.py --keyboard`
in the native ARM64 display job after building the canonical input pair.
The resulting `windows-quit-keyboard-private/` directory contains the
button evidence, GUI log, worker and desktop receipts. The supervisor
checks the staged profile cleanup and return to the original unlocked
console. The separate `windows-quit-private/` trial retains the UIA
invocation evidence.

The first ARM64 attempt at `82b8530` compiled both GUI executables.
Worker staging stopped before the keyboard step. The shared review had
accepted the optional YAML `localization.language` field at `f2202ee`,
but the Windows staging script still required the previous worker entry
hash. The job skipped all runtime steps and uploaded zero artifacts.
The original job log has SHA-256
`a3a11024a9d430e7fc1bc0cf624dcc88188cd2c38d222b9b05768f099f66c667`.
[Original ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46136008198/job/140951347865)

Windows staging now verifies each of the three original worker files
against the [shared review](../../tools/rust-qa/performance/worker-inputs.json).
The reconstructed Windows entry has SHA-256
`f7af44c8f26c5f753bfcf387605ad977f7a8bdb6be9ea0516d8c7f13f9a133ca`.
Removing the 313 bytes added at `f2202ee` reproduces the compiled-source
digest `35a0153c419e3b12a8a0e1b5cc0a4ccc5168dc97f991a78eee36f66cbc891be3`
from the earlier native `07c0d70` archive. The local staging test also
checks rejection of a missing or changed digest for each file.

Windows 11 ARM64 at `e610d61` passed the keyboard trial. After the Shell
refused initial tray registration, the original inventory worker (PID 4852)
read the synthetic file twice. Three Tab presses moved focus through
`Dateiname`, protected `Kennwort`, `English` and `Beenden`. All four
controls had distinct UI Automation runtime IDs and belonged to GUI PID
7972. At each step HWND 1048672 held the native foreground and keyboard
focus. The last focused ID matched the visible 70 × 22 Quit button.
Windows accepted the down and up events for Space. The worker exited
with reason `quit`, the control reader stopped and the GUI exited zero
after 23 passes. The supervisor removed the profile, closed its job and
returned to the original unlocked `Default` desktop in console session 2.
[Native ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46137194724/job/140955014110)

The same job independently passed the UI Automation invocation on GUI PID
2088 and HWND 524786. The two source-monitor edit steps on the default
desktop failed, giving the overall job a failure status. The original
43,277,752-byte archive matched Actions SHA-256
`f1327dad22ee9e53070ebe6786809b7fb6c92fa510fc32faa062a88f9f08f021`.
The local replay checked the six keyboard observer files against the
revision, all 47 files in the compiler pair receipt, all 18 worker source
files, both ARM64 PE images, both button records and their shutdown logs.
[Original artifact 15261255202](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46137194724/artifacts/15261255202)
[ARM64 workflow](../../.github/workflows/rust-windows-arm64-display.yaml).

At `446fc1f` the integrated ordinary editor repeated the private keyboard
trial on Windows ARM64. Its native PE and all 30 compiler-source entries
matched the archived receipt for the new GUI lock. Three Tab presses
again focused the password, language and Quit controls. The Space key
completed Quit. The supervisor recorded a verified session, successful
worker exit, closed job and return to the original desktop. The separate
source-monitor steps on the default desktop failed.
[Original ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46138706469/artifacts/15261487514).
