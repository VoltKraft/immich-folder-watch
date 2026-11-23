# RW-02 Windows filename rendering and editing

The native observer operates on the German `Dateiname` editor of the maintained DX12 GUI. It uses the same glyphs, names, click positions and expected logical caret offsets as the ordinary Linux field. The earlier Windows font comparison runs a separate specimen. [Linux field observer](../../tools/rust-qa/gui/profile_text.py), [source and font review](rw02-gui-dependencies.md), [comparison specimen](rw02-font-coverage.md)

## Run and evidence

Run on each disposable Windows host after the canonical GUI build from the same checkout. The launcher uses the existing Python, system PowerShell, UI Automation, GDI and User32. The two native target arguments are `x86_64-pc-windows-msvc` and `aarch64-pc-windows-msvc`. [Launcher](../../tools/rust-qa/windows-text/run.py)

```sh
python3 tools/rust-qa/windows-text/run.py "$NATIVE_TARGET"
```

The expected output is a fresh `artifacts/rust/gui-native/<target>/windows-text/`. The launcher verifies the PE machine against the operating system, the GUI build receipt and executable hash, all current Rust compiler inputs, the lock and target graph, the reviewed source trees, fonts and notices. It starts the GUI in a disposable profile and requires a real `ADAPTER Dx12` observation. The same command accepts `--isolated-vm` on an explicitly authorized disposable native Windows VM with the same checkout and build layout.

UI Automation verifies the initial name in both the editor’s `ValuePattern` and `TextPattern`. The observer sets each synthetic input through the field’s public `ValuePattern.SetValue`. For each character it moves the endpoints of a *cloned* document range by logical character count, reads its exact text, and obtains its physical screen rectangle. For each caret or marked range it reads the actual selection and measures its prefix from the start of the document. The probe uses physical per-monitor DPI coordinates. [Windows text ranges](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.text.textpatternrange?view=netframework-4.8.1), [UIA rectangle semantics](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.text.textpatternrange.getboundingrectangles?view=netframework-4.8.1)

The normal field must own keyboard focus on the unlocked input desktop. Right, Left, Tab and Delete use native keystrokes. A native pointer click places the caret. The observer drags from 10% to 90% of the target character’s own screen rectangle using a real button press, motion and release. It checks the HWND and PID along the entire drag path and reads back the actual pointer destinations. The test does not access the clipboard. [Windows observer](../../tools/rust-qa/windows-text/observe.ps1), [guarded Win32 input](../../tools/rust-qa/windows-text/Pointer.cs), [Microsoft SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)

| Entered filename | Logical offsets after click, Right, Left | Native drag selects | Text after Delete |
|---|---|---|---|
| `あ界⬟.jpg` | 0, 1, 0 | `界` at 1 | `あ⬟.jpg` |
| `L-بتث-R.jpg` | 4, 3, 4 | `ث` at 4 | `L-بت-R.jpg` |
| `L-ب12ت-R.jpg` | 3, 4, 3 | `ت` at 5 | `L-ب12-R.jpg` |

In the last row, sorting the actual screen positions from left to right must yield logical indices 5, 3, 4, 2. The glyph specimen contains `A`, `あ`, `界`, `⬟`, `ب`, `ت`, `ث` and the reviewed missing-character control U+10FFFD. After native Tab removes the caret, the observer captures the uncovered field into a PNG and serializes the same image losslessly for the existing P6 reader. Using the UIA rectangles, it compares the eight translation-normalized ink masks with the same contrast cutoff as Linux. All eight must contain ink and have distinct hashes. Captures are limited to the owned filename field. [Portable evidence evaluator](../../tools/rust-qa/windows-text/evidence.py)

`observations.json` retains each available native observation, including failures in an individual case. `result.json` identifies the executable, graph, driver inputs, DX12 adapter, foreground capability, passing cases and any failures. The two field images, subject and observer logs, exact plan and SHA-256 manifest accompany it. A missing prerequisite produces a failing process exit and the available evidence. Successful completion requires the eight masks, three native editing sequences and drained child.

## Validation status

Seven portable regression tests cover agreement with the executable Linux cases, translated ink and contrast, distinct original glyph crops, logical caret and deletion results, mixed-direction geometry, rejection of a different process or unavailable foreground, and survival of independent successful cases. The observer parsed in PowerShell 7.7 on Linux and its shared C# HWND code compiled together with the native pointer helper. A separate C# compilation resolved the UIA range, focus, drawing and WinForms signatures against WindowsDesktop 10.0.12 reference assemblies.

