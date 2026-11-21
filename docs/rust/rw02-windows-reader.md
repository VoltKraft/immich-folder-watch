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
