# GNOME Wayland input, monitors and scale

The integrated Linux x64 assessment committed Japanese input from both IBus
Anthy and Ubuntu Noble’s Mozc on a private GNOME Wayland seat without a
presentation override. The same 640 × 400 logical window committed buffers
at 100%, 200% and 125%. An earlier build lost its Japanese commit in the
default presentation run. Both revisions are indexed below.

## Earlier Anthy comparison

The private desktop used GNOME Shell and Mutter 51.1, IBus 1.5.35, ibus-anthy
1.5.18, Anthy Unicode 1.0.0.20260213, AT-SPI 2.62.1, libwayland 1.26.0 and
Mesa lavapipe 26.2.7. The tested native release executable has SHA-256
`5bd230d24989fc251b789bb152afdf78e5a4353fda1150e809f6a250ef61af3f`.
Its build record binds the Rust 1.100.0 toolchain, locked graph, application
sources and fonts. The test driver adds operating-system processes. Its Python
code is development-only. [Base GUI assessment](rw02-native-gui.md).

A disposable GNOME profile configured the installed `anthy` IBus source. The
driver checked the active global engine, focused input-context path and
running Anthy engine process. A Mutter RemoteDesktop virtual keyboard tabbed
to the titled application's filename field and cleared it. Pressing the Latin
`a` key produced `zwp_text_input_v3.preedit_string("あ", 3, 3)`. The cursor
offsets count UTF-8 bytes. Return produced `commit_string("あ")` on that
same object. Both the compositor and the app recorded these events. The
object had entered the app's titled surface and the app had enabled text
input. egui reported a nonempty one-character preedit and one-character
commit. An independent AT-SPI read returned `あ` in the focused entry
`Dateiname`. The recorded cursor rectangle uses surface-local coordinates.

Without the Mesa presentation override, the same binary and synthetic keystrokes
also produced a Japanese preedit. The client then disabled and re-enabled its
Wayland text input. The traces show ordinary Return key events and no Japanese
commit string. Six seconds later the filename entry was empty. The indexed
counterexample describes that earlier executable and driver combination.
Physical IME hardware, additional engines and visible Japanese glyph shapes
require their own evidence.

## Monitor transitions

The driver configured two independent Mutter virtual connectors through
`DisplayConfig.ApplyMonitorsConfig` with temporary scope. Native
Super+Shift+Right and Super+Shift+Left moved the focused window. Between the
two keystrokes the driver changed the occupied display's scale while the
window stayed on that connector. The table gives one combined run.

| Action | Connector | Logical display origin | Logical display size | Preferred scale (120ths) | Committed client buffer |
| --- | --- | --- | --- | ---: | --- |
| Open on primary | Meta-1 | 0, 0 | 2560 × 1440 | 120 | 640 × 400 |
| Move right | Meta-0 | 2560, 0 | 960 × 540 | 240 | 1280 × 800 |
| Rescale the secondary | Meta-0 | 2560, 0 | 1536 × 864 | 150 | 800 × 500 |
| Move left | Meta-1 | 0, 0 | 2560 × 1440 | 120 | 640 × 400 |

For each row, the client's xdg-output position and size matched Mutter's
current configuration. The same titled root surface received the
`wp_fractional_scale_v1.preferred_scale` values. The client issued
`wl_shm_pool.create_buffer`, attached that buffer to the root surface and
committed it. The server trace corroborated buffer creation, attachment,
commit and the advertised scale. The viewport stayed 640 × 400 logical
units. The two moves each had an output leave and enter. The focused Wayland
keyboard objects were recorded separately from output membership.

AT-SPI reported frame origin (0, 0) in both SCREEN and WINDOW coordinates at
all four positions, including on the output whose logical origin was
(2560, 0). Its reported width and height followed the four physical buffer
sizes. Clients can observe output geometry, surface-local geometry and the
compositor's output choice. The pinned winit 0.30.13 Wayland adapter returns
`NotSupportedError` from `inner_position` and `outer_position`, and its
`set_outer_position` method has an empty body. AccessKit's winit 0.34.2
Unix adapter uses a default origin when the winit query fails. The observed
AT-SPI screen origin cannot establish a global window position or its
restoration. A physical display, cable hotplug and hardware GPU were outside
this virtual test. [Reviewed graph](../../tools/rust-qa/gui/Cargo.lock).

## Reproduction and provenance

From the repository root, use the native assessment executable and its
adjacent `.inputs.json` build record. The existing `--input`, `--ime` and
`--screen-reader` paths retain their separate X11/bare-Mutter lifecycle and
accessibility runs. These optional GNOME modes start their own private
session and share a single native window when both are selected.

