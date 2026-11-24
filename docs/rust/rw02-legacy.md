# RW-02 legacy scalar and path feasibility

The dependency-free [`ifw-legacy`](../../rust/crates/ifw-legacy) crate implements
small legacy identity codecs. It is a feasibility component, not the completed
storage or configuration adapter. No external dependency has been adopted by
that crate, and no .NET component is required by its Rust codec binary. The
separate [storage assessment](rw02-storage-inputs.md) uses reviewed SQLite/JSON/SHA
inputs in a development-only workspace. C# oracles are development tooling only.

## Implemented boundaries

- `UtcTicks` represents the .NET year-0001 through year-9999 UTC range in exact
  100-nanosecond units. SQL parsing/writing uses fixed-width UTC `O` text with
  seven fractional digits and `+00:00`. Its separate repair-JSON scalar codec
  supports System.Text.Json's trimmed fractional representation. This scalar
  codec does not parse whole JSON records.
- Unix conversion uses floor-based seconds plus a nonnegative nanosecond
  remainder, including dates before 1970. Sub-tick precision is rejected rather
  than silently truncated. Calendar, leap-year, range, offset and precision errors
  are explicit. Direction/status codecs reject unknown numeric enum values.
- Native source normalization accepts explicit absolute OS paths and never opens
  them. Linux handles lexical dot components without losing arbitrary OS bytes;
  Windows uses the pinned standard library's `GetFullPathNameW`-backed expansion.
  Relative storage keys retain dot components, as the C# store does. These strings
  never grant filesystem authority. Windows device/verbatim namespaces are
  explicitly unqualified and refused; relative source paths require an explicit
  configuration base before using this API.
- `ReferenceCaseMap` applies a supplied simple Unicode map and preserves unpaired
  UTF-16 surrogates. Its constructor checks ordering, uniqueness, unchanged
  UTF-16 lengths and idempotence. The development driver selects an independently
  derived fixture when it matches the complete native C# observation. The
  runtime crate takes an explicit map. Product selection for existing and new
  database keys is still open.

