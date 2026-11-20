# RW-02 YAML compatibility feasibility

The maintained development-only
[`tools/rust-qa/yaml`](../../tools/rust-qa/yaml) workspace performs real Rust YAML
parsing/writing and real C# configuration readback. It is separate from both the
application workspace and the storage assessment. No shipping dependency,
configuration profile, migration routine or publication was changed. The C#
component is an oracle, not a required Rust runtime.

## Reviewed inputs and corresponding sources

The exact candidate is `serde-saphyr = 2.2.0`, default features disabled, with only
`deserialize` and `serialize`. Direct dependencies also pin `serde = 1.0.229`
(`std`, `derive`, defaults off) and `serde_json = 1.0.154` (`std`, defaults off).
The generated [`Cargo.lock`](../../tools/rust-qa/yaml/Cargo.lock) has SHA-256
`464bc4b82950c546729b7a4c287a18d45d3719e3b9abc3a2b2f4f44ffb2a9792`.
All **30 external archives** are an unchanged-version subset of the previously
reviewed [48-package storage/YAML source inventory](rw02-storage-inputs.md).
No newly resolved archive was admitted on metadata alone.

[`inputs.json`](../../tools/rust-qa/yaml/inputs.json), SHA-256
`6b72c432d9c9330d4c72d1c46bb26c764374423fca24a30a57ee3bd69769de7f`,
records archive checksums, supplied notices, original assets, build-script paths,
selected licenses, filtered source identities and all four target feature graphs.
Its original audit inventory hash is
`710c5b3cde154c5df53e03944908edfb7162b805f9cce69be3745806d4dbcb66`.
The x64 graphs select 30 external packages; both ARM64 graphs select 29, without
the x64 `core_detect` dependency. These are resolved native-target graphs, not
claims of native execution on the other three hosts.

The selected graph contains Rust implementations and CPU intrinsics, with no
additional native C library, bundled executable or font. Its nine build scripts
were included in the earlier source audit and rechecked in the filtered input:
`encoding_rs`, `num-traits`, `proc-macro2`, `quote`, `rustversion`, `serde`,
`serde_core`, `serde_json` and `zmij`. They generate/probe Rust/compiler settings;
the selected build has no source downloader, C compiler invocation or additional
native-library link directive. Cargo's exact graph and the actual source files
remain authoritative if a feature changes.

MIT is the selected option where dual licensing permits it. The **68 original
notice files** remain byte-identical, including `granit-parser`'s inherited Chen
Yuheng, Ethiraric and Bourumir Wyngs notices and its hidden `.licenses` files,
`encoding_rs`'s WHATWG BSD-3-Clause notice, and `unicode-ident`'s Unicode-3.0 notice.
The selected source/code notices are compatible with the repository's
AGPL-3.0-only distribution under the previously recorded audit. This disposition
does not extend to the excluded logo or arbitrary optional features.

The original `base64 0.23.1` archive has SHA-256
`ac07cdecf99051d9a5238b80f35af32cdeba5b336e55d957b318b50137e18da5`.
Its promotional image had distinct brand conditions; the original archive is
kept only in a private acquisition cache. The deterministic
[`prepare.py`](../../tools/rust-qa/yaml/prepare.py) recipe:

1. Authenticates each original archive before reading members and rejects links,
   duplicate members and traversal paths.
2. Omits `base64-0.23.1/icon_CLion.svg`, whose original SHA-256 is
   `cffa044ba75cb998ee3306991dc4a3755ec2f39ab95ddd4b74bc21988389020f`.
3. Removes exactly the README image link and adjacent promotional paragraph.
   Original README SHA-256:
   `e215f222008381c7e16c7616aea20c03e091f68f995699ca319e7f016463d905`;
   filtered README SHA-256:
   `f658264fa90effa1cbbbf30664b8265aa7431a021d1aebe9925945d2540a13b4`.
4. Preserves every other source and notice byte, writes a Cargo directory-source
   checksum manifest and records the two changes explicitly in `source-filter.json`.
   Cargo retains the original package checksum as package identity; the separate
   filtered tree identity is explicit, not presented as an unchanged upstream tree.
5. Emits an uncompressed tar with sorted members and fixed metadata. Actions
   compresses the transport ZIP separately. Original `.crate` archives stay
   in the private acquisition cache.

The resulting base64 file-map identity is
`1d1ab85ec3be094c4f0aeb79301b51a72f40f98ab8493cdc015f8e7822bce475`.
The 19,486,720-byte filtered tar has SHA-256
`f4caf0051b7bfd73f366bf3918721ddc6f0ebd35dd526fed1ddbd1335a8cab05`.
It contains **1,571 retained upstream files**, 30 generated directory-source
checksum files and the explicit source-filter manifest. The code and license
notices retain their upstream bytes.
The private original archive is never silently edited. All 30 filtered trees were
also checked for Windows case-colliding paths; none were found.

