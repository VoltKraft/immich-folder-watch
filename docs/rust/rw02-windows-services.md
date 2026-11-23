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
