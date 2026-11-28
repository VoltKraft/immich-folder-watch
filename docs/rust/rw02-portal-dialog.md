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

### Opening and revoking a directory with an escaped name

At `c7c614f` GTK selected both `album` and `Grüße #2 %2F` on private
Fedora x64 desktops. The chooser returned the latter basename as
`Gr%C3%BC%C3%9Fe%20%232%20%252F`. The Rust client previously stripped the
scheme and passed the encoded spelling to the filesystem. It now decodes
each component once into Unix filename bytes, checks the application's
Documents mount and opens the returned directory with `safe_fs`. The literal
`%2F` remains part of the name. [FileChooser response](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.FileChooser.html#org-freedesktop-portal-filechooser-openfile) ·
[File URI specification](https://www.rfc-editor.org/rfc/rfc8089.html#section-4) ·
[Rust decoder and tests](../../tools/rust-qa/portal-dialog/src/document_uri.rs).

On both X11 and Wayland, the installed client listed the distinct marker in
each directory. The external observer verified each ID, backing path and
permission set through `Documents.Info`. It then revoked the escaped grant.
A fresh process of the same Flatpak verified the FUSE mount, listed the
ordinary control directory and received `ENOENT` when opening the original
escaped URI. The service returned an empty permission set for that ID and
app. The ordinary grant was revoked and checked separately. The native host
chooser on both backends returned the corresponding encoded producer URI.

The native executable SHA-256 was
`c867688e16be62ef59a93e24796fbf15ce9aa67e474009bed11a5cb451854d90`.
Readback bound each run's 13 compiler inputs and 14 observer inputs to the
Git revision. Results are under `artifacts/rust/portal-dialog/`.

| Fedora x64 trial | Result directory | SHA-256 of `results.json` |
| --- | --- | --- |
| Installed X11 | `x11-flatpak-pmngdc01` | `cc338bab6a0514b784c08c7107a835a9a7145d5d195d2b605954970fab119132` |
| Installed Wayland | `wayland-flatpak-m7p_qubc` | `c99c1b974571c27c23545e45d459583d4f8fccc9875d0f4a05fbfffda3b9b5f9` |
| Host X11 | `x11-chooser-only-felfrzjz` | `8178d7f7f4535e791a7c774926f78b78a6e915f1b1e2cfa8401a6d8be6655d70` |
| Host Wayland | `wayland-chooser-only-vcdm_skm` | `5169f0f0c49ed6f6b25ed591d0dfa7542eda6765b1184c8bf36a2b31604b770f` |

The native Ubuntu ARM64 run at the same revision reproduced both installed
trials. On X11, the escaped grant `55e7c8cc` was revoked while `642762a6`
remained readable. On Wayland, the corresponding IDs were `360bb55c` and
`5cedd3d2`. Both fresh processes confirmed the FUSE mount and received
`ENOENT` for the revoked folder. Independent readback checked the original
parenting observations, both filenames and all 27 recorded source inputs
per desktop. The ARM64 ELF had SHA-256
`547fbf4e10dad38ec7609de55dfd407694b9a492cdd2ac2381b23c6c3231788d`.
The original ZIP had SHA-256
`1f716448e1aa5133528cb49381c0e62e8b081a3dd0d4baa38b063c1c4ecff15a`.
[Original Ubuntu ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46118180278/artifacts/15252637426).

### Resolving the display name inside the installed Flatpak

The installed chooser resolves its display text in the same order as the
shipping [DocumentPortalClient](../../src/ImmichFolderWatch.App.Linux/Platform/DocumentPortalClient.cs).
It first requests the `user.document-portal.host-path` attribute on the
grant. When that yields no absolute host path, it requests `GetHostPaths`
for that exact document ID and verifies the returned basename. A three-second
deadline covers both operations. If the label is unavailable, it displays the
grant path. The resolver returns text. Directory operations receive the original
grant separately. [Rust resolver](../../tools/rust-qa/portal-dialog/src/display_path.rs) ·
[Documents interface](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Documents.html).

In two Fedora x64 installed runs, the attribute returned the exact synthetic
backing path `/tmp/selection/Grüße #2 %2F`. An independent call by the same
Flatpak to version 5 of the Documents interface returned the same text for
that ID. The producer directory was outside the sandbox. Enumeration of the
granted directory, revocation and the surviving control grant all passed.
The `results.json` hashes were
`331baca16be096652dbcd415cc2efed6cf43161b932059c3614f471617d14024`
for `x11-flatpak-8r8044ee` and
`eb022486657231ae2f87c828413ec9405a8f07e74726fa54142115fdb978a839`
for `wayland-flatpak-fxzz3xmb`. Both used ELF SHA-256
`aee073300e00c7cf47c02ada88754f47402c23196db6f80f38759ed0750e12e4`.

At `3116139` the installed ARM64 client on Ubuntu used Documents version 4.
On both X11 and Wayland it displayed the grant path for `Grüße #2 %2F`.
The observer read the synthetic backing path from Documents.Info. Each fresh
client received `ENOENT` after revocation and read the other grant on the
same mount. The archive contains the ARM64 ELF with SHA-256
`656601bd42599766d3bcefe639747ddbccfe2cf0ff64cd0f6a354659d746a817`.
Host replay verified the ELF architecture, 14 compiler inputs, 14 observer
inputs, the native parent of both dialogs and the original client logs.
The Actions archive SHA-256 is
`8c7ee0e903b2aac2933fe72645b25a330ad97a389b911f860088b034f491b825`.
[Original Ubuntu ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46119147439/artifacts/15252723875).

The archived 3.0.4 Linux reference test assembly was also run with SDK
10.0.401 and the `DocumentPortalClientTests` filter. All 12 tests passed
in its isolated VSTest run, including the D-Bus fallback and timeout.
The assembly SHA-256 was
`351baf14b632033244043ed80179fea629bdc148429d0952efff168b6aa1f19c`.

The portal crate uses two existing audited inputs directly for the bounded
attribute read. The offline build reproduced the preceding receipt's 211
locked archives and the exact 116 active registry input records.
`rustix` 1.1.6 with its existing `fs` feature and `blocking` 1.7.0 both
offer MIT. Their original crate archives matched the Cargo.lock checksums
and each contained the MIT license text with SHA-256
`23f18e03dc49df91622fe2a76176497404e46ced8a715d9d2b67a7446571cca3`.
[Portal lockfile](../../tools/rust-qa/portal-dialog/Cargo.lock) ·
[rustix license](https://github.com/bytecodealliance/rustix/blob/4a563ad698b2c20ff848515821023d2265a788d0/LICENSE-MIT) ·
[blocking license](https://github.com/smol-rs/blocking/blob/e29a5e6979f56c7537b04ab17ca7bdceee66ef5f/LICENSE-MIT).

## Notifications and autostart

On Fedora x64 the private notification observer now publishes each complete
JSON event record by replacing the preceding file. In two earlier runs the
reader saw a partially written receipt after a successful portal submission.
The repeated installed Flatpak trial completed cancellation, selection, grant
revocation, background and autostart requests, notification submission and
withdrawal. Its `results.json` SHA-256 is
`35c8f40ad76a238c7ae26f6b66b4b20f95af04cf34c73e4e7e3997dc70c2bcf0`.
[Notification observer](../../tools/rust-qa/portal-dialog/notifications.py).

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

### Visible GNOME notifications on Linux ARM64

The [ARM64 notification workflow](../../.github/workflows/rust-linux-notification.yaml)
builds the Rust sender on Ubuntu 24.04 ARM64 and installs it in an isolated
Flatpak profile. The earlier hosted ARM64 X11 and Wayland tests used a
synthetic notification receiver. The focused trial uses a private GNOME
Shell as the receiver and matches its D-Bus owner to the observed compositor
process. The reader checks the app ID, notification ID, title and body on
submission, then checks withdrawal through the same backend.

Preserve the original monitor captures before posting, while the notification
is listed and after withdrawal. The pixel reader requires the title and body
in the middle capture and recognizable list controls after withdrawal. The
Ubuntu runner uses Pillow to read the PNGs and Tesseract with English data
to read their text. [Observer dependencies and replay command](../../tools/rust-qa/portal-dialog/notification.md).

In the Fedora x64 control `gnome-wayland-flatpak-8kra069i`, the installed
sender matched the compiled ELF, SHA-256
`94920bcef6dfa7f2161a54244b247ed18b1e830722feb80f41a64957cde43049`.
GNOME Shell was both the compositor and the notification service at PID 12
in the private namespace. Replay found the exact title and body only in the
middle image. The Clear and World Clocks controls remained visible after
withdrawal. The original middle image has SHA-256
`d090c4354e77bf7d95774f16a28a96caa2cc14870d53d19d5c9400cd939968b2`.

At `10ab0b8` on Ubuntu ARM64 the installed sender matched the native ELF,
SHA-256 `1fa404ff22bd4e2502be75cc1800057ad6f6a4cb314eb9440d1f64c82bc8da0b`.
The GTK backend at `:1.11` delivered the app's exact title and body for
`native-test` to GNOME Shell at `:1.5` (PID 13) and withdrew the same
ID. The image stream stayed paused. WirePlumber 0.4.17 exited after it
could not start its logind monitor in the isolated session. The archive
contained zero of the three required PNGs and the detached reader
rejected it. On Fedora x64, a separate clean-checkout control at the
same revision passed the bus and pixel checks and matched all 25 recorded
source files. [Original ARM64 artifact](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45963591797/artifacts/15181348629).

The native ARM64 run at `1a62d5c` retained the same sender ELF and
produced all three 1280 × 900 monitor captures. GTK at `:1.12`
forwarded the notification and withdrawal to GNOME Shell at `:1.6`.
That bus connection belonged to compositor PID 26. The open list showed
**Synthetic notification** and **Private portal delivery test** under
**Portal assessment**. The withdrawal removed the entry while the list,
its controls and two independent system messages remained visible. Visual
inspection and detached OCR agreed. The 2,601,390-byte archive contained
24 entries and matched the Actions SHA-256
`bc2dacb2807575d5e1f9bda80c881996d19b859138fffd418bfb6b84bf3a21c1`.
[Three original images, bus trace, installed sender and native readback](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45964876262/artifacts/15182840409).

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
