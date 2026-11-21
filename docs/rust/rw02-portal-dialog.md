# RW-02 native Linux folder dialogs and desktop portals

On 2026-11-20, private Fedora 45 x86-64 sessions showed the GTK folder
chooser as a child of a Rust window under both X11 and Wayland. Selecting a
directory from an installed test Flatpak returned a real Documents FUSE grant.
A fresh process lost access after revocation. GNOME Shell displayed and removed
the app's notification, and the Background portal created, disabled and denied
autostart for the same private app identity.

The standalone application uses winit 0.30.13, the existing `safe-fs` crate
and zbus 5.19.0. Its release executable had SHA-256
`6aa0b9db7afe3f1e49abcc904a8a5e54d555d0cb0ca2af8bfee5b39340866943`.
The five native trials used xdg-desktop-portal 1.22.1, xdg-desktop-portal-gtk
1.15.3, GTK 3.24.52, Mutter and GNOME Shell 51.1, and the GNOME portal 51.0.
[Fixture workspace](../../tools/rust-qa/portal-dialog/Cargo.toml)

## Native parenting, selection and cancellation

The client installed its response match before calling
`org.freedesktop.portal.FileChooser.OpenFile`, matched the current frontend's
unique bus owner and verified the returned request path. The driver waited for
the real GTK window, used its Cancel and Use folder keyboard mnemonics, and
checked the returned response and URI count.

| Native execution | Independent parent observation | Portal result |
| --- | --- | --- |
| X11, registered host app and installed Flatpak | The X server reported `WM_TRANSIENT_FOR` on the titled GTK dialog. In the Flatpak selection the dialog's XID was `0xa00279` and its parent was the app's mapped `0x600002`. | Cancel returned code 1 and zero URIs. Selection returned code 0 and one URI. |
| Wayland, registered host app and installed Flatpak | The private compositor issued the parent's `zxdg_exported_v2.handle`. The separate GTK process imported the exact token and invoked `set_parent_of` for its titled toplevel. The observer verified an attached buffer and keyboard focus on that child surface. | Both cancellation and selection returned the same response codes and counts as X11. Each activation obtained a fresh compositor handle. |

The chooser's trusted synthetic producer held `/tmp/selection/album`, with
one fixture entry. Every application process first checked that this path was
inaccessible. A registered host app received `file:///tmp/selection/album`
as selection metadata. The app performed grant-relative filesystem I/O only
for the installed Flatpak's Documents URI.

## Installed Flatpak grant

Each run used the real Flatpak CLI to export the synthetic application to a
temporary OSTree repository, install `app/org.example.IfwPortalDialog/x86_64/test`
in a fresh user profile and run it with the local freedesktop Platform 26.08.
The platform deployment was
`df26daaf9d07610b4a72cc4585566194051275ac68396597b06474396f66427c`.
The chooser, Documents portal and application were separate processes. The
portal frontend identified the actual Flatpak sender.

| Selection | Opaque document ID | Application result |
| --- | --- | --- |
| X11 | `fFbOlErdyO2FlI_SOTO5rQ` | Enumerated `fixture` through the selected root. After the portal revoked rights, a fresh Flatpak process received `ENOENT` (2). |
| Wayland | `xZPHItc6bxuQF4jDjFLbKg` | Enumerated the same fixture under its separately granted root. A fresh process again received `ENOENT` after revocation. |

The returned URI used `/run/user/0/doc/<id>/album`. Within this Flatpak,
`/run/user/0/doc` resolved to `/run/flatpak/doc`. The kernel reported a
`fuse.portal` mount rooted at `/by-app/org.example.IfwPortalDialog`.
The client validated the mount and path components before calling
`safe_fs::Directory::open_root`. The independent driver called `Documents.Info`
and verified the synthetic backing directory and the granted `read`, `write`
and `grant-permissions` rights. The directory trial complements the separate
shared media-lock tests. Fedora's shipped portal still refuses the required
media `flock`. [Documents capability comparison](rw02-linux-services.md)

## Notifications and autostart

