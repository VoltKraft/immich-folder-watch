# RW-02 storage input assessment

This dependency/source audit is dated 2026-11-20. Application workspace
dependencies and the application lockfile are unchanged. The reviewed
SQLite/JSON/SHA subset is maintained in the separate development-only workspace
[`tools/rust-qa/storage`](../../tools/rust-qa/storage). Its complete generated
lockfile, source/notice inventory and native runner are checked-in inputs;
per-run archives and databases remain ignored development evidence. The original
broader prospective audit is in `artifacts/rust/storage-assessment/`. Its YAML
graph has not been adopted by either maintained Rust workspace.

## Exact candidates and graph

The pinned Rust 1.100.0 Cargo resolved the following explicit candidates against
the real crates.io registry. These are assessment inputs, not a blanket approval
of optional features, future versions or final application distribution.

```toml
rusqlite = { version = "=0.43.0", default-features = false, features = ["bundled", "backup"] }
serde = { version = "=1.0.229", default-features = false, features = ["std", "derive"] }
serde_json = { version = "=1.0.154", default-features = false, features = ["std"] }
serde-saphyr = { version = "=2.2.0", default-features = false, features = ["deserialize", "serialize"] }
sha2 = { version = "=0.11.1", default-features = false }
```

Primary package/source references: [rusqlite](https://docs.rs/crate/rusqlite/0.43.0),
[serde](https://docs.rs/crate/serde/1.0.229),
[serde_json](https://docs.rs/crate/serde_json/1.0.154),
[serde-saphyr](https://docs.rs/crate/serde-saphyr/2.2.0), and
[sha2](https://docs.rs/crate/sha2/0.11.1). Actual downloaded package contents,
including normalized/original manifests and source license files, were examined;
registry metadata alone is not the license evidence.

The union contains **48** third-party packages. Target-filtered normal/build
feature graphs were captured for all four targets, without compiling or executing
foreign targets:

| Target | Third-party packages | Distinct CPU support |
| --- | ---: | --- |
| `x86_64-unknown-linux-gnu` | 47 | `core_detect`; no `libc` in this selected graph |
| `aarch64-unknown-linux-gnu` | 47 | `libc`; no `core_detect` |
| `x86_64-pc-windows-msvc` | 47 | `core_detect`; no `libc` |
| `aarch64-pc-windows-msvc` | 46 | Neither of those two packages |

`cpufeatures` and `multiversion_no_op` occur on every target. Native execution is
still separately required. The exact archive checksums were independently
recomputed and all 48 matched the generated lockfile.

Assessment artifact SHA-256 values:

- `Cargo.lock`: `ba3303d430e0c596b87a37617a36a15c8499d7ec036601f6a9db913c615e9d7e`.
- `source-inventory.json`: `710c5b3cde154c5df53e03944908edfb7162b805f9cce69be3745806d4dbcb66`.
- Canonical `target-graphs.json`: `ab4bef4edf3af7bd36bab7f15869f65e629273f63e4df4ed67746788f3eec13d`.

The graph was obtained with `cargo metadata --format-version 1`, then, using the
same lockfile/cache, `cargo metadata --locked --offline --filter-platform <target>`
and `cargo tree --locked --offline --target <target> --edges normal,build,features`.
No build script was executed during graph extraction.

## Native SQLite and build boundaries

`libsqlite3-sys 0.40.0` contains SQLite **3.54.1**, source ID
`2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76`.
The amalgamation carries SQLite's copyright disclaimer; the official
[SQLite copyright statement](https://www.sqlite.org/copyright.html) confirms the
deliverable library's public-domain status. The Rust bindings/wrapper carry MIT
notices. The selected build compiles the supplied amalgamation, with supplied
bindings; it does not invoke bindgen or download SQLite at build time.

| Input in `libsqlite3-sys 0.40.0` | SHA-256 |
| --- | --- |
| `sqlite3/sqlite3.c` | `0c657666d819f261cc4007526ad57e1669de9949df7a8ea847aa284a2bf0ee52` |
| `sqlite3/sqlite3.h` | `d6c84557261893439b341d2e6c35187ae3ea24fbfd843ad94616f72d89242b8c` |
| `sqlite3/bindgen_bundled_version.rs` | `a25057a06d8cb5053a61c8f0ff746cc3d81b3bd778fbd3199ba12c8a6ee2945d` |
| `build.rs` | `769b31370a41aa722e1d5a530012432c985bb142eab34d095481ffd1a3436e1b` |

Resolved rusqlite features are `backup`, `bundled`, `modern_sqlite`. Native sys
features are `bundled`, `bundled_bindings`, `cc`, `default`,
`min_sqlite_version_3_45_3`, `pkg-config`, `vcpkg`. The last two are build helpers;
the selected bundled branch does not link a system/vcpkg SQLite. SQLCipher,
OpenSSL, extension APIs, sessions, loadable modules, wasm, chrono/time and statement
cache dependencies are absent from the selected Rust graph.

The native build script nevertheless enables SQLite FTS3/5, JSON, RTree, STAT4,
SOUNDEX, DBSTAT, column metadata, API armor, foreign keys and URI handling, with
`SQLITE_THREADSAFE=1`; these are part of the real native inventory. It also enables
native extension loading by default, independently of the disabled Rust API.
The maintained assessment explicitly sets
`LIBSQLITE3_FLAGS="-USQLITE_ENABLE_LOAD_EXTENSION -DSQLITE_OMIT_LOAD_EXTENSION"`
and asserts runtime compile options. It fixes `LIBSQLITE3_SYS_USE_PKG_CONFIG=0`
and records compiler commands and removed build-override variable names.
No native compiler pin or final candidate ABI is established by this source audit.

## License and asset findings

The selected code licenses permit this repository's AGPL-3.0-only distribution
when their notices and source obligations are retained. Where a package permits
MIT or Apache-2.0, MIT is the selected redistribution option; both supplied license
files are retained in the assessment notice bundle. This statement is limited to
the examined code and the explicit findings below, not every unrelated asset in
an archive. **103** supplied notice/license files are preserved and hashed.

- `granit-parser`'s root `LICENSE` requires inherited Chen Yuheng and Ethiraric
  notices plus the Bourumir Wyngs modification notice. Its four hidden `.licenses/`
  files are present and included; collecting only filenames beginning `LICENSE`
  would miss them.
- `encoding_rs` includes WHATWG encoding data under BSD-3-Clause in addition to
  its MIT/Apache code; retain `COPYRIGHT` and `LICENSE-WHATWG` in binary/source
  notices. `unicode-ident` additionally requires its Unicode-3.0 notice.
- `arraydeque` declares MIT/Apache in metadata but the archive's actual `LICENSE`
  supplies the MIT option. That option is sufficient and is the selected one.
- `serde-saphyr` identifies tests adapted from `yaml/yaml-serde` PRs 9 and 10.
  The source project's [MIT notice](https://github.com/yaml/yaml-serde/blob/main/LICENSE-MIT)
  and [Apache notice](https://github.com/yaml/yaml-serde/blob/main/LICENSE-APACHE)
  support that compatible source license, rather than relying on the comments'
  word “assuming”. The tests are not linked into the application.
- `vcpkg`'s apparent DLL/EXE fixtures are empty placeholders, not bundled runtime
  libraries. Crypto `.bin` files are test vectors. `annotate-snippets` SVGs are
  example diagnostics; no fonts or precompiled executables were found in runtime
  inputs. Runtime build/source scanning remains part of final packaging acceptance.
- **Source-bundle disposition is open:** `base64 0.23.1/icon_CLion.svg` is a real
  promotional JetBrains logo, referenced by that crate's README. It is not
  compiled into the library and has no file-specific free-software license.
  [JetBrains' brand terms](https://www.jetbrains.com/company/brand/) impose
  attribution and usage conditions distinct from MIT/Apache. Do not call an
  unchanged full archive fully AGPL-compatible. Before redistribution, select and
  verify a reproducible source-bundle exclusion of this non-build asset and its
  README image reference, or establish separate redistribution permission.
  The downloaded archive remains untouched in the private assessment cache.

The YAML candidate enables only `serialize`/`deserialize`; filesystem includes,
property interpolation, robotics extensions, comments, huge documents and GUI
integration features are disabled. It has explicit duplicate-key and complexity
budget controls, but compatibility/budget tests have not run yet. SHA-2 uses the
reviewed RustCrypto crate and CPU-specific Rust intrinsics/fallbacks; no handwritten
cryptography is proposed. Complete YAML/parser security and native crypto evidence
are not implied by source-license review.

## Execution and adoption status

Graph download, checksum verification, target-feature capture and notice/asset
inspection passed. No application dependency has been adopted. The SQLite/JSON/SHA
subset has no identified license blocker for an isolated synthetic compatibility
spike, retaining its notices and the native build restrictions above. The complete
YAML source distribution has the explicit logo disposition outstanding.

The source/feature audit cleared the **31-package SQLite/JSON/SHA subset** for
the private synthetic experiment. Its separate generated lockfile is
`sqlite/Cargo.lock`, SHA-256
`db9353d95a8e9c73c2a8183a76fa329e0e72a76d3155ed95d908c521c4f71b98`.
It uses the same reviewed package versions and the dependency-free `ifw-legacy`
codecs. YAML and its assets are absent from this executed subset.

Native Fedora Linux x64 execution passed on 2026-11-20 with Rust 1.100.0 and
`CC=/usr/bin/cc`, GCC 16.2.1 20261029 (Red Hat 16.2.1-3):

- Rust SQLite **3.54.1** imported both reviewed sensitive/insensitive C# SQL
  fixtures and matched all typed values in their four tables and repair JSON.
  Each database contains nine rows, including values above JavaScript's exact
  integer range. Snapshot comparison normalizes only DDL line endings and row
  order; the C# snapshot's `ORDER BY 1,2,3` is not a unique order for sync entries.
  It does not normalize identity keys, numeric values or JSON payload strings.
- Parameterized transactions updated an entry, exact album ownership, account
  history and repair JSON together. A deliberately failing nonnegative-size
  constraint rolled back an earlier valid history update. A changed snapshot was
  explicitly unequal to the original.
- Each database retained **24,752 WAL bytes** with committed changes while the
  main database file hash was unchanged. The actual SQLite online-backup API
  copied those changes; all four backup tables matched and `integrity_check`
  returned `ok`. This was not a raw main-file copy or a checkpoint-only test.
- A future-version database in **DELETE journal mode** was inspected through a
  read-only SQLite connection. This first experiment observed version 99 and
  omitted the initializer. It retained identical bytes with no new WAL/SHM/journal. Future-version databases
  with an existing WAL remain a separate, unproven no-mutation case.
- All five account SHA-256 vectors matched the actual C# corpus, including URL
  spelling and key-space sensitivity. SHA-256 of the rewritten repair's synthetic
  content was independently checked again by C#.
- Existing C# Core readers with .NET **10.0.12** and SQLite **3.53.4** passed
  **40 assertions** over both original and backup databases: full ordered entry
  and repair records, exact ownership, unrelated account preservation, account
  history timestamp, tombstones, a `9,007,199,254,740,995` file size and a pre-1970
  repair timestamp with 100-nanosecond precision. This exercises the storage
  readers, not full application startup or worker side effects.
- Formatting and Clippy with `-D warnings` passed. Native compile options include
  `OMIT_LOAD_EXTENSION`, exclude `ENABLE_LOAD_EXTENSION`, and a SQL attempt to use
  `load_extension` fails. ELF dependencies are the system C/math/GCC runtimes and
  loader; SQLite is linked from the reviewed bundled source.

Subsequent independent review verified all 254 evidence hashes from
`maintained-linux-x64-02`. It distinguished read-only detection from an
initializer actually refusing a database. The corrected assessment routes
both supported and future versions through the same initialization entry
point. The supported file entered WAL mode. Version 99 returned the specific
unsupported-schema error on both read-only and writable connections, before
journal changes. Both future files retained their original bytes and had no
new sidecars. This result covers DELETE mode on the local Linux x64 host.
The corrected source SHA-256 is `1ca0c0e3192a66716796b1ee6f06996c2802e46831c2c48912a5d52bc1acbccd`.
In `artifacts/rust/storage-native/maintained-linux-x64-03/`, all 254 evidence
hashes matched. The result digest is
`19da6195eb1f5de959164d4f8fe9eb85cfa5f7899d10273f3304cc765a5c4d07`.
Independent re-review at `f6e832823d65eb074492f5ea64d79f6561482268`
verified both error branches and all 128 archived source hashes. It confirmed
that the two future files retained DELETE-mode headers and had no sidecars.
The earlier evidence-precision finding is closed.

The first experiment exposed the comparator's ordering difference and stopped;
the corrected complete rerun and C# reread passed. Final evidence is in ignored
`artifacts/rust/storage-assessment/run-linux-x64-03/`, including explicit unproven
areas and `evidence-hashes.json`. Key hashes:

| Artifact relative to the assessment directory | SHA-256 |
| --- | --- |
| `sqlite/src/main.rs` | `da5d67bbc7a2c0c163d38ab7344f2bbb99f3e05c691943b606e83422114ccf76` |
| `dotnet/Program.cs` | `e18cf913b2be97ec1504ed69cddaede2a64445ed8a1800ba1ac7d798d7b3f024` |
| `run-linux-x64-03/result.json` | `da54725636183d0ad1af4ef52735143f9c699b74951d755707576e86260ecbe6` |
| `run-linux-x64-03/csharp-readback.json` | `304497118107249204a63397f55afec2d7b7a6c96965759d6615b3ecc700cff7` |

The isolated invocation from the repository root, with the pinned toolchain on
`PATH` and `CARGO_HOME=artifacts/rust/storage-assessment/cargo-home`, is:

```text
CC=/usr/bin/cc LIBSQLITE3_SYS_USE_PKG_CONFIG=0 LIBSQLITE3_FLAGS='-USQLITE_ENABLE_LOAD_EXTENSION -DSQLITE_OMIT_LOAD_EXTENSION' cargo run --manifest-path artifacts/rust/storage-assessment/sqlite/Cargo.toml --offline --locked -- rust/tests/fixtures/legacy/linux artifacts/rust/storage-assessment/<new-run-directory>
dotnet run --project artifacts/rust/storage-assessment/dotnet/StorageReadback.csproj --artifacts-path artifacts/rust/storage-assessment/dotnet-output -- artifacts/rust/storage-assessment/<new-run-directory>
```

The output directory must not exist; the tool refuses to mutate an existing
profile. The C# reader additionally restricts inputs to the assessment tree.
These were the initial disposable sources. Their maintained successor is
described below; neither is a production adapter.

The [observed native casing divergence](rw02-legacy.md#casing-source-and-license-audit)
requires preservation of stored identity keys and explicit legacy-variant
compatibility. This experiment does not rewrite keys or infer one universal map.
Remaining work includes complete YAML semantics/budgets, old optional schema
upgrades, future WAL preflight, full-disk/process-crash recovery, device identities
and the other native targets. Final application adoption requires primary-agent
integration of the approved manifest/lock/build-input policy, independent review
and the remaining [acceptance gates](acceptance.md).

## Maintained native runner

[`storage/Cargo.toml`](../../tools/rust-qa/storage/Cargo.toml) declares its own
workspace and uses exact rusqlite/serde_json/sha2 versions from the reviewed graph,
plus the local dependency-free `ifw-legacy` crate. Regenerating its lockfile after
relocation with pinned Cargo and `--offline` produced **byte-identical output** to
the reviewed disposable SQLite lockfile: SHA-256
`db9353d95a8e9c73c2a8183a76fa329e0e72a76d3155ed95d908c521c4f71b98`.
All **31** external `(name, version, checksum)` entries match. Cargo includes
inactive serde configuration dependencies in that lockfile; it is not a list of
31 linked packages. The exact selected graphs have 24 external packages on Linux
x64 and both Windows targets, and 25 on Linux ARM64 (the additional `libc`).

Generated [`inputs.json`](../../tools/rust-qa/storage/inputs.json), SHA-256
`2e5306ed6b8a951ad64738c508b645e904cf19d2598ceacc1cc655448e36b596`,
preserves each original archive identity, license selection, **62 supplied notice
hashes**, four native SQLite source hashes and all four selected feature graphs.
[`record-inputs.py`](../../tools/rust-qa/storage/record-inputs.py) generated it
from the earlier source audit and matching offline Cargo sources; regeneration
does not replace a new license/source review when an input changes. No vendored
source or supplied notice was hand-edited. The runner archives original source
packages and notices unchanged in every completed acquisition.

With the repository's pinned native Rust and .NET toolchains available:

```text
python3 tools/rust-qa/storage/run.py x86_64-unknown-linux-gnu --output artifacts/rust/storage-native/linux-x64
```

Use the corresponding native target on Linux ARM64 or Windows x64/ARM64. The
output directory must be new and strictly below repository `artifacts/rust`;
omitting it selects a fresh timestamp/UUID directory. `--cargo-home` selects an
isolated repository-local cache, `--dotnet` selects an SDK executable, and
`--offline` requires cached dependencies and disables NuGet advisory retrieval
for that run. Default acquisition is network-enabled and locked. It does not
alter the global Cargo/.NET setup. Builds use separate scratch output below
`artifacts/rust/storage-build`, avoiding huge evidence artifacts.

Before running any crate build script, the runner verifies the generated lock,
every original archive SHA-256 and **all unpacked source bytes**, then compares
the selected target features. It rejects traversal, archive links, duplicate
members, changed notices and unexpected unpacked source files. The only allowed
additional source files are Cargo's bookkeeping metadata. Four negative-control
tests cover tampering, traversal, duplicate/injected files, archive links and
wrong-platform/changed corpus data. Native compiler/OS validation reuses the
pinned toolchain checker. The C# process independently requires matching native
process and OS architectures.

The Windows runner uses the reviewed native Windows corpus, including Windows
separators and its original DDL provenance. Fixture payloads and this tool's
sources are checked out as LF by `.gitattributes`; raw historical C# source hashes
in corpus manifests retain their original CRLF/LF provenance and are not treated
as current source-file hashes. Each new run archives and hashes its actual C#
Core sources separately. SQL snapshot comparison canonicalizes DDL CRLF only;
stored path keys and repair JSON strings are preserved. No Linux-generated
absolute source path is substituted into Windows expected results.

The native build uses upstream `cc`/`find-msvc-tools` on Windows. The selected
`-USQLITE_ENABLE_LOAD_EXTENSION -DSQLITE_OMIT_LOAD_EXTENSION` overrides follow
libsqlite3-sys's existing `-D` convention. Microsoft's
[command-line syntax](https://learn.microsoft.com/en-us/cpp/build/reference/compiler-command-line-syntax?view=msvc-170)
accepts `/` and `-` prefixes; its
[`/U` contract](https://learn.microsoft.com/en-us/cpp/build/reference/u-u-undefine-symbols?view=msvc-170)
can undefine a symbol set by `/D`. Each Windows lane must still prove the actual
options and source ID at runtime. The runner requires
both debug/release compiler command logs from Cargo 1.100's real
`build/libsqlite3-sys/<hash>/run/stdout` layout. Runtime assertions reject a missing
`OMIT_LOAD_EXTENSION`, any `ENABLE_LOAD_EXTENSION`, or a changed SQLite source ID.
SQL `load_extension` must fail. Existing Windows/Linux Core behavior is selected
by its normal platform APIs; no fake OS flag overrides the C# readback.

Per-run `result.json` records step exit codes, native identities, source revision
and modified paths, graph/source counts, Rust/C# results and explicit unproven
cases. `evidence-hashes.json` covers retained logs, source copies, 31 original
archives, supplied notices, feature graphs and synthetic databases. A failed run
retains its failure state; directory existence never implies a passing result.

The maintained runner passed a fresh native Linux x64 end-to-end run on
2026-11-20 in `artifacts/rust/storage-native/maintained-linux-x64-02/`. Its Git
source is `92b5518e7b78bb4fd9e9fd5c5092911d3a9d12c9` plus the archived,
then-uncommitted assessment inputs; all **128 archived first-party files** were
rechecked against the workspace after execution. All **13 steps** exited zero,
including four negative-control unit tests, formatting, Clippy with `-D warnings`,
Rust release build, real Rust round-trip, C# restore/build and **40 actual Core
readback assertions**. The C# build emitted zero warnings/errors.

The run authenticated **31 archives / 2,214 unpacked source files**, selected
24 native packages, and retained both SQLite compiler-command logs. GCC
16.2.1 20261029 compiled SQLite 3.54.1 with both required extension restrictions;
its compiler-family detection probe's expected unsupported `-?` diagnostic is
retained separately from successful compilation. Both live WALs contained
24,752 bytes. C# ran natively as X64 on an X64 OS with .NET 10.0.12 and SQLite
3.53.4. All **254 evidence-file hashes** were recomputed successfully. A second
invocation targeting that existing output directory was refused before execution
and left its result bytes unchanged.

| Maintained run artifact | SHA-256 |
| --- | --- |
| `result.json` | `143a9879e5bab479a64f2ab51427bd503e6bf75fa017e8194e01c2e61aa9d8e8` |
| `evidence-hashes.json` | `f735c653c942519e09c0cc999aed07547e1a4b11d437792b079cf3fbe9e528f9` |
| `databases/result.json` | `cd0e08db167eb75f8ebc16de7f49a1821889d2177c06ec350be0d853d5cbcd84` |
| `databases/csharp-readback.json` | `98dfc02ba4cf5fd2ce6629ca7991db200b801282f3f29e3d95ab73b4a8eefc65` |

Exact local command, with the pinned Rust `bin` directory on `PATH`:

```text
CC=/usr/bin/cc python3 tools/rust-qa/storage/run.py x86_64-unknown-linux-gnu --output artifacts/rust/storage-native/maintained-linux-x64-02 --cargo-home artifacts/rust/storage-assessment/cargo-home --dotnet artifacts/flatpak-local-2.11.2/sdk/dotnet --offline
```

Use a fresh output name when repeating it. These are Linux x64 results only;
Windows x64/ARM64 and Linux ARM64 must execute this maintained assessment before
its four-target gate can pass. Earlier scalar-probe results do not substitute for
these real SQLite/JSON/SHA and C# reverse-readback results.

## Exact resolved archive inventory

These are checksums of untouched crates.io `.crate` archives, not hashes of a
future filtered source bundle. The generated lockfile owns resolution; this table
preserves the reviewed input identities while that disposable lockfile is outside
Git.

| Package | Version | Archive SHA-256 |
| --- | --- | --- |
| `annotate-snippets` | `0.12.18` | `0258346f92c78dbc5b336b9a5b27c64447aa10643bc64e651db2edb145361564` |
| `anstyle` | `1.0.14` | `940b3a0ca603d1eade50a4846a2afffd5ef57a9feac2c0e2ec2e14f9ead76000` |
| `arraydeque` | `0.5.1` | `7d902e3d592a523def97af8f317b08ce16b7ab854c1985a0c671e6f15cebc236` |
| `autocfg` | `1.5.1` | `f2032f911046de80f0a198e0901378627c33f59ea0ac00e363d481118bd70a53` |
| `base64` | `0.23.1` | `ac07cdecf99051d9a5238b80f35af32cdeba5b336e55d957b318b50137e18da5` |
| `bitflags` | `2.13.2` | `3ded4057c258ba199e2d26386d3af3780957ecaee6c4ef4041c6b4b8b97c0b06` |
| `block-buffer` | `0.12.1` | `d2f6c7dbe95a6ed67ad9f18e57daf93a2f034c524b99fd2b76d18fdfeb6660aa` |
| `cc` | `1.11.3` | `02f0e023adb368345ce0ca6cdfc0f24a06554468d0e8503e14a0841de79bfa69` |
| `cfg-if` | `1.0.5` | `4e7648175b45a9a48536d676f68d918270699102aa8dab5496df06904c914600` |
| `core_detect` | `1.0.0` | `7f8f80099a98041a3d1622845c271458a2d73e688351bf3cb999266764b81d48` |
| `cpufeatures` | `0.3.1` | `5ca28b0ae3115b884660db4118d803791fd6756b6e88f39c0f3f7859060d7566` |
| `crypto-common` | `0.2.2` | `ce6e4c961d6cd6c9a86db418387425e8bdeaf05b3c8bc1411e6dca4c252f1453` |
| `digest` | `0.11.3` | `f1dd6dbb5841937940781866fa1281a1ff7bd3bf827091440879f9994983d5c2` |
| `encoding_rs` | `0.8.44` | `89253175e704ab869b04f9db224d38630e0211a53841a79181deae0889e169f5` |
| `encoding_rs_io` | `0.1.8` | `fba3fe847045ecff794b9c138293a80db914678c453ad63fbf0c6a9eb6e00b22` |
| `fallible-iterator` | `0.3.0` | `2acce4a10f12dc2fb14a218589d4f1f62ef011b2d0cc4b3cb1bba8e94da14649` |
| `fallible-streaming-iterator` | `0.1.9` | `7360491ce676a36bf9bb3c56c1aa791658183a54d2744120f27285738d90465a` |
| `find-msvc-tools` | `0.1.15` | `1c66915cc5391097de7a2b0b972e8505aa33c0df401fd3a6811dbdb32881ba48` |
| `granit-parser` | `2.2.0` | `9bd04d0d9c7079b416b458d2317aea4aa964c81938cb7c20f559758c4f422dc8` |
| `hybrid-array` | `0.4.15` | `27f864f10dfb56725ce5ce5472bc52252c8f93a4ab86327122cebf62c5f59a17` |
| `itoa` | `1.0.19` | `3bd1574e617a9a6c1f8f8181bd7e841e1f20e4277607ef28945765188d6284d4` |
| `libc` | `0.2.191` | `65cd87c9a6d60536580b316ad985726104730a5151c99845f2490428ef91240a` |
| `libsqlite3-sys` | `0.40.0` | `b06e69070b7e12262b0cd90832f0a7396f142a2b330181255562decf9f0c6215` |
| `memchr` | `2.8.3` | `cf8baf1c55e62ffcace7a9f06f4bd9cd3f0c4beb022d3b367256b91b87513d98` |
| `multiversion_no_op` | `1.0.0` | `743fb55ba31b18fb1ecef6bdc9aa2743314978ac084044301a7eee33fb99a20d` |
| `nohash-hasher` | `0.2.0` | `2bf50223579dc7cdcfb3bfcacf7069ff68243f8c363f62ffa99cf000a6b9c451` |
| `num-traits` | `0.2.19` | `071dfc062690e90b734c0b2273ce72ad0ffa95f0c74596bc250dcfd960262841` |
| `pkg-config` | `0.3.34` | `f6b464fbc74e149a392436b17d523f769e057cb6877f6a5c4618bc6f11800548` |
| `proc-macro2` | `1.0.107` | `985e7ec9bb745e6ce6535b544d84d6cd6f7ad8bd711c398938ae983b91a766d9` |
| `quote` | `1.0.47` | `1fbf4db142a473a8d80c26bbf18454ed458bf8d26c8219c331daecfdbd079001` |
| `rusqlite` | `0.43.0` | `f172c4812a19b26d1c23cdb0070e69db335503dfa378b910eb857386e5b8beba` |
| `rustversion` | `1.0.23` | `cf54715a573b99ac80df0bc206da022bcd442c974952c7b9720069370852e21f` |
| `scopeguard` | `1.2.0` | `94143f37725109f92c262ed2cf5e59bce7498c01bcc1502d7b9afe439a4e9f49` |
| `serde` | `1.0.229` | `4148590afebada386688f18773da617792bf2ef03ffc1e4cbd2b1d45b023e0ba` |
| `serde-saphyr` | `2.2.0` | `969cde0349344dbbf58b5f9badbfb8f806db13969364eb8007c057ef687007d9` |
| `serde_core` | `1.0.229` | `67dca2c9c51e58a4791a4b1ed58308b39c64224d349a935ab5039aa360942a48` |
| `serde_derive` | `1.0.229` | `e7a5d71263a5a7d47b41f6b3f06ba276f10cc18b0931f1799f710578e2309348` |
| `serde_json` | `1.0.154` | `e7e9cc8b1b85264074fbcc02a88680c4096b1e47df8f739dceb03bf482f04bd6` |
| `sha2` | `0.11.1` | `47d7069beb7d6ac7b9acd1039986e73443f24234f41074da099d6f994ac9ad19` |
| `shlex` | `2.0.1` | `f8fadd59c855ef2080decdef8ff161eb6661b86933c9d82e5ba29dc602a55aba` |
| `simdutf8` | `0.1.5` | `e3a9fe34e3e7a50316060351f37187a3f546bce95496156754b601a5fa71b76e` |
| `smallvec` | `1.16.6` | `3244542535d5de959d90ec55d1b5ff0fd2bb7b1310223907d5f11932847f7b59` |
| `syn` | `3.0.10` | `4ae9ccbea3a7b0b09443036490c8f34a8b1b760fd345e5c0dae0aac718faea79` |
| `typenum` | `1.20.1` | `b6f5e870be6c3b371b77fe0ee0bafb859fa4964b4404c27de1d380043c4dda20` |
| `unicode-ident` | `1.0.27` | `a2c754d6c33795a1c324727428e5a7dedb5b06195f9890bdbcba760d3e246563` |
| `unicode-width` | `0.2.3` | `ca718471876992059f251e33aafc334346ada08042b7661dd1fe313a9bced557` |
| `vcpkg` | `0.2.15` | `accd4ea62f7bb7a82fe23066fb0957d48ef677f6eeb8215f372f52e48bb32426` |
| `zmij` | `1.0.23` | `29666d0abbfad1e3dc4dcf6144730dd3a3ab225bbbdac83319345b1b44ccfc1b` |
