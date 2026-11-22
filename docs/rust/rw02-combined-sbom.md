# SPDX inventories for the combined native development build

The combined RW-02 build produces one SPDX 2.3 JSON document per native target. Each document describes the development executable measured on that runner, the Cargo sources that actually compiled, the five embedded fonts and the audited native and protocol inputs. The generator runs offline with Python 3.11+ and Git. The SBOM uses the native source commit time for its reproducible timestamp. Its creation record identifies the generator, source-notice audit, Cargo-unit verifier, font reader and historical review pin by SHA-256. [Generator](../../tools/rust-qa/combined-profile/sbom.py) · [Native build evidence](rw02-combined-profile.md) · [SPDX package fields](https://spdx.github.io/spdx-spec/v2.3.1/package-information/)

## Generate and check

Run from the repository root with the native source commit available in Git.
The following commands generate the corrected Ubuntu x64 document from the
source-matched original ZIP. The first audit uses the local checked Cargo
archives and the three reconstructed GUI source directories. The optional
`--source-inventory PATH` accepts an already generated supplemental
`inventory.json` with the exact checked canonical digest. A native run
using the revised source inventory supplies it directly. [Native inputs](rw02-native-gui.md#native-follow-up-at-7517e3b) and [notice bundles](rw02-combined-notices.md).

```sh
revision=7517e3b6be84645bc0d40603750b003dd5792104
target=x86_64-unknown-linux-gnu
archive=artifacts/rust/hosted-desktop-storage/45047460092/linux-x64.zip
digest=afd05f889c75c40f2a1f3cebc9f413c9fc48c488160f1fa1f0f45bd68e0f8b6c
output=artifacts/rust/combined-profile/qualified-notices-7517e3b/first/linux-x64.spdx.json
python3 -B tools/rust-qa/combined-profile/sbom.py "$target" \
  --revision "$revision" --input "$archive" --archive-sha256 "$digest" --output "$output"
python3 -B tools/rust-qa/combined-profile/test_sbom.py --target "$target" \
  --revision "$revision" --input "$archive" --archive-sha256 "$digest" --document "$output"
```

For an existing native combined run directory containing `result.json`, pass that directory to `--input` and omit `--archive-sha256`. Both paths authenticate the same input schema and emit identical content. ZIP mode verifies the published digest before accessing the archive. Directory mode trusts the supplied runner receipt for the measured executable hash. Both modes verify every indexed output, the revision's source witnesses, the canonical source inventory, the target graph and the original notice files. The checker rebuilds the host/target compiler units and link directives from the original Cargo JSON log. [Combined source review](../../tools/rust-qa/combined-profile/review.json) · [Compiler verification](../../tools/rust-qa/combined-profile/units.py)

The stand-alone command `python3 -B tools/rust-qa/combined-profile/test_sbom.py` exercises six small offline controls. Supplying a native input also exercises its package, build-role, link, font, license and platform assertions, both forms of inventory tampering, altered compiler-unit ownership, wrong source revision and wrong target. The optional `--schema PATH` on this test command uses the locally installed Python `jsonschema` validator and checks the schema file's SHA-256 first. The pinned official SPDX 2.3.1 schema digest is `4126dc29f15e92feec92e9622f4939131ad58b125d6f578aa93e980a6e6f3212`. [Test controls](../../tools/rust-qa/combined-profile/test_sbom.py) · [Official JSON schema](https://raw.githubusercontent.com/spdx/spdx-spec/v2.3.1/schemas/spdx-schema.json)

## Evidence and interpretation

- A version-qualified Cargo entry represents a compiler input. Its comment records each observed target, kind and feature group and any build-script link directives. Explicit Cargo build dependencies and host-only components such as procedural macros use `BUILD_DEPENDENCY_OF`. Other Cargo edges describe normal dependencies. The document associates the executable with its source using `GENERATED_FROM`. Actual executable and installed-file contents require separate evidence. [SPDX relationships](https://spdx.github.io/spdx-spec/v2.3.1/relationships-between-SPDX-elements/)
- Unmodified registry sources carry their archive checksum and download location. Filtered base64 and the reconstructed egui, epaint and unicode-bidi entries identify the original archive and the actual compiler tree separately in `sourceInfo`. Each external package links its retained native and shader input paths to their hashes. These include build fixtures, tests and examples. Windows source entries retain the architecture-specific Microsoft import-library hash. The PE dependency observation identifies DLL names. Installed DLL bytes, modules loaded later and the separate import reconstruction have their own evidence. [Source filtering](rw02-yaml.md) · [Windows import reconstruction](rw02-windows-imports.md)
- The five font entries use `DATA_FILE_OF`, pinned font and OFL hashes, original copyright, version and trademark records. The build's drawing smoke and reviewed embedding functions establish the source path into the executable. The original runner retained its executable hash. It did not archive the executable for a new scan. SQLite's source ID, static-link directive and reviewed amalgamation establish its own SHA-256 and `blessing` entry alongside the MIT-licensed Rust bindings. [Font evidence](rw02-gui-dependencies.md) · [SQLite dedication](https://www.sqlite.org/copyright.html) · [SPDX blessing](https://spdx.org/licenses/blessing.html)
- Each external entry preserves the original Cargo declaration, the selected top-level license branch and the original and supplemental notice hashes. Legacy Cargo `/` alternatives have an SPDX `OR` expression. The concluded expressions retain applicable Chromium, tiny-skia, Unicode and Khronos terms. The SPIR-V grammar declares MIT and carries the Khronos standards advisory present in the supplemental license. Its full text matches `MIT-Khronos-old`. The ring entry retains the ISC and Apache grants and all six notices including BoringSSL, Fiat and embedded once_cell. The 996-byte inherited redistribution notice of granit-parser is a document-local `LicenseRef` with its exact original text, verified against the crate's `LICENSE` digest. Its four additional inherited notices remain identified individually. [GUI and native license review](rw02-gui-dependencies.md) · [Storage license review](rw02-storage-inputs.md) · [SPIR-V grammar declaration](https://github.com/KhronosGroup/SPIRV-Headers/blob/04f10f650d514df88b76d25e83db360142c7b174/include/spirv/unified1/spirv.core.grammar.json) · [SPDX Khronos license](https://spdx.org/licenses/MIT-Khronos-old.html) · [SPDX extracted licensing information](https://spdx.github.io/spdx-spec/v2.3.1/other-licensing-information-detected/)
- Each Linux document identifies 101 individual retained Wayland XML inputs. Their conclusions are 60 MIT, 18 LGPL-2.1-or-later, 12 HPND-sell-variant, ten MIT-CMU and one BSD-3-Clause. Three normalized bodies cover the 70 untagged embedded grants and match the official MIT and HPND templates. The historical Weston fullscreen-shell XML uses its separately authenticated COPYING notice. The source entry for wayland-client’s core XML identifies both generation calls in its crate. Tagged XMLs identify their full original REUSE text by path and digest. [Wayland source history](rw02-gui-dependencies.md#locked-assessment-and-additional-rights-holders) · [MIT matching template](https://github.com/spdx/license-list-data/blob/v3.29.0/template/MIT.template.txt) · [HPND matching template](https://github.com/spdx/license-list-data/blob/v3.29.0/template/HPND-sell-variant.template.txt)

## Corrected source-bound standalone documents

The native build at `7517e3b` authenticates the historical inventory. A
second pinned digest authenticates the newly qualified source records.
Packages with reviewed file-local attributions carry hashes, source paths
and exact byte ranges. Their aggregate `licenseConcluded` stays
`NOASSERTION` where a top-level selection would obscure possible per-file
terms. The inherited granit-parser LICENSE has its own source entry.
Ring also records its architecture table and generator-to-output map for
the individual target. The two XML macro calls, full REUSE references,
four target checks and all files in each matching notice archive were
checked separately. [Qualified source evidence](rw02-combined-notices.md).

| Target | SPDX packages | Relationships | Corrected SPDX SHA-256 |
| --- | ---: | ---: | --- |
| Linux x64 | 446 | 1,063 | `0a96a483f2a0f9ef0de29fe8cf2fc4239f912bd274e66b7b275f2cee57391a07` |
| Linux ARM64 | 445 | 1,063 | `ec6fe66801df44f4582c3e0055f2c109ebe13d069dc5037231e60c109705205e` |
| Windows x64 | 258 | 615 | `8b41e52cb0ee753826d7c9f829ebc18ddbf3e980b1bb701e7abf7e5073d58d09` |
| Windows ARM64 | 257 | 614 | `19259e747ed17fd541a1ea0813867e90372645f5a077e205a0deae91c4032a8c` |

All four passed the pinned SPDX 2.3.1 schema, SPDX reference checks and
target-specific readback. Historic checksums below still identify the
original documents, which missed the core XML, REUSE texts and file-local
source notices. The installed product package has a separate acceptance
gate. [Acceptance record](acceptance.md).

## Verified historical outputs

On 2026-11-22 all four complete a66e045 desktop ZIPs passed checksum validation. Each historical SBOM passed the official JSON schema, internal SPDX identifier and license reference checks, and the target-specific controls. Two independent CLI invocations produced byte-identical outputs on each target. Reusing the extracted native run directory reproduced each archived result. The retained files are under `artifacts/rust/combined-sbom/45034293002/`.

| Native target | Cargo packages | Units | Host-only packages | SPDX packages | Relationships | SPDX JSON SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| x86_64-unknown-linux-gnu | 337 | 402 | 41 | 444 | 1,061 | `c426e12d5869033492b553de86a4403d1839a17a98a11a0575700c559fee32e9` |
| aarch64-unknown-linux-gnu | 336 | 401 | 41 | 443 | 1,061 | `8e6704eed05b62eb57404902437384808fb995aa531dad1f0e9c7e4bf4b063a8` |
| x86_64-pc-windows-msvc | 250 | 281 | 28 | 257 | 614 | `346dc11a475c10e49ac2a72d386d1a84fd8a1ecb241637000efec20f4d2232a0` |
| aarch64-pc-windows-msvc | 249 | 280 | 28 | 256 | 613 | `7602dd020bc501f1e40f0cdd7a878c31609737624e23e7edb2947377456ac959` |

The product packaging gate separately requires the exact built and installed product, its corresponding sources, bundled notices, relink materials and a package-level SBOM. [Rust acceptance record](acceptance.md)

## Inventories generated on all four native runners

At `7517e3b6be84645bc0d40603750b003dd5792104` each runner generated its
own SPDX document and included it with the compiler evidence. After download,
the published digest of each complete ZIP and every member CRC passed.
Local generation from each native receipt reproduced the uploaded document
byte-for-byte. All four passed the pinned SPDX 2.3.1 schema, compiler-unit,
notice, font and target checks, including the altered-inventory controls.
Each document is the `combined-profile/sboms/<target>.spdx.json` member of
its native archive. [Actions archives](rw02-native-gui.md#native-follow-up-at-7517e3b).

| Native target | Compiled Cargo packages | SPDX packages | Relationships | Uploaded and reproduced SPDX SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Linux x64 | 337 | 444 | 1,061 | `1209cfbc5715bf233f9631f1b714efd9d7d5bc64eafeffb5deecd882e531c357` |
| Linux ARM64 | 336 | 443 | 1,061 | `1e6bda9e7e22d7ed344d06fd432f88797f7f9275c9b0f6a2085a734d2f62930c` |
| Windows x64 | 250 | 257 | 614 | `cf9c45d0692f00db34ad87ba55ffc8277d81334162414dd819c6c7df657a8519` |
| Windows ARM64 | 249 | 256 | 613 | `4e04407310d8a5ed0764214e65b695d323e7a6827620d451696741e0dc4cd3e8` |
