# RW-02 native SQLite fault experiment

This is independently preparable RI-AC03 feasibility evidence. RW-02 remains
open and RW-03 has not begun. The experiment reuses the reviewed storage code,
SQLite build and real synthetic C# corpus; it introduces no application storage
adapter, migration protocol or dependency. The
[maintained runner](../../tools/rust-qa/storage-faults/README.md) owns commands,
isolation and exact scenario steps.

## Engine and workload

On 2026-11-22 an independent reviewer replayed all eight Linux x64
recoveries at `966b861317559e85c7f50eede87d65d215868560`. The reviewer
verified 453 evidence hashes, 138 source bindings, 208 C# assertions and
16 expected Rust/C# hash-mismatch rejections. The producer hash survived
all phase and final checks on each original snapshot. The review closed
the two earlier findings about the initial backup hash and documented
timeouts. Independent report SHA-256
`02534d16f4abc9c24e31199af88eafc5c35165d7f47877b5d4e88a058823ee60`,
source run manifest `a0c5035758144586b3e743d4db04769c9dcdd9be2bcfead88e72560827b45492`.
This covers the Linux x64 feasibility experiment. The product migration and
installed recovery require separate review.

The existing development assessment compiles unchanged as the seed executable.
It imports the actual C#-generated native SQL/JSON corpus and exercises all four
tables, both path-casing modes, Unicode paths, identities, tombstones, repair
JSON, exact owned album IDs, account separation, 64-bit file sizes and transfer
history. The fault probe compiles the original source bytes with two appended
test-visibility wrappers for its existing WAL initializer and full snapshot
reader. Generated source and original source hashes are archived. This is test
instrumentation of the existing feasibility code, not a production API change.

The separately generated lockfile has the same 31 external packages, exact
checksums and target features as the [reviewed storage graph](rw02-storage-inputs.md):
rusqlite 0.43.0 with `bundled`/`backup`, SQLite 3.54.1 source ID
`2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76`,
serde_json 1.0.154, sha2 0.11.1 and the local legacy codecs. The source verifier
checks every original archive, unpacked source byte, supplied notice and native
source before building. SQLite extension loading stays omitted; actual runtime
compile options and debug/release native compile commands are checked. No new
license or dependency input is introduced. Existing notices are retained.

The schema is unchanged. The synthetic workload changes one mapping, one owned
album, account history and the repair JSON in a single transaction. Other-account
rows and tombstones must remain unchanged. A fixed 2-MiB extra field in the repair
JSON forces cache spill or capacity failure without large data. This field is
test-only and never becomes a proposed schema extension. The complete raw
snapshot comparison still covers every row, column, index/schema SQL and
`user_version`, and the existing typed C# readers supply an independent check.

## Failure and recovery contract

