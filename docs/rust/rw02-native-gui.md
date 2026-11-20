# RW-02 native GUI assessment

On 2026-11-20 the Linux x64 assessment started without allocating a native
window, accepted activation on a private session bus and reopened after a native
close. The isolated test executable uses the existing `desktop-lifecycle`
policy and the [reviewed GUI profile](rw02-gui-dependencies.md). Its separate
[Cargo workspace](../../tools/rust-qa/gui/Cargo.toml) and generated lockfile
belong to the development fixture. All 374 third-party lock records, checksums
and dependency edges match the assessed dependency graph. The fixture adds
direct Linux references to the already selected futures-lite 2.6.1 and zbus
5.19.0 with its asynchronous I/O features.

## First-frame regression

The original `with_visible(false)` prototype created its eframe event loop
during background startup. Xvnc reported a mapped 640 × 400 window 177 ms
after launch. At 835 ms the app reported a visible window, background intent
and five UI passes. Foreground startup, native close, reopening and quit worked.
In eframe 0.37.0, the native integration shows the window after its first paint.
The resolved winit Wayland adapter also implements `Window::set_visible` as an
empty method. The original external observation has SHA-256
`99f6aeaecfe458c4db87f19094e683ba9529b93c4b036828f7051c58824a79b4`.
The preserved sources, fonts, executable, X server and D-Bus logs reside under
`artifacts/rust/gui-run/eager-first-frame/`. The tracked
[evidence index](../../tools/rust-qa/gui/evidence/native-linux-x64.sha256)
binds the raw records retained under the ignored artifact directory.

The revised supervisor blocks on its bounded control queue before creating the
first native window. An acknowledged tray registration permits background
startup. Failure of the first registration reveals the UI. A native close
releases the eframe window and returns to the same supervisor. Model state and
the activation endpoint survive. A visible window receives repaint wakeups on
control delivery. Quitting before the first activation completes without
initializing the renderer. No upstream crate patch is required.

## Isolated native runs

Both native Linux backends selected the Mesa lavapipe Vulkan CPU adapter
reported as llvmpipe (LLVM 23.1.5, 256 bits). Xvnc 1.16.2 exposed independent
root-window map and unmap notifications. Mutter 51.1 used a headless virtual
monitor, with X11 disabled for the subject. Its compositor-side Wayland trace
identifies the titled xdg_toplevel, committed root-surface buffers, close
requests and surface destruction. The driver uses Mutter's private virtual
keyboard for Alt+F4.

| Scenario | X11 | Wayland |
| --- | --- | --- |
| Background start, absent StatusNotifierWatcher | Window mapped | Toplevel buffer committed |
| Background start with registered item | Zero maps before SNI activation | Zero maps before SNI activation |
| Quit before first show | Zero maps and zero UI passes | Zero maps and zero UI passes |
| Close, stay active, reopen through a separate desktop client | WM_DELETE_WINDOW, unmap, map | Alt+F4, compositor close, destruction, new mapped surface |
| Visible startup and explicit quit | Window opened and process drained | Window opened and process drained |

The isolated Linux app exports real D-Bus methods at the SNI item and
freedesktop application paths. A synthetic watcher registers the item on the
private bus. The absent-tray case runs with no watcher name owner. The fixture
currently covers primary activation and initial registration. Desktop-panel
rendering, watcher replacement, menu parity, native notifications, portals,
physical GPU/device loss, real multi-monitor scaling and an engine running
through shutdown still require evidence. See the [acceptance record](acceptance.md)
for target and stage status.

## Keyboard, accessibility and rendering

On both backends a separate AT-SPI client read the titled frame, named
filename entry, password role and language button. Native Tab events moved
focus through Dateiname, Kennwort and English. The fixture accepted three
synthetic password characters. AT-SPI returned `•••`. Space activated the
language button, updated the field names to Filename and Password and retained
the button's focus. Ctrl+C, clearing the field and Ctrl+V restored
`Grüße – Sommer.jpg`. The X11 observer recorded a clipboard selection owner.
Mutter recorded a Wayland data-device selection with input serial 56.
The indexed `x11-kl1urbp4` and `wayland-74ulqton` records contain source
and compiler hashes, native window events and accessibility trees. Both runs used executable SHA-256
`06abf418bfefa3a0b21011663e2ba9d234767c6ebc21d87c84f27f52c1bbd4d9`.
The release build, rustfmt check and frozen all-target Clippy check with
warnings denied passed with pinned Rust 1.100.0 on Linux x64.

With default Mesa presentation on the virtual Wayland monitor, two key presses
arrived at the compositor. The application model and accessibility tree had
one character after the three-second deadline. A repeat with a private PipeWire
monitor consumer also stopped at one character. Selecting the Mesa Mailbox
present mode passed the lifecycle and keyboard tests twice on this software
adapter. The stack decision still requires testing display timing and renderer
selection on the supported hardware and desktops. The index lists the default
input observation and both raw compositor traces.

The optional X11 IME run established an IBus XIM selection on the private
server. A Unicode-entry shortcut with the US engine produced literal digits.
Selecting the installed Anthy engine returned a closed-connection error before
a composition reached egui, including with a synthetic configuration for its
system dictionary. Native preedit, commit and visual CJK coverage remain open.
Orca speech, hardware keyboards, mixed-direction editing and selections in
additional scripts still require explicit runs. The fixture embeds the
reviewed Latin Sans and Mono fonts.

## Reproduction

Use a native pinned Rust toolchain and the reviewed font files under
`rust/assets/fonts`. Supply a Cargo registry cache containing the locked crates.
Run the Linux checks from the repository root.

```sh
python3 tools/rust-qa/gui/build.py
python3 tools/rust-qa/gui/build.py --clippy
python3 tools/rust-qa/gui/native.py --backend x11 --input
python3 tools/rust-qa/gui/native.py --backend wayland --input --present-mode mailbox
```

The offline build mounts its compiler, source, registry and fonts read-only
inside bubblewrap. Each invocation of the observer creates a fresh artifact
directory and private mount, network, PID, IPC and user namespaces. The tests
run in a synthetic home with a private D-Bus and display. The default software
driver comes from the native Mesa lavapipe manifest. `--binary` accepts a
separately built native assessment. The build script writes the executable
digest, compiler identity and input hashes alongside its binary. The observer
embeds that record when supplied alongside the tested executable.

On the originating host, check its retained records with
`sha256sum --check tools/rust-qa/gui/evidence/native-linux-x64.sha256`.

Use the Wayland command without the present-mode option for the default
presentation diagnostic. Add `--capture` to attach a private PipeWire/GStreamer
consumer to the virtual monitor. The optional XIM diagnostic uses
`--backend x11 --input --ime` with IBus, ibus-x11, Anthy and xprop installed.
The ordinary Linux observers use bubblewrap, Xvfb or Xvnc, libX11, libXdamage,
libXtst, gdbus, PyGObject and Mesa lavapipe. Wayland additionally uses Mutter's
headless, virtual-monitor and RemoteDesktop interfaces. The accessibility
case uses at-spi2-core and its introspection bindings.

The Windows fixture accepts an initial tray result on its inherited input pipe
and bounded open, close or quit commands. The [Windows observer](../../tools/rust-qa/observe-windows-gui.py)
owns the OS-specific observation. Linux results above cover the native Linux
x64 executable only.
