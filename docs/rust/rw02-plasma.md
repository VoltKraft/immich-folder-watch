# KDE Plasma tray integration

On 2026-11-21 the native Linux x64 Rust GUI started hidden, opened from
two actual Plasma panel clicks, hid after each native X11 close, and drained
on Quit. The KDE watcher removed the exited application's item. KWin and
Plasma Shell ran as separate Ubuntu 24.04.5 processes on the local Fedora
7.3.4-300.fc45.x86_64 kernel. KWin used llvmpipe on an isolated 1280 × 900
Xvfb display. The application rendered with Vulkan llvmpipe. [Native observer](../../tools/rust-qa/plasma/observe.py)
and [previous watcher lifecycle controls](rw02-linux-services.md).

Ubuntu x64 repeated two actual X11 pointer clicks on the Plasma-owned tray
in `a66e045`. Both delivered `Activate` from the shell's bus connection to
the Rust item, reopened the same window and were followed by a native close.
Quit drained the application and removed the item. The result SHA-256 is
`c4d3ac2c06725eb072249bc3da929cb5cd287ddaf684af18bd48b9b8a85d2d50`.
[Verified archive](rw02-native-gui.md#native-follow-up-at-a66e045).

## Native Ubuntu ARM64 panel at 6af7100

At `6af71006c17e4f3014f6046ccd32b2f9dd192c72`, two X11 pointer clicks on
the branded item in the Plasma panel reopened the hidden Rust GUI on a
native ARM64 runner. The shell's D-Bus messages 248 and 250 carried the
observed screen coordinates (163, 878) to the application's registered
item. Both openings mapped window `0x1a00002`. Two window-manager close
requests hid it. Quit drained after 12 UI passes and KDED removed the item.
[Native ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/job/137590852330) · [Original archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14805991978).

Independent decoding of the two 22 × 28 button images counted 303 and
294 colors, including 277 and 259 gold pixels. The neighboring button
had seven colors each time. The first button image matched the same region
of the full 1280 × 900 screenshot byte for byte after RGB decoding.
KWin, KDED, the watcher, Plasma Shell and the GUI reported AArch64 ELF
machine 183. KDED owned the watcher. The loaded Qt Core, Qt Quick and XCB
objects in the shell and the watcher plugin in KDED matched the actual
ELF files extracted from the four authenticated ARM64 packages.

The GUI executable SHA-256 was
`aed7d2f2e5d9e67c5f249710e25de72090df8d0ad60433d4ad8f7ec132899b3c`.
The archive bound its native build to 23 application inputs and seven
observer sources. All five embedded icon frames matched the project
artwork. The original result had SHA-256
`f754c5637396732b2bdab1dfe38ecd36142e9d43368cc5be8c838dc941a6bf00`,
the Actions archive `39953a567e721e356eeb54a8587848e94cfe117c6ecdc88e6e875ea366fd9015`,
and the independent readback `24a65cb2bea2f7ad609d5d226067973f77e8f4058f7220baf2cab7d5bfced522`.
The 21 original panel files are under `plasma/runs/plasma-yb6be126/` in
that archive.

Ubuntu x64 repeated the two panel clicks in the same run. D-Bus serials
248 and 250 carried the click at (163, 878). KWin mapped the same
`0x1a00002` window each time. Two native closes hid the window, Quit drained
after 11 UI passes, and the watcher removed the item. The original panel
result SHA-256 is `2f5821b945108573fe5467a5c0215b192b9c13778b3ffe1389c421c797e5c673`.
Independent image, executable and library readback produced SHA-256
`7ed39ec64ce3eee3a4b3be11bc98ffa8a4b405c1678b4a7ebd731e54569d715a`.
[Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14806677718).

## The visible tray entry

The original Rust GUI registered `org.example.IfwGuiProbe/StatusNotifierItem`.
The shell exposed a push button named **Desktop input probe**, yet its entire
22 × 28 screen rectangle was the panel background. The item exported its
title and status without an icon. The installed Plasma applet uses the
item's icon pixmap or theme name when drawing this button.
[Plasma 5 system tray implementation](https://invent.kde.org/plasma/plasma-workspace/-/blob/v5.27.12/applets/systemtray/package/contents/ui/items/StatusNotifierItem.qml).

The Linux item now exports the project's folder artwork in `IconPixmap`.
The D-Bus property has signature `a(iiay)`. Its 16, 22, 32, 48 and 64 pixel
frames use straight-alpha ARGB32 in network byte order. The test guest
recreates all 32,656 bytes from the canonical SVG and checks each frame
returned by the application. The application embeds those bytes and uses
its existing zbus dependency. The artwork SHA-256 is
`402073a5d81779a92c54629de7fb16a511c0764391bcdec060095c691b3d0a31`.
[Project artwork](../../assets/branding/logo.svg), [reconstruction](../../tools/rust-qa/plasma/brand.py)
and [StatusNotifierItem icon specification](https://specifications.freedesktop.org/status-notifier-item/latest-single/#icon-pixmap).

| Native x64 observation | Original item | Branded item |
| --- | ---: | ---: |
| Colors in the button before the first click | 1 | 303 |
| Gold-colored pixels before the first click | 0 | 277 |
| Colors / gold pixels before the second click | 1 / 0 | 294 / 259 |
| Colors in the neighbouring tray arrow | 7 | 7 |
| Panel activations opening the actual Rust window | 2 | 2 |

The original native binary `a94b3ffa9545` and the first corrected binary
`156655d94247` produced these counts in `plasma-eyruvb9v` and
`plasma-k1odgpap`. A freshly reconstructed guest repeated the original
control in `plasma-cl0sinbp` and observed the same counts for the integrated
binary `afb90507e465` in `plasma-acgjk77x`. Both final runs used the same
observer and rebuilt the icon bytes from the project SVG.

The matching probes began with an empty registered-item list. The D-Bus
watcher belonged to KDED, and the panel's `org.kde.plasma.systemtray`
applet belonged to the observed Shell PID. The driver obtained the
button's bounds from that PID through AT-SPI. Immediately before each
XTEST click it verified the actual pointer position and the Shell-owned
X11 dock beneath it. The private bus monitor saw two `Activate(163, 878)`
calls from the Shell to the Rust item. The external X11 observer verified
the window title, owning PID and mapped state through KWin. Both native
closes hid the window. Quit removed the registration and the GUI logged
`DRAINED`. [Source-bound observations](../../tools/rust-qa/plasma/evidence.sha256).

The frame check requires at least eight colors and twelve gold-colored
pixels in the actual button. AT-SPI supplies the button name and the screen
capture supplies the visible pixels. The negative control accepts only the frozen
original binary and build receipt, requires missing icon properties and
demands exactly one color in its screen crop. The ARM64 inputs and native
test are described below. Plasma Wayland and installed-candidate behavior
have separate evidence requirements.

## Private Noble runtime

The x64 guest contains the signed Ubuntu Base 24.04.5 image and 696
Ubuntu binary packages. The release, updates and security InRelease
signatures validated against Ubuntu's archive keyring. Every selected
package's name, version, architecture, pool path, size and SHA-256 matched
the signed binary index. The separate CD image key authenticated the base
image checksum. Reconstruction checks each downloaded archive, every
package's complete copyright-file digest, and the KWin, KDED, Shell,
watcher and applet payloads before execution. The runtime uses a temporary
home, two private buses, a private X server and separate user, PID, mount,
network, IPC and UTS namespaces. The accessibility, artwork conversion and
shell packages are external QA inputs. [Image checksums](https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/SHA256SUMS),
[release and executable pins](../../tools/rust-qa/plasma/ubuntu-amd64.json)
and [package and notice inventory](../../tools/rust-qa/plasma/ubuntu-amd64.tsv).

| QA package | Exact Ubuntu version | Licensing of the reviewed code |
| --- | --- | --- |
| plasma-workspace | 4:5.27.12-0ubuntu0.1 | Default GPL-2.0-or-later. The displayed StatusNotifierItem QML declares LGPL-2.0-or-later. The package notice covers its other components. |
| kwin-x11 | 4:5.27.11-0ubuntu3 | Default GPL-2-or-later. The package notice records the BSD, LGPL, documentation and other component terms. |
| kded5 | 5.115.0-0ubuntu5 | Default LGPL-2. The notice also identifies LGPL-2-or-later files. |
| libgdk-pixbuf-2.0-0 | 2.42.10+dfsg-3ubuntu3.3 | The main notice combines LGPL-2-or-later, LGPL-2.1-or-later and CC0-1.0. |
| librsvg2-2 | 2.58.0+dfsg-1ubuntu0.1 | Default LGPL-2-or-later with additional file-specific terms. |

## Reproduction

In the desktop runs at `549066f` and `ba02f8b`, the public binary-pool
request received HTTP 403 on both architectures after fetching Ubuntu Base.
The corresponding Noble source acquisitions also received HTTP 403. The
logs omit the affected package names. Both Plasma package manifests now
name the dated Ubuntu snapshot corresponding to their signed review.
Independent retrieval matched all six original InRelease files including
their archive signatures, and the architecture-specific `libxcb-keysyms1`
files matched their frozen sizes and SHA-256. The snapshot times are
`20261121T210000Z` for x64 and `20261123T100000Z` for ARM64. The package
and notice checks still apply to every file at reconstruction.
[Ubuntu Snapshot Service](https://snapshot.ubuntu.com/) · [First native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471) · [Second native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405).

The local x64 guest rebuilt offline from Ubuntu Base and all 696 reviewed
archives. Its first probe used a Fedora-linked binary. The Noble loader
reported missing GLIBC_2.43 and GLIBC_2.44 before the application started.
The matching Noble-linked Rust binary `e346e5e7` then registered its icon
and reopened through two real panel clicks. The panel list was empty after
Quit. The new result in
`artifacts/rust/plasma/snapshot-native-check/plasma-qrvees5k/result.json`
has SHA-256 `746f9f2ebd381b513296ec64e3f92e9944d77128ff3437ba159998972eab6878`.

The private ARM64 guest uses the Ubuntu Base 24.04.5 ARM64 image and 691
packages totalling 415,479,768 bytes. APT resolved them against the ARM64
image's installed-package database. Independent verification authenticated
the Base checksum with the Ubuntu CD image key and all package fields
against the three signed Noble releases and their six ARM64 main/universe
indexes. Of these packages, 598 target ARM64 and 93 are architecture
independent. The review checked all 691 archive checksums and complete
copyright files. The shared package names have the same versions and notices
as x64. The two ARM64-specific C preprocessor packages carry the same
version and notice as their x64 counterparts. The GUI uses these tools as
external test inputs. [Ubuntu Base image](https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/) · [Ubuntu Ports repository](https://ports.ubuntu.com/ubuntu-ports/dists/noble/InRelease) · [ARM64 runtime review](../../tools/rust-qa/plasma/ubuntu-arm64.json) · [Frozen package records](../../tools/rust-qa/plasma/ubuntu-arm64.tsv).

The native launcher checks the ELF architecture of the Rust executable,
Python, KWin, KDED, Plasma and the selected binary libraries. During the
panel run the observer reads the running service executables and the
Qt Core, Qt Quick, XCB and watcher libraries mapped in the shell and KDED.
Both the frozen x64 blank-icon control and a fresh x64 build from
`725f1cd` passed the new observer on an isolated local display.
The ARM64 run above also passed on Ubuntu's own kernel.
[Native workflow](../../.github/workflows/rust-desktop-assessment.yaml).

On an Ubuntu Linux x64 or ARM64 assessment runner with Python 3.11 or newer,
Bubblewrap and tar, run the ordinary audited GUI build, then run these
commands from the repository root.

```sh
python3 tools/rust-qa/plasma/prepare.py --acquire
python3 tools/rust-qa/plasma/run.py --binary artifacts/rust/gui-build/release/native-gui-assessment
```

The first command creates `artifacts/rust/plasma/guest-amd64` or
`artifacts/rust/plasma/guest-arm64` and populates its private cache.
With the cache present, omitting `--acquire` reproduces
the guest offline in a fresh output directory. Package data is unpacked
inside Bubblewrap. Each assessment creates a fresh run directory. Retain
`artifacts/rust/plasma/runs/**` for the JSON receipts, the target-limited
bus trace, the GUI and desktop logs, and the panel and window images.
[Guest preparation](../../tools/rust-qa/plasma/prepare.py) and [launcher](../../tools/rust-qa/plasma/run.py).