The GTK-only sessions recorded the Rust client's Add/Remove acknowledgements.
The real GTK backend delivered the exact title and body to a synthetic
freedesktop notification server, then withdrew the returned numeric ID.
The GTK backend lacked a Background interface. Its request returned
`UnknownMethod`, and the private autostart directory gained no entry.

The fifth trial ran an actual GNOME Shell, GNOME portal and installed test
Flatpak. A private WirePlumber/PipeWire stream carried pixels from the 1280 × 900
virtual monitor. After the client posted a notification, a separate D-Bus
monitor observed the GNOME backend delivering it to `org.gtk.Notifications`.
The driver opened GNOME's notification list with Super+V. Visual inspection
of the saved image found **Synthetic notification** and **Private portal
delivery test** under **Portal assessment**. After withdrawal a second image
showed only the independently generated system message in that list.

The GNOME Background API returned `background=true, autostart=true` and wrote
the private `org.example.IfwPortalDialog.desktop` entry with the Flatpak ID
and `Exec=flatpak run --command=portal-dialog-assessment org.example.IfwPortalDialog notify`.
Disabling autostart removed the entry. The driver then stored an explicit
denial for this synthetic app in its temporary PermissionStore. A new request
returned code 1, both flags false and no autostart entry. Startup following a
real desktop login and observations from other desktop environments remain open.

## Inputs, isolation and reproduction

The frozen Rust 1.100.0 workspace has 211 third-party lock records matching
the reviewed GUI graph. Its Linux normal/build tree activates 116 packages.
The builder checked their feature sets and verified 5,770 unpacked files
against the authenticated archives. The native Wayland adapter uses
raw-window-handle 0.6.2, wayland-backend 0.3.17, wayland-client 0.31.15 and
wayland-protocols 0.32.13. Direct features stay within the reviewed graph.
The `xdg-foreign-unstable-v2.xml` input carries the Red Hat 2015–2016
MIT-style permission notice and has SHA-256
`625d83fbb068f48e69e739eafde507f10cdfe7480146f3ac10af9a2ddf551c80`.
The Rust adapter borrows the existing display and surface through two unsafe
conversions. An owned winit window keeps them alive until the export and guest
connection have dropped. A private shared-memory buffer maps the real parent.
The app reuses the system libraries and services at runtime.
[Parent adapter](../../tools/rust-qa/portal-dialog/src/parent.rs) · [GUI dependency assessment](rw02-gui-dependencies.md)

All test desktops used fresh PID, network, mount, IPC and user namespaces,
a private session bus, private display sockets, temporary homes and a routeless
network namespace. Namespace UID 0 mapped to the invoking user. The launcher
allowed only private FUSE mounting and nested user/loopback setup. The latter
allowed the packaged GTK Glycin icon decoder to retain its own sandbox.
The GTK selector received the synthetic producer as a read-only bind. The native
host client received only its executable and the private session, display and
Documents services. Flatpak's user and temporary system repositories were
under private tmpfs. The public Platform deployment was mounted read-only.

On the assessed Fedora system, use the repository's pinned toolchain, existing
public Cargo registry cache and locally installed freedesktop Platform 26.08.
The live runs need user namespaces, `/dev/fuse`, native GTK/portal services,
GIO/PyGObject, Xvfb or Xvnc with XTEST, Mutter, and for GNOME display capture
WirePlumber, PipeWire and GStreamer with PNG output.

```sh
python3 tools/rust-qa/portal-dialog/build.py
python3 tools/rust-qa/portal-dialog/build.py --lint
python3 tools/rust-qa/portal-dialog/native.py x11
python3 tools/rust-qa/portal-dialog/native.py wayland
python3 tools/rust-qa/portal-dialog/native.py x11 --flatpak
python3 tools/rust-qa/portal-dialog/native.py wayland --flatpak
python3 tools/rust-qa/portal-dialog/native.py wayland --flatpak --gnome
sha256sum --check tools/rust-qa/portal-dialog/evidence.sha256
```

