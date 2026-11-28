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

## Starting the German editor on an English test desktop

The tests that switch from German to English launch the editor with
`LC_MESSAGES=de_DE.UTF-8` and remove an inherited `LC_ALL` from its environment.
The desktop, Orca and input method keep their original locale. The worker
fixture retains its ordinary YAML. The second launch activates the existing
editor in its selected language. [Process environment](../performance/session.py)

On Fedora x64, the staged startup-language executable with SHA-256
`2b751a662a093ed7e30b629e66c62654caf3d818d317f00c999b28e18471b76f`
initially exposed **Filename**, **Password** and **Deutsch** under `LANG=C.UTF-8`.
The original German-first X11 observer timed out. With the editor's message
locale set explicitly, Orca spoke **Dateiname entry**, **Kennwort password text**,
**English button** and **Filename entry** on X11 and Mutter. Both process
readbacks showed `LANG=C.UTF-8` for the observer, editor and Orca. Only the
editor had the German `LC_MESSAGES`. Both runs replaced the backward selection
on the ordinarily reopened editor and produced `Gx – Sommer.jpg`. Anthy also
committed `あ` through XIM on X11 and through GNOME Shell's text-input protocol
on Wayland. The original results under `artifacts/rust/gui-run/` are
`x11-t4gt3h_8`, `wayland-3cgkyozs` and `wayland-xuiyvoul`. The earlier
English tree is in `x11-bdy2onwv/last-accessibility-tree.json`.
[Staged compiler and original language cases](startup/README.md#fedora-desktop-readback)

The ordinary Ubuntu x64 GUI and inventory worker from `6ea1b2e` also passed
the updated private Plasma menu control. The panel opened the German editor,
published English labels at revision 2, restarted worker 100 as 298 and
drained both processes on Quit. The original archive matched Actions SHA-256
`88e74f836491131744bdb52412257eb5e77dc2513dc9c34283e1181920807bb5`.
The local panel result is under
`artifacts/rust/plasma/language-controls-6ea1b2e/runs/plasma-xayd2pry/`.
The same ordinary pair passed the Fedora tray-loss control and the maintained
editor's glyph and text checks in `tray-loss-quit-7ogw_crh` and
`profile-text-wg6xonz_` under `artifacts/rust/gui-run/`.
[Original Ubuntu compiler archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46135261539/artifacts/15259187852)