Every case starts from the reviewed backup, opens WAL with automatic checkpoint
disabled and `synchronous=FULL`, commits the first four-table transaction, and
prepares its acknowledgement. The main database file must still have its original
hash while committed WAL frames exist. The
[SQLite backup API](https://sqlite.org/backup.html) then captures that live state;
the producer closes its destination and immediately emits its SHA-256, before
any verifier opens it. The destination must then match the entire source snapshot
and pass `integrity_check` without changing that digest. The transaction
confirmation repeats the original digest. Every completed backup made by the
fault probe emits such a receipt; the retained pre-fault snapshot is the invariant source used
through all later phases.

The two crash barriers distinguish an uncommitted transaction from a committed
transaction whose application acknowledgement was not sent. The parent observes
the explicit test barrier and uses real SIGKILL on Linux or TerminateProcess on
Windows. The blocked process cannot run a Rust destructor or graceful rollback.
The pending transaction already has measured WAL spill. Raw DB/WAL/SHM copies
before and after termination are compared and retained before recovery opens
the database. They are forensic evidence, not the backup used for restoration.

The capacity case sets and reads back SQLite's
[`max_page_count`](https://sqlite.org/pragma.html#pragma_max_page_count), then
requires the actual [`SQLITE_FULL` result code 13](https://sqlite.org/rescode.html#full).
That page limit is not a full filesystem and is never labelled `ENOSPC`. Its
bound is the observed page size multiplied by the accepted page limit. The test
records whether SQLite returned to autocommit automatically and whether the
preceding statements are still dirty before the Rust transaction is dropped.
Continuing or committing after a write failure is not the tested policy.

The additional Linux case uses an actual private 8-MiB tmpfs, with separate user,
mount, network and PID namespaces and zero effective capabilities. A bounded
filler encounters OS errno 28. While the filler remains present, the independent
namespace controller requires `statvfs` to report zero free and available bytes,
and the Rust SQLite writer must report error 13. The normal SQLite page limit
remains 4,294,967,294 pages. Only the experiment's filler is removed, and the
retained snapshot is restored through the backup API on that same tmpfs before
its contents are preserved and the namespace exits. This is real filesystem
ENOSPC on tmpfs, separate from the logical SQLite page limit.

A fresh Rust process reopens each failed database and requires exactly `ok` from
the full integrity check and the exact expected snapshot. A confirmed transaction
must survive. An uncommitted one must disappear completely. A commit without an
application acknowledgement must be recognized as complete rather than blindly
replayed. A real SQL album-ID mutation in a separate backup clone must compare
unequal despite passing SQLite integrity. The retained
pre-fault backup is then restored through the same backup API into a fresh file,
checked in full and subjected to a real write/rollback. The original failure
files and snapshot are preserved. C# Core reads the recovered, snapshot and
restored databases independently (24 assertions per portable case; 32 with the
extra same-tmpfs restoration). Because the C# initializer writes header metadata,
the retained snapshot is tested through a closed, byte-identical disposable copy.
The Rust verifier also uses its own authenticated copy. The supervisor supplies
the original producer digest explicitly to both verifier entry points. They
check it before opening any SQLite database, check the snapshot copy against it,
and check the retained original again after their work. The supervisor separately
checks before and after each language phase, carries the digest in the raw
kill/ENOSPC receipts, and defers a final check of every actual original until all
eight cases finish. ENOSPC restoration uses a verified private copy as well.

Every case additionally flips byte 100 in another isolated snapshot copy. Both
real verifier entry points must reject it with `SNAPSHOT_SHA256_MISMATCH` before
any SQLite open or derived file. Rust exits 1; C# exits 42. The exact changed byte,
original/changed hashes, error logs and absence of derived files are recorded.
This byte-corruption check is separate from the existing semantically unequal
but structurally valid SQL control. Authentication here means continuity against
the producer digest retained by the independent supervisor; it is not a signature
or protection against compromise of both processes.

This proves database state recovery at these bounded points. It does not undo
uploads, downloads, deletes or other external side effects, and it does not
establish a production retry/idempotency policy.

## Pre-review local observations (2026-11-21)

The pre-review native Fedora Linux x64 run on 2026-11-21 passed all eight cases and
208 C# assertions in ignored `artifacts/rust/storage-faults/linux-x64-05`. It
verified 31 archives, 2,214 source files and the exact native feature graph,
passed all 29 command steps, Rustfmt, Clippy with warnings denied, release
compilation, both native compiler-log gates and the real Core readback. The
C# build reported zero warnings and errors.

| Observation | Measured result in both casing modes |
| --- | --- |
| Confirmed update exclusively in live WAL | 24,752 WAL bytes; unchanged main-file SHA-256 |
| Dirty transaction before hard kill | WAL grew to 2,142,432 bytes |
| Crash before commit | Only the complete confirmed state survived |
| Crash after commit, before application acknowledgement | Complete second transaction survived and was distinguishable |
| Capacity boundary | 4,096-byte pages; 11 pages initially, limit 27 pages / 110,592 bytes |
| Attempted large repair payload | 2,097,152 bytes; actual SQLite error 13 |
| Autocommit after the page-limit `SQLITE_FULL` | False; earlier updates still visible inside the transaction |
| Page-limit error handling | Rust transaction drop rolled back all earlier updates |
| Real tmpfs capacity | 2,048 × 4,096-byte blocks = 8,388,608 bytes |
| At the OS ENOSPC barrier | Zero free/available bytes; filler 8,183,808 bytes; OS errno 28 and SQLite error 13 |
| Autocommit after tmpfs ENOSPC | True; SQLite had already rolled back this transaction |
| After removing the owned filler and restoring on the same tmpfs | 8,200,192 bytes available; full restored state matched |
| Every reopened/backup/restored database | `integrity_check = ok`; full snapshots matched |
| C# semantic readback | 24 × 6 portable cases + 32 × 2 tmpfs cases = 208 |

The different transaction states after the two error mechanisms matter. The
page-limit failure needed the existing Rust scope/drop rollback, whereas the
tested tmpfs failure had already returned to autocommit. Production integration
must stop work and handle errors explicitly; it cannot infer one universal
automatic rollback behavior from the shared SQLite result code.

That run records four actual SIGKILL exits (`-9`) and eight real SQL mutation
controls. Every post-kill DB/WAL/SHM hash equals its quiescent pre-kill hash. All
eight snapshot hashes measured at the end of native verification remained
unchanged through C# readback. Independent review correctly found that this late
anchor did not establish byte continuity from backup completion through native
recovery. The new producer receipt and per-phase checks above close that evidence
gap; the preserved earlier outputs are not reinterpreted as having them.
The 138 first-party source bindings and 405 evidence-file hashes were
verified again against disk after execution. The actual C# process and OS were
X64, with .NET 10.0.12 and SQLite 3.53.4; the Rust engine was SQLite 3.54.1.

| Pre-review source/evidence identity | SHA-256 |
| --- | --- |
| Generated `tools/rust-qa/storage-faults/Cargo.lock` | `bd31bfdbcfdce6a63176a71918d64885c036bef198be096913f7be5f4fbf3eb0` |
| Rust fault executable | `2d46ecf2a164ca1c4aefcf138405f60b98bcd0bfc6f89a9d0d06215c124a44d4` |
| Unchanged reviewed storage executable | `a54528c312bb27726546ad1cf265b6ffd6f19ba78e40e610adeab8174e94c800` |
| C# fault readback assembly | `812817f440b5927e5618c3ffa2a9d3bb674f5ef576f7eae33646e171b6ed18a8` |
| `linux-x64-05/result.json` | `370d315c3bc970d1383eaea4bc0d4be3fd76a5eda91b6b330cf5c04e45034eeb` |
| `linux-x64-05/first-party-source-hashes.json` | `82caf4a91e449f9989c4190d3ca69a019ea5449d9bd3af6f6a519dc62d042142` |
| `linux-x64-05/evidence-hashes.json` | `41fac475f28ca03b02671b488fdac7757901c560c20d41cce7bf95caec955577` |
| `linux-x64-05/cases/sensitive-enospc/tmpfs.json` | `8e6247dae29e3f539c98438f065eacf8c8a90a5dca623f3b4b8b2b2152ccd2ea` |
| `linux-x64-05/cases/insensitive-enospc/tmpfs.json` | `e6b56bbcdc45ee3213f7be4c0afa2203ef5ce56c15eee234e5ae3bc5b3f1c62c` |

Run paths are relative to ignored `artifacts/rust/storage-faults`. The final
inventory and source bindings were read back against the files after execution.
The unchanged reference executable has the same hash in all five runs. No result
was published and no shared workflow, lockfile, status or application source was
edited. The primary agent owns review and native matrix integration; the remediation
commit below is explicitly delegated and limited to this experiment's files.

## Remediation and native revalidation (2026-11-22)

Independent review of `e4e1cf2` identified the late snapshot-hash anchor and the
README's overly broad 30-second timeout description. The maintained recipe now
distinguishes ordinary 600-second command steps from the 30-second crash-worker
readiness deadline and the private tmpfs supervisor's 30-second watchdog. Both
supervisors retain a 10-second termination wait. No timeout was shortened or
silently represented as a previously executed check.

The fresh `linux-x64-06` run used the documented command with `--tmpfs` on native
Fedora x64 and passed all eight cases, all 45 command steps and 208 C# semantic
assertions. Of those steps, 16 deliberately failed with the required hash-mismatch
diagnostic: eight Rust exits 1 and eight C# exits 42. Each negative copy differed
from its original at exactly byte 100 and no other offset. Neither verifier
created any file in the rejection directory, and neither changed the corrupt
input. The original eight valid profiles still passed full Rust and actual C#
comparison through separately authenticated copies.

Each original passed six supervisor hash checkpoints: before/after Rust,
before/after C#, after the negative controls and after all eight cases completed.
The native verifiers also check independently. Every crash and tmpfs receipt
includes the original `backup-completed` event and three supervisor checks
around its fault boundary. Four actual SIGKILL exits remained `-9`; the two
8,388,608-byte tmpfs filesystems again reported zero free/available space, OS
errno 28 and SQLite error 13. Same-volume restoration passed in both. The added
private restore-source copy and its locking sidecars account for the newly
measured 8,122,368 bytes available after restoration; the earlier 8,200,192-byte
observation above remains associated with the earlier recipe.

| Retained original snapshot, all four cases per mode | Producer SHA-256, unchanged at every later checkpoint |
| --- | --- |
| Sensitive | `b69cd07bea7531bc989678571dcd7146468cd293bc8befe2afe85005149ecfc4` |
| Insensitive | `2f706e13554d5cf262b67a4f0c72611157084be3423019ca71c97d8328412544` |

The exact 31-package graph, 2,214 external source files, both native compiler
flag logs, Rustfmt, Clippy with denied warnings, release build and C# build
(zero warnings/errors) passed again. All 138 archived first-party source hashes
matched both their archived bytes and the current source files. All 453 new
evidence-file hashes were checked against disk after the run. The previous
`linux-x64-05` inventory still matched all 405 original files. Engine/runtime
versions remained Rust SQLite 3.54.1, C# SQLite 3.53.4 and native .NET 10.0.12.

| Remediation evidence identity | SHA-256 |
| --- | --- |
| Rust fault executable | `84797f53931b7ec15c45218ce8b41c39e061c5eb7916ff09c68e2786a8514f8b` |
| Unchanged reviewed storage executable | `a54528c312bb27726546ad1cf265b6ffd6f19ba78e40e610adeab8174e94c800` |
| C# fault readback assembly | `d5d4ecb4346e8e4f10c830a1924d12206a008ae9ee08952c505f1a9ce23f2ffd` |
| `linux-x64-06/result.json` | `d6fbfc44d6b62ae5442bc4bc32ff2a6225067d4e79ddd77f1fb7f4e4d0b63160` |
| `linux-x64-06/first-party-source-hashes.json` | `15fa7d9c19245f20923001d23bc6feccc25abddd6ed697c9b13d2299f8ba55cf` |
| `linux-x64-06/evidence-hashes.json` | `a0c5035758144586b3e743d4db04769c9dcdd9be2bcfead88e72560827b45492` |
| `linux-x64-06/cases/sensitive-enospc/tmpfs.json` | `79581f27e9b283d2ae5bb3df5ea07e2ae723fb2da94049e20abc2ba3932e56e4` |
| `linux-x64-06/cases/insensitive-enospc/tmpfs.json` | `84a55efc15b1280105d4177add1c12e9068a4a88831268e07315112d92e510ea` |

## Retained diagnostic attempts

`linux-x64-01` through `linux-x64-03` passed their earlier six-case semantic checks.
A subsequent hash audit identified writes by the real C# initializer to the
retained backup. The isolated `csharp-snapshot-diagnosis` reproduced changes at
byte offsets 27, 95, 98 and 99, in header bookkeeping/writer-version fields; both
before and after remained WAL format `2/2`. It did not change the logical profile.
The final tool reads a byte-identical copy and explicitly fails if the original
snapshot changes. Earlier results are not relabelled as having that later check.

`linux-x64-04` passed three portable cases and then timed out after 30 seconds
while using the readonly seed bind as a normal WAL source. The retry uses a
private hash-checked copy of the closed seed so SQLite can create locking
sidecars. That bounded retry passed in `enospc-check-01`, followed by the complete
eight-case final run. The failed attempt and progress/error records remain
available. An automatic permission-review timeout prevented one retry from
starting; the single allowed retry with explicit sandbox arguments succeeded.

## Limits and next gate

Native Windows x64/ARM64 and Linux ARM64 executions remain required; the runner
interface is prepared but local Linux x64 results do not stand in for those
hosts. Matrix integration belongs to the primary agent after review of this
first proof. No shared workflow or application file changed in this assignment.

Physical disk/filesystem ENOSPC beyond the tested tmpfs, power loss,
storage-controller behavior, interrupted
backup or restore, every app transaction boundary, unknown-schema WAL preflight,
installed migration/ownership handover, and application-side retry/replay remain
unproven. This is not acceptance of full-disk recovery under every mechanism or
completion of RI-AC03. The production migration/recovery implementation and its
independent review remain behind the existing stage gates.
