# Bounded native storage faults

This RW-02 development-only workspace tests the existing reviewed SQLite
assessment with real process termination and SQLite capacity failure. It does
not implement a production adapter or start RW-03. It adds no external package,
feature or native source to the [reviewed storage graph](../storage/README.md).
See [scope, results and limits](../../../docs/rust/rw02-storage-faults.md).

From the repository root, with the pinned native Cargo/Rust compiler on `PATH`,
a populated reviewed Cargo cache, the selected .NET SDK and native C compiler:

```sh
python3 tools/rust-qa/storage-faults/run.py x86_64-unknown-linux-gnu \
  --output artifacts/rust/storage-faults/linux-x64-new \
  --cargo-home artifacts/rust/storage-assessment/cargo-home \
  --dotnet artifacts/flatpak-local-2.11.2/sdk/dotnet --tmpfs
```

The target must be native. The interface also supports
`aarch64-unknown-linux-gnu`, `x86_64-pc-windows-msvc` and
`aarch64-pc-windows-msvc`; those lanes require their own execution evidence.
Use their installed `dotnet` command or repository-local SDK path. MSVC is
required on Windows. Omit `--tmpfs` outside Linux or for the six portable cases.
No external service or installation is needed. The optional Linux ENOSPC check
requires existing Bubblewrap and permission to create a private user/mount/network
namespace. Its tmpfs is capped at exactly 8 MiB and exists only in that namespace.
The runner kills only children it starts. Compilation uses `--frozen`; cached
NuGet restore disables advisory retrieval explicitly, and does not establish a
current vulnerability scan.

Output must be a fresh directory strictly below `artifacts/rust/storage-faults`.
Each failed run is retained; retry with a new name. Only this fresh synthetic tree
is mutated. No user application profile is opened. Every native child has a
30-second readiness timeout and a 10-second termination wait. The transaction
payload is fixed at 2 MiB. The `SQLITE_FULL` case limits database growth to 16
pages beyond its measured initial size; this is not filesystem `ENOSPC`.

The original `storage/src/main.rs` compiles unchanged as a separate seed binary.
The fault binary also compiles an exact byte-for-byte copy of that source with
only two appended test-visibility wrappers for its existing snapshot/WAL helpers.
`build.rs` generates and the runner archives this copy. Original source is not
edited; no production API is exposed. The new fault transactions and kill
barriers are test code. Cargo.lock is generated, and all external identities and
features must equal the existing 31-package reviewed closure before compilation.

The six scenarios cover both C# casing modes:

1. Commit a four-table change, emit its confirmation, take a consistent snapshot
   with the SQLite backup API while committed pages are still exclusively in WAL.
2. For crash-before-commit, change all four tables, spill dirty pages to WAL, and
   block. The parent kills the child with SIGKILL/TerminateProcess; no Rust
   transaction destructor executes. A new process must see only confirmed data.
3. For commit-before-ack, commit the second transaction and block before emitting
   its application acknowledgement. The test barrier discloses the commit to the
   harness. Recovery must find the complete committed transaction; an absent
   application acknowledgement does not imply an absent commit.
4. For `SQLITE_FULL`, apply three updates and attempt the large fourth update at
   the measured page limit. Require exact SQLite error 13, record autocommit and
   dirty transaction state, then drop the transaction and require complete rollback.
5. Reopen each failed database in a new Rust process, run full `integrity_check`
   and compare the entire schema/version/four-table snapshot. Restore the retained
   pre-fault snapshot through the backup API into a new file. Verify all content
   plus a write-and-rollback operation. A separate backup clone receives a real
   SQL update to its album ID and must fail the expected snapshot comparison.
6. With `--tmpfs`, both casing modes additionally consume all space in an actual
   private 8-MiB tmpfs. A bounded filler must return OS errno 28; an independent
   `statvfs` measurement must report zero free/available bytes while SQLite returns
   error 13. The normal SQLite page limit remains large. Release only the owned
   filler, restore the pre-fault snapshot via the backup API on the same tmpfs,
   and retain that result before the namespace exits. Readonly fixture binds are
   copied privately with hash checks so WAL locking sidecars can be created.
7. The actual existing C# Core readers independently validate entries, repairs,
   history, exact album ownership, account separation, 64-bit values and tombstones
   in the recovered database, snapshot and restored database (also the tmpfs
   restoration, when present). The reader initializes databases and can rewrite
   header bookkeeping. It reads a byte-identical disposable snapshot copy; the
   original pre-fault snapshot must retain its exact SHA-256 throughout.

The before/after-kill raw DB/WAL/SHM copies are forensic evidence, not recovery
backups. Recovery uses only the completed SQLite backup API snapshot. Actual
failures and all source/recipe/native compiler hashes, dependency archives,
notices, logs and per-case JSON remain in the output. The large build tree is
kept locally but excluded from the evidence-hash inventory; its actual executables
and generated source are separately hashed or archived. Do not upload build
caches as evidence. No remote side effect is undone by restoring a database.