The standard library documents that
[`std::path::absolute`](https://doc.rust-lang.org/std/path/fn.absolute.html) performs
no filesystem access and currently delegates ordinary Windows paths to
[`GetFullPathNameW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfullpathnamew).
Neither API resolves or authorizes a file object. Runtime authorization remains
the [handle-bound filesystem contract](../watch-root-security.md).

## Executable differential test

The development-only
[`LegacyScalarOracle`](../../tools/rust-qa/legacy/Program.cs) scans every Unicode
scalar through actual `.NET String.ToUpperInvariant()`, also comparing complete
4096-scalar batches to exclude hidden context dependence. Separate UTF-16 vectors
cover unpaired surrogates. It generates BCL tick/SQL/JSON-scalar/Unix answers for
Gregorian boundaries and every timestamp found in the reviewed C# database
expectations. Its output is synthetic and goes to an ignored artifact directory;
it never loads an installed application profile.

[`verify.py`](../../tools/rust-qa/legacy/verify.py) verifies reference payload
hashes, reads the four synthetic SQLite tables with Python's standard library,
and sends scalar/key requests to the actual Rust executable. Every timestamp's
numeric and text answer is compared with independently calculated C# output.
The native path/identity answers come from the reviewed RW-01 corpus. The driver
checks all valid Unicode scalars and separate malformed/range controls. It also
changes only the map supplied to Rust and proves that the resulting disagreement
is detected; a duplicate map entry must be rejected. Python does not implement a
replacement runtime codec or echo Rust output into expected results.

From the repository root, using the exact SDK/compiler pins:

```text
dotnet run --project tools/rust-qa/legacy/LegacyScalarOracle.csproj -- export artifacts/rust/legacy-scalar/native
cargo test --manifest-path rust/Cargo.toml -p ifw-legacy --locked
cargo build --manifest-path rust/Cargo.toml -p ifw-legacy --bin legacy-probe --locked
python3 tools/rust-qa/legacy/verify.py --probe rust/target/debug/legacy-probe --scalar-reference artifacts/rust/legacy-scalar/native --output artifacts/rust/legacy-scalar/result.json
```

Use `legacy-probe.exe` on Windows and the selected `CARGO_TARGET_DIR` if different.
Set `IFW_ORACLE_EXPECT_ARCH=x64` or `arm64`; the C# generator refuses a mismatched
native process/OS architecture. The driver additionally checks the Rust process's
compiled OS/architecture against that reference. No production server is involved.

## Casing source and license audit

Do not substitute Rust's expanding `str::to_uppercase()` or an assumed current
Unicode table for .NET invariant casing. The authoritative .NET 10
[`ChangeCaseInvariant` source](https://raw.githubusercontent.com/dotnet/runtime/v10.0.0/src/native/libs/System.Globalization.Native/pal_casing.c)
uses simple ICU uppercase and deliberately preserves U+0131 (dotless i).
The relevant .NET source is covered by its
[MIT license](https://raw.githubusercontent.com/dotnet/runtime/v10.0.0/LICENSE.TXT).
No implementation code was copied from that source.

For comparison, the official
[Unicode 17.0.0 data](https://www.unicode.org/Public/17.0.0/ucd/UnicodeData.txt)
was downloaded as an ignored audit input, SHA-256
`2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c`.
Its [version record](https://www.unicode.org/Public/17.0.0/ucd/ReadMe.txt) identifies
the exact release. The
[Unicode License V3](https://www.unicode.org/license.txt) permits redistribution
with its notice retained; that requirement is compatible with this repository's
AGPL-3.0-only distribution. The downloaded notice is retained unchanged in
[`licenses/Unicode-LICENSE.txt`](../../tools/rust-qa/legacy/licenses/Unicode-LICENSE.txt),
SHA-256 `e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96`.
This audits that data source and notice, not a prospective third-party crate graph.

The initial native Linux x64 .NET 10.0.12 output scans **1,112,064** valid scalars
and records **1,504** changed mappings. Its map SHA-256 is
`195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e`.
Comparison with Unicode 17.0.0 finds exactly one difference: .NET preserves
U+0131; Unicode's simple uppercase maps it to U+0049. The generator records the
actual runtime and invariant sort version; it does not infer an ICU version from
that value. The complete generated map remains in ignored artifacts until native
Windows/Linux x64/ARM64 outputs have been compared and independently reviewed.

The native Linux x64/ARM64 jobs in
[run 44808944620](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44808944620),
source `2ff988095045739b6eeb0735750f5ec9aa9baca6`, each exported **1,449** changed
scalars under .NET 10.0.15, whereas the local Fedora reference has **1,504** under
.NET 10.0.12. Each native driver passed using its own reference. This is an
observed environment difference, not evidence that the runtime version alone
causes it. The verified hosted Linux maps are byte-identical, SHA-256
`02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f`.
Exactly **55 code points** differ from Fedora; for example, U+019B is unchanged
in the hosted map but maps to U+A7DC on Fedora. The archived comparison is
`artifacts/rust/hosted-feasibility/44808944620/casing-comparison.json`, SHA-256
`9f77bfb9da51d3e27f853a990dedda4ed2fd574ecb005ba6a38ad9c58c6381b7`.
The later four-native
[run 44811901356](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44811901356)
at `4dcccb7` produced this same 1,449-entry map on Windows x64/ARM64 and Ubuntu
x64/ARM64, with 5,844 requests passing on each target. Archive identities and
source-bound native results are recorded in the [acceptance record](acceptance.md).
These observations still do not qualify a universal map. Preserve existing
database keys and qualify legacy variants and any new-key policy separately;
never recompute old keys automatically from a newer Unicode table.

`verify.py --unicode-data <downloaded-UnicodeData-17.0.0.txt>` optionally records
the exact comparison without performing network access itself.

### Independently reproduced casing profiles

The two assessed UnicodeData releases reproduce every recorded native mapping
after applying .NET's dotless-i rule. The generator uses the Simple_Uppercase_Mapping
field from each pinned original. It emits the fixture format independently of
the C# exporter. Each source has 15 semicolon-delimited fields per record.
Five offline controls cover profile identification, the 55 differences,
source and table mismatches, the uppercase column and the retained Unicode
license. [Unicode 15.1 release inventory](https://www.unicode.org/versions/components-15.1.0.html)
· [Unicode 17.0 version record](https://www.unicode.org/Public/17.0.0/ucd/ReadMe.txt)
· [.NET invariant implementation](https://raw.githubusercontent.com/dotnet/runtime/v10.0.0/src/native/libs/System.Globalization.Native/pal_casing.c)
· [Generator and source pins](../../tools/rust-qa/legacy/casing_profiles.py).

| Unicode input | Original UnicodeData SHA-256 | Changed scalars | Native reference with identical complete map |
| --- | --- | ---: | --- |
| 15.1.0 | `2fc713e6a31a87c4850a37fe2caffa4218180fadb5de86b43a143ddb4581fb86` | 1,449 | Windows and Ubuntu x64/ARM64 at `7517e3b` |
| 17.0.0 | `2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c` | 1,504 | Fedora x64 with .NET 10.0.12 |

The version labels identify data that reproduce the observed behavior.
Selecting by the digest of all 1,112,064 scalar observations also detects
hosts with a different profile. The native feasibility command requires a
known profile. For an unfamiliar one the driver first preserves the original
oracle comparison and then reports that independent qualification is missing.
The two development tables accompany the original Unicode License V3.
[15.1 data](https://www.unicode.org/Public/15.1.0/ucd/UnicodeData.txt)
· [17.0 data](https://www.unicode.org/Public/17.0.0/ucd/UnicodeData.txt)
· [Unicode terms for data](https://www.unicode.org/copyright.html)
· [Retained license](../../tools/rust-qa/legacy/licenses/Unicode-LICENSE.txt).

The same Fedora Rust binary passed 5,844 requests with each independently
derived table. The 15.1 expected values came from the archived Ubuntu x64
C# reference and the 17.0 expected values came from Fedora. The resulting
SHA-256 values were `61c9fc28e894f6cfc176c21de278d3ceca41b497ea5f3058581748e360a1423b`
and `c2a5577060fadd609994205913e791e3f3864fde33d7afb2793198fa3ac53be9`
respectively. A synthetic change to the U+019B mapping completed the scalar
comparison and returned a failing eligibility result. Choosing a writing
policy for a legacy database still requires preserving its stored keys and
handling mixed or ambiguous rows. [Four original hosted references](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460118).

```sh
python3 -B tools/rust-qa/legacy/casing_profiles.py 15.1.0 /path/to/15.1.0/UnicodeData.txt
python3 -B tools/rust-qa/legacy/casing_profiles.py 17.0.0 /path/to/17.0.0/UnicodeData.txt
python3 -B -m unittest discover -s tools/rust-qa/legacy -p test_casing_profiles.py
```

At `8091469` all four native hosts passed the strict comparison with the
independently generated 15.1.0 table. Each archived C# table matches the
pinned bytes and all 1,112,064 scalar observations. The native Rust probes
passed 5,844 requests each. The archived comparison records identify the
UnicodeData digest, Unicode license digest and actual profile driver. The
Windows driver bytes include the checkout's CRLF endings.
[Four native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343481).

### Stored SQLite identities across two casing profiles

A Fedora x64 experiment ran the same shipping C# store and .NET 10.0.12
assembly with ICU 74.2 and ICU 78. The two full scalar exports reproduce
the qualified 15.1.0 and 17.0.0 tables respectively. A source path and
relative filenames included ƛ (U+019B), whose uppercase is Ƛ (U+A7DC)
in the newer table. The store wrote both filenames, one tombstone, a
pending repair linked to an entry, a separate pending repair, album IDs
and the transfer timestamps of two accounts. It created a separate
standalone backup for each comparison mode. [C# fixture](../../tools/rust-qa/storage/dotnet/CasingCases.cs).

| C# writer | Path mode | Primary media and tombstone rows | Standalone backup SHA-256 |
| --- | --- | ---: | --- |
| ICU 74.2 or ICU 78 | Sensitive | 3 | `9c5fc8805d55e7ba8425007c8fadbdbb3be29fca478c2e372135c797ddcc7d65` |
| ICU 74.2 | Insensitive | 3 | `55eb8fa0d955aeeebfd6c726a31adfaf9a16dc9abc558d0400c823cb27e7383b` |
| ICU 78 | Insensitive | 2 | `6d54b1c758dec5449af7b726864a199f1465b6d022cc9ea264470de1300f353c` |

Each backup is 45,056 bytes. All four were reproduced byte-for-byte and
checked with a separate read-only SQLite reader. Both C# writers also
stored one media row for the other account. Under ICU 74.2 the two
case-insensitive media keys were distinct. Under ICU 78 the second ordinary
upsert updated the first physical row.

Eight reads through the production C# store covered both writers, readers
and path modes on private copies. In each direction of a library change,
the case-insensitive reader found zero entries at the original source
spelling. It also missed the repairs, tombstone and album bindings. Both
transfer timestamps remained readable. The case-sensitive readers found
the three primary entries and both repair journals with either library.
The source-bound fixture manifest and eight-way readback are retained in
`artifacts/rust/casing-oracle-verified-e59a691/`.

The separate Rust inspection reads previously stored source and relative
keys together with the original spellings in entries and repair JSON.
It keeps the account scope exact. A unique historical identity returns
the original stored keys when every compatible writer interpretation
agrees. Distinct existing keys that could address the same name produce
an ambiguity. A spelling that would only match after changing profiles
returns a possible alias. An unexplained persisted key blocks an absence
claim for that account. The lookup checks both components with the same
profile and includes standalone journals. Ownership IDs and transfer
history stay outside path matching. [Read-only Rust probe](../../tools/rust-qa/storage/examples/inspect_stored_keys.rs)
· [Independent SQL readback and controls](../../tools/rust-qa/storage/stored_keys.py).

An independent review of the initial 24 lookups per C# generation found
that appending a separator to a source path yielded a false absence. The
probe now applies the tested native legacy normalization before casing
both paths. The same C# process that creates the SQLite snapshot emits
its complete casing table. The reader checks its digest against both
qualified originals, counts the recorded scalars and requires the context
comparison. The Python observer decodes Rust output explicitly as UTF-8.

At `b77fc12` the native Fedora probe passed 28 lookups against each C#
generation and nine controls per generation. These include a conflict
between an entry and a repair journal, an altered snapshot with its
original expected digest, and an unfamiliar full casing table that
still maps ƛ exactly as the original. Two controls returned the expected
structured observations and seven refused the input. The original files
stayed byte-identical. The probe reads finalized synthetic
backups through an immutable read-only connection. Any SQLite sidecar
causes refusal. It examines the historical rows under both qualified
profiles. Production migration still needs a writing policy, complete
inventory of historical state and rollback after actual activity.
[Reproducing the eight C# reader combinations](../../tools/rust-qa/legacy-keys/README.md).

At `f538495` the Fedora x64 writer and reader also ran with .NET 10.0.12
globalization-invariant mode. The same fixture produced byte-identical
databases to the ICU 78 writer in both path modes, including the same ƛ
mapping. The complete scalar table had 1,475 changed values and SHA-256
`51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4`.
The two-profile C# reader and Rust inspector each refused that writer before
returning any database observations. All three Fedora captures and the
separate scalar-oracle comparison are recorded in
`artifacts/rust/casing-profile-verified-f538495/evidence.json`.

Independent replay at `b77fc12` matched all 56 answers to the four SQLite
tables in the `f538495` writer backups, including the ambiguous and alias
cases. The integrated Fedora run passed all 16 steps, including 40 C#
checks on the Rust-written databases. All 299 evidence hashes and 137
first-party files matched the archive and Git. A separate invalid query
exposed a difference for a whitespace-only account. The corrected probe
now refuses such a query and preserves leading and trailing whitespace
in otherwise valid account names, matching the shipping store. Each of the
two genuine writers passed 30 lookups and ten controls on Fedora. The
unqualified third writer still requires separate evidence before adoption.

### Managed globalization-invariant casing in .NET 10.0.12

The separate Fedora study at `86ae038` reproduced the managed table in
two ways. Unicode 16.0 contains 1,477 simple uppercase changes. The .NET
generator preserves dotless i (U+0131) and long s (U+017F). Decoding the
published runtime's generated tables produced the same 1,475 changes
across every Unicode scalar as the native writer. The study checks the
source manifest, the exact runtime revision and the upstream data hashes.
[Source reconstruction and original notices](../../tools/rust-qa/legacy-invariant/README.md).

The shipping store wrote twelve synthetic names under the same source
spelling in each environment. Sensitive comparison retained all twelve.
Insensitive comparison retained eleven unique entries with ICU 74.2, ten
with managed invariant casing and eight with ICU 78. Each of the three
profiles stored a different source key for `Archive-ſ-ƛ`. The independent
SQL reader retained the six original database hashes.

At `3c58fc1` the production C# reader opened separate copies in all 18
writer, reader and path-mode combinations. The 432 single-file reads, 36
listings and 18 transfer timestamps matched the independent SQL projection.
Using the raw ICU 78 source key made all eight filenames visible to each
reader. The same twelve relative lookups beneath that key returned nine,
ten and twelve matches respectively. A path migration must account for
both key components. [Cross-profile reader evidence](../../tools/rust-qa/legacy-invariant/README.md).

The native feasibility entry point now exercises the same compiled C#
scalar oracle twice. The second child explicitly selects
globalization-invariant mode and records its CoreLib build and SHA-256.
The comparison verifies that the two processes used the same runtime and
oracle assembly. The Rust probe receives the separately derived managed table. A different runtime,
mode or table fails this comparison. Fedora x64 passed 5,844 requests with
each of the ICU and managed inputs, including the full Unicode range and
1,335 timestamp vectors. Database write qualification is tracked separately
under the stored-identity and migration checks.

At `0a2b5ca`, SDK 10.0.401 selected CoreLib 10.0.15 on all four native
hosts. All four passed the 5,844 ordinary requests. Each managed oracle
exported all 1,112,064 Unicode scalars and the expected 1,475 mappings.
The version guard rejected CoreLib source `8e0f8ed2` before issuing a
managed Rust request. At `c1fd776` the harness builds the oracle once and
runs its verified DLL twice with `dotnet exec --fx-version 10.0.12 --roll-forward Disable`.
Both children in a clean Fedora x64 checkout loaded the same DLL and
CoreLib, SHA-256
`26304a2985357b9ee277f273667fcd9c892edae3ee6eba76f739033e95eb39b3`.
All fourteen steps passed, including 5,844 requests in each mode. Seven
profile tests and the replay of an actual 10.0.15 receipt verified refusal
of missing or different inputs. The clean local verification SHA-256 is
`81447081a29a8948baf4588a0964e74ad154da1b05e0bb3e96bf957d330e932c`.
[Original four-host run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818246)
· [Runtime selection](../../tools/rust-qa/test-native.py).

At `93ecc35` both Ubuntu and both Windows hosts passed all fourteen native
steps. For each host the two processes used the same oracle DLL and CoreLib
10.0.12 from runtime build `95017c711e6afc1085133d440e42b4bd78155701`,
despite 10.0.15 being installed alongside it. Both runs covered 1,112,064
Unicode scalars and 1,335 timestamp vectors. The ordinary and managed Rust
results each passed 5,844 requests and reproduced the independently derived
1,449- and 1,475-mapping tables respectively. The readback compared the
complete tables, timestamp and UTF-16 payload digests, mode, native machine,
compiled oracle and Rust binary within each native pair.
[Four native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264215).

| Native host | Original feasibility archive | CoreLib SHA-256 |
| --- | --- | --- |
| Linux x64 | [14778251690](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264215/artifacts/14778251690) | `26304a2985357b9ee277f273667fcd9c892edae3ee6eba76f739033e95eb39b3` |
| Linux ARM64 | [14777204379](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264215/artifacts/14777204379) | `87ec81f7dafea078d904b79c8c52056f494bdcb7312fbb168261aee7ba18e406` |
| Windows x64 | [14777998886](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264215/artifacts/14777998886) | `1125acc8106c43fc8bad2d203c4c4485df6182d292846c2fff415c1040c54678` |
| Windows ARM64 | [14778675110](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264215/artifacts/14778675110) | `7cc56b492774fff48f2156b738f5fbef0a50dd65aba40969118d4261f7efbc8c` |

### Read-only lookup across three historical writers

The separate Fedora x64 study at `733194b` reads the finalized backups and
writer receipts from `86ae038`. It checks the eighteen C# reader combinations
from `3c58fc1` before comparing Rust observations with the stored SQL rows.
Each backup receives the same 53 queries, covering original names, alternate
spellings, distinct accounts, ambiguity, possible aliases and confirmed
absence. Across three writers and both comparison modes all 318 observations
agreed with the SQL projection. Fourteen controls passed, and the twelve
original files retained their SHA-256 values. The ordinary two-profile
inspector also passed its 60 queries and twenty controls. It refused the
managed writer in both path modes before returning a query result.

The three-profile study applies only to the three source-bound Fedora writers.
It opens existing records for inspection. Choosing how to write new or
ambiguous identities during an installed migration remains open.
The result and verification manifest are in
`artifacts/rust/stored-keys-three-profile-verified/`, with SHA-256
`9ee4efa144f87a6e6b45f2c5e41dbf580c3d1beb883017dad2d48da9bb3268e1`
and `6e7f5c54901bfc009b92e8e522d2433821c7f741b7e174e6c3e973dc5f1b36f7`.
[Reproduction and corpus inputs](../../tools/rust-qa/storage/README.md).

Independent review reran the three C# writers and readers with their
original CoreLib and ICU settings. All 36 output files were byte-identical
to the archived captures. On a fresh Rust build an additional 5,400 queries
agreed with a separate SQL reader, including 608 existing identities, 189
ambiguous results and 58 possible aliases. Twenty-five additional controls
confirmed refusal for changed corpus inputs, invalid queries and SQLite
sidecars. The study's databases have empty repair and album tables. The
separate two-profile backups exercise populated journals and ownership.
The independent SQL report SHA-256 is
`cdfd454878ee5cb88722e0265f792bb3b9dd323fd902ff6c36570019a8727915`
under `artifacts/rust/review-stored-733194b-o1xwcpjx/`.

### Updating a known row on finalized copies

At `b7190ea` the Rust study opened six new copies from the three Fedora C#
writers in both path comparison modes. A transaction updated one known
physical entry's file size from 19 to 37 in each copy. The independent SQL
review reproduced all six before/after pairs byte-for-byte. Names, account
and source keys, asset IDs, history, schema and every other stored value
matched the original. Both shipping Core read APIs returned the expected
results in all 36 reader/profile combinations. The twelve donor files
retained their original content and modification times.

The independent review also found three defects in the development fixture.
An expected value equal to the requested size could misreport a stale row
as unchanged. Direct invocation created Unix scratch files using the caller's
umask. A C# readback on an active WAL reported size 37 from the main file
while a separate SQLite connection observed the committed size 38. The six
positive captures used finalized databases. The findings concern verification
of changes to copies. Installed migration, ambiguity handling and rollback
after synthetic synchronization still need application-level evidence.
The original result SHA-256 is
`a492cf09a3a2b07c458b004218dd2ef8e109a0021f9535b5265cd29237632ee9`.
The independent row and control readbacks have SHA-256
`f720959ac9272027be9bc6bcc59203f3a86dfe78ea0d5897c97f743e36334e8a` and
`c20e3558e7945dc66dcf97e5938ffa4051884fce722c8f0eeb6622d40410e7c9`.
[Study entry points](../../tools/rust-qa/storage/README.md).

At `5d4ce2d` the direct Rust entry point created every new directory with
mode 0700 and both database files with mode 0600 even under umask 000.
The Fedora run recorded six targeted updates, six genuine unchanged repeats,
nine declined mutations and 36 C# observations. Both the Python and C#
readers rejected all six invalid input classes, including a real committed
WAL whose main file still gave 37 while a connected reader saw 38. All
thirteen validation steps passed. The result and verification digests are
`8de7a7de95aec2a78ff96b6fa90b53bea23f0edb17bfd1713f0550643fb160e1`
and `114367f29e36dd884f732956ba514634386d3a70880fd955919d69264bb95582`.

Independent re-review at that revision closed all three findings. Six
separate stale updates and six unchanged repeats preserved every input byte.
All twelve direct destination directories had mode 0700 and their 24
database files had mode 0600 under umask 000. A fresh ICU 17 writer
committed size 38 while its main file still contained 37. Both readers
refused it. Three newly executed C# readers reproduced their archived
outputs byte-for-byte. Independent SQL matched all 72 individual lookups
and 72 lists. The CAS/mode, WAL and clean-reader reports have SHA-256
`555b2ba26de904bbfd47ef534833b516abcef9820c48c241cee09114f3b7ec2b`,
`83c551179ed8e3fef17524a3da53e60db0cf4289b5357c468e9f746d124443a9` and
`7dc596381f7a8e463c17373a471c76092af77a2b9f4ea0cc5b6d4b5bc628a57b`.

## Evidence and remaining work

The C# scalar exporter ran on native Linux x64 with SDK 10.0.401/runtime 10.0.12:
1,112,064 scalar observations, context-batch checks, twelve UTF-16 vectors and
1,335 timestamp vectors. Restore emitted NU1900 because advisory retrieval was
unavailable; the exporter completed successfully.

On 2026-11-20, the pinned Rust 1.100.0 native Linux x64 compiler passed all nine
crate unit tests (zero failures or skips), formatting, probe build and
`cargo clippy --manifest-path rust/Cargo.toml -p ifw-legacy --all-targets --locked -- -D warnings`.
The executable differential driver passed **5,844 requests**, including four
independent conversions for each of the 1,335 timestamps, all 1,112,064 valid
Unicode scalars, twelve UTF-16 cases, 36 native path vectors, twenty invalid-value
controls and the separate unequal-map/duplicate-map controls. Both casing modes
loaded four sync entries, two owned albums, two account-history records and one
repair from the actual reviewed SQLite fixture tables; their extracted scalar
values and stored keys agreed with Rust. The optional Unicode-17 comparison
again found only the documented U+0131 exception.

The local report is ignored
`artifacts/rust/legacy-scalar/result.json`; it records request categories,
reference and executable hashes, and explicit unproven areas. Local builds used
`CARGO_TARGET_DIR=artifacts/rust/legacy-target`, with the probe at
`artifacts/rust/legacy-target/debug/legacy-probe`. These results establish native
Linux x64 scalar behavior only; no cross-build substitutes for the other targets.

Required remaining RW-02/RW-03 evidence includes:

- Cross-environment casing policy and legacy variants before adopting a shipping
  map; native Windows namespace cases beyond the existing corpus.
- Four-target execution of the separately audited SQLite/JSON/SHA assessment,
  followed by final application dependency adoption; complete YAML source-bundle
  disposition and real parser compatibility. Python's container extraction above
  is not Rust SQLite or JSON implementation evidence.
- Complete configuration semantics, account/device identity hashing, unsupported
  schema read-only preflight, migration/backup, write-failure/full-disk/crash and
  C#→Rust→C# compatibility after activity.
- Handle-bound authorization and application orchestration. String normalization
  must never replace the secure-filesystem boundary.

The broader [acceptance record](acceptance.md) remains authoritative; this bounded
probe does not close the full legacy-persistence or RW-02 gate.
The separate [storage input assessment](rw02-storage-inputs.md) records real Rust
SQLite/JSON/SHA-256 execution and C# reread. Its maintained development-only
workspace is [`tools/rust-qa/storage`](../../tools/rust-qa/storage); those
dependencies are not adopted by the application workspace.

## Windows storage example compilation

The storage driver lints all examples with warnings denied before it runs the
SQLite and C# probes. At `0a2b5ca`, the file-size study mutated its directory
builder only on Unix. The pinned compiler reproduced `unused_mut` on the
original directory-creation block with both Windows MSVC target libraries.
The updated example uses a private Unix directory and the standard
single-directory creation operation on Windows. Both branches require a
fresh name under an existing parent.

On Fedora x64 the example test and full storage Clippy check passed. Six
synthetic updates through the ordinary executable retained their original
donors and gave each directory mode `0700` and each file mode `0600` under a
zero umask. Reusing any of the six destinations failed without a byte change.
Both authenticated casing fixtures also passed the standard stored-key
observer, with 30 lookups and ten controls per fixture. The two MSVC target
checks type-checked the changed function and its test. The original native
Windows logs both identify the same `unused_mut` at `update_study_copy.rs:110`
and Cargo exit 101. At `dff8cb0` the example uses the platform-specific
construction described above. [Original desktop assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235)
· [Desktop assessment with the fix](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235).

## Native desktop storage at 93ecc35

At `93ecc354f9be40ad0c76e33c46bdadb55f2e2fb8`, Ubuntu x64 and ARM64 each
passed all 16 storage steps, including Clippy with warnings denied. Each
original ZIP matched its Actions digest. Independent readback verified all
306 storage hashes, 141 first-party files against Git and 31 pinned crate
archives containing 2,214 files per host.
[Ubuntu x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14780360288)
· [Ubuntu ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14779783396).

In both path modes, Rust SQLite 3.54.1 backed up committed changes while
24,752 bytes remained in the live WAL. Read-only SQL reproduced the schema,
index and all nine rows in each finalized main database and its backup. The
download size was exactly 9,007,199,254,740,995 bytes, and the repair retained
the single tick after `1900-01-02T03:04:05Z`. Both version-99 fixtures retained
their original rows. The shipping C# reader passed 40 assertions per host
using .NET 10.0.15 and SQLite 3.53.4.

Each C# writer produced the complete 1,449-mapping Unicode 15.1 profile and
two standalone schema-v1 backups. Both architectures produced byte-identical
backups for the same path mode. Direct SQL reproduced all 30 path lookup
answers per host, including the two ambiguous matches in insensitive mode,
and confirmed the standalone repair, tombstone, distinct album IDs and both
accounts' transfer times. The native probes also passed ten controls per
host. The independent reports in
`artifacts/rust/hosted-desktop-storage/45083264235/` have SHA-256
`16d040918b307649a0b4125d224bf4e3e83b5a4b8754a02bd7b389d98c4a3262` (x64) and
`24c41015ced128438a27420fe0a1989c5397544136dd2f5ea900743735737228` (ARM64).

Windows x64 and ARM64 each passed all 15 storage steps. Native Clippy
checked the corrected file-size example with warnings denied on both hosts.
Both ZIPs matched their Actions digests. All 305 storage hashes, 31 pinned
crate archives and 141 first-party files matched per host, accounting for
Windows checkout line endings in 81 source files. The shipping C# reader
passed all 40 assertions on each host with .NET 10.0.15 and SQLite 3.53.4.
[Windows x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14782395756)
· [Windows ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14782220563).

All four hosts produced the same complete casing table. For the Windows
source `C:\IfwSynthetic\Case-ƛ`, direct SQL reproduced all 30 lookups on
each architecture, including both ambiguous names and the two possible
aliases in insensitive mode. Within each operating system, x64 and ARM64
produced byte-identical main databases, WAL backups, version-99 controls
and C# casing backups. The Windows x64 and ARM64 independent reports have
SHA-256 `bb2217c71c092dbc425e974e980a4573cfffd4d9effa24c3e259984d7b4a7095`
and `b754cd0b93f9eafb6512b2eca9fa2715086ae8b7449a3f54d642cc0d282bc7a1`.

The four-host comparison opened 32 synthetic database files read-only and
checked 296 rows, including eight online WAL backups and eight version-99
controls. It reproduced 120 stored-key lookups. The native probes passed
40 casing controls and 160 C# assertions across the four hosts.
`four-host-storage-sql.json` records the archive and report digests under
the same evidence directory. Its SHA-256 is
`f5f1071c20d2d624190d24fe52e073536fe11b27a42716fcb6ca28ff7327b7c7`.
Installed migration and rollback after application activity remain open.

## C# readback of newly inserted Rust rows

The Fedora x64 study inserted three new entries on each of eight copies of
the two historical C# writers' finalized databases. The Rust development
writer used the pinned storage libraries and explicitly selected either
the 15.1 or the 17.0 casing table for each trial. The C# readers ran the
shipping 3.0.4 store from `0cb3689`, whose Core tree matches `19dcbaf`.
Both used .NET 10.0.12 and captured their own complete ICU casing table.
[Reproduction and independent SQL comparison](../../tools/rust-qa/legacy-keys/README.md#insert-new-identities-on-finalized-copies).

| Lookup using the original spelling | Sensitive, either reader | Insensitive, same table as the insert | Insensitive, other table |
| --- | --- | --- | --- |
| Stable source and relative name | Found | Found | Found |
| `New/Only-ƛ.jpg` under a stable source | Found | Found | Single lookup empty. Source list still returns the original name and asset ID. |
| `New/Source.jpg` under `/IfwSynthetic/Case-ƛ` | Found | Found | Single lookup empty. Listing the original source also misses the new entry. |

In insensitive mode, querying the alternative spelling with `Ƛ` reached
the 17.0 insertion from both readers. Both returned empty for that spelling
when the insertion used 15.1. Both accounts retained their original transfer
timestamps in every trial. Direct SQL agreed with all 96 single-file lookups,
64 source lists and 32 history reads. Each copy gained exactly three rows.
The four original databases held 39 rows. Across their eight working
copies, independent readback recovered all 78 original rows with their rowids. The five study inputs, the original
receipt and both writer directories were checked by opened file and
directory identity before and after the trial. The worker compiled from a
read-only source snapshot and ran with a separate network namespace showing
only loopback and an empty IPv4 route table. The storage verifier checked
all 31 crate archives and 2,214 source files before and after the native run.

The report at `artifacts/rust/new-entry-readback-f932674-offline-01/result.json`
has SHA-256 `4cc86159873ef842dc8460e21f1f6dfe145b6c1d1cec231ddaec291aee5f58dd`.
Its raw `evidence.tar` has SHA-256
`1194dacc81f3abb99625276755bf2f38c9dfe2bf97ae169a2adf5063e12eeca4`.
Independent extraction compared all 160 raw members with the exported files.
Choosing a production write policy for profile-dependent keys remains open.

### First C# upsert after rollback

On Fedora x64, the shipping 3.0.4 store wrote the three Rust-inserted
entries again under their original spellings, changing only the file
size from 83 to 101. Each of the two .NET 10.0.12 casing profiles wrote
a fresh copy of all eight databases and repeated the same writes. The
inputs came from the finalized Rust backups in the preceding study.
Both profiles then read every final backup through the shipping store.

| Path comparison and casing profile | First C# write | Readback |
| --- | --- | --- |
| Sensitive, or insensitive with the same table as Rust | All three entries kept their ROWIDs. | The writing profile found size 101 for all three original spellings. |
| Insensitive with a different table from Rust | The stable entry kept its ROWID. The changing relative name and changing source name each gained a second physical row with the original spelling and asset ID. | For these two entries the insertion profile still found size 83 and the writing profile found 101. Both source listings under the stable root returned the relative name twice with the same asset ID. |

Across 16 working copies, the first pass updated 40 existing rows and
added eight. The repeated writes produced byte-identical standalone
backups in all 16 cases. Independent SQL confirmed preservation of the
original ROWIDs, schema, repairs, tombstones, album bindings and both
accounts’ transfer times. It matched all 480 single-entry reads, 320 source lists and
160 history reads. The source archive came from `13e4af8` and the Core
assembly SHA-256 matched the preceding study. The original 160 exported
files and both original C# writer directories were checked before and
after the offline run.

The [study driver](../../tools/rust-qa/legacy-keys/rollback-upsert/study.py)
uses the same cached SDK, ICU package and finalized Linux x64 evidence as
the insertion study. Run from the repository root with a fresh output name.

```bash
python3 -B tools/rust-qa/legacy-keys/rollback-upsert/study.py \
  --output artifacts/rust/rollback-upsert-comparison
```

The result at `artifacts/rust/rollback-upsert-13e4af8-offline-01/result.json`
has SHA-256 `10f88914879023f006fb8779205fc936da984f568de7ba84e80dcb46751d1f36`.
The raw archive contains both native writer reports, both reader reports,
all four in-process casing tables and 32 standalone backups. Its SHA-256
is `1ca6d3c0072539b4151fd4a5168ee904e3830919c47d0ca406e961ddf6d3fdd2`.
Production migration policy and installed rollback after synchronization remain open.
