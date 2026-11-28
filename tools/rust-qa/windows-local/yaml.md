# Native YAML tests in the Windows x64 guest

The [YAML compiler](../../../.github/workflows/rust-windows-x64-yaml-build.yaml)
builds the reviewed, filtered dependency graph, the Rust release executable
and test harnesses, and the C# oracle with its runtime dependencies.
Cargo emits its original harness list with `test --all-targets --no-run`.
The archive contains that compiler stream, executable hashes, the
source hashes, native graph and reviewed source bundle. Actions uploads
`rust-yaml-windows-x64-<revision>` for the exact source revision.

Use the dedicated standard account in the local 3072 MiB Windows x64 guest.
Check out the compiler revision using the same native checkout settings as
the [storage trial](storage.md). Copy the original downloaded ZIP, the
SHA-256 reported by Actions for that artifact and the private .NET 10.0.12
Windows x64 runtime into the guest. The output path must be new.

```powershell
python -B tools/rust-qa/windows-local/yaml_guest.py D:\compiler.zip $digest `
    .\artifacts\rust\local-yaml --dotnet C:\QA\dotnet\dotnet.exe
```

The [guest driver](yaml_guest.py) checks the ZIP digest, source revision,
native graph, lockfile, fixture hashes, compiler stream and each native
Rust PE image. It runs the source-filter checks and every Cargo harness,
retaining each harness's test counts and exit code. The Linux startup
language example contributes an empty Windows test harness.

The [canonical YAML exchange](../yaml/run.py) starts with the native C#
loader exporting the synthetic Windows fixtures. The driver moves the
original profile, runs Rust on those bytes and asks C# to reopen both the
unchanged and edited Rust outputs. Both C# passes record the Windows process
architecture and runtime version. Return the entire output directory,
including `guest.json`, `reference/`, `rust-output/` and the stage logs.
A completed compiler run establishes the availability of the inputs.
The guest's own receipt records the native comparisons.