The local evidence index pins the five manifests and observations, selected
backend/compositor logs, Flatpak grants, GNOME bus trace and screenshots under
ignored `artifacts/rust/portal-dialog`. It covers this Fedora x86-64 assessment.
Linux ARM64, other desktop implementations and integration into the product UI
require separate observations. [Evidence index](../../tools/rust-qa/portal-dialog/evidence.sha256)

## Host FileChooser on older frontends

At `2e7ed89`, Ubuntu 24.04 x64 and ARM64 returned D-Bus
`org.freedesktop.DBus.Error.UnknownMethod` for the host Registry before the
X11 or Wayland dialog opened. The 1.18.4 frontend's interface list includes
FileChooser. Host Registry is a separate API for associating a host peer with
an application ID. [Hosted run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828363871),
[1.18.4 portal interfaces](https://github.com/flatpak/xdg-desktop-portal/blob/1.18.4/data/meson.build),
[current Registry contract](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.host.portal.Registry.html).

`--host-chooser-only` runs two unregistered FileChooser requests. The client
accepts only the explicit unregistered host select and cancel actions. Each
dialog retains a real native parent and the independent GTK-side observation.
The native host receives the URI of the synthetic producer directory while its
own mount namespace blocks direct access. Capabilities requiring an
application identity use the registered host or installed Flatpak modes.
[FileChooser contract](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.FileChooser.html).

Seven Fedora x64 runs exercised executable SHA-256
`1d8c7dfc84959bd4581e0121eb01ceb3bb8fb914fd4804c02f4fa494f85ea9d2`:
the two unregistered host runs (`x11-chooser-only-0hqqi0jf`,
`wayland-chooser-only-41rk_q4w`), registered host controls
(`x11-92phbnnj`, `wayland-mvwx3q1p`), installed Flatpak controls
(`x11-flatpak-5scdgwhk`, `wayland-flatpak-00xnrd79`) and the real GNOME
Shell desktop (`gnome-wayland-flatpak-5t79ycdj`). The six chooser runs
confirmed their respective native parents and both responses. Both installed
clients received a portal document for the selected folder and the GTK
notification relay acknowledged their delivery and withdrawal. Following
revocation, a fresh instance of each installed client received `ENOENT` from
the grant-relative root open. The GNOME run exercised notification display
and withdrawal and the private autostart allow/disable/deny sequence.
Frozen Clippy with warnings denied, rustfmt and the native release build
passed. The portal build reuses the hash-verified GUI manifest/lock pair from
`6c953e3` to compare active features. The first-party Cargo graph still has
211 locked external archives and 116 target-active external packages.
[Local evidence index](../../tools/rust-qa/portal-dialog/evidence.sha256).

## Signed runtime on hosted Linux

The GitHub Actions acquisition creates a fresh `FLATPAK_USER_DIR` under
`RUNNER_TEMP`, with separate cache, GPG home and an empty temporary system
installation. It imports Flathub's HTTPS remote descriptor, requires GPG
verification of the summary and commits, selects the reviewed native
Platform ref and verifies its deployed commit. If the branch has advanced,
the explicit commit update selects the reviewed version. An independent
OSTree signature check and a SHA-256 of the deployment metadata are retained
in that private acquisition directory. The launcher accepts the matching
checksum-named deployment under that runner directory and bind-mounts that
one directory read-only. Its sibling runtime checkouts and remote repository
stay outside the test desktop.

| Architecture | org.freedesktop.Platform 26.08 commit |
| --- | --- |
| x86_64 | `df26daaf9d07610b4a72cc4585566194051275ac68396597b06474396f66427c` |
| aarch64 | `b66eec6a19d747f56191c318c11a6ec765b8d7cc45cf16e4926349a64504d620` |

On a Linux Actions runner, install `flatpak` and `ostree` alongside the
existing portal desktop prerequisites. Run the acquisition in a step with an
ID and pass its `deployment` output through `PLATFORM_DEPLOYMENT` in the two
Flatpak steps. The installed test application is built inside each private
desktop and installed from its temporary offline repository. The public
platform and the local test-application ref have independent provenance.
The two Fedora Flatpak controls used the matching system-provided x64
deployment. Hosted acquisition, Ubuntu native responses and Linux ARM64
execution require their own run receipts.
[Flatpak command reference](https://docs.flatpak.org/en/latest/flatpak-command-reference.html).

```sh
python3 tools/rust-qa/portal-dialog/hosted_runtime.py
python3 tools/rust-qa/portal-dialog/native.py x11 --host-chooser-only
python3 tools/rust-qa/portal-dialog/native.py wayland --host-chooser-only
python3 tools/rust-qa/portal-dialog/native.py x11 --flatpak --hosted-runtime "$PLATFORM_DEPLOYMENT"
python3 tools/rust-qa/portal-dialog/native.py wayland --flatpak --hosted-runtime "$PLATFORM_DEPLOYMENT"
```

## Ubuntu Flatpak launch bus

In hosted run `44835826452` at `8b071ab`, the signed runtime acquisition
and offline installation of the fixture app completed on Ubuntu x64 and
ARM64. Each of the four installed-client runs then reported `Could not
connect: No such file or directory` before the Rust process reported an
application identity or parent. The x64 launcher SHA-256
`25a6e33ac9307e5ece4c16eb49e03b5b25bdc4facc7175b1c7638718682bcf5a`
matches the executable from Ubuntu's signed `flatpak 1.14.6-1ubuntu0.1`
package. This build links libmalcontent. During app startup Flatpak opens
a system-bus connection before querying the account service. It propagates
a missing socket as a launch error. With an available bus it handles the
absence of that optional service itself.
[Ubuntu Flatpak package](https://launchpad.net/ubuntu/+source/flatpak/1.14.6-1ubuntu0.1),
[Flatpak 1.14.6 launch check](https://github.com/flatpak/flatpak/blob/1.14.6/common/flatpak-run.c#L3671-L3709).

The fixture creates a second D-Bus daemon in its existing private network,
mount and PID namespaces. Only the host-side `flatpak run` commands receive
its system-bus address. The new daemon has no service activation directories.
The driver checks the distinct bus ID and activatable names and writes both
to `steps.flatpak_launch_bus` in `results.json`. The chooser, Documents
service and permission store use the original private session bus. The
installed application's metadata still grants only its display sockets.

After opening the bus, version 1.14.6 also requires five read-only source
directories under `/sys`. The outer fixture supplies `block`, `bus`,
`class`, `dev` and `devices` on a new private tmpfs and checks that each
is empty. The installed runtime receives those empty directories.
[Flatpak base sandbox setup](https://github.com/flatpak/flatpak/blob/1.14.6/common/flatpak-run.c#L3237-L3252).

Native x64 runs used the APT-verified Ubuntu 24.04.5 userspace on a
Fedora kernel. The launchers, portal frontend, Documents service, GTK
backend and permission store matched the hosted x64 binary hashes. The
original fixture's only traced socket connection returned `ENOENT` for
`/run/dbus/system_bus_socket`. With the private bus and device directories,
both real installed clients proved native dialog parenting, cancellation,
selection, document access, notification delivery and withdrawal. After
permission revocation a fresh client on each backend reported `ENOENT`
opening its grant-relative root. The public runtime and compiled Rust
client matched the earlier Fedora controls. A fresh hosted ARM64 run must
exercise the same paths.

| Native x64 receipt under `artifacts/rust/gui-noble-native/runs/portal-dialog/` | SHA-256 |
| --- | --- |
| `x11-flatpak-uekzaksp/cancel-connect.strace` (original driver, socket calls only) | `c3ba77d28a52e9c94c455e936560a81462554ecbd656eb61be9eb6a0ccbf1a7b` |
| `x11-flatpak-imkfupty/results.json` | `a6aab7952b7474585113e31e90ba2f6d54a87fcedb103299e3e43dff06f5f08f` |
| `wayland-flatpak-sts9536y/results.json` | `104c6827e17e9044ff87afabdd30aee62dd34c7e59c7ef5d7a249568328d53d8` |
