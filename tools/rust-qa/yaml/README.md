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
The uploadable output contains `filtered-sources.tar.gz`, which removes the image
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

See [the YAML assessment record](../../../docs/rust/rw02-yaml.md) for exact inputs,
license disposition, actual results, policy choices and remaining qualification.
