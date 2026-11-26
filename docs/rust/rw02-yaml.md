# RW-02 YAML compatibility feasibility

The maintained development-only
[`tools/rust-qa/yaml`](../../tools/rust-qa/yaml) workspace performs real Rust YAML
parsing/writing and real C# configuration readback. It is separate from both the
application workspace and the storage assessment. No shipping dependency,
configuration profile, migration routine or publication was changed. The C#
component is an oracle, not a required Rust runtime.

## Reading the original YAML file bytes

The shipping loader calls `File.ReadAllText`. Its byte-order mark selects
UTF-8, UTF-16LE/BE or UTF-32LE/BE. In reference format v2, C# preserves the
original file for each case and records its SHA-256, selected code page and
whether decoding needed replacement characters. The Rust reader opens those
files after the reference directory has moved. It bounds both the source
read and the decoded UTF-8 before parsing. The shipping C# loader then opens
each new Rust file directly in editing and runtime modes.
[Shipping reader](../../src/ImmichFolderWatch.Core/Configuration/AppConfigLoader.cs) · [C# byte fixtures](../../tools/rust-qa/yaml/dotnet/YamlFileEncodings.cs) · [Rust reader](../../tools/rust-qa/yaml/src/encoding.rs).

Six valid examples include a literal U+FFFD, a surrogate-pair character,
combining text, German and Japanese. The two UTF-8 files exercise the
presence and absence of a BOM. Ten other examples have deliberately incomplete
or invalid units. The shipping reader accepted all ten with replacements.
For the UTF-16BE high surrogate followed by an odd byte, it emitted two
replacements. Rust matched the legacy settings in all ten and kept the
damaged inputs read-only. The trial writes normalized UTF-8 to new files
for the 35 accepted inputs which decoded cleanly. Every original retains
its bytes. Production editing, backup and atomic replacement require their
own migration evidence.

On Fedora x64 at clean source `a7a62fa`, the offline 13-step run passed
with Rust 1.100.0 and .NET 10.0.12. The 54 files produced 162 decoding
comparisons, 259 semantic comparisons and 140 C# readbacks of 70 new files.
Eight Rust tests passed. All 124 source bodies matched Git and all 270
indexed artifacts matched their digests. The producer's original directory
was absent during readback. The report under
`artifacts/rust/yaml-assessment/runs/a7a62fa-linux-x64/` has SHA-256
`fc233032edee7999c8afbbbcd7fac850bf9921f304ee2f333870746d1d750053`.
Its evidence index has SHA-256
`25794b5002a869e821f450271b786cca7d22d6bf27dd2473424251ee040d5fa0`.

An independent fixture review reproduced and then verified fixes for an
absolute producer path and incomplete rejection of altered encoding controls.
All 22 negative controls were rejected, including a missing BOM, a different
malformed sequence with an updated digest, incomplete comparisons and extra
or missing files. The new C# verifier also opened 58 archived v1 Rust files
after relocation and passed all 116 comparisons. A wrong architecture was
rejected. A separate Linux x64 comparison against the actual .NET file
reader matched text, code page and fallback flags for 8,762 byte sequences,
including truncated preambles and split scalars near buffer boundaries.
The four-target v1 results below cover the decoded-text corpus.

At `8566f81`, both Windows and both Ubuntu hosts completed all 13 steps
with Rust 1.100.0 and .NET 10.0.15. Detached readback checked the original
54 files, the 70 Rust outputs and their 140 C# comparisons on each host.
All ten malformed but readable inputs kept their original bytes. The
124 archived source files matched the checkout for each platform, including
Windows line endings. All 270 indexed files per host matched their hashes.
The four-host readback SHA-256 is
`aec2180ad6ffd36b2feaea15f11e5022a8af8991e2b38259a898f4dd0553a8a0`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14813839731) · [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14812923204) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14818067206) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14817086899).

## Reviewed inputs and corresponding sources

At `11e4e6f7f385e8b69f1404a18fae82c02780c7d4` all four native hosts
completed the 13-step YAML assessment. Every host matched 183 Rust assertions
and 116 production C# readback assertions and rebuilt using the same canonical
tar SHA-256 `f4caf0051b7bfd73f366bf3918721ddc6f0ebd35dd526fed1ddbd1335a8cab05`.
All 204 indexed files in each downloaded report matched their hashes.
The native artifacts also contain the separately reported desktop results.
[Native jobs and artifacts](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44825008977).

