# Windows notification history trial

Run the x64 trial on the [local VM with the archived sender](#original-sender-on-a-disposable-windows-x64-vm). On the native ARM64 rewrite runner the recorder uses the existing Rust executable from the same job and checks its source, native compiler, test results, dependencies and PE import table before it uses the desktop.

```powershell
python -B tools/rust-qa/windows-services/toast_console.py --observe-arm64
```

A fresh UUID identifies one synthetic app. The recorder creates a new private folder under the current user's Programs known folder. Its single shortcut targets the probe and carries the app's AUMID and a unique stub CLSID. Each subsequent process opens the installed shortcut and verifies its executable, arguments and both properties. Windows documents this mode for unpackaged apps with a protocol-type toast. The trial uses a unique inert protocol URI and requests no activation. Each toast is silent, disables mirroring and expires after five minutes. [Microsoft's shortcut instructions](https://learn.microsoft.com/en-us/windows/win32/shell/enable-desktop-toast-with-appusermodelid) · [Microsoft's unpackaged desktop activation options](https://github.com/MicrosoftDocs/windows-dev-docs/blob/2e559c1c7064af00d993650b1eb2f380a7153c94/hub/apps/design/shell/tiles-and-notifications/toast-desktop-apps.md#alternative-option---no-com--stub-clsid)

Each sender records its session, token elevation, setting query and the HRESULT of any `Show` call. One request sets `SuppressPopup`; the other allows normal presentation under Windows settings. Separate processes read the app's history through `GetHistoryWithId` and compare the actual tags, group, titles and bodies. A successful run finds both messages, removes the normal tag while the quiet tag survives, removes the quiet tag and reads an empty history. The recorder holds its runner directories and shortcut during the trial and checks removal of the synthetic profile and Start Menu folder. [Popup setting](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotification.suppresspopup) · [History lookup](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotificationhistory.gethistory?view=winrt-26100) · [Exact removal](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotificationhistory.remove)

The stand-alone service keeps its lockfile and all 15 exact registry archives. The `windows 0.62.2` feature change adds XML DOM and notification interfaces, WinRT apartment initialization, the Shell property store, typed property keys and PROPVARIANT support. Both target graphs were checked against the complete unpacked inputs. Their archive contents have 31 license and attribution files and contain no native binaries or fonts. The selected licenses are MIT and the additional Unicode-3.0 terms for `unicode-ident`. The native calls use the Windows Shell, COM, property system, token query and WinRT system interfaces. Each native run records the complete import table in `pe-imports.json`. [Exact archive, notice and feature-graph hashes](inputs.json) · [Microsoft Rust bindings](https://github.com/microsoft/windows-rs) · [Microsoft's original source archive](https://static.crates.io/crates/windows/windows-0.62.2.crate)

The result and raw per-process logs are under `artifacts/rust/windows-services/toast-history-<target>/`. Exit 0 records both independent history observations and exact cleanup. Exit 2 records an unavailable desktop or notification capability. Exit 1 records an invalid result, unexpected native error or unconfirmed cleanup. Banner visibility and user activation have separate desktop acceptance criteria. Detached replay verifies the complete captured import table against the original native build report, which identifies the executable by SHA-256. It also checks the original Windows desktop context and each process's session, operation and history-read phase. To replay the original positive result on any host, supply the downloaded evidence directory.

```sh
python3 -B tools/rust-qa/windows-services/toast_history.py x86_64-pc-windows-msvc --replay /path/to/evidence
```

## First notification on a fresh Windows ARM64 console

The [focused ARM64 workflow](../../../.github/workflows/rust-windows-arm64-notification.yaml)
builds the same source-bound sender on a fresh Windows 11 ARM64 runner.
It exercises the ordinary and suppressed notifications immediately after
the native Shell controls. The general desktop assessment also exercises
the sender later in its session. The fresh trial archives the compiler
and service receipt, the two notification histories and the physical
screen evidence together. Its last step requires independent confirmation
of both visible labels. When the point provider misses a label, the
original crop remains available for visual review.

The original console job queries both notification switches after the
sender exits. A second job uses its own fresh ARM64 runner. Before sending,
it opens Windows Settings and requires notifications to be on. If Do not
disturb is on, the fixture saves a run- and session-bound rollback record
to disk, switches Do not disturb off and verifies the new state. After the
sender, it restores the original setting and opens Settings once more for
an independent read. Each observation identifies and closes its own Settings
window. When Do not disturb is already off, the comparison records that
state before and after the sender.

Extract either complete archive into a separate directory. Supply its
sender directory and the corresponding policy to replay the console
identity, Settings script digest, original state and any restoration.

```powershell
python -B tools/rust-qa/windows-services/toast_console.py --check-policy permitted $historyDirectory
```

The earlier [ARM64 history at 3d55500](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46043105348/artifacts/15244648584)
contained both messages. The normal sender returned success from Show,
and selective removal ended with an empty history. Its point observer
made 93 samples across the Show call and the following ten seconds.
It saw two known Shell roots and recorded zero provider errors. Neither
label was visible to that observer. This archive predates the separate
physical screen observer.

At `6c4a364` the native ARM64 sender posted both messages and completed
selective removal. The physical observer stopped before process creation
because its launcher had received the ambient environment without the
fixture token or isolated-profile flag. Windows Settings subsequently
reported notifications on and Do not disturb on. The owned Settings
window closed. This run has no physical popup observation. The corrected
physical observer uses its own pinned marker and scratch directory, checks
them in PowerShell and records cleanup. [Original fresh-console receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103222352/artifacts/15246364381).

At `8474f1f` the native ARM64 physical observer started in session 2.
Windows PowerShell 5.1 could not resolve `Get-FileHash` before the
observer armed. The child exited, its process job drained and the private
profile was removed. The independent history replay confirmed both sends
and selective removal. Its 92 screen samples found neither label and
Settings again reported Do not disturb on. The physical observer now
uses the runtime SHA-256 implementation to hash its script and image.
[Original native process log and histories](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46104122444/artifacts/15247386025).

At `1fe4a36` the original ARM64 physical observer reached readiness
before the sender, sampled the console after Show and exited zero. It
found no matching popup. Its private job drained and its profile was
removed. The separate timed observer completed 92 samples. History replay
verified the normal and quiet messages and their selective removal.
In the sibling job, Windows PowerShell rejected the settings reader's
omitted by-reference argument before any toggle. The corrected default
supplies a reference and the regression test calls both parameter forms.
[Original console](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46105006703/artifacts/15247072856) ·
[Companion settings trial](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46105006703/artifacts/15247930467).

At `ee0bcd2` both fresh ARM64 consoles completed the settings and sender
checks. On the original console the master notification switch and Do not
disturb were on. On the comparison console the master stayed on. The
fixture observed Do not disturb on, switched it off before the sender,
read it back off after the sender, then restored it to on. A new Settings
window confirmed that restoration. The run, session and script hashes
matched the native sender receipts. The Shell reported state 6 when the
comparison started and again immediately before restoration.

Both normal and quiet sends appeared in the corresponding histories and
selective removal succeeded. Neither physical observer found the popup.
Both armed before their sender, exited zero and removed their private
profile. The independent timed observers made 92 and 93 samples
respectively. Visible ARM64 presentation remains open. Microsoft
identifies Shell state 6 as quiet time after first logon. On the local
x64 console a banner had been visible during that state.
[Original runner](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46105620407/artifacts/15246969338) ·
[Runner with verified restoration](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46105620407/artifacts/15247358753) ·
[Shell state definitions](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ne-shellapi-query_user_notification_state) ·
[Observed x64 banner](../../../docs/rust/rw02-windows-services.md#visible-winrt-banner-on-the-local-windows-server-2025-x64-console).

## Visible normal WinRT popup

On the hosted ARM64 desktop the command above starts a second, native
PowerShell observer before the original sender. It checks the ordinary
Shell popup at the notification corner and the visible CoreWindow
candidates on the same desktop. The expected title and body must appear
inside the Shell's normal toast view and have distinct physical hit
points on the original Shell HWND. The observer
captures the screen crop containing both labels.

The focused workflow retains the history and physical observations in one
archive per console. To verify a positive physical observation, extract
both directories from the same archive and run the command below. Replay checks the original sender's
Show interval, its run and revision, the observer's native process and
desktop, and the image digest. An empty history or an unobserved popup
leaves the corresponding native check open.

Replay reports `presentation=visible` when the independent timed UI
Automation point queries also found both labels on that same Shell window.
With `review-screen-crop`, inspect the archived PNG for both strings and the
sender's token before recording a presentation result. Another surface
inside the same native window can cover accessible text.

```powershell
python -B tools/rust-qa/windows-services/toast_console.py $historyDirectory $physicalDirectory
```

The normal sender records the native performance-counter frequency and the interval around its single synchronous `Show`. An independent UI Automation process on the runner's unlocked `WinSta0\Default` desktop starts before the normal sender. It first checks for the absence of the two fresh labels, then searches for the exact normal title and body through ten seconds after the sender returns. The quiet toast has different text and uses `SuppressPopup`. The observer supplies no input and leaves notification settings and the notification center alone.

The shared Shell observer verifies two distinct on-screen points, their UI Automation labels and the native window under each point. The match must belong to a same-user Shell process in the original console session. A popup observation also requires a common ancestor with the normal toast window's automation ID, `NormalToastView` or `Normal Toast View`, on a `Windows.UI.Core.CoreWindow` host. Replay checks the recorded ancestor path from the common label container. A visible label pair from an unrecognized Shell surface is retained as a diagnostic. A Windows version exposing a different popup identity leaves the banner outcome open. The popup criterion follows the original accessibility observation from the NVDA project. [Native toast window identification](https://github.com/nvaccess/nvda/issues/5136)

The numbered `*-normal-popup.json` file binds the normal sender's original PID and creation time to the observer process, active desktop and clock interval. The matching `.log` retains its baseline, timed sweeps and terminal result when the observer ran. A complete positive trace sets `presentationObserved` to true. `normalBanners` records unavailable or incomplete observations, and `historyStatus` records the independent native delivery and exact removal. The process journal still limits each tag to one `Show`. Detached replay uses the source list from the native build to identify earlier history-only archives.

Each sender checks its installed shortcut and records the HRESULT from
`CreateToastNotifierWithId` and, when creation succeeds, the HRESULT from
`ToastNotifier.Setting`. Each pair appears in order in the original log
and in the process record's `notifierReadiness` list. A newly registered
app can return `0x80070490` during either read-only call. Only that result
permits another query. Queries are spaced 500 ms apart and bounded by
eight seconds and seventeen starts. Each child retains its 25-second
process limit. An explicit disabled setting ends the sender. If the final
notifier was created successfully and its setting alone still returns
`0x80070490`, the sender records the elapsed wait and `setting=unavailable`.
It issues one `Show` on that same notifier, as it does for an observed
enabled setting. A failed final creation, access denial or other setting
error ends the attempt. Each sender that queried a notifier records its
`postResult.setting` and signed `postResult.showHresult`. A missing Show
has a null HRESULT. Independent history reads and exact removal determine
delivery. Microsoft's Win32 example uses the verified shortcut's AUMID and
calls `Show` directly. [Desktop toast quickstart](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/legacy/hh802768%28v%3Dvs.85%29) · [Setting return values](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotifier.setting?view=winrt-26100)

## Per-user display name comparison

The earlier sender ended its trial on the unavailable setting. Replay
retains that sender's original contract for historical positive results.
When both shortcut-only senders stopped on `ERROR_NOT_FOUND` from the
notification setting and an independent final reader found zero entries,
the observer attempted to add one volatile display-name value under
`HKCU\Software\Classes\AppUserModelId\IFW.RustQA.Toast.<token>`.
This follows the unpackaged desktop reference's display-name registration.
The comparison retained the same shortcut, stub CLSID, caller, executable
and tags. After reading the value from a separate handle, it ran both senders
and the independent history readers again. A disabled setting or access
refusal ended the original trial. The current sender uses the shortcut-only
exchange for the unavailable-setting case. Once a sender reaches `Show`,
the observer skips the display-name comparison even if the history stays
empty or Windows refuses the call. Each tag can reach `Show` at most once
across both runs. [Microsoft's unpackaged desktop registration example](https://github.com/WindowsNotifications/desktop-toasts/blob/master/CPP-WINRT/DesktopToastsCppWinRtApp/DesktopNotificationManagerCompat.cpp)

The recorder keeps the first exchange in `shortcutOnly` and records the
second exchange's process range in `display-name.json`. Before preparing
the shortcut it checks that the UUID leaf is absent from the per-user
registry. Creating the leaf also checks the native creation disposition
for a collision. On the disposable hosted runner, the observer opens
`HKCU\Software\Classes\AppUserModelId` with rights to read and create a
child. When the namespace is missing, it opens the current user's existing
`Software\Classes` and creates the single standard container with ordinary
registry lifetime. The receipt records whether Windows created it or
another caller supplied it first. Only the UUID leaf receives a value.
A newly created shared container remains in the disposable runner profile
until the VM is discarded. On exit the observer removes
its display name, deletes the empty UUID leaf by its original handle and
checks that the name is absent. The shortcut and synthetic profile
remain pinned throughout both exchanges.
[Registry creation and dispositions](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regcreatekeyexw) · [User-mode removal by handle](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-zwdeletekey).

## Original sender on a disposable Windows x64 VM

The former Server 2022 notification workflow uploaded `rust-native-toast-sender-<revision>`
after compiling the sender. Save the original ZIP and its Actions SHA-256 digest.
In a fresh Windows checkout of that revision, sign in on the disposable
VM's unlocked console with the standard test account. Run the following with
native x64 Python and Git from an ordinary, non-elevated shell.

```powershell
python -B tools/rust-qa/windows-services/toast_history.py x86_64-pc-windows-msvc --isolated-vm C:\QA\sender.zip --archive-sha256 $digest
```

The fixture verifies the archive, executable, compiler, dependency graph and
checkout bytes before posting. It uses the same native sender, scoped history
operations and timed Shell observer as the hosted test. The result in
`artifacts/rust/windows-services/toast-history-x86_64-pc-windows-msvc/` records
the VM observation separately from its compiler run. Replay the directory with
`--replay` and check `presentationObserved` for the visible banner.

## Ordinary notification after the ARM64 console accepts notifications

The [dedicated ARM64 trial](../../../.github/workflows/rust-windows-arm64-eligible-notification.yaml)
uses one fresh Windows 11 ARM64 console. A change to that workflow on
`rewrite/rust` or an explicit dispatch requests the longer test. The usual
fresh-console comparisons keep their 35-minute job limit.

The trial builds the original Rust sender, records both notification switches,
temporarily turns off Do not disturb if necessary, and closes its Settings
window. It checks the unlocked input desktop and calls
`SHQueryUserNotificationState` every 30 seconds for up to 65 minutes.
Each sample preserves the native HRESULT, returned state, performance
counters and elapsed time. Only a successful return of
`QUNS_ACCEPTS_NOTIFICATIONS` (5) releases the sender trial. It reads both
switches again and arms the physical observer before invoking the existing
history test. The restoration and independent Settings read also run when
the eligibility wait expires.

A separate read-only observer samples the same Shell API roughly every 25 ms
while the original sender runs. Offline replay finds the successful ordinary
WinRT `Show` in the native process log and compares its counter interval with
the raw queries. The complete queries immediately before and after the call
must each fall within 500 ms of it. Replay reports both measured gaps and
any overlapping queries. The archive retains the original executable, compiler
receipt, SHA-256 of the actual observer scripts, job and session identities,
and the source revision. The physical observer counts visits to visible
CoreWindows, verified Shell windows, completed toast-view queries and their
matches. Positive visibility still requires both synthetic labels on the
original physical Shell popup and the independent provider match.

For a downloaded archive, use the two original directories from that job.

```powershell
$target = 'aarch64-pc-windows-msvc'
python -B tools/rust-qa/windows-services/toast_eligibility.py --verify "toast-history-$target" "toast-physical-$target"
python -B tools/rust-qa/windows-services/toast_console.py --require-visible "toast-history-$target" "toast-physical-$target"
```

### Shell states over 65 minutes at 85936d4

On November 28, 2026, the fresh Windows 11 ARM64 console returned
`S_OK` in all 131 queries over 3,900.003 seconds. The first 99 samples
reported `QUNS_QUIET_TIME` (6). At 2,970.338 seconds, the state changed
to `QUNS_APP` (7) and stayed there for the remaining 32 samples.
Microsoft describes state 7 as a running Windows Store app. The API
returns a state code, with no application identity. The test recorded
the same unlocked `WinSta0\Default` console in session 2 at both ends of
the wait. [Microsoft Shell state values](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ne-shellapi-query_user_notification_state)

The eligibility check failed at its deadline. Without an observed
`QUNS_ACCEPTS_NOTIFICATIONS` (5), the workflow skipped the ordinary
WinRT send and its physical banner capture. Visible presentation on an
eligible ARM64 console remains open. The permitted-settings comparison
observed Notifications On and temporarily turned Do not disturb Off.
Restoration observed Off before returning it to On. A separately opened
Settings window then confirmed both switches On.

The [native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46107366401/job/140863008512)
ran at `85936d49b4acecf2a5e17a5c78a0561c2e3f07ba`. The
[original 182,294-byte ZIP](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46107366401/artifacts/15249954131)
had SHA-256 `d7c59ab411ad3d60b7e3c591a936e4927610cf5e6e8978db7de838efc4e65a99`.
Offline replay verified all 54 source hashes, the original compiled sender
(`89c66b130dbfc5abed5e90dd14111a3c2efe553c327f8ade62c9f1c60ef75619`),
the raw Shell query sequence and the Settings restoration receipts. The
archive and replay are under
`artifacts/rust/hosted-toast-history/arm64-eligible-85936d4/`.
