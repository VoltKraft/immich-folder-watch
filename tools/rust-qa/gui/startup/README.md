# Linux editor and tray startup language

The assessment reconstructs the GUI and the complete read-only settings library
at `c63d91c42eae9f71f07a2d1816214a1e16609ef8`. The staged application reads
the standard XDG configuration after winning the instance election. It uses
that selection for the first editor and the initial tray menu, including a
watcher that appears later. A secondary exits through the existing activation
path. The source change is in [language.patch](language.patch). The signed
3.0.4 comparison covers configuration decoding and the system fallback.
[Startup settings reader](../../yaml/startup/README.md).

## Offline inputs

The standalone renderer lock and YAML lock contain the 385 original registry
archives used by this candidate. Their compiler trees contain 20,517 files. The combined review authenticates their
original archives and compiler trees. Its existing YAML filter removes the
approved promotional asset and block in `base64 0.23.1`. The source receipt
has SHA-256
`1fde2469c1e00f08882bb863eca1110eb1c45fe78fe55e4b7767fcd3db0388e3`.
The [vendor builder](vendor.py) reproduced these bytes from the normal local
crate archive caches in a fresh output directory. An empty builder can use
`--fetch` for missing checksum-pinned original archives.

The [assessment](qualify.py) snapshots the first-party source bytes from
the specified Git revision and reproduces the lock with the pinned Cargo.
Each target's normal and build packages equal the expected platform-specific
selection, and every feature group has an original GUI, YAML or combined
witness. The readback also checks each original registry archive and the bytes
of every compiler source file. The Windows x64 and ARM64 renderer selections
retain their respective 135-package feature graphs. Linux x64 resolves 251
packages and Linux ARM64 resolves 250. These four observations qualify Cargo
resolution. The native build and desktop measurements below cover Fedora x64.

Use the existing checked GUI font and text-source materialization, the pinned
Rust toolchain and a combined-profile result directory that contains the
original four feature maps and `source-trees.json`. All example output
directories should be fresh.

```sh
area=artifacts/rust/combined-profile
python3 -B tools/rust-qa/gui/startup/vendor.py --output "$area/startup-vendor"
python3 -B tools/rust-qa/gui/startup/qualify.py \
  --vendor "$area/startup-vendor/registry/src/reviewed" \
  --combined-receipt "$area/runs/digest-native-2f63c15" \
  --output "$area/startup-build" --native
python3 -B tools/rust-qa/gui/startup/observe.py \
  --gui "$area/startup-build/native-build/release/native-gui-assessment" \
  --compiler-receipt "$area/startup-build/native.json" \
  --worker artifacts/rust/performance/subjects/startup-language-worker-20261128 \
  --sdk artifacts/flatpak-local-2.11.2/sdk \
  --signed-repo artifacts/rust/yaml-assessment/signed-flatpak-3.0.4-folders/ostree \
  --output "$area/startup-desktop"
```

The example worker directory is the local output of
[build_worker.py](../../performance/build_worker.py). Any supplied worker must
match its native receipt and accept the optional synthetic localization
section. The verified worker has SHA-256
`20df28770221c4f31a2729d54a138af165845b6ca5d2b14a869a37f0b6bf64f9`.
When using the optional `--build-cache` on the compiler, use its
`release/native-gui-assessment` as the observer's `--gui` input.

The original compiler run is under
`artifacts/rust/combined-profile/editor-language-replay-verified/`.
The pinned rustc 1.100.0 compiled 310 units matching the 251 Linux x64 package
and feature groups. All 22 native GUI binary unit tests passed. The GUI
executable has SHA-256
`2b751a662a093ed7e30b629e66c62654caf3d818d317f00c999b28e18471b76f`.
The source and compiler receipt `native.json` has SHA-256
`bfde3d81b0948a70d55221591ec3b57d3a7707a497d889d3758ccbdfbfd1fac0`.

## Fedora desktop readback

For the ordinary GUI, `observe.py` accepts the per-target `build.json` from
`build-gui-probe.py`. The [native Plasma workflow](../../../../.github/workflows/rust-linux-plasma.yaml)
uses `--native-only` to observe the elected editor, tray and worker in four
private X11 sessions on each Ubuntu architecture. Providing `--sdk` and
`--signed-repo` additionally compares the same four original configurations
with the signed 3.0.4 assemblies.

Four ordinary launches on four private Fedora X11 desktops opened the editor
before any StatusNotifierWatcher existed. AT-SPI exposed the two fields, the
language button and Quit in the expected language. The new watcher then
observed the existing primary registering. Its first menu revision had the
following native IDs and labels.

| System UI culture | Saved language | Filename field | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| de_DE.UTF-8 | en | Filename | Open GUI | Restart | Quit |
| en_US.UTF-8 | de | Dateiname | GUI öffnen | Neustart | Beenden |
| de_DE.UTF-8 | absent | Dateiname | GUI öffnen | Neustart | Beenden |
| en_US.UTF-8 | absent | Filename | Open GUI | Restart | Quit |

In each namespace the GUI process owned the original X11 window and bus name.
Its original child completed passes zero and one, then detected the newly
added synthetic file on pass two. Activating menu ID 3 exited the GUI and
worker, released the window and preserved the configuration bytes. The
[observer](observe.py) uses the application's exported dbusmenu directly.
The [Plasma test](../../../../docs/rust/rw02-plasma.md) covers physical shell
menu selections separately.

