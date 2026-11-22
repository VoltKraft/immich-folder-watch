# Native watch hints

Use the operating system's directory notification APIs to wake the inventory
worker. The isolated Rust package has one first-party Cargo entry, zero
registry dependencies and zero optional features. The existing shipping
worker debounces events for 750 ms and sweeps every five seconds. Changes
made outside a Documents-portal FUSE mount can be invisible to its inotify
view. The full sweep remains mandatory on every backend.
[Shipping worker](../../src/ImmichFolderWatch.Core/Services/FolderWatchWorker.cs)
and [inventory authorization contract](../watch-root-security.md).

## Source and lifetime

A subscription accepts a previously authorized, open directory. It returns a
source-scoped wakeup carrying a generation and reason. File names and file
operations stay in the caller's handle-bound inventory. A queue holds
1–256 hints. A separate generation and accumulated reasons stay observable
when that queue fills. A scan takes an opaque inventory token, independently
inventories the source and acknowledges the token only on complete success.
A later event, an incomplete scan or a dropped token leaves work pending.
An overflow, lost watch or partial registration requests renewed registration
even after an inventory succeeds. [Rust interface](../../tools/rust-qa/watch-events/src/lib.rs).

- **Linux.** Register the borrowed root using its kernel descriptor in
  `/proc/self/fd`. A recursive subscription accepts the retained handles for
  its inventoried descendants and caps registrations at 1,024 directories per
  source, including the root. Each installed registration retains the directory
  handle and its device and inode. After arming, the caller supplies a fresh,
  authorized enumeration to `confirm_directory_set` before its first complete
  inventory can settle. A different root or set of identities, an unavailable
  comparison or a directory change invalidates this subscription. A complete
  inventory can update the baseline while renewal is pending. The caller arms
  and verifies its new subscription before retiring the old one.
  The worker polls the inotify descriptor and a private cancellation pipe.
  Closing the single writer wakes an idle reader or takes priority over a
  full event stream. [Linux adapter](../../tools/rust-qa/watch-events/src/linux.rs),
  [inotify](https://man7.org/linux/man-pages/man7/inotify.7.html) and
  [descriptor links](https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html).
- **Windows.** The caller acquires a dedicated asynchronous directory file
  object inside its authorized grant, opening the entry itself with read/write
  sharing and no delete sharing. `NotificationDirectory::bind` verifies its
  volume/file identity against the retained authorized directory and rejects
  absent 128-bit IDs, reparse entries, synchronous objects and missing
  listing/attribute access.
  `Watch::start` consumes this object; it never reopens a name or file ID.
  Identity comparison binds the notification source, not authorization for
  destructive work. Concurrent/replacement subscriptions need distinct file
  objects, not duplicated handles to an active subscription. Failure leaves
  the caller's periodic inventory available. One 32-KiB DWORD-aligned buffer covers a flat or
  recursive subscription. A zero-byte completion or `ERROR_NOTIFY_ENUM_DIR`
  returned on either submission or completion records `NativeOverflow` and
  retires the subscription. Even the first submission exposes this state to
  the caller, which inventories and registers again. The worker exits after
  that single failure. An explicit stop cancels any outstanding request and
  waits for its final completion before releasing the buffer, event or
  directory handle. A timeout leaves the caller owning the worker.
  Windows reports changes below the subscribed directory. The periodic check
  also covers the root itself. [Windows adapter](../../tools/rust-qa/watch-events/src/windows.rs),
  [asynchronous acquisition](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew),
  [handle identity](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info),
  [directory notifications](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-readdirectorychangesw)
  and [cancellation lifetime](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex).

## Native evidence

On 2026-11-21 the first three Fedora x64 runs each passed five library tests
and twelve independently recorded native scenarios. A separate Python process created,
modified, renamed and deleted synthetic files, changed a nested file, drove a
one-entry queue to capacity, and inventoried the on-disk names and payloads.
It confirmed that an incomplete or overtaken scan could not acknowledge the
new generation. It replaced the registration after a new subdirectory appeared
and observed the next write under that directory. Linux also reported an actual
directory-registration refusal and a moved watch root.

For the kernel overflow case the fixture briefly stopped its own native child,
renamed one synthetic file repeatedly and resumed the child. At the host's
existing queue limit of 16,384, inotify delivered `IN_Q_OVERFLOW` in all
three runs. The application queue retained one hint, coalesced 16,384 further
signals and independently verified the final inventory. Across the twelve
recorded stop observations per run, the native watch drained in 48–4,309 µs.
The release executable was ELF64 x86-64, SHA-256
`49db018ef5bb486192a3636ab92c02be7263e27418b41661f113b9f72ae07560`.
[External observer](../../tools/rust-qa/watch-events/run.py) and
[native fixture](../../tools/rust-qa/watch-events/src/main.rs).

| Local receipt under `artifacts/rust/watch-events/x86_64-unknown-linux-gnu/` | SHA-256 of `result.json` |
| --- | --- |
| `fedora-03` | `7008fffc771c4ed583bfd442224545c2c280183fc7ac0ddd4f2903c89d237de6` |
| `fedora-04` | `a2c9c5b775175c8790cab64ab6f5911fa0c880c73b9cb9c75f13e0f8b0c88eea` |
| `fedora-05` | `f483dc11ff2cdc1113dc12609668c78852d35cb1da8a3c79fcce6dd57f573cfa` |
| `fedora-review-01` | `c5248b646aa609bd140d55d0724fb622b0a19e7da563cb76b3e18e2b05cbf866` |

These receipts bind the development sources on top of `72fff40` by SHA-256.
The review run added a cancelled periodic inventory starting from a clean
baseline. It passed six library tests and thirteen native scenarios.

### Inventory and registration recovery

The external observer checks the configured root, enumerates each selected
directory with `os.scandir` and verifies the identity of opened files and
visited directories. It calls `finish(false)` on a failed or bounded partial
scan. On Fedora the observer moved an already-inventoried root, received
`ENOENT` at its configured name, and read the original fixture file at the
displaced location. A second trial moved a child between parent enumeration
and child opening. Both actual errors preserved the last acknowledged baseline
and required another inventory. [External observer](../../tools/rust-qa/watch-events/run.py).

A separate Linux trial replaced a directory between enumeration and inotify
registration. The replacement retained the original name and directory count.
The first post-arm comparison detected the changed device/inode pair and
invalidated the original watch set. A file created there produced no hint
during a 250 ms observation and appeared in the full inventory. After a fresh
subscription passed its identity comparison, the next write in that same
directory produced a native wakeup. The final inventory read both files.
[Registration interface](../../tools/rust-qa/watch-events/src/lib.rs) and
[fixture handshake](../../tools/rust-qa/watch-events/src/main.rs).

Two deterministic controls exercise the Windows worker's decision functions
for a direct submission error, the pending state, ordinary successful
completion, zero-byte completion and completion errors. The Windows native
fixture additionally opens the original root for `DELETE`, requires
`ERROR_SHARING_VIOLATION` during the lease, and checks rename of the same
directory after release. An exclusively opened fixture file checks the failing
scan, retained baseline and subsequent successful read. The raw Win32 sharing
result and the inventory's error are recorded separately. Both MSVC targets
passed compiler and Clippy checks with warnings denied. Windows x64, Windows
ARM64 and Linux ARM64 native receipts are pending at this revision, including
native Windows sharing checks. An actual Windows kernel-buffer overflow also
remains unobserved. [Win32 control tests](../../tools/rust-qa/watch-events/src/windows_status.rs),
[file sharing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [C runtime file-open errors](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/open-wopen?view=msvc-170).

Three further Fedora x64 runs each passed eight library tests, including the
two Win32 status controls, and fifteen filesystem scenarios. The preserved
drop/cancel test also passed in all three. Each received `IN_Q_OVERFLOW` at
the host's existing 16,384-event limit. Across the 45 recorded stop timings,
the native worker drained in 95–4,606 µs. The three identical release
executables have SHA-256
`30a0099b640891c6fc09b65fe16bd340710bbda23159197a485ce0968cb0975f`.
The receipts include the individual source digests on top of `d2010ca`,
the frozen graph, compiler `0ef1bc386` and the shipping worker from
`19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`.

| Local receipt under `artifacts/rust/watch-events/x86_64-unknown-linux-gnu/` | SHA-256 of `result.json` |
| --- | --- |
| `review-verified-01` | `0e61e7e76f4e8c0c4278b5a0885d591333ce6772a9b7c014efbf6f544bb9276a` |
| `review-verified-02` | `bdf38c577ca0cbac996b0521f4bf263a73fa2d6112bec39e37e5383566673030` |
| `review-verified-03` | `120f4fb69582cc57186d94da00778f3f8d312494135665a594cb210dd9515d40` |

Independent review confirmed the recovery behavior and found one additional
fixture error. Linux ARM64 assigns different bits to `O_DIRECTORY` and
`O_NOFOLLOW` than x64. All fixture directory opens now share one native
implementation. Each Linux run compares the Rust constants to both values in
its host Python ABI. Three further x64 runs each passed eight tests and
fifteen scenarios, with values 65536 and 131072 and identical ELF SHA-256
`ca2c5751b6aebd40729746f20159c0b65e8eec278d379b84aa4f901b1bdb47b7`.
The reviewer matched all three reports to the current source files.
The ARM64 runtime comparison remains pending. [Linux ARM64 UAPI](https://github.com/torvalds/linux/blob/v6.12/arch/arm64/include/uapi/asm/fcntl.h)
and [fixture directory opens](../../tools/rust-qa/watch-events/src/main.rs).

| Fedora x64 receipt | SHA-256 of `result.json` |
| --- | --- |
| `linux-abi-01` | `eee3dd33ad35cf6093e75bf902ab69b96f3ba07dbb89fe493297331a6f0ed080` |
| `linux-abi-02` | `c1ef046fd90cfbf32225f03552546f1d679f96a49356dd1bfcbbccf13fc595df` |
| `linux-abi-03` | `dd15da5a9f35bafcddd02bdf6c546cc5a374033e78dda4801accc80686a09f6c` |

### Reproduction

```sh
python3 tools/rust-qa/watch-events/run.py "$NATIVE_TARGET"
```

Use the pinned compiler installed by the native feasibility workflow. The
driver verifies the actual OS, compiler host and executable machine, resolves
the lockfile offline and uses a fresh private synthetic tree. Archive
`artifacts/rust/watch-events/<target>/result.json` and the accompanying
`evidence.sha256`. The `--run-name` option retains an independent local
repeat. [Pinned toolchain](../../rust/toolchain-inputs.json).

For the cross-compilation checks all 45 files in each target's local sysroot
matched the corresponding files in its checksum-pinned Rust standard library
archive. Both `x86_64-pc-windows-msvc` and `aarch64-pc-windows-msvc` passed
`cargo clippy --frozen --all-targets --target <target> -- -D warnings` in the
watch package. [Target archives and digests](../../rust/toolchain-inputs.json).

## Distribution inputs and integration

At `45dc03b` both native Ubuntu jobs passed eight unit tests and fifteen
filesystem scenarios. Each saw a real kernel overflow at the unchanged
16,384-event limit, coalesced 16,384 notifications and detected the next
edit after registration was renewed. The native flags read back from Python
were 65,536/131,072 on x64 and 16,384/32,768 on ARM64 for directory-only
and no-follow opens respectively. On both Windows targets, all seven
portable unit cases passed and the native executable exited with Windows
error 5 before reporting its first registration. The original logs did not
identify the failing API. The observer now retains native operation errors
and compares two handle-bound opens of the same synthetic directory with
a direct fixture control. No notification or scan is credited for these
independent handle checks. [Four native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44950398472)
· [ReOpenFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-reopenfile)
· [OpenFileById](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-openfilebyid).

| Target | Actions artifact | SHA-256 of verified ZIP |
| --- | ---: | --- |
| Ubuntu x64 | 14725487369 | `16f8dad05b0cfce7e895cea0d8459a0c7a3d99c68b766e06d2b6bf0a395e01b4` |
| Ubuntu ARM64 | 14725526245 | `bcaa572e37c06bfc5d088a4ab638e02cb1451e7329b1c7c6da2f96b9ea9b5cb4` |
| Windows x64 | 14725745848 | `fbd03d2ab82a41b95efe0c174dc363d5b7cbeb655f77d64e8fdb73f622880aac` |
| Windows ARM64 | 14725174102 | `aef9b68dcc38c4836977d4ed7dc352605e19580755a9b96bd36b9d16b170beac` |

At `cd1d7d7`, Windows Server x64 and Windows 11 ARM64 both identified
`ReOpenFile` as the source of error 5. The separate `OpenFileById` and
ordinary fixture opens both returned the identical volume/file identity.
Neither Windows worker reached its first notification in those runs. Both
Ubuntu targets again passed all fifteen observations. The four ZIPs matched
their Actions digests and passed CRC verification. Windows x64 artifact
14725763446 has SHA-256 `989506eef632cdc1942c16dda5be63d2f5740d8a4687acc312d38ad18963d1fc`
and Windows ARM64 artifact 14726270855 has SHA-256
`450d189cd9a808cae34ab27a44c1c71c984888896a816573f7a00ceb0b356292`.
The revised registration uses the demonstrated lookup and independently
compares the new handle. Both MSVC target builds passed Clippy.
[Four diagnostic runs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44951905544).

At `d403feefce23cad5357bf3fb0b49af03f012333e`, Ubuntu x64 and ARM64 each
passed eight unit tests and fifteen filesystem scenarios. Both Windows hosts
passed seven unit tests. Their Rust workers opened the directory by ID and
verified the handle identity. The first `ReadDirectoryChangesW` submission
then returned `ERROR_INVALID_PARAMETER` (87) on both hosts, before either
could record a wakeup or a completed shutdown. The separate Win32 controls
again observed equal volume and file IDs after opening by ID and by fixture
name. All four ZIPs matched their Actions digests and passed CRC and
inner-receipt verification. [Native run 44953046277](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046277).

| Target | Actions artifact | SHA-256 of verified ZIP |
| --- | ---: | --- |
| Ubuntu x64 | 14726730278 | `ce27f34e24b751cf3c9f060802c9ee50b199441af574e9d0bc8a481072823b08` |
| Ubuntu ARM64 | 14726610641 | `3fc03245854921a4098a5f93c017fc403ba877a79fd47c3b63431ad5c22635e8` |
| Windows x64 | 14726726502 | `99e7d3811601180e7205c264f526674c6caf136c7d63cbcd87b2eb79257eb071` |
| Windows ARM64 | 14726636141 | `040069239aee2d4d44a6a2b876827968658ffbced2ab8108e033fd55b161decb` |

The subsequent `windows-notification-handle-lease` scenario isolates the
worker's handle. The observer first opens the root for `DELETE` and closes
it. After registration the Rust fixture closes all caller-owned directory
handles. The observer requires a sharing violation for the same access,
checks that a sibling write leaves the generation unchanged for 350 ms, then
creates a file under the watched tree and checks its native wakeup and full
inventory. After `stop_and_join`, the observer obtains `DELETE` access again
and renames the same directory while the Rust process and joined `Watch` are
still alive. Both MSVC targets passed Clippy with warnings denied. Fedora
x64 passed all eight unit tests and fifteen Linux scenarios in
`independent-lease-guard-01`, and a separate live fixture answered a state
query after joining. Native Windows results for the additional lease scenario
were pending in those runs; the later Windows results below exercise it.
[Fixture control](../../tools/rust-qa/watch-events/src/main.rs) and [external observer](../../tools/rust-qa/watch-events/run.py).

### Dedicated asynchronous object candidate (2026-11-22)

The error-87 result demonstrates that matching file IDs alone did not establish
a usable notification object. It does not identify every filesystem-internal
cause. The next candidate removes the failing reopen from the adapter entirely:
the initial grant supplies the dedicated asynchronous object, and ownership
moves into the worker. Its original no-delete lease remains until that worker
has completed or cancelled and drained its I/O. No pathname recovery or retry
loop was added. The separate caller-input release scenario remains unchanged.

Both the Rust adapter and Python controls reject an all-zero 128-bit file ID
immediately after an otherwise successful identity query, before any binding
or by-ID lookup. MS-FSCC specifies this value when the filesystem does not
support 128-bit file IDs; equal absent IDs cannot establish object identity.
Deterministic Rust and Python controls reject the absent value and accept a
nonzero value at each of its sixteen byte positions. The Rust controls also
run on Linux. [FileIdInformation contract](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fscc/e4185a8a-ed8d-4f98-ab55-ca34dc8916e6).

Before arming, synchronous `NtQueryInformationFile` requests read
`FileAccessInformation` and `FileModeInformation`. They verify listing/attribute
rights and absence of either synchronous-I/O flag, so mistakenly passing an
ordinary synchronous directory cannot block the worker inside the first arm.
An additional native unit case accepts a correctly bound async acquisition and
rejects a synchronous object, missing listing access and a different directory.
Microsoft documents file-information queries as synchronous even on asynchronous
file objects.
[Query classes](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntqueryinformationfile)
and [query lifetime](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ioisoperationsynchronous).

The optional Win32 controls now compare real notification requests on fresh
direct, by-ID, `ReOpenFile`, and empty-name handle-relative `NtOpenFile` objects.
Each method records requested access/sharing/flags, actual identity,
access/mode/reparse attributes, submission, returned notification names and a
separate idle-request cancellation. A positive cancellation requires an idle
pending request, successful `CancelIoEx` and completion with error 995. The
report records NT `CreateOptions` (`0x204001`) separately from Win32 open flags
(`0x42200000`). The historical by-ID adapter and control at `d403fee` requested
access `0x81`; the current acquisitions request `0x100081`, including
`SYNCHRONIZE`. These are different access requests, so later success alone
cannot isolate the cause of the historical error 87. Each method runs in a
bounded child process;
pending buffers are drained before release, or that isolated process is killed
after 20 seconds. These controls are diagnostic evidence and do not substitute
for the Rust worker's independent scenarios. The handle-relative NT route is
an experiment, not a selected fallback. Complete native Windows acceptance
was still pending at that stage; the subsequent observations follow below.

Both MSVC targets passed Clippy with warnings denied for this candidate. The
native Fedora x64 guard passed ten library tests, three Python control tests
and fifteen scenarios, including the actual inotify overflow. Its source-bound
receipt is
`artifacts/rust/watch-events/x86_64-unknown-linux-gnu/direct-object-guard-03/result.json`,
SHA-256 `d5193fbf49c4e8f5abbd6e411710915ae310cb328a2b08745312897f6818cb76`.
These are compilation/Linux results, not Windows notification acceptance.

### Native direct-object result and flat scope diagnosis (2026-11-22)

At `a66e0456a85a62844e2de2fd155aaeac3577f87c`, the Windows Server x64
fixture passed ten library tests, three Python controls, pending-I/O shutdown,
the independent notification-handle lease and the create, modify, rename,
delete and nested-create scenarios. The lease trial denied `DELETE` with error
32 after the caller handles closed, observed the nested write, then restored
`DELETE` access and renamed the directory while the joined subject remained
alive. The standalone direct and empty-name NT acquisitions each delivered a
notification and completed an explicit idle cancellation. By-ID acquisition
still failed at the first notification submission with error 87 despite the
same `0x100081` requested/queried access and asynchronous mode; `ReOpenFile`
still returned error 5.

Windows 11 ARM64 repeated all seven positive observations at the same commit,
including error 32 while the notification lease was held and successful rename
after join. Its direct and empty-name NT delivery/cancellation controls passed,
while `ReOpenFile` returned 5 and the by-ID notification submission returned 87.
It then failed at the identical flat-scope assertion, also without retaining
the native notification names. Neither Windows run establishes the cause of
that scope assertion or a complete watcher pass.

The run failed at the flat-scope assertion before recording that scenario's
native names. That assertion equated any generation increase with a nested
file notification. Microsoft defines notification names relative to the watched
handle and action 3 as a modification that may concern metadata. A flat watch
can therefore observe an immediate entry such as the `nested` directory;
this is distinct from observing `nested/item.jpg`. The archived result cannot
distinguish those cases, so a parent-directory metadata event remains a
hypothesis and this run remains failed.
[Directory scope](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-readdirectorychangesw)
and [notification records](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-file_notify_information).

The follow-up retains raw completed bytes from the actual Rust flat watch only
when fixture diagnostics are enabled, capped at 32 buffers of at most 32 KiB.
It does not filter wakeups or change rescan, overflow or cancellation decisions.
The observer requires every new generation to have its bounded native record.
For the nested-write phase only action 3 for the immediate `nested` entry is
accepted; a nested filename, unknown action/name, missing record or truncated
trace fails. A separate direct-child creation must produce an actual added
record for `flat.jpg`. Complete nonrecursive inventories must exclude the
nested file both before and after this direct write. The Linux quiet-nested
assertion remains in place. Failed record qualification preserves the raw
trace and states in the receipt.

The receipt field `parentMetadataObservedDuringNestedPhase` describes only
the nested-write observation interval. A parent modification delivered later
in the direct-child phase remains in `batches` but does not set this field.
The Python controls cover that delayed-delivery distinction.

The raw-record implementation at `b7c6577` passed ten library tests, six Python
controls and fifteen native Fedora x64 scenarios. Both MSVC targets passed
Clippy with warnings denied.
`artifacts/rust/watch-events/x86_64-unknown-linux-gnu/flat-notification-guard-01/result.json`
has SHA-256 `afefd9df972c060093932eab57b75c0813f36ce7ec7adbc96f4bcc809a2b0563`.
Its native Windows raw-record observations were pending at that revision;
the four-target results below provide the subsequent observations.

The archived x64 ZIP from [run 45034293004](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45034293004)
has verified SHA-256
`e775d3f2a090f36123de610a76a24fc8ea6ecd632c5a3285db55c9384603f97d`;
its `result.json` has SHA-256
`684bb1d66a737ace2e6c092021487bc4810fb0c59a01be67a998a3f3a792e025`.
CRC and inner digest verification passed. All watch source digests match the
commit exactly. The toolchain JSON and verification script match its content
with the Windows checkout's CRLF representation.

The ARM64 archive from the same run, artifact `14759221577`, has verified
SHA-256 `c44bbaab454c39929c2d4b4999a0e0716f348a2715f8df665bba51e6d0f287c8`;
its `result.json` has SHA-256
`ab31229b148ca56402b40d328df8c9525c24d5b940c90358c0f1c8248b7a090b`.
CRC, inner digest and committed input checks passed with the same two CRLF
representations noted above.

### Four-target watch observations at 3b4854d

[Run 45039099706](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099706)
passed all four native jobs at clean revision
`3b4854d867f614a956042dfe987ecc7c008e53ec`. Every target passed ten Rust
unit tests and six Python control tests without skips. Ubuntu x64 and ARM64
each passed fifteen native scenarios; Windows Server x64 and Windows 11 ARM64
each passed thirteen. These are executions on the reported native compiler
hosts and executable machines, not cross-build results.

Both Windows flat subscriptions returned the following three raw completed
buffers. An independent decode of their length fields and UTF-16 names matched
the parsed receipt and accounted for every generation after the initial one.

| Generation | Phase | Native action | Relative name | Completed bytes |
| ---: | --- | --- | --- | ---: |
| 2 | Nested-file write | 3: modified | `nested` | 24 |
| 3 | Direct-child creation | 1: added | `flat.jpg` | 28 |
| 4 | Direct-child creation | 3: modified | `flat.jpg` | 28 |

Thus this run directly observed the immediate parent-directory modification;
it did not report `nested/item.jpg` from the flat subscription. Both receipts
set `parentMetadataObservedDuringNestedPhase=true`. Their complete flat
inventories were empty after the nested write and contained only `flat.jpg`
after the direct write. The Linux subscriptions stayed at generation 1 for
the nested write and advanced for the direct child. This resolves the previous
scope assertion with native records while preserving conservative rescans.
The earlier runs remain failed records because they did not retain those names.

Both Windows targets also passed the independent notification-handle lease,
pending-I/O shutdown, ordinary mutations, inventory cancellation, application
queue pressure, renewed coverage, missing-child scan and sharing trials.
The sharing trial observed Windows error 32 for conflicting delete, rename and
read access; the failing Python inventory retained its baseline with errno 13,
then recovered after release. The separate direct and empty-name NT controls
each delivered their synthetic file and cancelled an idle request successfully
with completion 995. `ReOpenFile` still returned 5 and by-ID notification
submission still returned 87; neither is the selected adapter route.
The two Linux runs each observed the actual 16,384-event inotify overflow,
registration refusal, root movement and post-arm directory replacement.

Each local ZIP below was independently matched to the live GitHub artifact
digest and size, then checked for CRC integrity. The four inner `evidence.sha256`
files matched `result.json`. All twelve input digests in each watch receipt
match the commit: the two Windows receipts use CRLF for `rust/toolchain-inputs.json`
and `tools/rust-qa/check-toolchain.py`; all other inputs match byte for byte.
The four receipts report no modified source paths. Archives are retained under
`artifacts/rust/hosted-watch-events/45039099706/`.

| Host | Native scenarios | Artifact ID | ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Linux x64 | 15 | 14761190564 | `8fbe0dba24de0ee1ab208572fc6d6b33d80c31632c99b34aac901cc924e327c2` |
| Linux ARM64 | 15 | 14760309747 | `039e40647adf162fdda5c6140c1a1d0f0f7d25b5d08a6eb0d29ad9569d8ff514` |
| Windows x64 | 13 | 14760802069 | `ae44296d88e24b6feb9f26cbca4de27041c417a196e525ce72f6d2558ac4fcce` |
| Windows ARM64 | 13 | 14760184752 | `bad868b9491343f4f683e298b00a38d894fd5eca557e2b5ba77cbc47d20544fb` |

This covers the selected isolated watch scenarios. Actual Windows kernel-buffer
overflow remains unobserved; its status handling has deterministic coverage.
The filesystem SMB tests are separate from these local watch runs and do
not establish notification delivery over SMB or portal/FUSE. Safe-fs grant
integration, scheduling and engine reconciliation remain later-stage work.
[Filesystem evidence](rw02-filesystem.md#retained-identity-follow-up-at-3b4854d).

The standalone package and FFI declarations are first-party AGPL-3.0-only
code. The Cargo lock has SHA-256
`b9dd28af9ec3c24651b64336d0e50acd168b50eb80daef390a09bfdcc9eb953b`.
The Fedora executable loaded the system dynamic loader, glibc 2.44 and GCC's
unwind library. Each receipt identifies the actual mapped files by digest.
The Fedora glibc `LICENSES`, libgcc `COPYING.RUNTIME` and pinned Rust
`COPYRIGHT-library.html` were inspected. These host components stay in their
OS packages. The Windows adapter imports the system Kernel32 and Ntdll APIs.
The native Windows fixture inventories the DLLs loaded by its own executable. The
assessment adds only its own Rust source to the reviewed runtime inputs.
[Manifest](../../tools/rust-qa/watch-events/Cargo.toml),
[Rust licensing at the pinned revision](https://github.com/rust-lang/rust/blob/0ef1bc386059596dada8fb65b50425aab2ea637a/COPYRIGHT)
and [GNU C Library](https://sourceware.org/glibc/).

The assessment supplies authorized directory handles from a synthetic profile.
The Windows fixture performs both name-based opens only during the initial
private grant, then binds the async object before the observer starts mutations.
Production must acquire that object within its safe-fs grant or retained-parent
relative open; the fixture pathname is not an application fallback. Connecting
that operation to the application's safe-fs leases, applying the
shipping debounce and five-second schedule, and reconciling the resulting
state belong to the foundation and engine stages. The later package inventory
must still cover its actual binary inputs. [Stage dependencies](../rust-rewrite-plan.md#staged-implementation-proposal).
