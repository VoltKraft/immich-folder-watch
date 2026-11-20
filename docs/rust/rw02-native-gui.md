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

The first hosted Ubuntu builds at `167a03d` authenticated the locked GUI
inputs and reached the isolated build launcher. Both architectures received
`RTM_NEWADDR: Operation not permitted` during loopback setup. The hosted
fixture now checks the caller UID and private namespace capability before
building. It can provision a temporary, root-owned test launcher with an
AppArmor user-namespace grant specific to that executable on the disposable
VM. [Hosted run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44816389612).

At `06298d9` the Ubuntu x64 and ARM64 fixtures successfully built the native
GUI and passed all four lifecycle scenarios independently under both X11 and
Wayland. The two executables had SHA-256
`c9f365cf40035653bd0e0f409aace88c8fea882e4f46306fbced9b71247db9fd`
and `54f1f14022792793f1e85b2bdbc5b051dfd41b9cd4cb0c8c167f20e268dd5a92`
respectively. Their Actions ZIPs matched `854b44df94f8d891b152562092839eeb272bd539114504c50f4f296e4bdbcd69`
and `ee549449e778561144fb94741953379eefb82c26cf46793d7576167aa1564366`.
In the following input scenario the private AT-SPI launcher reported a dconf
write failure. The observer saw only the desktop root on both backends.
The revised fixture gives the launcher an in-memory settings backend, reads
back its enabled state and identifies the tested application by its native
process ID. This passed the complete keyboard, masking and clipboard checks
on local X11 and Wayland. Hosted input results remain pending.
[Hosted logs and retained per-backend results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44818255659).

At `4961746`, both Ubuntu architectures also passed AT-SPI on both X11
and Wayland. All four independent reports recorded focus passing through
Dateiname, Kennwort and English, three protected bullets and the Unicode
clipboard round trip. The x64 and ARM64 archives matched SHA-256
`5c805eca86d2a14317477a370c8450c7a8c36ff8219e97d41d337407e8035b0d`
and `213838cd18cea87fbf6cecfcb4cd48b977aa4ceb72e50b19c88573b38c096feb`
respectively. A separate YAML archive comparison failed in that run.
[Native Ubuntu results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44820760903).

## Four native assessment archives

All four archives at `167a03dcb414ab1172713520a77b7517a6046b13` matched
the SHA-256 sums published by Actions. Both Windows machines rendered with
the DX12 Microsoft Basic Render Driver and the system FXC compiler. Each
passed foreground startup, fallback after tray refusal, hidden startup followed
by activation, and quitting before the first show. An independent WinEvent
hook saw zero show events in the last case and the subject recorded zero UI
passes. The three visible cases each closed through WM_CLOSE and reopened.
The tray availability input in these cases came from the test pipe. The
[Windows services fixture](rw02-windows-services.md) exercises the Shell
registration and shortcut APIs independently.

| Native host | GUI result | Actions archive SHA-256 |
| --- | --- | --- |
| Windows Server 2025 x64, build 26100 | Four DX12 lifecycle cases, executable `e5c15f31ade5ae35e91f31dc0688e737be3052a241ae5d40c8387d21a1b6e960` | `6e98768bea3bdf722d5f8d094ada0244c38f57ab47b16d180d62536e59b7737d` |
| Windows 11 ARM64, build 26200 | Four DX12 lifecycle cases, executable `efc7152a5ccd79d8533484709786cc24bcad7e024175d55045e541d9fe2d3840` | `8a00a511eaa349ff6fcbfc40316fd488f61a9c30d476a0c12e1e5df25afb4d0f` |
| Ubuntu x64 | Namespace setup denied before GUI execution | `ef9d072a8f6b65a3ca6b096b4122279bf32a8ec1921ba64ae192f1a3094921e6` |
| Ubuntu ARM64 | Namespace setup denied before GUI execution | `d93e9b44e39aba80c1e90a2083b4aed7d39729cf32b4bba020c1f04cb74a57df` |

On each of these hosts the [SQLite workload](rw02-storage-inputs.md) backed
up both live 24,752-byte WALs. The production C# readers using .NET 10.0.15
and SQLite 3.53.4 passed 40 assertions per host. All 15 independent
[transport scenarios](rw02-realtime-transport.md) passed per host. The
redirect target recorded zero requests and zero credentials. Verification
covered the 253 Windows or 254 Linux storage evidence files and all ten
indexed transport outputs in each archive.

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

### Native composition and screen-reader output

