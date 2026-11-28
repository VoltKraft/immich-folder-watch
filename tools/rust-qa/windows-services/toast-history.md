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

## Visible normal WinRT popup

On the hosted ARM64 desktop the command above starts a second, native
PowerShell observer before the original sender. It checks the ordinary
Shell popup at the notification corner and the visible CoreWindow
candidates on the same desktop. The expected title and body must appear
inside the Shell's normal toast view and have distinct physical hit
points on the original Shell HWND. The observer
captures the screen crop containing both labels. Windows notification
settings stay under the runner's control.

The workflow retains the history and physical observations in separate
artifacts. To verify a positive physical observation, extract both
archives and run the command below. Replay checks the original sender's
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