| Hosted target | Downloaded artifact SHA-256 |
| --- | --- |
| Windows x64 | `264fd206affaa301a48c9e450c8a262b9530c0b38e3a3235ee029f774f9fe5b5` |
| Windows ARM64 | `4a685bc7d7ce7754fb3867edc1a5001e7db9352f09142dacc8c30b63e447ffd6` |
| Linux x64 | `2055ef6dabe058d476a71b0cd4a6273412ec957bad788bb8450b469f9f0b583a` |
| Linux ARM64 | `2156eb5fdd40c72792b4f74d72fe71f8bebccaf1d54cb42a76f98b882a46a2fc` |

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
The x64 graphs select 30 external packages. Both ARM64 graphs select 29.
The x64 `core_detect` dependency accounts for the difference.

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
| YAML file bytes | 1,048,580, including a possible byte-order mark |
| Decoded UTF-8 text / serialized output | 262,144 bytes each |
| Structural / flow depth | 16 |
| Nodes / parser events | 16,384 / 32,768 |
| Total scalar bytes | 131,072 |
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
wall-clock/RSS measurement, production file acquisition, supported path
namespaces and application-level validation remain separate
work. Negative numeric values accepted by the legacy loader are not thereby
approved by the application's configuration validator.

### Ordinary profiles with 100 and 300 folders

The original native corpus contained at most four watch folders per
profile. On Fedora x64 the shipping .NET configuration reader, writer
and validator also accepted ordinary lists of 20, 100 and 300 synthetic
folders. The earlier Rust codec could read and rewrite the 100-folder
case. Adding a 101st folder reached node 2,049 and failed. A concise
300-folder profile reached the same node limit on its first read. A
73,280-byte C# save exceeded the old 65,536-byte file limit. The trial
kept the original files for a second comparison.

At `0468771` the codec gives flat records the finite byte, node, event
and scalar allowances in the table above. The raw file allowance
accommodates a four-byte UTF-32 code unit for every ASCII character in
the text budget plus its BOM. The alias and anchor limits, replay limits
and read-only treatment of malformed encodings still apply.

The regression uses the shipping C# writer to save profiles with a
different path and album name for each folder. The cases include
per-folder sync modes, recursive flags, extensions and exclusions. Rust
reopens each file, writes it, then writes a second copy with an additional
folder, German language and a changed retry limit. The original C# loader
reads both copies in editing and runtime modes. On Fedora the 300-folder
UTF-8 and UTF-32LE saves occupied 84,930 and 330,124 bytes. Both produced
the same 89,998-byte UTF-8 result after insertion of folder 301. The
independent readback compared all settings and the order of every folder.
This is measured capacity for those profiles. Admission of larger
production configurations remains a migration decision.
[C# fixture](../../tools/rust-qa/yaml/dotnet/Program.cs) · [Rust codec](../../tools/rust-qa/yaml/src/codec.rs) · [Byte decoder](../../tools/rust-qa/yaml/src/encoding.rs).

The local run at `artifacts/rust/yaml-assessment/runs/0468771-linux-x64/`
matched all 124 first-party sources to that commit. Its `result.json` has
SHA-256 `6ccd5cb696151e9a1dbb19571f4ac5cc37acbb864d38c091d0fe1147ba213496`.
The 279-file evidence index has SHA-256
`6045eb7806513aa7b28ca2c4eb9d1c4f426bc0fee2d42a7e23ca7c85c651728b`.

### Four native saved-folder exchanges at 5efe1f1

Each native host completed 57 cases using the shipping C# configuration
sources on .NET 10.0.15. Each passed 171 byte comparisons, 277 semantic
assertions and 152 C# readback assertions. The ten inputs with decoding
errors produced no replacement files. The 300-folder C# saves differed
in byte length between Windows and Linux. Across both encodings and all
four hosts the final Rust YAML for 301 folders was identical. Its 89,998
bytes have SHA-256
`d189a42aaf1efa502f70eed2a676f7d8b4587f0b372fed93a4e791e3364081f2`.

| Original archive | UTF-8 bytes for 300 folders | UTF-32LE bytes for 300 folders |
| --- | ---: | ---: |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14991894015) | 84,930 | 330,124 |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14992767644) | 84,930 | 330,124 |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14992778162) | 88,849 | 345,800 |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14991884778) | 88,849 | 345,800 |