On Fedora x64 the X11 fixture started the actual Anthy 1.5.18 engine and
registered it on the private IBus 1.5.35 instance. Direct engine selection
and readback confirmed Anthy's `default` keyboard layout. The IBus CLI also
attempts a layout switch, which returned failure for that layout. A native
key press produced a nonempty IME preedit. Return produced a one-character
IME commit, and an independent AT-SPI client read `あ` from the filename
field. The fixture's two Latin fonts still require a CJK rendering check.
[IBus CLI implementation](https://github.com/ibus/ibus/blob/1.5.35/tools/main.vala#L477-L552).

Under both X11 and Wayland, Orca 51.1 followed the actual keyboard focus and
sent the control names and roles to Speech Dispatcher 0.12.1. It announced
the German filename and password, the English language button and the
renamed Filename field. The three password keystrokes produced exactly three
spoken mask symbols. eSpeak NG 1.52 generated non-silent samples for a
private ALSA file device. The sample-prefix hashes can be checked against
the retained raw files. These tests exercise the native accessibility and
speech stack with synthetic input and a software audio sink.

| Fedora x64 run | Native input and speech | Observed audio bytes |
| --- | --- | ---: |
| `x11-m34b3ex8` | Four lifecycle cases, AT-SPI, Anthy preedit and commit, Orca | 939,144 |
| `wayland-eoyrquw0` | Four lifecycle cases, AT-SPI and Orca under Mutter with Mailbox presentation | 743,308 |

Both runs used the measured executable SHA-256
`5bd230d24989fc251b789bb152afdf78e5a4353fda1150e809f6a250ef61af3f`.
Wayland composition, mixed-direction editing, other monitor configurations
and assistive technology on the remaining targets still require observations.
[Source-bound desktop evidence](../../tools/rust-qa/gui/evidence/native-linux-x64.sha256)
and [native speech observer](../../tools/rust-qa/gui/screen_reader.py).

## Reproduction

At `2e7ed89`, Windows x64 passed the full keyboard sequence. Focus traversed
Dateiname, Kennwort, English and Filename. Three keystrokes produced three
masks in both UI Automation patterns, the translated controls appeared, and a
Unicode filename completed a real clipboard round trip. Windows ARM64 confirmed
the same German names, password protection and access to the input desktop.
Its foreground request and coordinate-checked click did not acquire the test
window, so the observer withheld all keystrokes. Both desktops measured 96 DPI
on one 1024 × 768 monitor. The retry records the click location and active
console session. It can raise only the synthetic window before repeating the
owner/point checks. The corresponding downloaded x64 and ARM64 archives had
SHA-256 `cb2d3533ca1ee0ea2077fdd0c94887e49311a1a133208830ee57a69340f83eac`
and `20e7ef5cbb8bce2fa72358b614616735f914b13a9ba9499bf65ea3cea9479922`.
[Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828363871).

The separate [portable NVDA assessment](rw02-windows-reader.md) coordinates
the foreground driver with actual screen-reader announcements and records the
source of protected-character feedback.

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
Add `--screen-reader` to an input run with Orca, Speech Dispatcher, its eSpeak NG
module and its ALSA plugin installed to exercise native synthesized output.
The ordinary Linux observers use bubblewrap, Xvfb or Xvnc, libX11, libXdamage,
libXtst, gdbus, PyGObject and Mesa lavapipe. Wayland additionally uses Mutter's
headless, virtual-monitor and RemoteDesktop interfaces. The accessibility
case uses at-spi2-core and its introspection bindings.

The Windows fixture accepts an initial tray result on its inherited input pipe
and bounded open, close or quit commands. The [Windows observer](../../tools/rust-qa/observe-windows-gui.py)
owns the OS-specific observation. The local keyboard and compositor traces
come from Fedora x64.

The separate Windows `--input-only` case attaches the system UI Automation
client to the observed HWND and checks its process ID. The client reads German
and English control names, follows keyboard focus, checks the protected
password field and verifies a Unicode clipboard round trip. Each keyboard
operation requires the observed HWND to own foreground input. The report
retains the observed DPI, monitor size, protected-pattern behavior and the
last completed input checks if the host cannot supply interactive input.
At `11e4e6f` both Windows UI Automation clients identified Dateiname, Kennwort
and English and the protected password property, on a 1024 × 768, 96 DPI monitor.
On x64, Tab reached both edit controls and the native application received
one synthetic password character. The observer then met a Windows sharing
violation reading the application's active log. The observer now uses a
shared read handle and matches complete lines. On ARM64 the test window
failed the foreground check before any keystroke. The follow-up records the
input desktop, requests focus through the owned UI Automation element and
can click its bounds only after checking the live screen point against that
HWND and PID. Each keystroke still requires the input desktop and foreground
window to match. [Native inputs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44825008977)
and [Windows foreground rules](https://learn.microsoft.com/windows/win32/winmsg/window-features).
[Windows UI Automation observer](../../tools/rust-qa/observe-windows-input.ps1).