The signed 3.0.4 Linux assemblies then read each original synthetic file
from the same path with the corresponding system UI culture. They loaded
all four configurations and produced the same selection shown in the table.
The native observations and signed readbacks are in
`artifacts/rust/combined-profile/editor-language-shipping-readback/results.json`,
SHA-256 `5653a5c8e5ae73a7fca73dfcc3d3d5c193cebe713a2d1019ab90c13ad0be7be0`.

This staged integration leaves adoption by the ordinary cross-platform
compiler entry points open. The current normal renderer profile, retained
Windows variants and Linux headless renderer each have their own compiler
and source-reconstruction contracts.

## Full source, feature and notice audits

The [report driver](full_audit.py) runs the existing full GUI audit twice per
target. It reconstructs the ordinary GUI from `c63d91c` and compares its
full report, including unpacked archives, with that revision's pinned
SHA-256. The opt-in `--startup-vendor` path
then checks the staged manifest, lock, three first-party source trees and
the 385-package directory-source receipt. For the local YAML dependency it
records the Rust library target, `src/lib.rs`, the manifest SHA-256 and the
digest of the eight-file source tree at `c63d91c`. For `base64 0.23.1` it
reconstructs the two approved changes from the original archive and checks
all 38 compiler files and their Cargo checksum manifest. Other registry
inputs retain the ordinary unpacked-archive check. Both paths verify the
three separately reconstructed GUI text packages. [Full dependency audit](../../audit-graph.py).

After preparing the stage and directory source above, run the eight audits
serially with an isolated, offline Cargo home.

```sh
python3 -B tools/rust-qa/gui/startup/full_audit.py \
  --stage "$area/startup-build" \
  --vendor "$area/startup-vendor/registry/src/reviewed" \
  --output "$area/startup-full-audit"
```

| Target | Ordinary packages | Staged packages | Staged full report SHA-256 |
| --- | ---: | ---: | --- |
| Linux x64 | 235 | 251 | `3e84d4df1f4e63cbac21b98b36d9ab79aa14bafd12702ae5f3b9b9897837b48e` |
| Linux ARM64 | 235 | 250 | `b2f22a81c6d3683cc124ce751f20187d7c5b90ccd35a5ad5e8c7268d133b2cd6` |
| Windows x64 | 135 | 135 | `79a0ed7a1e0ca41324862e43a95fa17182140a36a18af5726f90b9249e7d5763` |
| Windows ARM64 | 135 | 135 | `1e74eb803d67b0f21e7e9545bc1705ef0673ceb789f60284036d7b854734ab89` |

All four ordinary reports reproduced byte-for-byte. Both staged Windows
reports changed only the top-level lock digest, from `6716b1cc…` to
`bdda6dc8…`. Every package row, original notice, native file, font and
shader entry matched its control. Among the existing Linux packages,
`serde_core 1.0.229` gained a second feature group comprising `default`,
`result` and `std`. Of the newly selected Linux packages, `core_detect 1.0.0`
was specific to x64. All eight reports had zero excluded packages or features.

Local originals are under
`artifacts/rust/combined-profile/editor-language-full-audits-01/`.
The comparison `results.json` has SHA-256
`aea72a8efa7c1786e488347f779223e4353f4b1f0e9087db8dd2fcb7c8b35e8d`.
As negative controls, the ordinary unpacked verifier rejected the filtered
README. The staged verifier rejected an additional README change in a
private copy and a substituted YAML manifest path. These are source audits
for four Cargo targets on Fedora x64. The runtime measurements retain
the platform scope described above.

### Current YAML library at bb3afd5

Add `--current-yaml` to the command above and select a fresh output
directory. The driver reconstructs the composed GUI twice from Git, first
with the library at `c63d91c`, then with the library at `bb3afd5`.
The two source trees differ in `yaml/src/anchors.rs` and `yaml/src/model.rs`.
Both runs use the original 385-package registry and the same composed lock.

| Cargo target | Packages | Current full report SHA-256 |
| --- | ---: | --- |
| Linux x64 | 251 | `9e254bf981615bc4f473a9e7c0aa131226274fc3be1fee5a74075b38ebbba286` |
| Linux ARM64 | 250 | `7125d9c1a9e2531973e7596f4df6072c660064c715c37003e234b0b1d51cc96d` |
| Windows x64 | 135 | `79a0ed7a1e0ca41324862e43a95fa17182140a36a18af5726f90b9249e7d5763` |
| Windows ARM64 | 135 | `1e74eb803d67b0f21e7e9545bc1705ef0673ceb789f60284036d7b854734ab89` |

Fedora x64 resolved all four Cargo targets offline. The two Linux reports
changed only the source revision and source tree digest in the first-party
YAML library row. Its source SHA-256 is
`7c317d1ec009960a6ec7c279539c5380358de956b9846fde7a18ddc0b579f450`.
The Windows reports reproduced their controls byte-for-byte. All eight
reports passed the package and feature exclusions.
The local comparison is
`artifacts/rust/combined-profile/editor-language-updated-audits-01/results.json`,
SHA-256 `a74296e184c2beb765fc5c40df93f97e493ed48f63fc1435d2b0f4df2ac1c3c3`.
A separate reconstruction of the ordinary and staged historical controls
also passed in `editor-language-original-replay-02/results.json`,
SHA-256 `241940404be98ef5427830997f3319990babb3387faef138a54b0cd9b373db68`.
