# Private upstream Documents portal reference

This Linux x64 development tool builds an isolated comparison executable. It is
not an application dependency or a portal installation. The default host portal
must remain the negative control. See [the evidence and limitations](../../../docs/rust/rw02-portal-upstream.md).

The source is the official xdg-desktop-portal 1.22.1 release archive, with exactly
the C hunk from upstream commit
[`caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57`](https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57).
The upstream tests added by that commit are not backported or claimed as run.

## Run

From the repository root, using the already installed system freedesktop SDK
`org.freedesktop.Sdk/x86_64/26.08` at commit
`a1b744b072d9f55d061e35382547ae80dad8d92abecc1da7dc1818de2daabfd3`:

```sh
python3 tools/rust-qa/portal-reference/build.py \
  --output artifacts/rust/portal-reference-build/sdk-flock-new \
  --download
```

Omit `--download` when the three checksum-pinned archives already exist in
`artifacts/rust/portal-reference-build`. An alternative `--cache` directory must
also be inside that root. The output directory must be new; failed output is
preserved for diagnosis and retries use another directory. Acquisition uses
official HTTPS URLs. The Fedora RPMs must also pass the host's existing trusted
RPM-key verification. No key import or package installation is performed.

Host prerequisites: Python 3.12 or newer, Bubblewrap, `patch`, `rpm`, `rpmkeys`,
`rpm2cpio`, `cpio`, `readelf`, x86_64 glibc loader and the pinned SDK. Bubblewrap
must be permitted to create user, mount and network namespaces. The build sandbox
has no network, user home, session/system bus or running desktop service. It sees
only the SDK, its fresh output, verified staged FUSE inputs and the real host
Bubblewrap executable read-only. SDK compilers, Meson and Ninja do the build.
The only target compiled is `xdg-document-portal`; nothing is installed.

Pass the resulting binary to the separate real FUSE grant harness:

```sh
python3 tools/rust-qa/linux-services/native.py documents \
  --portal-binary artifacts/rust/portal-reference-build/sdk-flock-new/build/document-portal/xdg-document-portal \
  --expect-lock supported
```

That command has its own isolation prerequisites and evidence. A successful
build, loader check or `--version` is not a successful FUSE grant test.

For a source-matched negative control, add `--unpatched-control` to the builder,
choose another fresh output directory, and pass its binary to the same harness
with `--expect-lock enosys`. This retains the same SDK, compiler flags and native
inputs but applies no source changes. The distro binary remains the default
independent host control.

## Reproduction and evidence

`result.json` records status, archive pins, source-only diff, options, SDK commit,
recipe and binary hashes. Logs retain RPM verification, extraction, patch,
configuration, compilation and host loader output. Full source manifests, staged
input manifests, compile commands, generated headers, object files, the binary,
an archived copy of this recipe and runtime RPM/library identities remain in the
output. Failed steps retain their log and error status. An initial missing cache
does not silently fetch without `--download`.

1.22.1 lacks the standard `<sys/file.h>` declaration included by later upstream
code. Compiler options `-D_GNU_SOURCE=1 -include sys/file.h` supply that declaration;
the feature macro is the same value already set by upstream `config.h`. Setting
it on the command line prevents the forced standard include from freezing feature
selection before `config.h`. These are declared build adaptations, not an extra
portal source patch. The staged `fuse3.pc` changes only `prefix=/usr` to
`prefix=/fuse/usr`. The untouched RPM version is retained beside it.

The ELF has a build-only RPATH `/fuse/usr/lib64`. The host loader check must resolve
all libraries from the host, where that staging path does not exist. The private
harness supplies host libraries and no `/fuse` mount. Do not install or distribute
this executable; a distributable portal package is outside this experiment.
