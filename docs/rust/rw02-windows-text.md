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

Seven portable regression tests cover agreement with the executable Linux cases, translated ink and contrast, distinct original glyph crops, logical caret and deletion results, mixed-direction geometry, rejection of a different process or unavailable foreground, and survival of independent successful cases. The observer parsed in PowerShell 7.7 on Linux and its shared C# HWND code compiled together with the native pointer helper. A separate C# compilation resolved the UIA range, focus, drawing and WinForms signatures against WindowsDesktop 10.0.12 reference assemblies. These are portable checks. The Windows x64 and ARM64 observations for this ordinary-field suite require their respective native results.

```sh
python3 -m unittest discover -s tools/rust-qa/windows-text -p 'test_*.py' -v
```
