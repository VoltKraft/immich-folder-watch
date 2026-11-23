# Rebuild the Noble Documents portal package

Build the private seed from the signed source cache and a resolved
[dependency plan](../debs.py) for the current test image. The destination must
be new. The VM starts the package build as a disposable unprivileged user.

```sh
qa=tools/rust-qa/portal-noble/installed
area=artifacts/rust/portal-noble/installed
python3 -B "$qa/source_payload.py" "$area/apt-amd64" "$area/build-inputs"
python3 -B "$qa/vm.py" package --payload "$area/build-inputs"
```

The guest launcher mounts these inputs read-only. Its underlying build command
requires a new output directory on the guest's writable disk.

```sh
python3 -B /mnt/ifw/payload/tools/rust-qa/portal-noble/installed/package/build.py \
  --inputs /mnt/ifw/payload/ubuntu-source --output /var/tmp/ifw-build
```

The input directory contains the original DSC, both upstream tarballs, the
Ubuntu Debian tarball, the pinned Noble Updates InRelease and its Sources.xz
index. The [source input contract](../../inputs.py) provides their identities.
The guest needs the pinned Ubuntu archive keyring, `gpgv`, `dpkg-dev`,
`build-essential` and the build dependencies declared by the authenticated DSC.
The [parent source experiment](../../../../../docs/rust/rw02-portal-noble.md) pins the FUSE headers, notices
and original upstream change.

The builder adds `+ifwqa1` to the Ubuntu revision and appends the single reviewed
backport to its quilt series. It reconstructs the source package before invoking
the complete distribution binary build, including the installed-tests and
development packages. The normal invocation requests Debian's build tests.
`--source-only` stops after verified source reconstruction. An explicit
`--skip-build-tests` selects Debian's `nocheck` profile. The chosen build options
appear in `result.json` for a successful binary build.

Keep the unsigned source and binary packages, build logs, `.changes`,
`.buildinfo`, `runtime-files.json` and `result.json` together in the private
trial output. The runtime manifest binds the unpacked paths, types, modes and
bytes to the native staging tree. The result binds both activation declarations
and checks the Documents ELF build ID and libc lock import. Package
installation, actual service activation, lock behavior and rollback are separate
observations on the disposable guest.

The synthetic verifier regressions run from the repository root.

```sh
python3 -B -m unittest discover -s tools/rust-qa/portal-noble/installed/package
```
