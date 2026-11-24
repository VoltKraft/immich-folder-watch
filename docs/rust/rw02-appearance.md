# Desktop system appearance

The shipping Avalonia host requests the desktop's default theme. In pinned
winit 0.30.13, the Linux event loop's `system_theme()` returns `None`. The
unmodified Rust window kept the same dark panel while the real desktop
portal reported five successive color and contrast settings.
[Avalonia application](../../src/ImmichFolderWatch.App.Linux/App.axaml)
and [pinned Linux event loop](https://docs.rs/winit/0.30.13/src/winit/platform_impl/linux/mod.rs.html).

The Linux adapter uses the existing zbus dependency. It subscribes before
its first `ReadAll`, reads the appearance namespace after each settings
change and observes replacement of the portal service. It retains the
last snapshot while the window is hidden. A change wakes an existing
window and the GUI thread applies the palette. Missing or unknown values
use the framework default. Shutdown closes the observer connection and
joins its worker. The settings adapter only handles the portal's unsigned
integer values and stays independent of egui.
[XDG Settings specification](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Settings.html),
[native adapter](../../tools/rust-qa/gui/src/linux_appearance.rs) and
[palette](../../tools/rust-qa/gui/src/appearance_style.rs).

## Native observation

Fedora 45 x64 provided a private X11 server, D-Bus session, GTK portal
backend and Settings frontend. The observer changed the private desktop
settings in a second process, read the actual portal values, and captured
the Rust window after checking its PID and caption. It measured a 16 × 16
panel region and the first static label. Each measurement required a
second identical sample.

| Portal setting | Original panel, grey level | Adapted panel, grey level |
| --- | ---: | ---: |
| Prefer light | 27 | 248 |
| Prefer dark | 27 | 27 |
| Dark, high contrast | 27 | 0 |
| Light, high contrast | 27 | 255 |
| Prefer light, ordinary contrast, changed while hidden | 27 | 248 |

The high-contrast label region contained 97 near-white pixels on black
and 42 near-black pixels on white. Reopening preserved the same native
window ID. Replacing the private portal frontend yielded a new process
owner. The running GUI followed its dark setting and the next light change,
then drained on Quit. The original and candidate result SHA-256 values are
`37d0a871727de2a68ae4b8b2940b1b2ec3854ddc1c0a4d90e35d1fccdc8690ba`
and `cab14c2e7523cbd158e4d0ade0b7ad1b87f6bc6d517bc62d06709a4bfc40ba45`.
These samples cover the named Linux window and its first label. The
remaining screens, Windows appearance and user accessibility evaluation
have separate acceptance work.

Ubuntu 24.04 x64 and ARM64 at `a66e045` ran the same native fixture on
Xvfb. Each portal exported `color-scheme`. Both panels went from RGB 248
to 27 and back to 248 on the same window after a hidden settings change.
Each replacement portal had a new PID and the GUI followed its next two
changes before clean shutdown. Neither host exported a contrast setting.
The x64 result SHA-256 is `56037dbb1baea9c3636f3f3de54703c8a438ca419141f7ba3d90e15a0245b4b1`.
The ARM64 result SHA-256 is
`38bad20b406431c813060b6abe05fb772398495dbf9ee8d3eac627df137a5a6b`.
[Verified native archive](rw02-native-gui.md#native-follow-up-at-a66e045).

From the repository root after preparing the pinned GUI inputs, run

```sh
python3 -B tools/rust-qa/gui/build.py
python3 -B tools/rust-qa/gui/build.py --test
python3 -B tools/rust-qa/appearance/linux.py --binary artifacts/rust/gui-build/release/native-gui-assessment
```

The observer verifies the compiler inputs and native image, then creates
a fresh directory in `artifacts/rust/appearance/runs`. The
`--original-control` option uses a genuine pre-adapter GUI built from
`45dc03bc05d71766b19f4d0b56f37dbc92951ef9` alongside its original
build receipt. Contrast is measured when the running portal exports it.
[Native observer](../../tools/rust-qa/appearance/linux.py).

## Windows contrast theme observation

The shipping WPF `ThemeWatcher` reads the app light/dark preference and
accent color. Pinned winit 0.30.13 reports a light or dark theme to egui.
Its Windows dark-mode calculation returns light when high contrast is on.
Windows also supplies user-selected colors for window backgrounds, text,
buttons and selections. The contrast trial compares the ordinary Rust
window with these native values. [Shipping theme watcher](../../src/ImmichFolderWatch.App/Services/ThemeWatcher.cs) · [Pinned winit implementation](https://docs.rs/winit/0.30.13/src/winit/platform_impl/windows/dark_mode.rs.html) · [Microsoft contrast themes](https://learn.microsoft.com/en-us/windows/apps/design/accessibility/high-contrast-themes).

The Rust feasibility window reads the current mode at startup and on
`WM_SYSCOLORCHANGE`, `WM_SETTINGCHANGE` and `WM_THEMECHANGED`.
When the system palette changes, the owning thread invalidates a visible,
unminimized window once. It caches changes while hidden for the next frame.
egui paints text, buttons, disabled controls and selections with their
respective system colors. Turning contrast off makes the next root UI
inherit the current system theme. Five portable controls checked these
transitions, including the actual glyph meshes of a selected edit and
enabled and disabled buttons. Both canonical and retained sources passed
frozen compiler checks for Windows x64 and ARM64. The Windows feature
graphs and Cargo lock stayed byte-identical. [Native setting reader](../../tools/rust-qa/gui/src/windows_appearance.rs) · [egui colors and checks](../../tools/rust-qa/gui/src/windows_style.rs) · [Win32 high contrast messages](https://learn.microsoft.com/en-us/windows/win32/winauto/high-contrast-parameter).

The hosted Windows desktop assessment runs the observer after notification
and resource measurements. It verifies the native executable and Git inputs,
opens a synthetic profile and resolves the German filename label through
UI Automation. The recorder checks the HWND and PID at every point in the
label's physical crop before and after each capture. Two stable bitmap
samples from that label are retained in each mode.

The supervisor records the original flags, scheme name and eight system
colors. It creates a private input desktop and a synthetic profile. A
separate bounded worker opens the window there, reads the session palette
and captures its label. The supervisor owns both setting changes, restores
the input desktop and removes the profile after the worker's job closes.
It broadcasts from the subject's desktop and opens the native executable
and process by handle.
It requests an in-session contrast change and broadcast, then restores the
original mode even if the capture worker fails. It verifies the original
flags, scheme and colors through Win32. For a successful observation,
the high-contrast crop must show the actual system window background and
visible ink matching the system text color. The restored crop must match
the original dimensions and pixels. The receipts bind each original BMP
by its file digest. A separate digest covers only its dimensions and
ordered pixels so a header or row-padding change cannot count as a visible
change. Native results belong to
`artifacts/rust/gui-native/<target>/windows-contrast/` in the desktop archive.
[Observer and measurements](../../tools/rust-qa/appearance/windows.py) · [Win32 setting and rollback](../../tools/rust-qa/appearance/windows_colors.py) · [HIGHCONTRASTW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-highcontrastw) · [SystemParametersInfoW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow).

### Native baseline and scheme ownership at e796d30

Four native trials at `a1011bf` and `e796d30` stopped during the ordinary
appearance baseline. Each supervisor read flags `0x7e`, an empty scheme
name and eight colors. Each original result matched its Actions ZIP digest,
its GUI compiler receipt and all 54 source inputs from the corresponding
Git revision. None reached the first request to change the Windows setting.

| Revision | Windows x64 archive | Windows ARM64 archive |
| --- | --- | --- |
| [a1011bf run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45257863212) | [14869362811](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45257863212/artifacts/14869362811) | [14870570105](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45257863212/artifacts/14870570105) |
| [e796d30 run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266) | [14874798632](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14874798632) | [14873982830](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14873982830) |

Both x64 windows rendered the same 66 × 18 pixel filename label. In all
four BMPs, 857 of the 1,188 pixels had RGB (248, 248, 248). The raster
SHA-256 was `60b0c5288a6f7e28c00e0d1b1c59fe2b6395c57c6b1aff2946118000eddda8b1`.
Each capture process then exited with Windows status `0xc0000374` (heap
corruption). Its job closed and the synthetic PowerShell cache remained
in the worker's profile. On ARM64, Windows denied the original foreground
request on the default desktop both times. UI Automation found the label,
both guards refused to capture its pixels, and each subject drained and
removed its synthetic profile. Detached readback of all four archives is
in `artifacts/rust/hosted-appearance/readback.json`, SHA-256
`9f09896e8d17cf585d7554858784ae37fc5c899c6e043080dfd9937ade998b20`.

The Rust adapter and the Python observer both called `LocalFree` on the
scheme pointer from `SPI_GETHIGHCONTRAST`. Microsoft's Windows Forms
implementation documents that Windows retains this pointer across calls.
The adapter now reads only the flags. The observer copies the scheme into
its own string before its next call. The original crash reports contain
the exit status but no stack identifying a particular free. Native
high-contrast pixels and the restored label on both architectures remain
open until the corrected trial completes. [Windows Forms implementation](https://source.dot.net/System.Private.Windows.Core/Windows/Win32/PInvokeCore.SystemParametersInfo.cs.html)

Twenty portable observer tests passed, including repeated reads from
borrowed storage and profile cleanup after an abrupt child exit. Frozen
Clippy checks with warnings denied passed for the ordinary and retained
GUI sources under both Windows targets on Linux.
