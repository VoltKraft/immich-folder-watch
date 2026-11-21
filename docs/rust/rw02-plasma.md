# KDE Plasma tray integration

On 2026-11-21 the native Linux x64 Rust GUI started hidden, opened from
two actual Plasma panel clicks, hid after each native X11 close, and drained
on Quit. The KDE watcher removed the exited application's item. KWin and
Plasma Shell ran as separate Ubuntu 24.04.5 processes on the local Fedora
7.3.4-300.fc45.x86_64 kernel. KWin used llvmpipe on an isolated 1280 × 900
Xvfb display. The application rendered with Vulkan llvmpipe. [Native observer](../../tools/rust-qa/plasma/observe.py)
and [previous watcher lifecycle controls](rw02-linux-services.md).

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
demands exactly one color in its screen crop. The next dimensions of this
assessment are native ARM64, Plasma Wayland and installation of a released
application package.

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

On an Ubuntu Linux x64 assessment runner with Python 3.11 or newer,
Bubblewrap and tar, run the ordinary audited GUI build, then run these
commands from the repository root.

```sh
python3 tools/rust-qa/plasma/prepare.py --acquire
python3 tools/rust-qa/plasma/run.py --binary artifacts/rust/gui-build/release/native-gui-assessment
```

The first command creates `artifacts/rust/plasma/guest-amd64`. It downloads
approximately 402 MiB of package archives plus the 29 MiB base image into
the private cache. With the cache present, omitting `--acquire` reproduces
the guest offline in a fresh output directory. Package data is unpacked
inside Bubblewrap. Each assessment creates a fresh run directory. Retain
`artifacts/rust/plasma/runs/**` for the JSON receipts, the target-limited
bus trace, the GUI and desktop logs, and the panel and window images.
[Guest preparation](../../tools/rust-qa/plasma/prepare.py) and [launcher](../../tools/rust-qa/plasma/run.py).
