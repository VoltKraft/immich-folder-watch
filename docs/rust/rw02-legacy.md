# RW-02 legacy scalar and path feasibility

The dependency-free [`ifw-legacy`](../../rust/crates/ifw-legacy) crate implements
small legacy identity codecs. It is a feasibility component, not the completed
storage or configuration adapter. No SQLite, YAML, JSON or cryptographic crate
has been adopted by this work, and no .NET component is required by the Rust
codec binary. The C# scalar oracle is development tooling only.

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
  UTF-16 lengths and idempotence; it cannot certify the semantic completeness of
  an arbitrary supplied map. No map is embedded, automatically downloaded, or
  accepted as a product configuration setting. The development probe supplies
  only the separately generated C# reference.

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

`verify.py --unicode-data <downloaded-UnicodeData-17.0.0.txt>` optionally records
the exact comparison without performing network access itself.

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

- Four-target Rust execution and full casing-map equality/review before adopting
  a shipping map; native Windows namespace cases beyond the existing corpus.
- Audited exact SQLite/native, YAML, serde/JSON and SHA-256 dependency graphs,
  followed by actual Rust database/YAML/repair-record reads and writes. Python's
  container extraction above is not Rust SQLite or JSON implementation evidence.
- Complete configuration semantics, account/device identity hashing, unsupported
  schema read-only preflight, migration/backup, write-failure/full-disk/crash and
  C#→Rust→C# compatibility after activity.
- Handle-bound authorization and application orchestration. String normalization
  must never replace the secure-filesystem boundary.

The broader [acceptance record](acceptance.md) remains authoritative; this bounded
probe does not close the full legacy-persistence or RW-02 gate.
