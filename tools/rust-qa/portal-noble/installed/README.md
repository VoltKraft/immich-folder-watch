# Installed Documents portal on native Ubuntu x64

This experiment installs a private Noble backport on a disposable x64 guest,
opens a synthetic upload from an installed Flatpak as an ordinary user and
restores the Ubuntu package. Distribution and ongoing host-package support
require a separate decision. [Source, patch and license review](../../../../docs/rust/rw02-portal-noble.md)
· [Native package reconstruction](package/README.md).

The host uses KVM, QEMU, cloud-init NoCloud seed media, xorriso, e2fsprogs,
GnuPG, Flatpak and OSTree. The existing native Noble test userspace supplies
the Ubuntu keyring and signed snapshot indices. The pinned native Rust
toolchain builds the reader. Every VM uses a fresh sparse overlay, a read-only
ISO, its own ext4 evidence disk, and no network adapter. All software installs
and service transitions occur on these guest overlays.

## Inputs and execution

Download `noble-server-cloudimg-amd64.img`, `SHA256SUMS` and `SHA256SUMS.gpg`
from the dated Canonical image directory. Put all three in
`artifacts/rust/portal-noble/installed/images/`, naming the image
`noble-amd64.qcow2`. The VM launcher verifies Canonical's signed image list
and the selected image bytes before boot. [Canonical release directory](https://cloud-images.ubuntu.com/noble/20261017/).

Run each command from the project root. Substitute the directories printed
by the preceding successful steps. The full Platform bundle is exported
into a private artifact directory after verification of the Flathub commit.

```sh
qa=tools/rust-qa/portal-noble/installed
area=artifacts/rust/portal-noble/installed
python3 -B "$qa/vm.py" inventory
python3 -B "$qa/debs.py" "$inventory" "$area/apt-amd64" --download
python3 -B "$qa/debs.py" "$inventory" "$area/lease-debs" --runtime-only --download
python3 -B "$qa/source_payload.py" "$area/apt-amd64" "$area/build-inputs"
python3 -B "$qa/vm.py" package --payload "$area/build-inputs"
python3 -B "$qa/runtime.py"
python3 -B "$qa/lease_payload.py" "$area/lease-debs" "$runtime" --build "$package"
python3 -B "$qa/vm.py" lease --payload "$payload"
```

`inventory` is the path printed by the inventory VM, `package` by the
successful package VM, `runtime` by the runtime exporter and `payload` by
the lease input builder. A stock-only run uses the same input builder
without `--build` and runs `vm.py lease-stock --payload "$payload"`.
The package build and original-package control can run on separate VMs.

## What to retain

The three-phase observation uses a single guest and a single test account.
Each phase reads the installed dpkg version, activates the two normal D-Bus
services and compares their live executables with the extracted package.
The same installed test app receives a fresh directory grant for each
phase. It opens the regular file with the workspace Rust filesystem crate,
checks the expected bytes on success and verifies that the sandbox cannot
read the backing pathname. The observer checks lock contention, release,
revocation, grant deletion and preservation of the backing file. During a
download it opens the sandbox's staged payload from the backing side and
keeps that descriptor until publication. Its inode and bytes must match
`download.jpg` after publication. The ordinary reader also tries an
occupied destination and cancels a separate transfer. The guest checks
the incumbent file, empty owner-only container and final published inode
after the package transitions.

Retain `vm.json`, `inputs.iso`, `console.log`, `guest.log` and the evidence
disk for each run. The package VM additionally exports `build.log`,
`build-evidence.tar`, `package-result.json` and `candidate.deb`. The lease
VM exports `stock.json`, `candidate.json`, `restored.json` and
`lease-result.json`. A failed setup or observation keeps the available
per-phase files and the guest exit status after shutdown.
