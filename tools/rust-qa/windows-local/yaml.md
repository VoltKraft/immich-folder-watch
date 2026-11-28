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
Windows x64 runtime into the guest. Choose a new output directory below
`artifacts/rust/yaml-assessment/`, the scope accepted by the C# oracle.

```powershell
python -B tools/rust-qa/windows-local/yaml_guest.py D:\compiler.zip $digest `
    .\artifacts\rust\yaml-assessment\local-yaml --dotnet C:\QA\dotnet\dotnet.exe
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

## Local Windows x64 exchange at 14541fb (2026-11-28)

The compiler built `14541fb4e1c885651d383cda4f579f6d3fd5f623`. Its
34,522,849-byte ZIP matched the Actions SHA-256
`51ebe85e8a1917af78d38e5fe169edbeacadc8873f71bee5060b7f36031c1f03`.
All 76 members indexed by the compiler matched. Of 145 source inputs, 57
matched the Git bytes directly and 88 matched the Windows checkout line
endings. The guest verified the native AMD64 release executable and all three
Cargo harnesses. [Compiler job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46134323367/job/140946126759) · [Original compiler ZIP](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46134323367/artifacts/15258389594).

The standard user ran the first test in a fresh Windows Server 2025 x64
guest, build 26100. All three filter checks and 14 Rust tests passed. The C#
exporter refused the first output directory, `artifacts/rust/local-yaml`,
before exporting a profile. Its original 4,227-byte guest ZIP has SHA-256
`c5a85fad51961687670507fefb61d0ff463c8e8387e7a84841146534b7ce84a3`.

The same user and RDP session repeated the test with the same compiler ZIP
and source revision under `artifacts/rust/yaml-assessment/local-yaml`.
Both C# processes ran on .NET 10.0.12 and reported native X64. They preserved
all 110 original inputs. Rust accepted 77 profiles, wrote the round-trip and
edited files for 67 of them and preserved the ten inputs with decoding errors
as read-only. The comparison recorded 475 Rust assertions, 330 byte assertions
and 268 C# readback assertions. All three filter checks passed again.
The library ran 13 tests, the binary ran one and the Linux-only example had
zero Windows tests.

The returned 210,470-byte ZIP has SHA-256
`1901468c7c236116ddb4bb60463c1f2b91d0371cdb0bb9372f5359a4b77c223f`.
The host verified the 255 files indexed by `guest.json`, replayed the
source-byte and typed-scalar checks and confirmed both native readers'
recorded editable and runtime results. The original ZIP, readback and shutdown receipt
are in `artifacts/rust/local-windows-server-2025-x64/20261128/yaml-native-01/`.
QMP reported exactly 3,072 MiB. After ACPI shutdown the host verified the
base and firmware metadata, the released loopback port and removal of both
temporary overlays.
