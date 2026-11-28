# Native storage readback in the Windows x64 guest

The [storage compiler](../../../.github/workflows/rust-windows-x64-storage-build.yaml)
exports the SQLite assessment, the .NET 10 C# readback assembly and its
runtime dependencies. The [guest adapter](storage.py) uses the original
ZIP from Actions and the Windows legacy corpus from the exact compiler
revision. It checks the file and source hashes, target graph, fixture
manifest, lockfile and AMD64 PE images. The private Windows runtime comes
from the original 10.0.12 win-x64 distribution. Its `dotnet.exe` has
SHA-256 `21a46f1e5235cf4e844b9de5429f0e198b9c97a41f0503a66442f1d639ca3ee6`.

Run the command in an ordinary user session of the local 3072 MiB guest
with a fresh checkout. Select an output directory beneath its
`artifacts/rust` directory.

```powershell
python -B tools/rust-qa/windows-local/storage.py D:\compiler.zip $digest `
    .\artifacts\rust\local-storage --dotnet C:\QA\dotnet\dotnet.exe
```

The guest runs the Rust binary on two synthetic native databases and uses
the existing C# store to read both Rust outputs and their backups. It
retains the programs' independent logs, their JSON output, the physical
databases and the SHA-256 of every output. The [storage assessment](../../../docs/rust/rw02-storage-inputs.md)
describes the quiescent WAL and finalized rollback-journal cases.

On Server 2025 x64 build 26100, the local guest ran compiler revision
`d13da92d47483ecc168a35b19ddd5297acd888eb`. The native C# store passed
40 assertions using .NET 10.0.12 and SQLite 3.53.4. The WAL cases read
committed versions and row values 99, 99 and 1. Rust refused version 99
with a finalized PERSIST journal. The host compared both original files
with the guest's two sets of hashes. The main file had SHA-256
`951fe0926fa9a859e404170d6732b03f76518caf42c78ccee30801c2c639e511`,
and its journal had SHA-256
`22e25855b1bc1c212fda148aec1c13583ba4cf0b0350941163d1be70caaae3bc`.
The original 25,292-byte guest ZIP has SHA-256
`991369c1bc8130742f582d8cc693c14d1f8a744d3a26139958a9818d37adbf50`.
[Compiler archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46131445215/artifacts/15258206307).

The local originals are under
`artifacts/rust/local-windows-server-2025-x64/20261128/storage-d13da92`.
`disc/compiler.zip` has the original Actions SHA-256
`f4ab5e9a89940c517973523ce03f146181bf2a3933132867bf7513a8db1e88b1`.
`share/original-guest.zip` is the original RDP transfer and `readback.json`
records the host's readback. After ACPI shutdown `shutdown.json` confirmed
the base and firmware metadata, closed QEMU and loopback port and disposal
of both private overlays.

## Read-only database and writable WAL control

A second fresh 3072 MiB Server 2025 x64 guest ran revision
`9d4d550ebd6d557e2360c258bdc5846786661a6e`. The ordinary Windows user
could not open the supported, read-only original for writing. SQLite
returned a read-only connection, which Rust refused before admitting a
writer. Its `ReadOnlyExisting.Observed` was true. The database's SHA-256
was `c9025554da20937e46278887e6f3d719d5f8f879c6df2b482a0ed35b33d565bf`
before the trial, after refusal and in the independently opened guest
archive.

The writable version-1 control recovered the committed WAL value 1,
updated the row in a transaction and rolled that update back.
`WriteRolledBack` was true. The C# store and the detached host reader both
read value 1. Both future-version WALs returned 99 in the C# readback.
The main files and sidecars of both refused cases matched their recorded
hashes. Rust also refused the version-99 PERSIST case. The original database
and rollback journal retained SHA-256
`951fe0926fa9a859e404170d6732b03f76518caf42c78ccee30801c2c639e511` and
`a91967b9e11dfaf5280fb144d937c23c01fb030a7164615dec7f05d489c1c08e`
respectively. Windows C# again passed all 40 assertions using SQLite
3.53.4 in .NET 10.0.12.

The [compiler ZIP](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46131824334/artifacts/15257647480)
has Actions SHA-256
`f086a355fcb6a7b7fa462f20a88ed3fd8d828c9819c2378eb6f7971346891a94`.
The 25,791-byte original result has SHA-256
`da5546036eac590a6dc307aa6310683886154e3a29ca9f85b542f452a051bfb4`.
The project SSD retains both under
`artifacts/rust/local-windows-server-2025-x64/20261128/storage-9d4d550`.
`readback.json` records the detached SQLite results and original file
digests. `shutdown.json` records the guest's ACPI shutdown and disposal.
