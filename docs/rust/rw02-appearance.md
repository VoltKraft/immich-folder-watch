# Linux system appearance

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