At `45dc03b` and `d403fee`, x64 completed all three ordinary editing cases.
ARM64 rendered the full specimen, completed the first edit and returned the
expected caret positions, selections and geometry for the two Arabic cases.
Both Arabic cases ended with an unclassified error before recording the edited
text. The revised observer records whether the guarded Delete completed,
reopens both UIA text patterns from the focused normal field and requires
their exact results. It records the native exception type and HRESULT if a
read fails. Only read operations can repeat.
[Archived observations](rw02-native-gui.md#native-follow-up-at-d403fee).

At `a66e045` the ordinary x64 and ARM64 GUIs completed all three edits in
the table above. Both observers read back eight distinct glyph masks,
the exact three caret sequences and the expected character and offset for
each drag. After native Delete both UI Automation text interfaces returned
the expected filename in every case. Both subjects exited with code zero
and their jobs drained. The ARM64 test used its private active desktop
after a different process covered the field on the original desktop.
The x64 test used its original desktop.

| Native GUI | Ordinary editor result SHA-256 |
| --- | --- |
| Windows x64 | `0284ca7aada43e91dccb6132a18113c81b1e8301c71f3977d7d808dc955b241c` |
| Windows ARM64 | `d860c81aeff3ea94aa8b524bccc06d5c4ea260b2a8f91cf43edb7dae3a7e0c6e` |

[Native archives](rw02-native-gui.md#native-follow-up-at-a66e045) and
[separate font probe](rw02-font-coverage.md#windows-x64-input-timeout-at-a66e045).

### Focus when capturing the caret-free field

The glyph specimen needs the caret outside `Dateiname`. The native Tab
places focus in the same window's `Kennwort` edit. At `549066f` and
`ba02f8b`, both architectures produced the same 276 × 18 filename image,
SHA-256 `94941c7babf5dc81e363d64cf9e4ba4ab52c8e1ccf98371a2cac093d2c0371ab`.
All three edits also returned the expected text through both UI Automation
patterns. The shared capture change at `a44848d` required the captured
element itself to have keyboard focus, which conflicted with the preceding
Tab. [Native run at 549066f](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471) · [Native run at ba02f8b](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405).

At `1b95ba0`, both original archives confirm the failure occurred in the
capture guard before it wrote the PNG. The three ordinary editing cases
passed on both hosts, including the visual order 5, 3, 4, 2 and the exact
Delete result from both text interfaces. The x64 observer used the
original desktop. ARM64 exercised the private desktop and restored the
original one. Both subjects exited successfully. Independent replay
matched the original plan and the 22 compiler and 22 observer inputs
per host. The separate font specimen rendered its eight glyphs on both.
[x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14843990978) · [ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14845081343).

The glyph observer now resolves the exact owned password field by name,
role and process, then verifies that it holds focus on both sides of the
capture. The bitmap comes from the non-password filename field. Its
screen coordinates and dimensions must match the full region verified by
the outer observer. The retained-editor and display trials still require
keyboard focus in the filename field they capture. Local PowerShell checks
accepted the expected rectangle and rejected four one-pixel changes in
position or dimensions. A new native run must supply the rendered glyphs.

```sh
python3 -m unittest discover -s tools/rust-qa/windows-text -p 'test_*.py' -v
```

## Ordinary filename on the reopened retained HWND

The disposable Windows desktop job also runs the same eight glyph crops and three editing sequences on the retained executable. Its separate process starts with the original filename, hides through WM_CLOSE and reopens through the existing supervisor. The native observer verifies the loaded executable path and hash, the process creation time and the original HWND. The GUI must retain generation one in DX12 CPU Mailbox/Wait mode. A create/destroy hook and root hide/show events cover the field observation.

```sh
python3 -B tools/rust-qa/windows-desktop/session.py "$NATIVE_TARGET" retained-text
python3 -B tools/rust-qa/windows-warm-window/filename.py "$NATIVE_TARGET" --replay path/to/windows-warm-window/"$NATIVE_TARGET"/windows-text
```

The first command uses the existing desktop placement decision after the retained build. Run the second from a Git checkout of the originating revision with the extracted artifact's sibling compiler stream, original source archive, canonical graph and build receipts in place. It verifies the observer files against that revision with Windows checkout filters. The field's HWND, PID, thread desktop and session must agree with the unlocked input desktop before and after the PowerShell observation.

The retained case writes under `artifacts/rust/windows-warm-window/<target>/windows-text/`. Failures preserve the native hook observations, current phase, subject log and available glyph or editing results. The normal teardown GUI continues to write its own results under `gui-native/<target>/windows-text/`.

### Captured ordinary and reopened filenames at 1904be7

On Windows x64 and ARM64, both the ordinary editor and the reopened
retained editor passed the three mixed-direction mouse, caret and Delete
cases. Both native UI Automation text interfaces returned the exact
edited text in all twelve cases. The eight glyph masks were distinct in
each image. All four original 276 × 18 PNGs were byte-identical and
contained 152 colors. Their SHA-256 is
`94941c7babf5dc81e363d64cf9e4ba4ab52c8e1ccf98371a2cac093d2c0371ab`.
Detached replay checked the compiler and source archive, original window
identity, hide and reopen events, exact field rectangle, decoded pixels
and native editing events. Each retained subject stayed at renderer
generation one across hide and reopen.

| Native host | Ordinary result SHA-256 | Reopened retained result SHA-256 |
| --- | --- | --- |
| [x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14859761846) | `62858e399afff8b8dff68fd5fbb827fd2a5e81d34bf8ee4ab71916f87c754f76` | `f4f2b3a4734fcd457773c9c368194f20c0cf32b2ce5518b1c8ea60bd43597af4` |
| [ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14857840215) | `ca315e10e2af185af7b72e246c3a200e7e094e411feeba41d5336d0e9bafe342` | `051eaa6b03d8e11bd0559e1e1922368350729096667255a5e475823679119d51` |
