# Quit from the editor after the Linux tray disappears

The Linux editor offers **Beenden** or **Quit**, as does the shipping Avalonia window. When its tray registration is unavailable, it explains that closing the window keeps the watcher running and that the app launcher can reopen it. A watcher change preserves the user's current window visibility. Quit enters the shutdown path and waits for the worker to finish. The Windows editor shows the new button when native tray registration is unavailable. [Shipping window](../../../src/ImmichFolderWatch.App.Linux/Views/MainWindow.axaml.cs) · [Lifecycle contract](../../../rust/tests/fixtures/lifecycle/window.json)

The observer runs the paired GUI and inventory worker on private X11 and D-Bus servers with a synthetic profile. It starts an acknowledging StatusNotifierWatcher, removes it while the editor is visible, reads the German and English notices through AT-SPI, and closes the original X11 window. It creates a file while the window is hidden. An ordinary second process must reactivate the same primary. The observer gives keyboard focus to the reopened window, tabs to Quit, reads the pixels in its accessible bounds and presses Space. It verifies worker identity using its executable, parent PID and an open pidfd. [Observer](tray_loss_quit.py)

```sh
python3 -B tools/rust-qa/gui/build.py --jobs 2
python3 -B tools/rust-qa/performance/build_worker.py --name tray-loss-quit
python3 -B tools/rust-qa/gui/tray_loss_quit.py artifacts/rust/performance/subjects/tray-loss-quit
```

## Fedora x64 observation on November 28, 2026

The GUI SHA-256 was `9a5f057ca3a34c8e9bdb0ecec73874c05b1101fcb8bd2ba0c58a86e15878be13`. After watcher owner `:1.5` exited, the German and English notices both appeared on window `0x400002`. Closing it left GUI PID 32 and worker PID 38 alive. The worker discovered the new synthetic JPEG on pass 2. The second launch, PID 66, exited zero and retained the first owner's bus name `:1.6`. The same X11 window remapped with the English notice.

The focused Quit button occupied a 42 × 22 pixel rectangle. The native pixel sample contained 212 foreground pixels. Pressing Space ended worker 38 with `reason=quit success=true`, released the bus name and exited the GUI with code zero after `DRAINED passes=33`. The ordinary X11 suite also passed foreground startup, absent-tray background startup, close/reopen, masked entry, Unicode clipboard, filename selection and keyboard traversal through the new button. Under `artifacts/rust/gui-run/`, `tray-loss-quit-skh1ffhu/` contains the result, source manifest and process logs and `x11-93fpobrs/results.json` records the input regressions.

The result SHA-256 is `966f54f0053d65692457481c15ba729cd7379e668f6c9fa3867742812ca1d0ab`. This native button observation covers Fedora x64 on X11. The other display backends and architectures have separate evidence requirements.