```sh
subject=artifacts/rust/performance/subjects/native-map-confirmed/native-gui-assessment
python3 tools/rust-qa/gui/native.py --backend wayland --binary "$subject" --wayland-ime --present-mode mailbox
python3 tools/rust-qa/gui/native.py --backend wayland --binary "$subject" --monitor-changes
python3 tools/rust-qa/gui/native.py --backend wayland --binary "$subject" --wayland-ime --monitor-changes --present-mode mailbox
python3 tools/rust-qa/gui/native.py --backend wayland --binary "$subject" --wayland-ime --monitor-changes
```

The launcher uses Bubblewrap with a fresh home, settings, session bus, private
network, display and PID namespace for each invocation. GNOME Shell uses the
private bus for system-service lookups too. The subject receives only Wayland
display connectivity. The existing Xvfb/Xvnc helper runs inside the same
namespace for driver bootstrap. `driver.json` binds driver inputs to hashes,
`native-inputs.json` records the active compositor, Wayland libraries, Mesa
driver and engine inputs, and `results.json` preserves a failed observation
when the command exits nonzero. The two protocol logs, display service states
and accessible snapshots stay under `artifacts/rust/gui-run/`. Run
`sha256sum -c evidence.sha256` from a GNOME run directory to verify its files.

## Local evidence

| Run directory | Observation | Indexed file | SHA-256 |
| --- | --- | --- | --- |
| `wayland-ery0jasw` | GNOME, combined Mailbox pass | `evidence.sha256` | `9ccc71f308a6ee8d908a994bee47641ee54e69c3e0144957a38746e38b174add` |
| `wayland-mq_big0r` | GNOME, default presentation, monitors pass | `evidence.sha256` | `12b92c62c316e2f1a8684de0cc885c25682296430abbb2e9d134ea8b96ca82c0` |
| `wayland-1huz160e` | GNOME, one monitor, Mailbox IME pass | `evidence.sha256` | `c226b921ca8bcfffc71a21725de28fba7fab3099e12df6b7115d515ae244dc24` |
| `wayland-7lzck8wo` | GNOME, default presentation, native IME commit failed | `evidence.sha256` | `1142cfecbf0e8767526367e9f52aa18f5dce94555736874cd6c67d5632aa6def` |
| `x11-hcgul15m` | X11 lifecycle, XIM and Orca pass | `results.json` | `9772b15eb6fa33ff218c3fa4c6f138e3ab201645dab7f25c3e7cbf269a921a65` |
| `wayland-si6_x0pe` | Bare Mutter lifecycle, AT-SPI and Orca pass | `results.json` | `2e0ea2a3c551dd939b77bf8b878861873aa2d03c0be686aba3682ff859a1a5ae` |

The legacy runs each passed all four lifecycle cases, named keyboard and
clipboard checks, and the real private Orca speech check. The X11 run also
passed Anthy via XIM. Each input record identifies the driver source hashes used
for its execution.

## Integrated release and Ubuntu Mozc

The integrated executable SHA-256
`80898c73bf97c9d6622ef837cd5361810b041e5d007a1fe742d32ad7921c1002`
passed the combined IME and monitor test with each engine. Both results
record a null Mesa presentation override. The executable logged
`GRAPHICS_PRESENT generation=1 mode=Mailbox driver=llvmpipe desktop=Wayland`
on the reported Vulkan CPU adapter. Its own Wayland software-renderer
selection supplied that mode. The packaged-engine observations are independent
of the older failed default-presentation control.

