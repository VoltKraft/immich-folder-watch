# Windows notification history trial

Run on the disposable Windows x64 or ARM64 rewrite runner, after the native service build. The recorder uses the existing Rust executable from the same job and checks its source, native compiler, test results, dependencies and PE import table before it uses the desktop.

```powershell
python -B tools/rust-qa/windows-services/toast_history.py $env:NATIVE_TARGET
```

A fresh UUID identifies one synthetic app. The recorder creates a new private folder under the current user's Programs known folder. Its single shortcut targets the probe and carries the app's AUMID and a unique stub CLSID. Each subsequent process opens the installed shortcut and verifies its executable, arguments and both properties. Windows documents this mode for unpackaged apps with a protocol-type toast. The trial uses a unique inert protocol URI and requests no activation. Each toast is silent, disables mirroring and expires after five minutes. [Microsoft's shortcut instructions](https://learn.microsoft.com/en-us/windows/win32/shell/enable-desktop-toast-with-appusermodelid) · [Microsoft's unpackaged desktop activation options](https://github.com/MicrosoftDocs/windows-dev-docs/blob/2e559c1c7064af00d993650b1eb2f380a7153c94/hub/apps/design/shell/tiles-and-notifications/toast-desktop-apps.md#alternative-option---no-com--stub-clsid)

Each sender records its session, token elevation and native notification setting before calling `Show` when enabled. One request sets `SuppressPopup`; the other allows normal presentation under Windows settings. Separate processes read the app's history through `GetHistoryWithId` and compare the actual tags, group, titles and bodies. A successful run finds both messages, removes the normal tag while the quiet tag survives, removes the quiet tag and reads an empty history. The recorder holds its runner directories and shortcut during the trial and checks removal of the synthetic profile and Start Menu folder. [Popup setting](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotification.suppresspopup) · [History lookup](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotificationhistory.gethistory?view=winrt-26100) · [Exact removal](https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotificationhistory.remove)

The stand-alone service keeps its lockfile and all 15 exact registry archives. The `windows 0.62.2` feature change adds XML DOM and notification interfaces, WinRT apartment initialization, the Shell property store, typed property keys and PROPVARIANT support. Both target graphs were checked against the complete unpacked inputs. Their archive contents have 31 license and attribution files and contain no native binaries or fonts. The selected licenses are MIT and the additional Unicode-3.0 terms for `unicode-ident`. The native calls use the Windows Shell, COM, property system, token query and WinRT system interfaces. Each native run records the complete import table in `pe-imports.json`. [Exact archive, notice and feature-graph hashes](inputs.json) · [Microsoft Rust bindings](https://github.com/microsoft/windows-rs) · [Microsoft's original source archive](https://static.crates.io/crates/windows/windows-0.62.2.crate)

The result and raw per-process logs are under `artifacts/rust/windows-services/toast-history-<target>/`. Exit 0 records both independent history observations and exact cleanup. Exit 2 records an unavailable desktop or notification capability. Exit 1 records an invalid result, unexpected native error or unconfirmed cleanup. Banner visibility and user activation have separate desktop acceptance criteria. Detached replay verifies the complete captured import table against the original native build report, which identifies the executable by SHA-256. It also checks the original Windows desktop context and each process's session, operation and history-read phase. To replay the original positive result on any host, supply the downloaded evidence directory.

```sh
python3 -B tools/rust-qa/windows-services/toast_history.py x86_64-pc-windows-msvc --replay /path/to/evidence
```

Each sender checks its installed shortcut and records the HRESULT from
`CreateToastNotifierWithId` and, when creation succeeds, the HRESULT from
`ToastNotifier.Setting`. Each pair appears in order in the original log
and in the process record's `notifierReadiness` list. A newly registered
app can return `0x80070490` during either read-only call. Only that result
permits another query. Queries are spaced 500 ms apart and bounded by
eight seconds and seventeen starts. Each child retains its 25-second
process limit. An enabled setting permits one `Show` per sender. A disabled
setting ends that sender's trial. Earlier reports preserve their original
combined `notifier` phase.

For a newly installed test shortcut each sender logs the HRESULT for
`CreateToastNotifierWithId` and for the notifier's `Setting` query.
Only `ERROR_NOT_FOUND` from either lookup can trigger another read for
the same app identity. The sender spaces the reads by 500 ms, with an
eight-second budget and a maximum of 17 attempts. The process supervisor
enforces its 25-second limit on a stalled native call. An enabled
notifier can call `Show` once for its tag. A disabled setting ends the
send. An access refusal, a presentation error and a cleanup error each
retain their own native outcomes.
