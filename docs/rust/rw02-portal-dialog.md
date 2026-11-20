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
