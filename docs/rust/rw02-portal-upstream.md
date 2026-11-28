# RW-02 private upstream Documents portal comparison

The official `flock` implementation can be built and exercised privately on the
same Fedora Linux x64 host where the installed Documents portal returns
`ENOSYS`. This is a development comparison, not a system update, application
dependency, distribution decision or RW-02 acceptance. No daemon, system package,
Flatpak setting, personal profile or production Immich resource was changed.

The maintained [builder and commands](../../tools/rust-qa/portal-reference/README.md)
own reproduction. The separate [Linux services fixture](../../tools/rust-qa/linux-services/)
owns the actual FUSE grant and .NET comparison. Both use synthetic isolated data.

## Exact source and native inputs

The [official 1.22.1 release](https://github.com/flatpak/xdg-desktop-portal/releases/tag/1.22.1)
resolves to `1d20fadc304f6601452b5db65ed91197dba77041`. Its published archive digest
was verified against the downloaded bytes. The only portal source modification
is the C hunk from
[upstream commit caa5ae9e](https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57),
authored by Sebastian Wick and committed 2026-10-29. It forwards `flock` to each
open file description's underlying descriptor and returns the actual error. The
commit's additional Python tests were not backported or claimed as executed.
GitHub reported the two source commits as unsigned; content hashes are not
represented as signature verification.

| Input | Verified identity |
| --- | --- |
| `xdg-desktop-portal-1.22.1.tar.xz` | SHA-256 `d4879ddb3d65ff1a8f19187497e6f13dc5d267bcac404a5d501218be355753d3` |
| Original upstream C patch | SHA-256 `5d7a386866288358b46621e85cbb68e9f008a19f669acc18859cd82f82f7fc5b` |
| Bundled libglnx | `ff64d52116ae74f0d25e24f089db28921ea171ff` |
| Bundled GVDB | `c6f2359cc1d00f16e0a0e2527fa0bc1882b8b5ab` |
| Installed freedesktop SDK `x86_64/26.08` | OSTree commit `a1b744b072d9f55d061e35382547ae80dad8d92abecc1da7dc1818de2daabfd3` |
| Fedora `fuse3-devel-3.18.3-1.fc45.x86_64.rpm` | SHA-256 `2118daa7274b5a426eea52b47f795f2d0409289cda1320a982730c97374dfeac` |
| Fedora `fuse3-libs-3.18.3-1.fc45.x86_64.rpm` | SHA-256 `ff4cfeae51ccec5ba95b47bec09727a592d96a038721068bf8c2064696027978` |

The two Fedora RPMs passed `rpmkeys --checksig` with the host's already trusted
RSA/SHA256 key `655a4b02f577861e`. They were extracted into private staging, never
installed. Their original pkg-config file is retained; a separate build-only
copy changes just `prefix=/usr` to `prefix=/fuse/usr`.

Both subprojects come directly from the published release archive; its wrap pins
match the identities above. Meson uses `--wrap-mode=nodownload`. All 499 released
files/symlinks are inventoried before and after patching. Exactly one source file
changes: `document-portal/document-portal-fuse.c`, from SHA-256
`8a4f4ae33ea81def6424f46dec3612ba5e325bb021a6037621608a0277484c15` to
`c5e284fa586a6511959c82f3f2590e9345dd099e9fe3f616b633cfe1a1b6c3b6`.
The patch applies with zero fuzz and a line-number offset of -121 only.

The SDK provides GCC 16.2.0, Meson 1.12.0, Ninja 1.13.2, GLib/GIO 2.88.3,
JSON-GLib 1.10.8, GdkPixbuf 2.44.7, GStreamer 1.28.6 and PipeWire 1.6.8. The last
three satisfy whole-project configuration but are not ELF `NEEDED` dependencies
of the selected Documents portal target. The actual ELF dependencies are GLib,
GIO, GObject, JSON-GLib, FUSE 3 and libc. `host-runtime-inputs.json` records every
loader-resolved library's SHA-256, package version and RPM license declaration,
including transitive dependencies.

1.22.1 predates the newer source's `<sys/file.h>` include. The builder supplies
`-D_GNU_SOURCE=1 -include sys/file.h`; `_GNU_SOURCE=1` already appears in upstream
`config.h`, but must precede the forced standard include. This compiler adaptation
introduces the standard declaration without changing another portal source line.
Tests, documentation, man pages, Flatpak interfaces, geoclue, gudev, systemd and
installed tests are disabled. Image/sound sandbox validation stays enabled; the
real host Bubblewrap binary is exposed read-only for Meson's required discovery.
Only `xdg-document-portal` is compiled, with no installation step.

## License and source boundary

[The retained notices](../../tools/rust-qa/portal-reference/NOTICE.md) distinguish
the LGPL-2.1-or-later portal files and patch from the project's broad
LGPL-2.0-or-later Meson label. Individual source notices govern. GVDB uses
LGPL-2.1-or-later; libglnx contains LGPL-2.0-or-later and LGPL-2.1-or-later code,
including systemd-derived lockfile code. Generated D-Bus C files inherit their
interface XML licenses. The 31 selected translation units and their original
headers remain inspectable in the source and `compile_commands.json`; static
libglnx objects and GVDB sources are part of this executable. All upstream
notices and license texts are retained unchanged. The Fedora FUSE files declare
LGPL-2.1-or-later and retain their packaged license text.

This build uses externally installed SDK/host libraries; it is not an audited
redistributable replacement portal package. No fonts or application assets are
adopted into the Rust application. Source redistribution and a packaged portal
would require a separate complete corresponding-source, notices and relinking
review. The new first-party tool is a development recipe, not runtime code.

## Executed build and FUSE evidence

On 2026-11-20, three fresh offline SDK builds, `sdk-flock-01`, `sdk-flock-02` and `sdk-flock-03`
under ignored `artifacts/rust/portal-reference-build`, produced byte-identical
executables:

`d58417869c6961c5ea318744b563ec728fa6101af9e228a83dd332ac371f90b6`

The retained executable is
`sdk-flock-03/build/document-portal/xdg-document-portal`. The original and patched
source inventories and compile-command files also match between those builds.
All compile successfully with one existing-source GCC `-Wstringop-overread`
warning in `src/xdp-app-info-flatpak.c:226` through GLib's `g_str_has_prefix`
macro; no warning was suppressed or claimed resolved. Host loader inspection
and `--version` pass. The ELF retains build-only RPATH `/fuse/usr/lib64`; that
path is absent on the host and in the runtime fixture. Resolution uses installed
host libraries, including GLib 2.90.1 and the matching FUSE `libfuse3.so.4`.
The signed staged FUSE library is byte-identical to the loaded host library.
The third build archives the final maintained recipe and passes its source-hash
readback. Python syntax and the maintained documentation's local links pass.

The runtime fixture used the first build's identical bytes. The actual kernel
was `7.3.4-300.fc45.x86_64`; the managed reference used .NET runtime 10.0.12 and
the existing Core secure-filesystem implementation. Private D-Bus services and a
real `fuse.portal` mount supplied directory grants. The consumer had a separate
mount namespace hiding the synthetic producer path and dropped capabilities.

| Scenario | Unchanged distro control | Private upstream fix |
| --- | --- | --- |
| Grant enumeration | Pass | Pass |
| Rust protected grant read, read-only and read-write grants | Refused with `ENOSYS` | Pass, stable file identity |
| .NET Core uncontended protected grant read | Refused with `ENOSYS` | Pass |
| Cooperative shared/exclusive `flock`, both backing/grant directions | Grant `ENOSYS` | Conflicting accesses return `EAGAIN`; no writes |
| Reads/writes after lock release | Grant `ENOSYS` | Pass |
| Traversal, read-only write refusal, revocation | Pass | Pass |
| Publish/no-replace/cancel, synthetic backing readback | Pass | Pass |

The upstream change does **not** make POSIX `fcntl` locks and `flock` one lock
domain. The explicit POSIX-versus-`flock` control can write, and the existing
POSIX same-grant-view gap remains visible. These are not accepted replacements
for the selected `flock` protection. This experiment does not establish exclusion
of noncooperating writers, a general filesystem security guarantee, another
distribution/kernel/architecture, or shipping portal availability.

Runtime records are owned by the services fixture. The checked files are:

| Ignored evidence | SHA-256 |
| --- | --- |
| `linux-services/documents-765u9lwj/documents.json` (distro) | `3a393f926488c8c9e395ef0ef62afb44c670e6c57a87c8bdf75097504450eaf7` |
| `linux-services/documents-765u9lwj/locks.json` (distro) | `d74164a35b80b4e8789d1958d29c0a3ebe35216eeba268655318115d355cc3e0` |
| `linux-services/documents-zcmtpflz/inputs.json` (fixed source/binary binding) | `2210992c256b55afa7f88d8ea783d524c62c29eefeda402abde241f49843ca19` |
| `linux-services/documents-zcmtpflz/documents.json` | `fc93f33eeef586f588c810fadabd4834b519cd78f6e4744ad231abfbb27fce23` |
| `linux-services/documents-zcmtpflz/locks.json` | `334fffff66d15c367c6809d12e058784a11a17040e945f33f1003e449d17b073` |
| `portal-reference-build/sdk-flock-02/result.json` | `6728b8a424251008b6fc67d6cba1f7bfd7422bf0a132c46e173510ccbbc31bbe` |
| `portal-reference-build/sdk-flock-02/host-runtime-inputs.json` | `82f2c0c26988c5979972ab69bafa16e4e2e2c78e76873c835645995ca454489b` |
| `portal-reference-build/sdk-flock-03/result.json` (final recipe) | `862cdb4913e7f2d82ed33847b7b17be9886b1a0598bcf573b97e9285e3a680eb` |
| `linux-services/documents-b7n99jdx/inputs.json` (source-matched unpatched) | `456b73a84cdf55f6ca6225290f920046e5e80d2c43b91839e7724c8e7d74704a` |
| `linux-services/documents-b7n99jdx/documents.json` | `618ae76615f5c9767247a296563c68ca2701f5f48caaeb80fbbf378c93a36fb2` |
| `linux-services/documents-b7n99jdx/locks.json` | `d74164a35b80b4e8789d1958d29c0a3ebe35216eeba268655318115d355cc3e0` |

All evidence paths in this table are relative to `artifacts/rust/`. They are
local, ignored artifacts; none was published. Parent integration owns any
checkpoint or acceptance-record update.

## Recoverable obstacles

The newest upstream tree needs libdex and WirePlumber that the host/SDK do not
provide, so this comparison uses the supported release source plus only the
selected fix. The initial rawhide RPM URL returned 404; the exact signed package
is in the official Fedora 45 release repository. Sandbox DNS/user-namespace
restrictions required scoped execution approval; no global setting changed.

An initial attempt to mount FUSE headers inside the read-only SDK failed, so the
builder uses the separate `/fuse` prefix. The SDK does not contain Bubblewrap;
the actual host binary is mounted read-only at `/tools/bwrap`. A first forced
header include without the command-line feature macro disabled GNU declarations
before `config.h`, causing compile errors; the final command preserves upstream's
feature macro before including the header. Earlier failed configure/compile logs
remain under the ignored root; successful fresh runs are separate directories.

The optional `--unpatched-control` mode was also built and run. The pristine
`sdk-unpatched-01` binary has SHA-256
`4c4766b8414f8e2057d0c9756411ede92fed5f1c3714cf8648f9cfa540cc5188`.
Its complete source inventory is unchanged from the release archive. SDK,
compiler flags, native inputs and Bubblewrap hashes match the fixed build, and
the same GCC warning occurs. The private FUSE harness passed with expected
`ENOSYS` in `artifacts/rust/linux-services/documents-b7n99jdx`, including the
managed reference. Thus the source-matched negative and positive controls hold
the build chain constant and differ only in the original upstream C hunk.
The original host portal binary also retains its recorded SHA-256
`dd0b626dd10ac8673482fb00f7dcd733dad723aba0781dd8bd4966eaa1b753b1`.

## Distribution availability on 2026-11-21

The latest published upstream release was still 1.22.1. Fedora listed
1.22.1-2.fc45 for Fedora 45 and Rawhide. The installed Fedora 45 x64 RPM
matched that version and its ordinary grant returned `ENOSYS`. Debian sid
listed 1.22.1+ds-1. Its two distribution patches change systemd activation
and a documentation font, leaving the released FUSE implementation intact.
Neither that published release nor those package sources establish a usable
portal update for the tested hosts. [Upstream releases](https://github.com/flatpak/xdg-desktop-portal/releases)
· [Fedora packages](https://packages.fedoraproject.org/pkgs/xdg-desktop-portal/xdg-desktop-portal/)
· [Debian packaging patches](https://sources.debian.org/patches/xdg-desktop-portal/1.22.1%2Bds-1/).

The Ubuntu Noble package and pristine Ubuntu rebuild both produced the same
refusal. A private rebuild with the upstream function passed 42 ordinary
shared/exclusive lock operations through a genuine Documents grant. Three
builds produced byte-identical unmodified and patched executables. The
native run used Noble x64 userspace on a Fedora kernel. [Noble package, source and lock receipts](rw02-portal-noble.md).

On 2026-11-22 the latest upstream release was still 1.22.1. Ubuntu had
added Noble `1.18.4-1ubuntu2.24.04.4` and Resolute
`1.21.1+ds-1ubuntu3.2` to Proposed. The complete distribution patches
address Snap camera access and an AddFiles deadlock respectively. They
do not implement file locking. The newer source archives were inspected
without installing them. The released Documents interface accepts file
descriptors on export and returns a document ID or a mountpoint.
It offers no call to obtain the authorized backing descriptor on import.
The existing private backport demonstrates native feasibility on both
Ubuntu architectures. Qualifying a generally available host component
remains necessary for a functioning Linux release candidate.
[Ubuntu publication records](https://api.launchpad.net/1.0/ubuntu/+archive/primary?ws.op=getPublishedSources&source_name=xdg-desktop-portal&exact_match=true&status=Published)
· [Upstream release history](https://github.com/flatpak/xdg-desktop-portal/releases)
· [Documents interface](https://github.com/flatpak/xdg-desktop-portal/blob/3152e604cf0eb2e195e298944cc8c728ee8009a7/data/org.freedesktop.portal.Documents.xml).

### Additional distribution sources checked on 2026-11-22

Upstream `main` at `3152e604` contains the forwarding operation. The 1.22
maintenance branch at `2fb63f87` still returns `ENOSYS`. Its FUSE source
SHA-256 is `8a4f4ae33ea81def6424f46dec3612ba5e325bb021a6037621608a0277484c15`.
[Maintenance source](https://github.com/flatpak/xdg-desktop-portal/blob/2fb63f8720a61891b0c1ca67ca675b0bce80271d/document-portal/document-portal-fuse.c)
· [Upstream lock change](https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57).

| Channel | Published sources examined | Evidence |
| --- | --- | --- |
| Fedora | Fedora 45 ships `1.22.1-2.fc45`. Updates and Updates-Testing had no replacement. Fedora 44 Updates supplied `1.22.1-1.fc44`, its Testing repository had `1.21.1-1.fc44`, and Fedora 43 supplied `1.20.4-1.fc43`. All four source RPM signatures verified and each contained the released handler. | [Fedora packages](https://packages.fedoraproject.org/pkgs/xdg-desktop-portal/xdg-desktop-portal/) · [Fedora 45 Updates-Testing](https://dl.fedoraproject.org/pub/fedora/linux/updates/testing/45/Everything/source/tree/Packages/x/) |
| Ubuntu | Jammy `1.14.4-1ubuntu2~22.04.2`, both Noble and Resolute releases and Proposed updates above, and Stonking `1.21.1+ds-1ubuntu6` retained the stub. The `.dsc` digests matched the inspected archives and their active package patches left this handler unchanged. | [Launchpad source publications](https://api.launchpad.net/1.0/ubuntu/+archive/primary?ws.op=getPublishedSources&source_name=xdg-desktop-portal&exact_match=true&status=Published) |
| Debian | Trixie/stable `1.20.3+ds-1` and Forky/testing and Sid/unstable `1.22.1+ds-1` retained the stub. The archive listed no separate current Experimental package. | [Debian archive](https://api.ftp-master.debian.org/madison?package=xdg-desktop-portal) |
| Arch Linux | Extra `1.22.1-2` had the original stub in its official debug source. The published binary package had SHA-256 `7df21ee565cd6f5b42dc374b77cd8a19ab31fb4bc5f76481f06713b5bd40d889`. | [Arch package](https://archlinux.org/packages/extra/x86_64/xdg-desktop-portal/) · [Corresponding debug package](https://geo.mirror.pkgbuild.com/extra-debug/os/x86_64/xdg-desktop-portal-debug-1.22.1-2-x86_64.pkg.tar.zst) |
| openSUSE Tumbleweed | The released `1.22.1-2.1.x86_64` RPM had SHA-256 `82fadbf91779435f2252754e0b36f16581c019f99d35d4aba3b7821385a612c4`. Factory revision `dc80b05532a4309cbe28b25403818a8a` used the release archive and a documentation/build patch. | [Published RPM](https://download.opensuse.org/tumbleweed/repo/oss/x86_64/xdg-desktop-portal-1.22.1-2.1.x86_64.rpm) · [Package source](https://api.opensuse.org/public/source/openSUSE:Factory/xdg-desktop-portal?rev=dc80b05532a4309cbe28b25403818a8a) |

This source comparison identified no newly released provider for a positive
native trial. The existing ordinary grant test can evaluate the first
distribution package containing the fix with an acquisition, a conflicting
cooperative writer and reacquisition after release.
The 9,401-byte local source manifest records the package URLs and digests,
the four Fedora signature checks and the inspected handler revisions. The
review read the original packages in memory. Its manifest is retained at
`artifacts/rust/portal-provider-availability-20261122/sources.json`, SHA-256
`c3c2cc70462556fa40dd9cff2a27e02fee5c163b196facf37f7a6f70d2f52e05`.

### Further host package sources checked on 2026-11-23

The package recipes for three further distributions selected upstream
1.20.4, 1.21.2 or 1.22.1. In each exact source the FUSE `flock` handler
returns `ENOSYS`. None of the selected packaging patches changes this handler.

| Distribution channel | Selected version and packaging |
| --- | --- |
| Alpine 3.24 and Edge | 1.21.2-r0 and 1.22.1-r0. Both build the release archive and add OpenRC scripts. [3.24 recipe](https://github.com/alpinelinux/aports/blob/255718024a4147fa290200f1a9553227775c0b81/community/xdg-desktop-portal/APKBUILD) · [Edge recipe](https://github.com/alpinelinux/aports/blob/06471599904835737e652e4fec73336ce91e3e55/community/xdg-desktop-portal/APKBUILD) |
| Gentoo | 1.20.4-r1 and 1.22.1-r1. The patches cover optional GStreamer, sandbox tests and D-Bus service startup. [Both ebuilds and their patches](https://github.com/gentoo/gentoo/tree/aa0eca2421ec52a9fcf84ac2a77347266089373e/sys-apps/xdg-desktop-portal) |
| NixOS 26.05 and Unstable | 1.20.4 and 1.22.1. The patches cover validators, installed tests and, on 26.05, a data path and a trash test. [26.05 recipe and patches](https://github.com/NixOS/nixpkgs/tree/8c61236de36e1dbd81fa53535ed28455dd46ae81/pkgs/by-name/xd/xdg-desktop-portal) · [Unstable recipe and patches](https://github.com/NixOS/nixpkgs/tree/c62712e183ef3134fb5281f3757d2bfa7ef8f0e0/pkgs/by-name/xd/xdg-desktop-portal) |

The 17 recipe and patch files are indexed in
`artifacts/rust/portal-provider-availability-20261123/recipes.json`, SHA-256
`36f191a3c89c50a0db68d93dd791718bd188db9344eb6a62c43542639244db52`.
The three upstream functions are identified in `release-handlers.json`,
SHA-256 `9503d898f0b96298b3792c46c6211ec77858f3798849661362a83361667da7cb`.
This source review identified no additional host package for a positive native trial.