The original Linux x64 assessment bound SHA-256 of the gzip wrapper
(`b453c3cb5bc96839ae7766d40beae9b7dc97bea3ec1860150babb5b981d15714`).
Both Ubuntu runners at `4961746` produced wrapper
`3c00a3410ef83a1352632ca98e114c747939a2be4badf6f72a06ead9b563d79e`.
Independent decompression of both downloaded wrappers and the Fedora wrapper
recovered the identical tar above. The regenerated inventory changes only
this final bundle identity. A fresh local offline run using the canonical
tar passed all 13 stages, 183 Rust comparisons and 116 C# readback assertions.
All 204 files indexed by `canonical-linux-x64-01/evidence-hashes.json` matched.
Its `result.json` has SHA-256
`965aedddf6d93324353a6a5efea3ea95d14dc15e2ca32f955264543ef05c2ffa`.
[Original four-host run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44820760903).

The runner compiles the complete normal release with a **new empty Cargo home**,
`--frozen`, and only this filtered directory source. It verifies that every
resolved dependency manifest is below that directory and that the resulting
native graph matches the reviewed inputs. This exercised removal of the image
and README reference in the actual build, not only an untested export filter.

## C# compatibility contract exercised

The native C# oracle reads all ten YAML inputs/writer outputs in the accepted
RW-01 corpus. For its five original inputs, it independently checks both editable
and runtime objects against the reviewed platform-specific expected files.
Twenty-eight additional small synthetic cases make the current loader's behavior
observable. No personal profile or media is opened, and no Immich service is used.

The Rust codec uses serde-saphyr directly with typed Serde configuration fields.
It does not implement a YAML parser. The observed normalization includes:

| Area | Verified behavior |
| --- | --- |
| Defaults and nulls | Absent/null sections restore defaults; null source entries are discarded; null strings/lists normalize as the C# loader does. A present null non-nullable integer becomes `0`; an absent field retains its initializer. |
| Legacy extensions | Trim, invariant lowercase, leading dot, stable ordinal-insensitive deduplication; per-source nonempty filters override old global filters. The legacy global list is emptied internally and omitted by the writable representation. Arbitrary extension text is retained under those rules. |
| Unknown fields | Unknown root/nested fields are ignored and omitted on write, matching the existing C# writer; this is not an unknown-field-preserving editor. |
| Duplicate and merge keys | The last explicit duplicate field/section wins. `<<` is treated as an ordinary unknown key, matching the default C# loader, rather than enabling YAML merge expansion. |
| Anchors and aliases | Actual alias reuse produces equivalent source records. Undefined aliases are rejected. Separate resource controls bound expansion. |
| Scalar spellings | Quoted YAML-sensitive text, plain string fields such as `001`, legacy `yes`/`ON` booleans, hex/leading-zero octal/underscore integers and signed 32-bit boundaries are checked. The overflowing/invalid numeric cases are rejected. |
| Localization and Unicode | DE/EN values, German diacritics, Japanese, emoji, Unicode whitespace, sharp-S/sigma/Turkish-I filter comparisons and multiline values survive read/write. |
| Runtime paths | Editing keeps relative spelling. Runtime conversion uses the explicit synthetic profile directory and native Windows expansion or Linux lexical normalization; source/log trailing separators are included. These strings grant no filesystem authority. |
| Rejection | Invalid booleans, an unknown alias, an include tag, multiple documents, null/empty/nonmapping roots and selected invalid integer spellings are rejected by both actual readers. |

The first extended run exposed a real mismatch for the C# legacy integer syntax.
It stopped before claiming compatibility. Enabling the parser's existing
`legacy_octal_numbers` option and distinguishing explicit-null integers from
absent fields made the complete rerun pass; no replacement number parser was
invented. `DuplicateKeyPolicy::LastWins`, `MergeKeyPolicy::AsOrdinary` and legacy
boolean handling are explicit reference choices. Includes, filesystem resolvers,
property expansion, comments, robotics and huge-document features are disabled.
The `${...}` synthetic string remains literal.

For each of **29 accepted cases**, Rust checks editing normalization, runtime path
normalization, and the separately generated C# writer output. It emits unchanged
and deliberately modified YAML through serde-saphyr and reads both back. C# then
loads each new Rust file through the actual existing loader in both editing and
runtime modes, independently constructing the expected mutation: DE language,
retry setting, and a new Unicode path/album/source. Nine additional cases are
rejected as the oracle observed. No Python stand-in generates parser answers.

## Native string rules and extra resource policy

Rust's general Unicode lowercase and a guessed uppercase map are insufficient
evidence for legacy filter deduplication. The C# generator scans **1,112,064**
valid scalars, observes actual `String.ToLowerInvariant()` and `String.Trim()`,
and builds equivalence classes with a real
`Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)`. The first scalar in
each class becomes its canonical development-test representative. It checks
**272 complete string batches** against the actual lowercase/comparer operations
to catch context differences. Rust consumes only that generated per-run
reference, whose hash is verified before execution; no map is embedded or exposed
as a product setting.