Detached replay checked all 1,116 indexed files, the 124 first-party
sources per target and the original loader and writer against the
shipping revision. An independent comparison of the decoded settings
checked each folder's path, album, mode, filters and position before
and after the edit. The combined receipt at
`artifacts/rust/hosted-yaml/45548715758/four-host-saved-folders.json`
has SHA-256 `e88c8c76667a4261f48b46df7542e6821e849d9b4ae7882377222b4b94600fce`.

### Reading the Rust output with the delivered 3.0.4 Flatpak assemblies

An isolated driver on Fedora x64 loaded the config reader, writer,
validator, YamlDotNet and .NET 10.0.12 runtime from the original signed
Linux x64 Flatpak via the local .NET host. The package's OSTree commit was
`abeebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da`.
The extracted `ImmichFolderWatch.Core.dll` had version 3.0.4.0 and
SHA-256 `22fd3d96b18f11a6bd018a3d378cbf7903140e1aed5bee2eb5a39c9a730a8e03`.

The test took the 300- and 301-folder Rust results from the original
Ubuntu x64 archive above. The delivered reader opened each in editing
and runtime modes. The writer saved both and the validator accepted the
reopened files. All eight fields of every folder, their order, all other
settings and the resolved runtime paths matched. In the unchanged case
the writer reproduced the original 84,930-byte C# save byte for byte.
After the edit it produced an 85,184-byte save with folder 301 intact.
The test exercised the delivered assemblies directly using a synthetic
profile. Its local `result.json` in
`artifacts/rust/yaml-assessment/signed-flatpak-3.0.4-folders/` has
SHA-256 `530106cdc6ba549daf0dc3464cde5988a728d82551bd2ba21efd991054c7a7b5`.
[Release input pins](../../tools/RustCompatibilityOracle/installed/release.json) ·
[Original native input](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14991894015).

### Leading U+FEFF in a saved album name

The shipping writer emits the five-character album name `\uFEFFFoto` as a
plain YAML scalar. The original Rust reader rejected the 590-byte C# save
with SHA-256 `a79e6909bf517ee563bed00a61054325c42cfcbfd824cbdb5f2568b963e34550`.
At the beginning of the scalar its UTF-8 bytes are `EF BB BF 46 6F 74 6F`.
The file decoder consumes a byte-order mark at the beginning of the file.
Inside the document the [parser options](../../tools/rust-qa/yaml/src/codec.rs)
now preserve U+FEFF as scalar content. A property named `\uFEFFmaxAttempts`
remains an unknown property. The one-document limit still rejects the
multiple-document control.

On Fedora x64 the native comparison passed 59 cases, 177 byte comparisons,
289 semantic comparisons and 160 C# readback assertions. The original save
and the same save with a UTF-8 preamble produced identical Rust output.
The Rust writer escaped the album as `"\uFEFFFoto"` in both the original
and edited configurations. The delivered 3.0.4 Flatpak assemblies described
above read, validated, saved and reopened both outputs. After adding a
second folder the first album retained all five characters. Saving the
unchanged configuration reproduced the 590 original bytes. The local
receipt at `artifacts/rust/yaml-assessment/format-mark-original-signed-x64/result.json`
has SHA-256 `2befca957f6b93bfb6a6a694bfc449b2850f7f4cc7496161a3d6f458370a960e`.

### Native format mark exchange at e2f161b

With a UTF-8 file preamble, the C# save occupied 593 bytes on both Linux
hosts and 621 bytes on both Windows hosts. Each file contained a second
`EF BB BF` sequence at the beginning of the album name. On all four hosts
Rust preserved that character through a read, write and edit. The unchanged
615-byte and edited 869-byte Rust outputs matched the two inputs read by
the signed 3.0.4 Flatpak assemblies above, byte for byte. In the separate
45-byte input the unknown property `\uFEFFmaxAttempts` left the ordinary
retry limit at seven. C# also read back its deliberate edit to nine.

Each native host completed 59 cases on .NET 10.0.15, with 177 byte
comparisons, 289 semantic comparisons and 160 C# readback assertions.
All ten inputs with decoding errors remained read-only. Detached replay
verified the Actions digest, 285 indexed files and 124 first-party source
hashes per archive. The combined receipt at
`artifacts/rust/hosted-yaml/45565563795/four-host-format-mark.json` has
SHA-256 `f1b739fe6ea8ab4f600caa5654e9df4c98ffa4e6699e6b0474479b88d00aef21`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/14999328017) ·
[Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15000251627) ·
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/14999932815) ·
[Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/14999349523).

