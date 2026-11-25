# Native YAML compatibility assessment

This standalone development workspace exercises actual serde-saphyr parsing and
writing against the shipping C# configuration loader/writer. It is not an
application dependency, profile editor or migration utility. Only synthetic
reviewed fixtures and new artifact directories are used.

With Python 3.11+, the pinned native Rust compiler and .NET SDK available:

```text
python3 tools/rust-qa/yaml/run.py x86_64-unknown-linux-gnu --output artifacts/rust/yaml-assessment/runs/linux-x64
```

Run the matching `aarch64-unknown-linux-gnu`, `x86_64-pc-windows-msvc` or
`aarch64-pc-windows-msvc` target on its actual native host. The output must not
exist. Optional `--cargo-home` selects the private acquisition cache, `--dotnet`
selects the SDK executable, and `--offline` requires cached inputs and disables
NuGet advisory retrieval. Each Rust build uses a new empty Cargo home, the
filtered directory source, and `--frozen`, even after online acquisition.

**Upload only the exact output directory.** The sibling `private-cache` may
contain the original upstream base64 archive with its excluded promotional logo;
it must not be published or uploaded. `private-work` contains disposable builds.
The uploadable output contains `filtered-sources.tar`, which removes the image
and exact README promotion, retains code/notices, and records every source hash
and both changes explicitly. No original `.crate` archives are exported.

`inputs.json` pins 30 previously reviewed original archives, 68 supplied notices,
the four selected feature graphs and the filtered source identity. Regeneration
requires a separate source/license review; the generator does not grant approval:

```text
python3 tools/rust-qa/yaml/prepare.py --reviewed-inventory <reviewed-source-inventory.json> --cargo-home <private-cargo-home> --output artifacts/rust/yaml-assessment/<fresh-source-review>
```

The Rust codec preserves observed C# defaults, null handling, duplicate/alias and
legacy number behavior. New explicit parser/serializer resource limits are tested
separately from the reference semantics. Case normalization uses observations
generated from the actual native C# runtime; no universal Unicode map is assumed.
Outputs include source-bound reports, rejected cases, positive/negative budget
tests, and real C# readback of unchanged and modified Rust YAML.

The shipping writer generates ordinary profiles with 100 and 300 ordered
sources and per-folder settings. The comparison reads both UTF-8 files and
a UTF-32LE copy of the 300-folder file. It checks the complete editing and
runtime objects and adds one folder before the second Rust write. The C#
reader verifies both returned documents.

The assessment admits up to 256 KiB of decoded UTF-8 text or serialized
output. Its separate file limit permits four bytes per UTF-8 byte plus a
four-byte BOM, so an ASCII-heavy UTF-32 file can carry the same text.
The parser allows 16,384 nodes, 32,768 events and 128 KiB of scalar text.
Depth, alias expansion and retained anchor data have their own limits.
The native report records the configured limits along with its observations.

See [the YAML assessment record](../../../docs/rust/rw02-yaml.md) for exact inputs,
license disposition, actual results, policy choices and remaining qualification.