The Mozc run used the signed Ubuntu 24.04 amd64 binaries and a Fedora 45
GNOME Shell 51.1 compositor. The private install-free overlay contained the
Noble `ibus-mozc`, `mozc-data` and `mozc-server` packages at
`2.28.4715.102+dfsg-2.2build7`, protobuf `3.21.12-8.2build1` and Abseil
`20220623.1-3.1ubuntu3`. The acquisition checked the Ubuntu Archive Automatic
Signing Key (2018) fingerprint
`F6ECB3762474EDA9D21B7022871920D1991BC93C`, verified the signed Noble
release, and followed its SHA-256 hashes through both package indices to the
five original Debian archives. Only the private process saw the extracted OS
files. The archived packages keep their distro copyright notices.
[Canonical signing-key verification](https://documentation.ubuntu.com/security/software-integrity/image-verification/),
[Noble signed release](https://archive.ubuntu.com/ubuntu/dists/noble/InRelease).

The actual component XML identified `com.google.IBus.Mozc` and
`/usr/lib/ibus-mozc/ibus-engine-mozc`. The engine's own `--xml` query
reported `mozc-jp`. The test set Mozc's documented `active_on_launch`
option in a new per-user profile, selected `mozc-jp` in the GNOME input
sources and observed the active global engine and input context. It verified
the running IBus process and the separate `/usr/lib/mozc/mozc_server`
conversion process. The observed server hash was
`bbf20e0971d85aba83ad9da75fb81b22dd95b22ae152ecb043e0e37f4e444040`.
Typing `a` produced `preedit_string("あ", 3, 3)`. Return produced
`commit_string("あ")` on the same focused object's client and compositor
traces. The private AT-SPI reader read `あ` from the focused filename field.
All four monitor geometry and buffer observations in the table above passed
in that session. The Fedora Anthy control independently passed the same
end-to-end checks on the same executable. [Mozc IBus configuration](https://github.com/google/mozc/blob/master/docs/configurations.md#activate-mozc-on-launch).

| Integrated Linux x64 evidence | SHA-256 |
| --- | --- |
| `artifacts/rust/wayland-mozc-noble/runs/wayland-mtbgfe3u/evidence.sha256` | `4818fa95a0f8447ebd8755d246aa33f5c21211aef24738c44903e9c7396a0ccf` |
| `artifacts/rust/gui-run/wayland-pz0ts8v_/evidence.sha256` (Fedora Anthy) | `f3715b0981803cd61d00dc434581835d130e5f6f50a1ebecaba4f4dd68fcf642` |
| `artifacts/rust/wayland-mozc-noble/packages.json` (signed-index package records) | `c29c51b6040a5f3504a64a29587e9c2072bc902b120978ea4950cde558d9baaf` |

## Ubuntu 24.04 runner prerequisites

The attempted `ibus-anthy` installation on Ubuntu 24.04 returned no installation
candidate. On Noble, provide `gnome-shell`, `ibus`, `gir1.2-ibus-1.0` and
`ibus-mozc` with its `mozc-server` and `mozc-data` dependencies alongside
the normal Linux GUI-test packages. Select `--ibus-engine mozc`. Fedora's
previously exercised selection stays available through `--ibus-engine anthy`,
the default when `--wayland-ime` is given. The probes require native
RemoteDesktop and DisplayConfig services, virtual monitors, text-input-v3,
viewporter and fractional-scale-v1. The driver enables the private
framebuffer-scaling option where Mutter accepts it.
[Ubuntu Noble GNOME Shell](https://packages.ubuntu.com/noble/gnome-shell),
[Ubuntu Noble package archive](https://archive.ubuntu.com/ubuntu/dists/noble/InRelease).

```sh
subject=artifacts/rust/gui-build/release/native-gui-assessment
python3 tools/rust-qa/gui/native.py --backend wayland --binary "$subject" --wayland-ime --ibus-engine mozc
python3 tools/rust-qa/gui/native.py --backend wayland --binary "$subject" --monitor-changes
```

The two commands use independent private sessions so either result survives
a failure in the other. A combined command still exercises the same native
window. It writes the monitor observations and IME commit separately and
reports each failed observation.

## Ubuntu GNOME 46 display configuration

In hosted run `44835826452` at `8b071ab`, both Noble architectures
retained physical layout mode 2. The secondary 1920 × 1080 connector
offered only scales 1 and 2, and reported all 1920 × 1080 logical units at
2×. The independent geometry check stopped the combined run before its Mozc
test. Ubuntu's `mutter-common 46.2-1ubuntu0.24.04.18` declares the
`experimental-features` key as a string array. Its schema description
includes `scale-monitor-framebuffer`, while the GSettings range describes
only the array type. Upstream GNOME 46 uses an enumerated flags key.
[Ubuntu Mutter source](https://launchpad.net/ubuntu/+source/mutter/46.2-1ubuntu0.24.04.18),
[upstream Mutter schema](https://github.com/GNOME/mutter/blob/46.2/data/org.gnome.mutter.gschema.xml.in#L93-L111).

The fixture range-checks the complete requested value, preserves the private
profile's existing entries and reads the saved value back before starting
GNOME Shell. `monitor-settings.json` records the exact range, values and
availability on that installation. The driver then requires Mutter to
report logical layout mode 1 and the requested connector configuration.
The independent protocol and committed-buffer checks still cover all four
transitions. A compositor with built-in fractional scaling can pass those
checks without an experimental settings key.