The measured Fedora .NET 10.0.12 reference contains 1,487 lowercase mappings,
1,478 nonidentity ordinal representatives and 25 trim scalars. Its SHA-256 is
`cc23276552d5b335b1038119145a594d9f89b7a524fae6d627c883554a693284`.
This is environment-bound observation, not a universal Unicode policy. The
[earlier casing divergence](rw02-legacy.md#casing-source-and-license-audit) still
requires an explicit compatibility policy before production adoption.

The Rust assessment adds its own conservative limits; it does not attribute
these limits to the C# baseline or send amplification attacks to that baseline:

| Resource | Assessment limit |
| --- | ---: |
| YAML input / serialized output | 65,536 bytes each |
| Structural / flow depth | 16 |
| Nodes / parser events | 2,048 / 4,096 |
| Total scalar bytes | 32,768 |
| Aliases / anchors | 32 / 32 |
| Retained anchor events / bytes | 4,096 / 65,536 |
| Replayed events / replay depth / per-anchor expansions | 4,096 / 16 / 32 |
| Documents / include depth | 1 / 0 |

String input size is checked before entering the YAML parser. The serializer
writes through a bounded buffer and fails before exceeding its output limit.
Four Rust tests exercise successful input/output boundaries and failures for
bytes, depth, nodes, events, scalar bytes, alias count, anchor count, retained
anchor events/bytes, replay work and per-anchor expansion. Unknown fields still
consume budgets. Additional cycle/tag/document controls reject malformed input.
The alias-depth and flow-depth caps are configured but do not yet have separate
threshold-isolation tests; structural depth is exercised. Errors returned by the
codec use a small fixed category and do not render parser snippets/scalar values;
a synthetic-secret diagnostic control passes.

These are new resource policy choices for a feasibility tool. Production limits,
wall-clock/RSS measurement, bounded application file acquisition, supported path
namespaces, UTF-16 edge cases and application-level validation remain separate
work. Negative numeric values accepted by the legacy loader are not thereby
approved by the application's configuration validator.

## Native runner and observed results

From the repository root with the pinned native toolchains:

```text
python3 tools/rust-qa/yaml/run.py x86_64-unknown-linux-gnu --output artifacts/rust/yaml-assessment/runs/linux-x64
```

Use the corresponding native target for Linux ARM64 or Windows x64/ARM64. Python
3.11+ is required; no C compiler is required by this candidate graph. Optional
`--cargo-home`, `--dotnet` and `--offline` select local cached acquisition/SDK
inputs. Output must be new. Native Rust and C# process/OS architectures are checked;
Windows uses the accepted Windows corpus and native path APIs. The source bundle
uses untouched binary notice/source bytes, independently of Git checkout EOLs.

**Upload only the exact output directory under `runs/`.** Do not upload the whole
`artifacts/rust/yaml-assessment` tree: its sibling `private-cache` may contain the
unmodified upstream logo archive, and `private-work` is disposable build scratch.
Uploadable evidence contains only the filtered dependency bundle, first-party
source copies, graph/source hashes, logs and synthetic reference/output files.

Native Linux x64 passed all **13 runner steps** on 2026-11-20 with pinned Rust
1.100.0 and SDK 10.0.401/runtime 10.0.12: three source-filter tests, four Rust
budget tests, formatting, Clippy with `-D warnings`, the offline release build,
ten accepted-corpus assertions, **183 Rust differential assertions** over 38
cases, and **116 real C# reverse-readback assertions**. The .NET build reported
zero warnings/errors. No tests were skipped. The run is source-bound to
`06298d9de9956e29ef50f9d5e98bd95b07367f6d` plus the archived then-uncommitted
assessment files; all **121 archived first-party hashes** still matched after
execution. All **203 evidence-file hashes** were independently recomputed.

Evidence is `artifacts/rust/yaml-assessment/runs/maintained-linux-x64-01/`:

| Artifact | SHA-256 |
| --- | --- |
| `result.json` | `7412764ca883d447a630a9e83a716aa05af995a7a91a28aded529070ff475e7e` |
| `evidence-hashes.json` | `ccd691b835fb71e34142a579d9e4729ccc7a3fddd863794ea563ef97529c6b1e` |
| `rust-output/result.json` | `d7bf78ff0f5d197a5f813d86792fb77e1dd2285909a163c48c9ab8a77feccbd1` |
| `rust-output/csharp-readback.json` | `d96fb6602225ada36fdbbfed70270828d2493ccac9c4959ad26cc901029885bb` |

Exact local command, with the pinned Rust `bin` directory on `PATH`:

```text
python3 tools/rust-qa/yaml/run.py x86_64-unknown-linux-gnu --output artifacts/rust/yaml-assessment/runs/maintained-linux-x64-01 --cargo-home artifacts/rust/storage-assessment/cargo-home --dotnet artifacts/flatpak-local-2.11.2/sdk/dotnet --offline
```

Choose a fresh output name for another run. Three other native executions and
independent review remain required. This bounded result does not approve all
YAML 1.1/1.2 edge cases, unrestricted Windows namespaces, a shipping casing table,
atomic profile publication, crash/full-disk recovery or migration. The
[acceptance record](acceptance.md) owns the remaining RW-02/RW-03 gates.
