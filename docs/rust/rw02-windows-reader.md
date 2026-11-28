# Windows screen reader assessment

The native Windows assessment starts portable NVDA 2026.3.1 with a fresh
configuration. It requests eSpeak and also accepts the reader's Microsoft
OneCore fallback when initialization succeeds. A separate UI Automation client verifies
the application HWND, process, focused field and foreground ownership before
sending keyboard input. It waits for announcements from the actual reader at
the German filename field, password field, language button and English filename
field. The protected-input check requires three separately observed masks and
rejects clear synthetic password characters. The speech log records NVDA's
utterances before synthesis. Acoustic output requires a separate observation.
[NVDA speech implementation](https://github.com/nvaccess/nvda/blob/08788e99cd9db570966063b549d2cd1f7496493a/source/speech/speech.py).

The fixture checks the official release asset's 69,896,584-byte length and
SHA-256 `6f80a5b0ca720a7d0d314b5be212f37388bbe81a1107ac3298c1821a1cd3f052`.
NV Access licenses this external test tool under GPL-2.0-or-later with two
upstream exceptions. The private portable copy and its bundled dependencies
stay in the temporary test directory, outside the candidate packaging inputs.
[NV Access release and checksum](https://www.nvaccess.org/post/nvda-2026-3-1/)
and [complete upstream terms](https://github.com/nvaccess/nvda/blob/08788e99cd9db570966063b549d2cd1f7496493a/copying.txt).

The driver refuses to launch on an occupied reader session. It disables
add-ons, remote access, update checks and changes to the system screen-reader
flag. The assessment retains a digest of the transient log, named synthetic
announcements, module names for warnings, the two executable architectures and
the independent UI Automation result. The private NVDA I/O log is discarded
with the temporary directory. The observer requires ordered speech records from
NVDA's own speech pipeline. A label seen only in a keyboard log or a UI tree
cannot satisfy it. [Documented portable operation and I/O logging](https://api.nvaccess.org/documentation/userGuide.html).

```sh
python3 tools/rust-qa/windows-reader/run.py --acquire-only
python3 -m unittest discover -s tools/rust-qa/windows-reader
python3 tools/rust-qa/windows-reader/run.py --binary artifacts/rust/gui-build/release/native-gui-assessment.exe --output artifacts/rust/windows-reader/native-test
```

The final command runs only on a disposable native Windows rewrite runner.
The local parser controls passed with ordered announcements, protected input,
split log writes and unrelated logging. The hosted observations below identify which cues each native run reached. [Fixture and input checks](../../tools/rust-qa/windows-reader/run.py).

At `8b071ab`, both Windows runners initialized NVDA and selected OneCore
after the audio device rejected eSpeak. The observer required eSpeak and
stopped before interacting with the app. It also discovered that the
portable reader kept DLLs open during cleanup. The profile now declares
the release's schema version 25 for its numeric typing-echo settings. The
fixture records the active synthesizer and gives the owned NVDA window
its normal quit message before bounded cleanup. The ARM64 runner used the
official x64 reader with a native ARM64 application. Ordered application
announcements remain a separate acceptance requirement on both hosts.
[Hosted observations](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452),
[release configuration schema](https://github.com/nvaccess/nvda/blob/08788e99cd9db570966063b549d2cd1f7496493a/source/config/configSpec.py)
and [reader shutdown](https://github.com/nvaccess/nvda/blob/08788e99cd9db570966063b549d2cd1f7496493a/source/nvda.pyw).


At `8a8adaa` the x64 reader initialized OneCore and produced all seven
expected announcements in 13 examined speech records. UIA confirmed three
masks and the DE/EN focus sequence. The native clipboard contained the
expected synthetic filename after Copy. The driver timed out waiting for
the empty field after Backspace. On ARM64, NVDA produced the initial
German filename label in six examined records. The owned foreground test did
not reach password typing. Both readers quit through their own windows and the
two temporary profiles were removed. The follow-up checks the full selected
filename before Delete and reads the empty document range independently.
[Native archives](rw02-native-gui.md#native-follow-up-at-8a8adaa).

## Native selection and Delete at `72fff40`

On Windows x64, OneCore again produced all seven ordered announcements,
including three separate password masks, in 16 examined speech records.
The foreground GUI had PID 7792. UIA confirmed the complete selection of
`Grüße – Sommer.jpg` before Delete. Copy had placed this exact name on the
clipboard. After the Windows Forms Delete gesture, both native text reads
still returned length 18 and the document endpoints were distinct. The
observer timed out. It recorded lengths only. The actual post-Delete strings,
selection endpoints and the reader's handling of that key are unknown.
The same GUI binary and input script completed the empty-field and Unicode
paste checks on both x64 control desktops without NVDA. A separate x64
normal-field test also passed extended Delete after a native drag selection.
The x64 archive SHA-256 is
`46a87220532d869cbc3c17a36e21e3f994675c8e6f6595ec3fec41cd9f688e46`.
[Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350).

On ARM64 the reader announced the initial German filename field in six
examined records. The native window never obtained foreground. The
filename center at (260, 175) did not belong to the subject, and the driver
sent zero keys. The reader exited normally and its profile was removed.
The ARM64 archive SHA-256 is
`823392ebb1a04a766e68a971482d389eb8ce259d9d6bef0cbd3b3d124b510009`.
[Native archives](rw02-native-gui.md#native-follow-up-at-72fff40).

## Reader-assisted editing

At `a66e045`, portable x64 NVDA 2026.3.1 observed the native x64 and
ARM64 GUIs. Its OneCore speech log recorded Dateiname, Kennwort, three
separate password masks, English and Filename in order on both hosts.
Each reader stayed active through ordinary Delete and the Unicode clipboard
paste, then quit through its own window. Both temporary profiles were
removed. The recorded utterances establish what NVDA submitted for synthesis.
Acoustic playback remains unmeasured.

| Native GUI | Utterances examined | Reader result SHA-256 |
| --- | ---: | --- |
| Windows x64 | 15 | `77189293d23f7854fa4d260b88b0dcfc45da84fb07b1b06b0dc9b072743c9db4` |
| Windows ARM64 | 13 | `bc7ec5f46e995cc9cf59b4db171c3f87f9cc57ad3338f5c662cde74c8970c710` |

[Native archives](rw02-native-gui.md#native-follow-up-at-a66e045).

The native reader scenario now submits the dedicated extended Delete
scan code E0 53 through Win32 `SendInput`. Before each gesture it checks
the input desktop, foreground HWND, GUI thread's active and keyboard-focus
windows, their process, and the UI Automation identity of the focused
unprotected filename field. The isolated keyboard uses Ctrl+A, Ctrl+C and
Ctrl+V. The driver records accepted input-event counts, the focus HWND, both
live text values and the selection's UTF-16 start and end. It retains only
strings from the known synthetic filename. Empty COM strings include their
original null-BSTR flags. [Win32 keyboard input](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput)
and [UI Automation range endpoints](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.text.textpatternrange.moveendpointbyrange).

NVDA binds Delete to an editing script that reads the caret and forwards
the gesture. If the first native Delete leaves the exact original text in
both patterns, the observer records that result, reselects the entire name
and presses NVDA+F2. It waits for the portable reader's own English
`Pass next key through` announcement and confirms the full selection again
before repeating the same Delete. An unexpected edit or lost focus fails
the case. The result distinguishes `ordinaryDelete` and
`nvdaPassThroughDelete`. A successful route requires an empty ValuePattern,
empty TextPattern document with equal endpoints, and a subsequent native
paste of the original Unicode clipboard value into the focused field.
Both text patterns must independently return that complete name.
[NVDA editing script](https://github.com/nvaccess/nvda/blob/08788e99cd9db570966063b549d2cd1f7496493a/source/editableText.py#L328-L345),
[NVDA pass-next-key command](https://github.com/nvaccess/nvda/blob/08788e99cd9db570966063b549d2cd1f7496493a/source/globalCommands.py#L3422-L3434)
and [NVDA keyboard guide](https://download.nvaccess.org/documentation/userGuide.html#BasicNVDACommands).

The native invocation above writes the per-gesture record to
`gui/input.json` and the accepted edit route and NVDA acknowledgement to
`result.json`. Eleven Python checks cover speech parsing, cleanup and
receipt validation. On Linux, PowerShell parsed the observer and compiled
the Win32 bridge. Disposable method doubles exercised both success routes,
null-BSTR results, changed text, a noncollapsed empty range and focus loss.
At `45dc03b` both Windows architectures cleared the real selection with
ordinary Delete, verified both empty interfaces and restored the exact name
by native Paste. At `d403fee` ARM64 passed again. On x64 NVDA delivered
all seven cues, then the UIA selection-prefix operation raised an error
after the recorded Delete. The revised observer checks both empty document
and selection endpoints directly when only position zero is possible.
Otherwise it measures the selection relative to the document. A bounded
retry obtains fresh ranges in the same verified focused editor and retains
the HRESULT for read failures. Both native repeats passed at `a66e045`.
[Earlier receipts](rw02-native-gui.md#native-follow-up-at-d403fee) and
[repeat results](rw02-native-gui.md#native-follow-up-at-a66e045).
