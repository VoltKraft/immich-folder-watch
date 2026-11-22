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
compile options and debug/release native compile commands are checked. This
Rust/SQLite closure is unchanged. The separately reviewed Windows development
image/generator input is recorded below; existing notices are retained.

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
The pending transaction already has measured WAL spill. Raw DB/WAL copies before
and after termination must match and are retained before recovery opens the
database. Linux additionally compares SHM when present. Windows captures SHM
after termination only, because its active mandatory locks deny ordinary reads.
Receipts identify each captured/compared file and explicitly record this Windows
omission. They are forensic evidence, not the backup used for restoration. The
[SQLite WAL-index contract](https://sqlite.org/walformat.html#the_wal_index_or_shm_file)
states that SHM contains no database content and is unnecessary for crash recovery.

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

## Hosted native recovery at a66e045

Ubuntu x64 and ARM64 each passed all eight recovery cases with four process kills, both
SQLite page limits and both 8 MiB tmpfs exhaustion cases. The C# reader
performed 208 assertions per host. Both readers rejected the altered snapshot in
each case. All eight original snapshots retained the producer's hash after
the final case. The archived 453 evidence files and 138 first-party source
hashes on each host matched the ZIP contents and the exact Git revision.
The x64 `result.json` SHA-256 is
`fa374508a6c2b055ae9f8d36d875c4bb72e73bb18fed47df078810b4cd247cce`.
The ARM64 `result.json` SHA-256 is
`38fa36b4203f80767a8ed398d1efaa74552c0ef4b1bfb0de786af3abeb7b89f2`.
[Verified native archive](rw02-native-gui.md#native-follow-up-at-a66e045).

## Prepared Windows filesystem-full experiment (2026-11-22)

`--windows-vhd` extends this development fixture with a real filesystem-capacity
trial intended for native disposable Windows x64 and ARM64 candidate runners.
It has **not executed on Windows yet**. No local emulation, image check or Linux
run below substitutes for attachment, Win32 errors, SQLite recovery or cleanup
on either target. The primary agent reported failed existing Windows storage
steps in run `45034293002`; their cause is not inferred here before source-bound
logs are available.

The Windows recipe uses an already initialized FAT16 data filesystem in a fresh
fixed VHD. It performs no online formatting or disk initialization. Microsoft's
[VHD specification](https://www.microsoft.com/en-us/download/details.aspx?id=23850)
describes this fixed, single-file format and declares the Open Specification
Promise. The native attachment uses the built-in
[OpenVirtualDisk](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-openvirtualdisk)
handle and
[NO_DRIVE_LETTER without PERMANENT_LIFETIME](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/ne-virtdisk-attach_virtual_disk_flag).
Both calls use their documented default parameters for the verified fixed
image. The three cleanup controls verify the open access mask and the exact
attach arguments, including a null parameter pointer on both calls.
[Open parameters](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-openvirtualdisk)
and [attach parameters](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-attachvirtualdisk).
The physical path comes only from that
[virtual handle](https://learn.microsoft.com/en-us/windows/win32/api/virtdisk/nf-virtdisk-getvirtualdiskphysicalpath).

Before attachment, independent readback verifies the complete initialized file,
its single inactive partition, exact payload template, new disk signature and
UUID, fixed footer/checksum, lack of a parent and fixed 16,777,728-byte file size.
It refuses existing output files, extra partitions, different identities,
payload changes, boot programs, redirects or oversized images. The backing file
remains open without delete sharing. Its ordinary handle ID and final path must
match the newly created, sole-link regular file. Sparse, compressed or encrypted
backing files are refused. The host must have at least 256 MiB available.

After attachment, the read-only physical handle must reproduce the exact new MBR
and 16-MiB virtual length. Only a newly appeared volume GUID with a single
[matching extent](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-ioctl_volume_get_volume_disk_extents)
is accepted. Its offset, 15-MiB partition length, FAT label/serial and 7,656 data
clusters of 2,048 bytes must match the image. No drive letter or preexisting mount
path is accepted. All trial files use that volume GUID directly, so a lost mount
has no host-directory fallback. The retained handle, MBR, extent and backing-file
identity are checked again before writes and at the full/recovery barriers.
Neither an ambient disk number nor a cached FAT file identifier selects a write,
format, rename, delete or restore destination.

The existing Rust transactions and native backup API remain the tested storage
implementation. The fixed-volume filler has a separate maximum attempted-write
bound of 33,687,552 bytes, including small remainder writes when Windows rejects
a multi-cluster allocation atomically. This is a safety ceiling, not proof of
fullness. Success instead requires actual
[Win32 error 39 or 112](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-),
zero independent free/available-byte observations and SQLite error 13 with its
ordinary large page limit. The reviewed SQLite amalgamation's Windows write
path maps both of those Windows errors to `SQLITE_FULL`.

Only after that observation may the worker remove its owned filler and perform
the same-volume restore. The two additional casing-mode cases retain the existing
producer-hash continuity, full-schema/data checks, C# semantic readback and
corrupt-copy rejections: eight cases and 208 semantic assertions if the complete
native qualification passes. A separate owned FAT file records extended and
legacy identifiers from the same handle and observes an ordinary rename. That
observation cannot establish that FAT IDs survive rename or authorize actions by
cached IDs.

All exit paths close owned handles and attempt explicit detach; no permanent
attachment is requested. Passing cleanup additionally requires the new volume to
disappear, a detached-image hash, unchanged fixed MBR/footer and the bounded file
size. Missing hosted-runner identity, native architecture or virtual-disk/admin
capability records `unavailable` and exits nonzero. There is no fallback to an
existing volume, policy change, quota change, driver installation or privilege
adjustment. The ordinary per-user application is not given these development
fixture capabilities. System DLL paths and hashes are recorded, and loading is
restricted to System32.

The [image source/notice and reconstruction recipe](../../tools/rust-qa/storage-faults/windows-image/NOTICE.md)
retain the original dosfstools 4.2 source archive and GPL-3.0-or-later notice.
This compatible development-only input is separate from the unchanged 31-package
Rust closure and excluded from product artifacts. Its archive contains 151
regular files, no links and no image/font assets. All 448 bytes of generated x86
boot code/message are removed from the template; the enclosing MBR has no code
or active partition. The formatter, image and Microsoft reference documents are
not application runtime inputs. The Microsoft firmware-scoped FAT document was
not used to introduce a new formatter and is not redistributed.

| Prepared input | SHA-256 |
| --- | --- |
| Original dosfstools 4.2 source archive | `64926eebf90092dca21b14259a5301b7b98e7b1943e8a201c7d726084809b527` |
| Empty 15-MiB FAT16 template | `7a2e1de34d343d0ed8e6844c1011b7b1f4867b73df6e4d06adb6e2c362ef3f93` |
| 15,409-byte compressed template | `adf67fb9d2e2c2d46fdeb0866eedeb318585b9654a25ef26a26524f46aad7de3` |
| Original GPL notice | `8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903` |

The unmodified upstream source built locally without installation. Its formatter
and the installed Fedora dosfstools 4.2-19.fc45 independently generated identical
template bytes. `fsck.fat -n -v` independently passed both after boot-code removal,
reporting 0/7,656 allocated data clusters. The exact commands, tool hashes and
logs remain in ignored `windows-template-01`, `windows-template-02` and
`windows-design-reference` under `artifacts/rust/storage-faults`. The first
source-build attempt used the host's ccache wrapper and failed during configure;
the successful retry explicitly selected `/usr/bin/gcc`. No installed file or
compiler configuration changed.

The fresh native Linux regression `linux-x64-07 --tmpfs` passed 46 expected
step outcomes, all eight existing fault cases, 208 C# assertions, 16 corruption
rejections and ten portable preparation tests. The latter include three injected
capability/post-attachment/cleanup failures using explicit test doubles; they
verify resource ownership without loading Windows APIs. Rustfmt, denied-warning
Clippy, both native compiler gates and the C# build passed. All 148 source bindings
and 464 evidence hashes matched disk. All 453 files of the independently reviewed
`linux-x64-06` remained unchanged. This is Linux regression and image preparation
evidence, not an executed Windows filesystem-full result.

| Local regression identity | SHA-256 |
| --- | --- |
| `linux-x64-07/result.json` | `e80a9c684179ebe16244c49e295b19090110380be57ef493e2f83207690ef95c` |
| `linux-x64-07/first-party-source-hashes.json` | `c4bb19c8ebac574296a0680cd922a2af9b298f65dd6445feca83310e13751d54` |
| `linux-x64-07/evidence-hashes.json` | `6fab7c8ba4c8b673aa052d4f7ef648fdbcf99d10bd7339875b870644c56fdd85` |
| Rust fault executable | `2b0955ac696872aec5a44357355d207bed1f26e64dae65046a500c6f8ea6cad0` |
| C# readback assembly | `60ec2b6e4007d2dfc8e8058129aca6053b2348aa0081913db02d0c96602c2517` |

The only required workflow delta is to pass `--windows-vhd` to the existing
storage-fault runner on the two native Windows lanes. Existing `--tmpfs` Linux
lanes and artifact inclusion remain appropriate. Source review precedes that
candidate execution; this task changes no workflow or shared acceptance record.

## Windows crash-capture failure and correction (2026-11-22)

The native Windows x64 job
[137244473417](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45034293002/job/137244473417)
at `a66e045` failed in the first sensitive/uncommitted case, before the intended
TerminateProcess call or any recovery validation. Its stack trace reaches
`run.py:103`, `shutil.copyfile` and Python's `fsrc_readinto`, then reports
`PermissionError: [Errno 13] Permission denied`. The retained `before-kill`
directory contains a complete 45,056-byte DB and 2,142,432-byte WAL but an empty
SHM destination; the original SHM has 32,768 bytes. All 264 files in this failed
storage evidence inventory match their recorded hashes. The completed native
build/seed/C# steps do not establish any passing recovery case. The old command
did not select `--windows-vhd`, so this failure says nothing about VHD attachment
or filesystem-full behavior.

This locates the failure in the extra forensic SHM copy, consistent with the
[Windows WAL locks at SHM offsets 120–127](https://sqlite.org/walformat.html#wal_locks)
and [mandatory byte-range read exclusion](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex).
The corrected runner captures mandatory DB/WAL before and after termination and
SHM after termination, before any SQLite reopen. Linux retains its three-file
comparison. It replaces the unqualified unchanged-files flag with the exact
compared file list and hashes, without suppressing required-file copy errors or
byte differences. This is a fixture portability correction; no SQL, transaction,
backup API, dependency or application behavior changes.

The new tests inject active SHM read denial, require DB/WAL copy failures and
missing files to stay fatal, detect same-length changed bytes, and ensure that
an unobserved SHM cannot be reported as compared. An additional actual Windows
byte-lock test is prepared for both native Windows lanes. Linux skips that test
explicitly; neither the portable controls nor the prior Windows failure are
represented as a successful native Windows rerun.

| Retained Windows x64 diagnostic | SHA-256 |
| --- | --- |
| Original artifact ZIP `14759798302` | `cdba4f57b20c8514ffdc3cb6b0ca96922f0a90e03a0c42af4ce4839f8ccce12c` |
| Original complete job log | `e589df94aac1c58a8bc5140cd20eba7c4b834714c1398cef62cd1a9cb4d3bc06` |
| Failed storage `result.json` | `d2f075cb032e2fea5496e5be155fb74b49c7023edd815e2ffae132b1459e5413` |
| Failed storage `evidence-hashes.json` | `1e13d364ddab73921498f1afc4cbecb08de84032606c44819f41027ecd6c9ee6` |

The unchanged originals remain under ignored
`artifacts/rust/hosted-desktop/45034293002`. Native Windows execution of the
corrected capture path and guarded filesystem-full experiment remains required.

The fresh native Fedora x64 regression `linux-x64-08 --tmpfs` passed all 47
expected command outcomes, eight cases, 208 C# assertions and 16 deliberately
rejected corrupt snapshots. All four actual SIGKILL receipts name DB/WAL/SHM and
confirm identical bytes across termination. Both actual 8-MiB tmpfs ENOSPC
cases and same-volume restores passed. The new capture suite passed six tests
and skipped its one native-Windows-only test; all ten image/preparation tests
passed. Rustfmt, denied-warning Clippy, native compile-option gates and the real
C# build/readback passed. All 149 archived source bindings and 466 evidence
hashes matched disk, and the owned tested sources matched the working tree.
The earlier 453-file `linux-x64-06` and 464-file `linux-x64-07` inventories remain
unchanged. No native Windows success is inferred from this Linux regression.

| Corrected local regression | SHA-256 |
| --- | --- |
| `linux-x64-08/result.json` | `3fd2493cdff128d53716651dcf704bb1fc55a9ea75985549c902f3b959d884b4` |
| `linux-x64-08/first-party-source-hashes.json` | `3c4d5dd97af0f92e6a5e7bbc0b41fa04b2d0055c278a5fd35d79c5de3f8b1c41` |
| `linux-x64-08/evidence-hashes.json` | `17fdb5d61129e7300d569a3a39b8ef244b962b865e05a37c5e666ba49f2b86e0` |

## Ubuntu ARM64 retest and source export (2026-11-22)

The native Ubuntu ARM64 artifact from
[run 45039099730](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730)
at `3b4854d867f614a956042dfe987ecc7c008e53ec` repeats all eight cases and all 47
expected command outcomes. The archived C# reader reports native process and OS
`Arm64`, .NET 10.0.15 and SQLite 3.53.4; the Rust verifier reports `aarch64`/Linux
and SQLite 3.54.1. Each case's separate `fault.json`, `verification.json` and
`csharp-readback.json` matches the corresponding aggregate result. All eight
retained original snapshots match their producer hashes, all 48 supervisor
phase/final checks agree, and both actual language entry points reject the eight
byte-100 corruptions with their required errors/exits. The corrupt directories
contain only the changed input, and the valid original files remain unchanged.

Four actual SIGKILL exits are `-9`. Every archived pre/post DB/WAL/SHM byte and
hash agrees with its named receipt. Both logical page-limit cases report SQLite
13 at 27 × 4,096 = 110,592 bytes and need transaction-drop rollback. Both private
8-MiB tmpfs cases report actual OS errno 28, SQLite 13, zero free/available bytes,
automatic rollback and successful same-volume restoration. These distinct
failure mechanisms retain their existing interpretation.

The actual C# source performs eight semantic assertions per opened database:
source entries, repair JSON, successful-sync time, exact owned album ID, other
account's album ID, other account's entry count, the 64-bit file size and tombstone
expiry. The per-file counts in this retest are:

| Actual C# subject | Cases | Assertions per file/case | Total |
| --- | --- | --- | --- |
| Recovered `state.db` | All eight | 8 | 64 |
| Authenticated `csharp-snapshot.db` copy of retained `snapshot.db` | All eight | 8 | 64 |
| Backup-API `restored.db` | All eight | 8 | 64 |
| `same-volume-restored.db` | The two actual tmpfs ENOSPC cases | 8 | 16 |

Thus each casing mode contributes 24 assertions for each of uncommitted,
commit-before-ack and SQLite page-limit recovery, plus 32 for actual tmpfs
ENOSPC: **208 assertions**. Every Rust recovery additionally reports `ok`
integrity, full recovered/restored snapshot equality, a successful restored
write/rollback and detection of the semantically unequal SQL control. These are
source-bound observations from the ARM64 run, not an ARM64 execution on Fedora.

The downloaded ZIP matches GitHub's advertised SHA-256. Direct inspection
verified **465 of 466** indexed storage evidence files and **148 of 149** source
copies. The sole absent file is
`first-party-sources/tools/rust-qa/storage-faults/windows-image/.gitattributes`.
The pinned uploader defaults to excluding hidden files
([exact action README](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/README.md#inputs)).
Its original Git blob at that exact commit is
`c051534be59047d5e35418324c101f55e321d467`: 78 bytes with SHA-256
`32452b24635fef482005490b54a1101d4c75b53dea74e33f2a13abd06d3c6364`.
Those reconstructed bytes match both archived hash indices. All 149 source
hashes also match their exact Git-commit blobs. This is **465 direct files plus
one separately reconstructed source**, not a claim that the original ZIP contains
all 466 files. The original archive and manifests were not changed.

The review and reconstructed bytes are retained separately in ignored
`artifacts/rust/storage-faults/hosted-arm64-45039099730-review/`; the archive stays
at `artifacts/rust/hosted-desktop-storage/45039099730/linux-arm64.zip`.

| ARM64 artifact/review identity | SHA-256 |
| --- | --- |
| Original ZIP | `e70016232c6a366280d2181de23d67fa400eac7255b9683a4b89e414bbc3b000` |
| Archived `result.json` | `6d12c52da24e0ed726cfc8695c4eaca5eb34b44c43b87752773b2d4bf9d5a6ad` |
| Archived `evidence-hashes.json` | `596bf89760924bfb5fc7fcb3ad2c0410ab807dd9731e7019a5944a7baa463689` |
| Separate `review.json` | `c23354ef8cd7083951ed330f99805dd4e1ab988d253ca42022ecb3edec113eff` |

The corrected export retains the existing logical source-hash index and ordinary
source paths. Only explicitly inventoried paths containing a dot-prefixed
component receive a visible `first-party-hidden-sources/<key>.source` location,
where the key is the SHA-256 of the UTF-8 logical path. The visible
`first-party-source-paths.json` maps every original logical path to its exact
stored location. Source and notice bytes remain unchanged, and copy digests are
checked before indices are emitted. Both indices and all visible copies enter
the ordinary evidence inventory. Existing artifacts without the new lookup keep
their original `first-party-sources/<logical-path>` convention. There is no
automatic reconstruction of missing archived bytes, global hidden-file upload,
workflow change or broader source discovery.

Six portable tests cover a hidden-file-excluding transfer and complete lookup,
exact retained notice/line-ending/Unicode bytes, deterministic ordering and
duplicate inputs, omission of uninventoried files, rejection of corrupt copies,
refusal to replace an existing export and rejection of out-of-inventory paths.
The maintained runner includes these tests; its recovery, fault, permission and
VHD contracts are unchanged.

The fresh native Fedora x64 `linux-x64-10 --tmpfs` run passed all 48 expected
command outcomes, eight recoveries, 208 C# assertions and 16 corrupt-copy
rejections. All six source-export controls passed. All 150 sources resolve via
the new lookup and match their hashes; all 469 indexed evidence files match.
A separate local transfer excluded every dot-prefixed path, packaged the
result into a ZIP and read every indexed byte back. No indexed file was excluded,
and all 469 evidence hashes and 150 logical source hashes still matched,
including the exact original `.gitattributes` and retained notices. This is a
local simulation of the relevant upload filter, not a completed hosted upload.
The transfer receipt and visible ZIP remain in ignored
`artifacts/rust/storage-faults/linux-x64-10-upload-check/`. The earlier
`linux-x64-06`, `linux-x64-08` and `linux-x64-09` evidence inventories remain
unchanged at 453, 466 and 466 files respectively.

| Corrected export / native regression | SHA-256 |
| --- | --- |
| `linux-x64-10/result.json` | `e0da5ae44cb00ade4d2e700ba206ab2e35dc832920bd43e38d1c979e7f6b16e6` |
| `linux-x64-10/first-party-source-hashes.json` | `5b28a4652424e569716f7ecb70c7eb176bb9ac8821a86aafe19587523e966c25` |
| `linux-x64-10/first-party-source-paths.json` | `e190f9eddde33e1f72eea9134e97ba76f71f370be0837584538f86769070d13e` |
| `linux-x64-10/evidence-hashes.json` | `f11b3fb82b29d285b8c60db0bbc14c0ac02d0bb433903643c3058c84b12647a2` |
| Local transfer `review.json` | `752b8509cc97c08a8f283f8aefe8066e3931663432751e23be80a7a145a2d54e` |

## Retained compiler evidence inventory (2026-11-22)

The inventory excludes only the run output's top-level `build/` scratch tree.
Copied compiler logs and generated reviewed sources under
`native-build-logs/.../build/...` and `generated-source/.../build/...` are retained
evidence and now receive individual hashes. The former filter excluded every
path containing a `build` component, so these copies could be present in an
archive without appearing in its index. Original archives and indexes remain
unchanged. A targeted control distinguishes the scratch tree from nested build
evidence and detects changed bytes in a retained generated-source copy.

Independent readback of both native Windows archives from run `45047460118`
confirmed all 465 original indexed hashes and exactly six additional retained
files per archive: two generated-source copies and four compiler log streams.
The corrected inventory would cover 471 files, excluding the index itself.
Both debug/release generated copies on both targets have SHA-256
`d1db8115be5497134d4dac1d3777fe34e4adc377b03469e25d922762447b5fae`.
The separate per-file review is retained in ignored
`artifacts/rust/storage-faults/inventory-review-45047460118/`; no original index
was rewritten. All seven source-export/inventory controls passed locally.

## Windows native partial results and release protocol (2026-11-22)

Both Windows artifacts from run `45039099730` at `3b4854d` now have verified ZIP
digests. Each contains **418 of 419** indexed storage evidence files with matching
hashes. The only absent file is the same 78-byte `.gitattributes` described above;
its separately verified Git bytes match the expected digest. All 149 source
identities are accounted for: 65 archived source copies match Git byte-for-byte,
the one missing file is separately reconstructed, and 83 archived text files
differ only by the native Windows checkout's CRLF line endings. Their raw archived hashes were verified
before comparing canonical LF bytes to `3b4854d`; no other content difference was
found. This does not relabel the old artifact as a complete source export.

On **each host**, all six portable cases completed all 37 expected command
outcomes, 144 actual C# assertions and 12 expected corrupt-copy rejections.
Four owned children were terminated with TerminateProcess, exit 1. The archived
DB and WAL bytes match exactly across each kill, including the committed and
uncommitted barriers. Each post-kill SHM is 32,768 bytes and was captured before
reopen; no pre-kill SHM comparison is claimed. Full Rust recovered/restored
snapshot checks, integrity checks, write/rollback and unequal-SQL controls passed.
Each completed case has five supervisor hash checkpoints. Because the later VHD
case failed, the run-level deferred loop did **not** execute. Independent archive
readback nevertheless confirms that all six actual retained snapshot files still
match their original producer digests. The two facts remain distinct.

Both hosts then attached and independently verified their own bounded VHD and
reached real Win32 error **112**, SQLite error **13**, and independently measured
zero free/available bytes in the 15,679,488-byte FAT data region. The sensitive
volume case then failed with worker exit 1 and
`supervisor did not confirm full private filesystem`. Neither same-volume
restoration nor C# verification of that volume case completed; the insensitive
volume case was not reached. Both explicit detach calls returned 0, both volumes
disappeared, the retained 16,777,728-byte images matched their recorded hashes and
fixed-layout checks, and both cleanup-error lists were empty. These are real
full-volume and cleanup observations, not passing Windows full-volume recovery.

The failure is the private release-message encoding. The supervisor opened stdin
in Python text mode and wrote `release-space\n`, while Rust requires that exact
LF-terminated token. Python's documented
[text-mode stdin conversion](https://docs.python.org/3.12/library/subprocess.html#frequently-used-arguments)
turns the LF into the Windows line separator, CRLF. The corrected sender explicitly
configures UTF-8 and untranslated LF on this one pipe, then writes and flushes all
14 bytes and records their length/hex value. It is called only after the unchanged
independent fullness, capacity, backing-file, volume-identity and snapshot checks.
The Rust exact-token check is unchanged. No whitespace trimming, additional VHD
case, disk privilege, fallback path or production behavior is introduced.

| Original native evidence | Windows x64 | Windows ARM64 |
| --- | --- | --- |
| GitHub artifact ID | `14763571611` | `14763606202` |
| ZIP bytes | 17,940,316 | 17,898,754 |
| ZIP SHA-256 | `eb9cb84546da440577f10018dc09882a0ba8983989a12bfef6ff87b862b35f46` | `cbbeaafadbfa07160aaf83f38a0157e6aa20ba960874d28be41cbd4204982257` |
| `result.json` SHA-256 | `f9002cc41f8a62a9e5a61309340ba8d8f095f89300439ee8ceb692e1d34e29f8` | `879b9098c6a8afdd4c3a6c8df4f0a50c9a5c1888be979c3807d7c84cfd4d2a9d` |
| `evidence-hashes.json` SHA-256 | `764c491b5c856b04d8c9f3989956a35f7542de4664eb16f8cc562a8c64569267` | `958673db2c96a3922bdddc42467868bb74c626281829347555bfe17c376848ad` |
| VHD receipt SHA-256 | `26e63ce4bf82674ca285157f96aa5028ff3b993186947b2905eb86d6308ab62d` | `077bd987c357c39dec122f9c981674204bd7412d614df1f093dc1307c5497632` |

The originals stay under `artifacts/rust/hosted-desktop-storage/45039099730`.
Separate detailed checks are in ignored
`artifacts/rust/storage-faults/hosted-windows-45039099730-review/`.
The x64 and ARM64 review JSON hashes are respectively
`b3b0cd1d11020e1c362a82b18bec9d1860106b5b5b752917d62e20fad1023aa7`
and `e440c527ddfbbf2db6955ad7afaa8adceb5906dd1a0d961fff79f856a6830a97`.

Three new portable protocol controls reproduce the old CRLF translation, require
exact LF under both host line-ending modes, and reject a closed output pipe.
An additional real-worker comparison uses the unchanged Rust source from
`3b4854d` in two private 8-MiB Linux tmpfs namespaces. After each independently
confirmed actual ENOSPC/SQLite-13 barrier, the old CRLF sender produces the same
exit 1 and diagnostic as Windows and no restored database. The corrected Windows
sender, called through an explicitly CRLF-configured stream, delivers exactly
14 LF-terminated bytes, returns exit 0 and completes same-volume backup restore.
These results and exact derived-supervisor recipes are retained in ignored
`windows-release-protocol-02`; its `recipe.json` SHA-256 is
`0228828de8e69c702a31045cafe44b4d4b836062decec61adf793c23ea823636`
and its `result.json` SHA-256 is
`2cae516947704b2931082cbd230b1824c3ef01c0adc5f62ad1afc8d93a98ee6c`.
This isolates the common Rust protocol gate. The later native Windows
results are recorded [below](#windows-native-recovery-at-7517e3b).

The fresh native Fedora x64 `linux-x64-11 --tmpfs` regression passed all 48
expected command outcomes, eight cases, 208 C# assertions and 16 corrupt-copy
rejections. All thirteen image/protocol controls passed, including the three
new line-ending/closed-pipe controls. Existing source-export and crash-capture
controls, Rustfmt, denied-warning Clippy, native compiler gates and actual C#
readback passed; the explicitly Windows-only byte-lock control remains skipped
on Linux. All 150 source bindings and 469 evidence hashes matched, including the
mapped hidden source. The earlier `linux-x64-06` and `linux-x64-10` inventories
remain unchanged. This narrow change introduces no dependency, Rust/storage
schema change, new VHD scenario or additional disk authorization.

| ACK correction regression | SHA-256 |
| --- | --- |
| `linux-x64-11/result.json` | `d2b4fbb20a75550e66e0ae6b95f1b12cc7fdb3cacc3c85eaf7d367893783406b` |
| `linux-x64-11/first-party-source-hashes.json` | `4f4187aa1a9c98c5a411d67422d7a198892c9e89c44699fe395027a884b0da39` |
| `linux-x64-11/evidence-hashes.json` | `8a215f0f6d5c39a26d2e331f306379b2367ec61d98a7d6b0ee761c5157fc7563` |

## Retained diagnostic attempts

`windows-release-protocol-01` reproduced the expected Rust rejection but its
additional audit incorrectly required zero space after the worker had exited;
61,440 bytes were available at that later point. It is retained, with that
failed assertion recorded. The final `-02` comparison measures and records
capacity at the actual full barrier, before sending either acknowledgement.

A Fedora x64 rerun exercised both casing modes for each portable fault
before the platform-specific volume cases. All eight cases, 208 C# assertions
and eight final snapshot checks passed. All 466 evidence hashes matched.
`linux-x64-09/result.json` has SHA-256
`e6810b0bcb8283cd33448c5c06cce6ccd2ad8b1ac5a11d419cc928420adaf075`.

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

## Windows native recovery at 7517e3b

Both native Windows jobs at `7517e3b6be84645bc0d40603750b003dd5792104`
passed all eight recovery cases. Each ran four abrupt process terminations,
two SQLite page-limit failures and two actual full FAT16 volumes, spanning
both path comparison modes. Each job recorded 48 expected command exits,
208 C# assertions, 16 rejected altered snapshots and eight final checks of
the original backup bytes. All 465 indexed files and all 150 source copies
in each ZIP matched their expected digests. The two archives were also
checked against GitHub's size, SHA-256 and ZIP integrity.
[Four native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460118).

| Native target | Artifact ID | ZIP bytes | ZIP SHA-256 | Recovery `result.json` SHA-256 |
| --- | ---: | ---: | --- | --- |
| Windows x64 | 14763768057 | 6,769,957 | `a6389dfc7df67982c3f4accf7bc627850af1e27f66417958748ba3c46d2f8e48` | `59532eb455854ec01211c9c5ce82fd7c5ebd02fa427b7a4046c03a7773821ea5` |
| Windows ARM64 | 14764805345 | 6,769,994 | `b4725d2695c7a64bc26200b12d135bc25e0a0a4b87d67c6131754815d5c6e731` | `79a24e9f1c65c96f4d18cb926fe641222f05efe11f6206f6fafe24be8c4b526e` |

On all four private volumes, Windows reported error 112, SQLite reported
code 13 and the observer measured zero available and free bytes. The worker
received the exact 14-byte LF-terminated acknowledgement, recovered the
database on the same volume and exited zero. Each VHD detached, its volume
disappeared and its retained layout matched. The two receipt paths for an
individual VHD contain identical bytes and refer to a single trial.

An independent read-only review parsed the detached FAT16 images. In every
image the 45,056-byte restored database matched the producer's original
snapshot. The reviewer separately checked WAL frame checksums and commit
boundaries in the pre-recovery captures. Uncommitted changes were absent
after restart, committed changes survived the missing acknowledgement, and an
incomplete trailing frame after exhaustion did not become a commit. The review
also compared schema, table contents and the explicit mutation controls.
The six archived compiler and generated-source files omitted from the inner
hash index are covered by the complete ZIP digest. Commit `39c7a57` corrects
future indices. [Compiler evidence inventory](#retained-compiler-evidence-inventory-2026-11-22).

## Limits and next gate

Native Linux x64/ARM64 have exercised tmpfs exhaustion, and native Windows
x64/ARM64 have exercised full private FAT16 VHDs. The corrected source export
arrived complete on both Windows hosts. Product migration, recovery after
external synchronization activity and their independent review remain open.

Physical disk failure, power loss,
storage-controller behavior, interrupted
backup or restore, every app transaction boundary, unknown-schema WAL preflight,
installed migration/ownership handover, and application-side retry/replay remain
unproven. This is not acceptance of full-disk recovery under every mechanism or
completion of RI-AC03. The production migration/recovery implementation and its
independent review remain behind the existing stage gates.

## Opt-in ordinary FAT provider follow-up (2026-11-22)

The optional `--windows-provider` follow-up uses the unchanged workspace
`safe-fs` public API after the existing eight-case Windows recovery experiment.
It is development-only, requires `--windows-vhd`, and is disabled by default.
No workflow enables it in this change. Independent review and a source-bound
native run remain required; the ordinary Win32 identity observations in the
earlier VHD receipts are not adapter qualification.

The last, insensitive VHD remains attached while its ordinary Rust/C# checks
finish. All eight cases, 208 C# assertions, sixteen corrupted-copy rejections
and a new comparison of all eight actual original snapshots must succeed first.
`recovery-before-provider.json` records those results and is flushed, fsynced
and closed before the supervisor reads the optional sources, imports the
provider or starts its format, control and build commands. Final VHD detach
and detached-image readback are pending at this checkpoint. The default path
archives the root Cargo manifest inherited by `ifw-legacy` and runs with the
optional sources absent. Each provider outcome returns control to the
independent VHD recheck and detach. Successful VHD readback is followed by
the deferred checks of all eight original snapshots.

The adapter intentionally accepts drive/UNC watch roots, not a volume GUID
namespace or a reparse point as the final root. To observe the actual FAT
provider without changing that contract, the supervisor creates one new empty
directory on the hosted runner's local fixed NTFS `RUNNER_TEMP`. Its parent
must be disjoint from the checkout. Both the evidence collector and the
workflow upload stay inside the checkout, including when cleanup must retain a
mapping. The supervisor retains and compares the held and named NTFS
identities, associates the already validated VHD GUID with that new directory
and reads the association back. Microsoft defines
this [mounted-folder operation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setvolumemountpointw)
for an empty directory; its target can be a non-NTFS volume
([mounted folders](https://learn.microsoft.com/en-us/windows/win32/fileio/volume-mount-points)).
Missing existing capability, NTFS backing or usable identity is an explicit
unavailable result, subject to successful cleanup of anything already created.
A change to the previously qualified volume's identity, extent or capacity
fails the observation.
There is no privilege adjustment, service change, drive letter, global alias,
new VHD, format, disk-number selection or alternate-path fallback.

The direct Rust child receives only an ordinary new FAT subdirectory beneath
that verified mount. It uses `Directory::open_root`, `open_file`, `Read`, `Seek`,
`metadata`, `identity` and `is_current_entry` against one fixed 45-byte synthetic
file. After one ordinary `std::fs::rename` by the fixture, the held lease must
still read those bytes, the old name must cease to match, and a new-name lease
must read the same bytes and match its current entry. Acquisition and reopened
identities are recorded without requiring equality across rename. The probe
does not implement a production rename operation, timestamp repair, a replacement
case or an attack simulation. The child exits after releasing all leases.

The supervisor enforces a 15-second child timeout and a 10-second kill/wait
bound. After the child's success it independently authenticates the volume
again and reads its GUID path. It must find exactly `renamed.txt`, with the
original length and bytes. The receipt records the name, length and SHA-256
of those observed bytes. It then removes only the owned file names and
subdirectory, undoes only
the verified mount, removes its authenticated empty NTFS stub and checks that
the volume has no remaining mount path. Existing volume-file hashes, root entry
names and measured capacity must match their pre-probe values. Cached FAT IDs
never authorize removal. An unconfirmed child exit prevents name removal and
is recorded as a cleanup failure. Every outcome still reaches the original
VHD cleanup/readback path. An unexpected mapping is retained as a failure rather
than being removed by the fixture.

Provider evidence is separate in `windows-provider.json` and
`result.json.provider_followup`. A provider import, preparation, execution or
receipt-write error is recorded in the latter and returns control to the VHD
supervisor. The recovery outcome is recorded in `result.json.status`.
Only when this option is selected does `selected_checks_status`
combine their statuses for the command exit code. It returns 0 only if both
passed, 2 for unavailable capability, otherwise 1. The separate
`provider-preparation/` inventory records the optional harness, unchanged
`safe-fs` sources, workspace and crate manifests alongside the format,
control and compiler logs. The pinned native compiler builds the isolated
rlib and executable. The supervisor verifies their hashes, the executable's
PE machine and the source bytes used for the build.

Supported invocation after review, on the existing disposable hosted runner:

```powershell
python tools/rust-qa/storage-faults/run.py x86_64-pc-windows-msvc `
  --output artifacts/rust/storage-faults/windows-x64-provider-new `
  --windows-vhd --windows-provider --dotnet dotnet
```

Use `aarch64-pc-windows-msvc` and a new output for native ARM64. Do not use
the provider executable as a standalone command on an arbitrary volume.
Portable controls: `python tools/rust-qa/storage-faults/test_windows_provider.py -v`.

Locally, all ten provider controls passed, including incomplete-recovery denial
before setup, actual direct-child timeout/termination, missing capability,
cleanup after failed/unavailable child outcomes, exact source-copy bindings,
both PE machine controls and refusal to remove another mount mapping. These
are explicitly portable controls with test doubles for native mount calls.
The unchanged library and probe compile on Fedora with pinned Rust 1.100.0;
Rustfmt and warnings-denied Clippy pass. The actual Linux executable refuses
its unsupported host before creating a directory. The final source check in
`provider-source-check-03` retains sixteen source bindings and six executed
steps. The earlier `-02` stopped before compilation because its toolchain check
used a missing `rustc` on PATH; that diagnostic remains, and `-03` supplies the
explicit compiler path. No Windows provider execution is claimed.

The independent default-path regression `linux-x64-12 --tmpfs` passed all 48
expected command outcomes, eight cases and 208 C# assertions. All 153 exported
source bindings and 478 evidence hashes matched, including the six newly indexed
compiler/generated-source copies. It validates the common verification refactor
and unchanged no-mount recovery path; the separately bound provider source check
covers the final provider-specific cleanup refinements.

| Local provider preparation evidence | SHA-256 |
| --- | --- |
| `linux-x64-12/result.json` | `83d90683df418fc15d83d715f3e33541e551f28d11dc3fe743d97a7bec974428` |
| `linux-x64-12/evidence-hashes.json` | `2ae8c725590dfeb6f00121fb36faaae678ca74cc8038bcca5c2f8c64499e8c7b` |
| `provider-source-check-03/result.json` | `6f167dbb2cbaf6f1dc33b0964ca9145644bbdbdba4b05e808a155071c1ddee63` |
| `provider-source-check-03/evidence-hashes.json` | `7fa93a7555d647126065dacd06e2666940f17a2248ab869ce9a6f111850029e1` |

The review follow-up in `provider-isolation-controls-01` passed 18 provider
controls on Fedora. They exercised a failed fsync, missing provider module,
format and build failures, wrong or changed PE bytes, a child error and a
refused receipt write. The retained mapping stayed outside both modeled
evidence walks. The independent rename readback rejected a missing name, the
old name, both names, an incorrect length and changed bytes of the right
length. The full storage control suite passed 44 tests. Its Windows-only
mandatory byte-lock test was skipped. All 17 source bindings and 22 evidence
file digests matched. The result and evidence index have SHA-256
`ea3d40f34174204626b6e81cf279178e710520104d31d35bcba5b7484b599e5e` and
`fb083056002d7a5255b114ca0a17db6d3c5b173124f6d1b74beb0e798582384b`,
respectively. The opt-in FAT provider still requires its own native Windows
x64 and ARM64 observations.

The unselected recovery path passed on Fedora x64 in
`linux-x64-provider-isolation-03`. Both 8-MiB tmpfs cases reached ENOSPC in
private namespaces. All 48 command outcomes, eight recovery cases, 208 C#
assertions, sixteen corrupted-copy rejections and eight deferred reads of the
original backups matched. The 151 first-party source bindings included the
inherited Cargo manifest. The run used no optional provider sources or
preparation steps. All 476 evidence file digests matched. The result SHA-256
is `ec2a3a93b1b9b6d617695e4bfd5d7e2b7694d16beeeee407986999afcab51841`
and the evidence index SHA-256 is
`be0b2d79b3f955ef0a248594e6d801ddc5d307bdb356375e5018f834c1d5f2d2`.
The first attempt stopped at a read-only compiler cache. The second used the
system compiler and finished the six portable cases before the outer sandbox
refused the private loopback socket. The completed run used the same compiler
and explicit permission for the private namespaces.

The `-03` process started with a missing home directory. During restore NuGet
created two empty migration markers under the checkout, one at the repository
root and one relative to the C# project. Both were verified and moved into
that run's ignored build directory. A repeat in `linux-x64-provider-isolation-04`
also started with a missing outer home. Every .NET invocation used the run's
new private home and XDG directories. NuGet wrote its single marker at
`build/dotnet-cli/data/NuGet/Migrations/1`, and neither source directory
acquired a marker. All 48 command outcomes, eight recoveries, 208 C#
assertions, 151 source bindings and 476 evidence file hashes matched.
The result SHA-256 is
`4c0f074f66d32c9f7e4634182827b3ae62014ddd96190826b829322328df3683`
and the evidence index SHA-256 is
`c1235e9cf798e06ca4d0dd423654090a44a34d61bd7b5fe262300e1baefdd309`.
