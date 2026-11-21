# RW-02 Windows foreground and keyboard observation

## Native observations

On Windows ARM64, the German filename and password editors exposed their accessible names and password protection on both recorded runs. Windows declined the foreground request. The guarded observer found a different window or no window at the filename field center, successfully raised its own HWND, and declined the click after its final hit test. It timed out before reaching the keyboard test. On both x64 controls the subject acquired the foreground, accepted three masked keystrokes, switched language and round-tripped the synthetic Unicode filename through the Windows clipboard.

| Hosted run and source | ARM64 filename center | ARM64 input.json SHA-256 | x64 input.json SHA-256 |
| --- | --- | --- | --- |
| [44831851264](https://github.com/voltkraft/immich-folder-watch/actions/runs/44831851264), `5895c0b1dc0b25717a2b5c81ad24c85b27c12b38` | (286, 201) | `946ba2cf12eb33de449a2456373d25c4f9f09d1beec68514ff6944cca2c80a58` | `48b9b101ec0bf404931fff4a79f0ea2e55d359f8a462386327529662fff75edb` |
| [44835826452](https://github.com/voltkraft/immich-folder-watch/actions/runs/44835826452), `8b071ab9089a87a65ae1cc23325fcbba452fe4d2` | (182, 97) | `6db6644a35893be2a0e0b210dd3765872733db40a530d109ecca31a4d84dccc3` | `5b6b667558672a60202849bba973226d382bee8fb74ab87d25267904a13657fb` |

The downloaded archives are under `artifacts/rust/hosted-desktop/<run>/windows-{arm64,x64}.zip`. Their `gui-native/<target>/windows-input/results.json` binds the executable and observer source hashes. In the first run both architectures reported process session 2, active console session 2, matching thread/input desktop names, one 1024 × 768 monitor and 96 DPI. The x64 system was Windows Server 2025 build 26100. The ARM64 system was Windows 11 build 26200. These records leave the occluding HWND and the Windows session lock state unidentified. A desktop-name match can also occur in a disconnected session. [Microsoft OpenInputDesktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openinputdesktop)

At `8a8adaa` both native runners had an active, unlocked console in
session 2. On ARM64, a full-screen `WWAHost.exe` window owned the field
center before and after raising the subject. The observer sent no click at
that point. Both architectures switched to their newly created input desktop
and restored Default. Before a test window appeared, enumeration returned
zero with Win32 error zero on both hosts. The observer now enumerates the
worker’s own desktop explicitly and permits this empty result to retry only
during a bounded wait for a visible window. A fresh native run is required
for the guarded input on that desktop.
[Native archives](rw02-native-gui.md#native-follow-up-at-8a8adaa) and
[EnumDesktopWindows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdesktopwindows).

## Native reproduction

Run from the source checkout in the existing hosted Windows x64 and ARM64 jobs, after building the native GUI assessment. The fixture uses Python's standard library, the existing Windows PowerShell/UI Automation observer and Windows system DLLs. It requires the current hosted runner identity and the target-specific executable and evidence directory.

```bash
python3 tools/rust-qa/windows-desktop/run.py \
  artifacts/rust/gui-build/release/native-gui-assessment.exe \
  "artifacts/rust/gui-native/$NATIVE_TARGET/windows-desktop"
```

1. The supervisor records its window station and visibility, assigned desktop, input-desktop name, the system's `UOI_IO` indicators, process session, active console session, and WTS connection/lock state of its own session. It records the immediate launcher executable and system shell/foreground window identities through native HWND, PID, thread ID, window class, rectangle and executable basename. [Microsoft user-object information](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getuserobjectinformationw) and [WTS session flags](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w)
2. On the original desktop it launches a fresh subject with a private synthetic profile. It resolves the German filename rectangle through the subject's own UIA tree and reads its physical center with `WindowFromPoint` and `GetAncestor(GA_ROOT)`. It records the native window and client rectangles, DWM frame bounds, DWM cloak state or failure HRESULT, styles, visibility, minimization, DPI and the subject thread's desktop. On an active unlocked console it repeats the hit test after briefly raising the subject without activation and then restores its Z order. This original-desktop phase sends zero pointer and keyboard events. [Microsoft WindowFromPoint](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-windowfrompoint) and [DWM attributes](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)
3. An active, unlocked `WinSta0\Default` session with both native input indicators set permits the named-desktop trial. A separate creator thread makes a random desktop in the same window station. The supervisor retains the original desktop handle, switches to the named one and independently reads the active desktop back. It launches its worker suspended with an explicit `STARTUPINFOW.lpDesktop`, assigns it to a process-tree job with kill-on-close and resumes it. The worker independently checks the actual subject HWND's session and desktop. Observer processes run without a new console window. [Microsoft CreateDesktopW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createdesktopw), [STARTUPINFOW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-startupinfow) and [job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
4. The named worker runs the shared Windows input observer on the verified test HWND. Each keyboard operation requires the current input desktop, the subject PID, and the subject HWND in the foreground. A pointer attempt additionally checks the native hit-tested root and PID. Success requires the guarded keyboard path, the protected editor, three typed characters, the translated field labels and the Unicode clipboard round trip. The inherited `T` and `Q` bytes start and stop the fixture's supervisor. The named worker and the subject must exit cleanly. [Shared input observer](../../tools/rust-qa/observe-windows-input.ps1) and [Microsoft foreground policy](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)
5. The supervisor closes the fixture job, restores the original desktop when the active desktop still belongs to this trial, verifies its name and closes its handles. A locked session or an independently selected desktop prevents a switch. The worker has a bounded runtime. The fixture uses no direct window-message substitute for keyboard input. [Microsoft SwitchDesktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-switchdesktop)

The report is `results.json`. The two phases write `original/observation.json` and `named/observation.json`. The latter also writes the shared observer's `input.json` when the named input trial reaches it. The top-level `evidence.sha256` covers the captured files. A missing prerequisite, an observer failure or unverified cleanup returns a failing exit status. Application, worker, keyboard observer and launcher source hashes appear in the report. System object names and window geometry are diagnostic data. A hardware keyboard, a different Windows account and a physical desktop are outside this hosted trial.

The historical runs above predate the named-desktop launcher. Nine portable regression tests cover desktop/session checks, restoration ownership, field and process checks, input acceptance, native structure layout and PE machine identification. The PowerShell observer parses on the locally available PowerShell 7.7. The initial hosted trials reached the newly created desktop on both architectures. Their input phase awaits a successful native rerun.

```bash
python3 -B -m unittest discover -s tools/rust-qa/windows-desktop -p 'test_*.py'
```