### Physical Unicode breaks in shipping saves

The signed Linux x64 3.0.4 writer saved `Foto\u2028Nord` and
`Foto\u2029Nord` as 609-byte profiles. In each folded YAML block it
emitted the actual Unicode separator followed by six indentation spaces.
Its loader returned the original album name. At `e2f161b` Rust included
those six spaces in the name. The original files and the comparisons
are under `artifacts/rust/yaml-assessment/signed-album-separators-x64/first`.
Its `result.json` has SHA-256
`614a17e927783f3d60d7b1e4de4092af82c7f20353a3ffe4047a37868d3132ea`.

The adapter uses a separate view of physical line boundaries for the
pinned scanner. It maps each scalar's byte span back to the original
decoded file and uses the reported scalar style and block indentation to
recover its value. This lets an ordinary dedented key end the previous
value. Extra indentation inside a literal or folded block survives, as
do spaces after an escaped `\L` or `\P`. The ordinary YAML serializer
quotes the reconstructed value for the final typed parse, which enforces
the document, alias and decoded-scalar budgets. The original input-byte
limit applies before this processing. Both the parser and serializer come
from the existing filtered sources.
[Rust scalar handling](../../tools/rust-qa/yaml/src/scalar_breaks.rs) ·
[Shipping scanner](https://github.com/aaubry/YamlDotNet/blob/v18.1.0/YamlDotNet/Core/Scanner.cs).

For `Foto\u0085Nord` the 3.0.4 writer itself produced a save that its
loader reopened as `Foto\nNord`. The comparison follows that observed
value. A tab and the punctuation control `Fotos 2026 – 日本語: #1`
survived unchanged. The original installed Windows x64 and ARM64 packages
contained the same Core DLL, and the two Linux packages shared their own
Core DLL. All four contained identical YamlDotNet bytes. A separate
Fedora x64 test exercised the managed Windows Core DLL with .NET 10.0.12
and reproduced the five original readbacks. Its receipt at
`artifacts/rust/yaml-assessment/shipping-package-assembly-comparison/comparison-9t1snsjs/comparison.json`
has SHA-256 `4a2e0afc02f3cb1e76a5d7b9ab4c49ebb62d6e9c625045b8c2ada81178ea89e4`.

On Fedora x64 the pinned release build completed all 13 native assessment
steps. The 67 inputs passed 201 byte comparisons, 332 Rust semantic checks
and 188 C# readback assertions. Ten inputs with decoding errors remained
read-only. The two new shipping saves exercise the watch path, album name
and excluded filename in the same profile. Both the original and changed
Rust outputs passed the shipping reader. The local native `result.json` at
`artifacts/rust/yaml-assessment/runs/scalar-separators-fedorax64-03/` has
SHA-256 `a268585164e42cc0e9f1a19177352f3a196fc7b1bb46c94462718bf87208362e`.
All 308 indexed files and 125 first-party source hashes matched on replay.
The signed Fedora five-label exchange with this release binary is at
`artifacts/rust/yaml-assessment/signed-album-separators-x64/frozen-readback/result.json`,
SHA-256 `d958b224f5febdaac45efb9f609b6ac12142225f27625522d435fbc6d64afefc`.

The frozen Fedora executable has SHA-256
`78c63f0fe5e14142ff7bb248019786a7a06fcaf047b43ebf5af0f469ae335c97`.
The original Windows and Linux managed assemblies each read, saved and
reopened 34 outputs from that executable on Linux x64. Ten outputs exercise a
watch path, log directory, excluded directory, excluded filename and extension.
The other 24 cover both separators in UTF-8 with and without a BOM, UTF-16LE/BE
and UTF-32LE/BE, before and after a Rust edit. Each original retained its hash.
Under `artifacts/rust/yaml-assessment/shipping-package-assembly-comparison/`,
`fields-tn22dsyh/result.json` and `encoded-smbdhp6b/rust-readback.json`
have SHA-256 `df8ac420dcfbb5fa753b481ec6ed0d85c533753cb7731d33a346fefdbdeec46c`
and `39701df03730f55b81dde0bb68e7abcb0d15940534c1feb3b7b82360f64c8729`.
Independent review also checked 38 synthetic profiles and their signed
resaves with the same adapter source, 76 signed readbacks of Rust output,
and three rejected indentation cases. The three respective reports under
`signed-album-separators-x64/independent-04/` have SHA-256
`ca223aa0f5d1173d5708de1eb37481d7f21599a193a7e3eab2ea14bbb77e0803`,
`0086f4fd1d24febf3470007363ee96d6abd437a3ebc61e6ee642be68c5cec1f3`
and `2f6384935eea5ed040d8bed3976f2001d451a8b4d478ec0bcb92e12572361d20`.
Native Windows and Linux ARM64 execution of the updated adapter is pending.

### Anchors on recognized and skipped properties

The shipped reader rejects an album alias whose only declaration occurs
in an unknown property or on a property key. When a recognized path
defines `&a Pictures` and a later unknown property defines `&a Ghost`,
the shipped reader still sets `albumName: *a` to `Pictures`. The earlier
Rust adapter set it to `Ghost`. The original 602-byte missing-anchor case
and the signed role comparisons are under
`artifacts/rust/yaml-assessment/ignored-mapping-anchor/`.
The 12-case `roles-first/comparison.json` has SHA-256
`20d59943a6cf81df7262b2ebcb74a67332d15d047e4e4e54595e79fa217bd61e`.

The adapter uses mapping and sequence events from the existing parser
to identify the values the shipping loader visits. It assigns each
declaration its own internal name and resolves a recognized alias to the
last recognized value with that name. A repeated recognized property
can therefore supply different values to earlier and later references.
Aliases used as property keys on a typed object fail. The original
tokens and file hashes remain available for the byte-level checks.
[Anchor handling](../../tools/rust-qa/yaml/src/anchors.rs) ·
[Shipping configuration model](../../src/ImmichFolderWatch.Core/Configuration/AppConfig.cs).

Ignored subtrees still go through the native depth, node, event, scalar,
unsupported-tag and anchor recording checks. Resolved aliases in ignored
data still consume replay work. An unresolved alias in skipped data
has no target. The adapter counts its token against the alias allowances
and supplies an empty scalar to the typed reader. The same structural
pass uses the shipping physical line boundaries when an input also
contains a Unicode separator.

The Fedora x64 run `artifacts/rust/yaml-assessment/runs/typed-anchors-fedorax64-02/`
passed 74 profiles, 222 input-byte checks, 359 differential assertions and
204 C# readback assertions. All 74 original files retained their hashes.
Eleven Rust tests passed, including limits for skipped data. The result
SHA-256 is `6bd917b517de6a064c5417495bd93355717a7385dd95a0f074c110456c8d7fa3`.
The exact release binary matched the signed loader on two profiles combining
a Unicode separator with an ignored anchor redeclaration and one case-sensitive
property profile. The original Flatpak 3.0.4 assemblies read, validated,
saved and reopened all six unchanged/edited Rust outputs.
The `signed-release-02/signed-readback.json` SHA-256 is
`145180f9268611cfab838f7d18fbd0fe3189157415d9597cda022b3bf602be22`.

An independent build from the same Rust sources matched the original
shipping results for 17 inputs and all 11 accepted C# resaves. The signed
Flatpak and MSI-delivered Core assemblies running on Linux x64 passed 44
checks of the resulting Rust files. The earlier 76 physical-separator
comparisons also passed. The role and readback report
`independent-02/summary.json` has SHA-256
`10e8eb99da2721fafc21963afe2930939fc4b301625ec5e407e45a88f68e7567`.
Native execution of this change on the other three targets remains pending.

The frozen release executable from the complete 74-profile run has SHA-256
`ad02d0e907f7ed6e5446070682d9005ab2dbd07b9112954266732861e5641588`.
The independent package readers repeated all 28 input and resave comparisons
and 44 readbacks of its alias outputs. The same release build also passed
the 20 field-placement and 48 encoding readbacks with the same two readers.
Under `artifacts/rust/yaml-assessment/` the original receipts are
`ignored-mapping-anchor/frozen-release-02/summary.json`,
`shipping-package-assembly-comparison/fields-gmsqzokq/result.json` and
`shipping-package-assembly-comparison/encoded-vlf4e8ry/rust-readback.json`.
Their SHA-256 values are
`7b5d227fb67db0426503d2ddc0928a789e746e861caacce0a125b4e82d08e82f`,
`43b4757faced67935354c05eb002e982e9d373273cda37aa20a7d136bb66ded8`
and `af152cef9ec7aa97c4080bed869600a4fe011ab592cb4a9ec5f6833bc180fa0f`.

The released parser also rejects three compact flow mappings where a
property follows an anchored plain path on the same line. Through `5b6cebf`,
Rust accepted these inputs, including the example using only recognized
fields. Both readers accepted the neutral unanchored controls. The report
`compact-extended/compare-candidate-02.json` has SHA-256
`2921353a514010512934e8462df7b3dc7ac12e3cf90ce6ef53b56324c3e87423`.

### Anchored scalars in compact mappings

In a flow mapping, YamlDotNet 18.1.0 looks ahead twice after an anchored
scalar value. The next property therefore causes a syntax error. The same
value as the last property is accepted, including a trailing comma. The
rule also applies when the value is quoted or the next key is on a later
line. An anchored collection, a mapping key and an implicit empty value
follow different parser paths. The Rust reader now distinguishes these
cases using the style, anchor and span from its bounded parser.
[Shipping parser](https://github.com/aaubry/YamlDotNet/blob/v18.1.0/YamlDotNet/Core/Parser.cs#L503-L541) ·
[Rust compatibility pass](../../tools/rust-qa/yaml/src/anchors.rs).

The Fedora x64 assessment `runs/compact-flow-fedorax64-01/result.json`
passed 82 profiles, 246 byte checks, 392 semantic comparisons and 224
C# readbacks. Twelve Rust tests passed. The result SHA-256 is
`cbe73af5104e87085bc4fcd441b78ba5598c34b130c240f7607bb51b5c67dde6`.
The release executable has SHA-256
`ee8f2f8ac0fcb687955d90c209d0ef5bea285f37dd2d272987130b0af101670a`.

Both 3.0.4 Core assemblies from the MSI and Flatpak, running on the
Linux x64 .NET 10.0.12 runtime, accepted 15 of 27 original profiles and
rejected the other 12. Rust matched every result, read the 15 signed
resaves and produced unchanged and edited YAML that passed all 60
package readbacks. `ignored-mapping-anchor/compact-independent-01/summary.json`
has SHA-256 `c5f3fad343c204370d67da752901691705542c9569a4e2d92d8527a224b8343c`.
A separate replay including all three original compact failures checked
23 source profiles, 12 signed resaves and 48 package readbacks against
the same release executable. Its `compact-two-packages-01/summary.json`
has SHA-256 `9e4be498e564bc18b2df8bbc56f5257e46689163da0127b8e59db21956a6f1dd`.

### Four native anchor and compact mapping exchanges at 0bb39bf

The Windows and Ubuntu x64 and ARM64 jobs each passed all 82 profiles,
246 byte checks, 392 semantic comparisons and 224 readbacks with the
native .NET 10.0.15 runtime. Each archive contained the expected 112
unchanged or edited YAML files. All 448 products were independently
decoded and checked. The excluded files for rejected or lossy inputs
were absent. On each host twelve Rust tests and three source-filter tests
passed. The readback matched all 342 indexed files and all 126 source
inputs to the checkout `0bb39bff547b649e4b4f4bf7647e8cbd1b91fe47`.

| Native host | Original Actions archive |
| --- | --- |
| Windows x64 | [15144287783](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15144287783) |
| Windows ARM64 | [15144996577](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15144996577) |
| Ubuntu x64 | [15145045928](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15145045928) |
| Ubuntu ARM64 | [15145015810](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15145015810) |

The archive digests, native observations and decoded products are indexed
in `artifacts/rust/hosted-yaml/45874234228/four-host-anchors.json`, SHA-256
`2a265c8e41381b76a59fedacb48b0f702ad7e92efa46b4530948b28e06dfcf9e`.
The clean offline Fedora build at this revision also reproduced the
filtered source tar and all 112 YAML outputs byte for byte. Its result
under `runs/compact-flow-clean-0bb39bf-fedorax64/` has SHA-256
`a986d61e739b0e2c7170abe54a47d38e66b4d4113fe0547f86a09b7e75884fca`.

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

Choose a fresh output name for another run. The four native executions and
independent filtered-source review cover the tested corpus. Additional YAML
edge cases, Windows namespaces, the shipping casing policy, atomic profile
publication, crash/full-disk recovery and migration retain their own scope.
The [acceptance record](acceptance.md) owns the remaining RW-02/RW-03 gates.
