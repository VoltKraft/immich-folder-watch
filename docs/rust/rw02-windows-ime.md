# RW-02 Windows system IME composition

The hosted wrapper first runs the actual field test with the installed
components. If the runner has an active input desktop and the native
inventory identifies a missing Japanese input service, Windows servicing
can add the official Japanese Basic Typing component to that disposable
OS. The wrapper adds Japanese to the test account's language list when
needed, reruns the full preedit, commit and UI Automation checks, then
restores the original list and removes any component it installed. The
receipt distinguishes the initial result, servicing state, observed
language package, subsequent field result and cleanup. A required reboot
or unavailable component remains visible as a failed prerequisite.
[Hosted fixture](../../tools/rust-qa/windows-ime/hosted.ps1),
[Microsoft language Features on Demand](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/features-on-demand-language-fod?view=windows-11)
and [test-account language list](https://learn.microsoft.com/en-us/powershell/module/international/set-winuserlanguagelist?view=windowsserver2025-ps).

A positive observation requires an ordinary virtual A key to produce a nonempty native preedit in the Rust filename field. The observer must see that preedit before pressing Enter. It then requires a distinct, one-character native commit and an independent UI Automation readback of the original filename with `あ` (U+3042) appended. The observed Windows x64 and ARM64 keyboard logs in hosted runs [44831851264](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264) and [44835826452](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452) contain zero IME events. Those earlier runs exercised a different keyboard scenario and leave Windows composition open.

At `72fff40` both runners installed the Microsoft Japanese Basic Typing
feature, version 10.0.26100.33828 on x64 and 10.0.26100.9974 on ARM64.
Both fixtures stopped during language-list readback before starting the
second GUI trial. Both restored the original language list and removed the
component without requesting a restart. The follow-up enumerates the actual typed language list, checks the
proposed entry, records the requested and observed language tags and allows
time for the account change to become visible. It also asks TSF for all
profiles and selects Japanese records by their returned language identifier.
Only observed preedit, commit and independently read text count as a pass.
[Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350/job/136971561540)
· [Windows ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350/job/136971561498)
· [Windows language list](https://learn.microsoft.com/en-us/powershell/module/international/get-winuserlanguagelist?view=windowsserver2025-ps)
· [TSF profile enumeration](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-enumprofiles).

## Hosted execution

Windows Server x64 at `a66e045` installed the Microsoft Japanese Basic
Typing capability in its disposable account. The ordinary focused Rust
filename received a real IME preedit before Enter, committed U+3042 (あ)
after Enter and returned the same character through native UI Automation.
The input layout and language list were restored and the temporary
capability returned to its original `NotPresent` state. The composition
receipt SHA-256 is `5758eac22dae57e9862d0a3ec32870a130a0540a74fdd48f9c083a37c40a6286`.
[Native archive](rw02-native-gui.md#native-follow-up-at-a66e045).

The ARM64 native window at the same revision also composed あ and returned
the edited filename through UI Automation. The GUI and observer exited
with code zero. The input layout and the account's language list were
restored, and Basic Typing returned to `NotPresent`. Removing the private
profile then raised Windows sharing violation 32. The old driver had already
written `passed` into its result and returned zero despite this traceback.
The ARM64 composition was verified in that run. The SHA-256 digests are
`9cf73126e33820653cdbf31c0dc42e27b5cbe2b1e1b13ddca0ec90713b194e01`
for the composition and
`93e850fbb9be7e76d491a2b8257dab4b27805b7d9ccc4914616156445647c0ea`
for the result with the cleanup failure.
[Windows ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45034293002/job/137244473575).

At `3b4854d` the ARM64 observer again saw preedit before Enter, a commit of
U+3042 and the edited filename through UI Automation. Both processes exited
zero. The driver reported no exception. The original input layout, language
list and `NotPresent` capability state were restored. This driver predates
the explicit `profileRemoved` field. On x64 the same revision restored the
original layout and servicing state, but both ordinary IME gestures produced
a literal `a`. The observer exited 1 without a qualifying preedit. The GUI
exited zero. The previous x64 composition and the unsuccessful repeat are
both retained. [Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/job/137259319529)
· [Windows ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/job/137259319278).

| Receipt at `3b4854d` | Windows x64 SHA-256 | Windows ARM64 SHA-256 |
| --- | --- | --- |
| Japanese composition | `8126d69dff09c76cfcd4df9b0a0e5c8852c3fe95b524cce0ac187fe0803a0b3d` | `5b5bae51eac8568817a07e37dbd8272fb5362c75e51ca637bc183c6fa5ecfcf2` |
| Japanese GUI result | `fe654f222d33ed91fd84438d4fae90081aeb158b3bcb6c0b144d0a3f5ac26b95` | `0857d9a38beeab3badc6a9e763c8f56dc6403159a62b08135c7ead0ddfbd17a8` |
| Language servicing | `fa327c36031356b549d1834fc78fed04a2df44742faa91fd73c83cfb293ea7f8` | `954a73028da7580a1fc2d2c908e376cda0d9c6107412aee7c8586d5481575ee2` |

On 2026-11-22 the two x64 receipts showed identical inventories (SHA-256
`f35d7a2d071c5ac3e074388918c2a63ce723fab9ccbd49d3b7aeabcd52e44dbc`),
13 matching observer inputs and 14 matching GUI compiler inputs. Both
selected Japanese HKL `0x04110411`. The input method's open and conversion
states during typing remain unknown for both runs. The IME fixture now
requests a sample before each mode gesture, before A, after its observed
outcome and after a successful commit. The GUI's own UI thread checks
that the German filename and its foreground HWND have focus, then reports
the editor's IME request, thread HKL, IMM open flag and conversion bits.
A missing context and unavailable conversion bits have separate results.
Zero is a reported alphanumeric mode. These readbacks add no keystrokes.
Native repeats on Windows x64 and ARM64 are pending.
[IMM thread ownership](https://learn.microsoft.com/en-us/windows/win32/intl/developing-ime-aware-multiple-thread-applications)
· [IMM open state](https://learn.microsoft.com/en-us/windows/win32/api/imm/nf-imm-immgetopenstatus)
· [conversion status](https://learn.microsoft.com/en-us/windows/win32/api/imm/nf-imm-immgetconversionstatus)
· [conversion flags](https://learn.microsoft.com/en-us/windows/win32/intl/ime-conversion-mode-values).

The revised IME and ordinary text observers start child processes in their
retained evidence directory. Profile, cache and temporary data use the
fresh private profile. A Windows file lock can delay cleanup for up to 20
seconds. The result records the composition and the removal separately.
Success requires both, with the native language and input desktop restored.
The hosted wrapper also rejects any result containing an exception.
[IME driver](../../tools/rust-qa/windows-ime/run.py) · [Private profile cleanup](../../tools/rust-qa/windows_observer.py).

At `8b64330` and `7517e3b`, Windows Server x64 and Windows 11 ARM64
each passed the strict composition and cleanup checks. All four trials
provisioned Japanese Basic Typing, observed preedit on the first IME On
attempt, then confirmed the Enter commit and U+3042 through UI Automation.
Each GUI and observer exited zero and each receipt recorded
`profileRemoved=true`. The original input layout and language list
were restored and Basic Typing returned to `NotPresent`. On the same
four builds the ordinary filename passed all three selection and deletion
cases, and NVDA's OneCore speech pipeline recorded all seven expected cues
in order. These runs predate the focused IMM mode readback in `f4d5b3a`.
[Run 45041728291](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45041728291)
· [Run 45047460092](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460092).

| Strict `japanese/result.json` | Windows x64 SHA-256 | Windows ARM64 SHA-256 |
| --- | --- | --- |
| `8b64330` | `28406dc31dd865a3c66133f70d54cc614dc6b7530b668fcbf31e5db23f7b4ee6` | `2e744c5b98d1ad6cababfee84a7ecc2fd670adc9a5691bb4da9b06b0925f5e63` |
| `7517e3b` | `69e2c7e3d4f72cc91dc6d2c3d183326187aab4ba7b7028c83be50ad7494e101e` | `fe29d3e2de2166f872dd44be1a684d7f605be9693ea274c8f85a57af96245426` |

Run both native architectures after building the existing GUI fixture. The driver uses Windows PowerShell with UI Automation, TSF, IMM and User32 from the operating system. The checked-in C# is an external development observer. The Rust application, dependency set and normal editor use the same GUI build as the other native tests.

```bash
python3 tools/rust-qa/windows-ime/run.py \
  artifacts/rust/gui-build/release/native-gui-assessment.exe \
  "artifacts/rust/gui-native/$NATIVE_TARGET/windows-ime"
```

The first phase reads the Japanese TSF profiles and enumerates the actual loaded input locale handles. It records the input service's class, profile, category and enabled flag. It also records any IMM description and the read-only Japanese Basic Typing capability and user input-method status where Windows exposes them. An unavailable query retains its diagnostic. The inventory process's active-profile bit describes that process alone. A loaded Japanese locale plus an enabled keyboard text service or a loaded IMM IME permits the input trial. The default command returns failure with the specific missing prerequisite when composition cannot be attempted. `--inventory-only` writes the inventory without opening the test window and labels its result accordingly. [Microsoft TSF enumeration](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-enumprofiles) and [input processor profile fields](https://learn.microsoft.com/en-us/windows/win32/api/msctf/ns-msctf-tf_inputprocessorprofile)

For the second phase the launcher verifies the GUI executable, native PE machine, build receipt and exact Rust filename source. It creates a private profile and checks the active, unlocked console, session, desktop and the subject's real HWND. The observer reuses the shared Windows desktop ownership helper for foreground activation and any fallback click. It requires the owned foreground process and the focused, unprotected filename UIA element before each keyboard gesture. It requests an already loaded Japanese input locale from that window and independently observes the actual input locale of its native UI thread. This request changes the input locale for the test window through the normal window procedure. [Microsoft input-language request](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-inputlangchangerequest) and [thread input locale](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getkeyboardlayout)

The driver moves to the end of `Grüße – Sommer.jpg`, sends the IME On gesture and types an ordinary A using `SendInput`. If the first attempt produces only a literal lowercase a, it removes that exact character and tries the documented Alt+Backquote gesture. The observer checks the Rust log from the byte boundary immediately before A and again immediately before Enter. Winit 0.30.13 receives Windows' composition messages and reads composing and committed strings through `ImmGetCompositionStringW`. Egui reports those events through the existing Rust logic. A pass requires the resulting Unicode field value, restoration of the original thread input locale, a clean application exit and return to the same input desktop. The driver sends no clipboard data, Unicode input packets, WM_CHAR or generated WM_IME_COMPOSITION. [Microsoft Japanese IME shortcuts](https://support.microsoft.com/en-us/windows/hardware/input-devices/microsoft-japanese-ime), [system composition message](https://learn.microsoft.com/en-us/windows/win32/intl/wm-ime-composition) and [existing Rust logging](../../tools/rust-qa/gui/src/main.rs)

The results include `inventory.json`, `compose.json` when reached, the Rust trace, the binary and source hashes in `result.json`, and `evidence.sha256`. Installed capability, enabled input service, subject thread locale and observed text composition are individually traceable. The engine identity list describes installed providers. The end-to-end result attributes the observed composition to the Windows Japanese input path of the subject thread.

## Separate Windows VM

When the hosted image lacks the Japanese input service or an unlocked foreground, use a separately authorized, disposable Windows VM with its own test account and active console. In that VM, add Japanese under **Settings → Time & language → Language & region**. Install Basic Typing, check that Microsoft IME appears under the language's keyboards, and select the Japanese input method once in the test account if the native inventory has no loaded Japanese locale. The usual Romaji input setting maps A to `あ`. Keep a VM snapshot for disposal after the observation. [Microsoft language and keyboard setup](https://support.microsoft.com/en-us/windows/hardware/input-devices/manage-the-language-and-keyboard-input-layout-settings-in-windows) and [Microsoft Japanese IME options](https://support.microsoft.com/en-us/windows/hardware/input-devices/microsoft-japanese-ime)

Run the same launcher in the matching checkout with the native binary and its build receipt. Each invocation creates a new output directory. With the normal repository layout the receipt path is inferred.

```powershell
python tools/rust-qa/windows-ime/run.py artifacts/rust/gui-build/release/native-gui-assessment.exe artifacts/rust/windows-ime-vm --isolated-vm --build-receipt artifacts/rust/gui-native/x86_64-pc-windows-msvc/build.json
```

At `d403fee`, both native Windows images installed Japanese Basic Typing,
accepted the requested `ja-JP` entry, and returned `ja` in the account's
language list. The observer missed that entry and the input trial stopped
before composition. Both images restored their original language list and
removed the temporary package. The observer now recognizes both Japanese
tags, retains the input-method identifiers, and still requires actual
preedit, commit and field readback for acceptance.
[Native servicing run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306).

Five portable regression tests cover input-service eligibility, preedit, commit, field readback, source binding, the observation pipe and cleanup. PowerShell 7.7 checked the response parser with absent contexts, unsupported flags, and partial, repeated and wrong-thread responses. Rust 1.100 passed rustfmt and Clippy for the ordinary and retained GUI builds on both MSVC targets from Linux. The earlier PowerShell check compiled the TSF/Win32 observer and the shared ownership bridge and measured the 64-bit TSF profile structure at 88 bytes. Native acceptance requires the Windows trace and UIA value.

```bash
python3 -B -m unittest discover -s tools/rust-qa/windows-ime -p 'test_*.py'
```
