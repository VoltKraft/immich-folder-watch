# RW-02 native filesystem feasibility

The [safe-fs crate](../../rust/crates/safe-fs) implements native directory and
regular-file leases on Linux and Windows x64/ARM64. The [watch-root contract](../watch-root-security.md)
defines the required behavior. The [security mapping](rw01-security-contract.md)
defines the remaining integration and recovery evidence.

## Acquisition and lifetime

`Directory::open_root` takes the absolute directory granted by configuration
or the portal. Its trusted ancestors participate in this initial acquisition.
Each subsequent child operation accepts one native OS name. Directory leases
retain the parent chain, including while queued work holds a clone. Relative
parent steps, reserved internal components and Windows streams are rejected.
Linux names retain their original bytes and Windows names retain their UTF-16
representation.

| Operation | Linux | Windows |
| --- | --- | --- |
| Pin and descend | `O_DIRECTORY\|O_NOFOLLOW`, then `openat` on the parent fd | Drive or UNC root with backup semantics and open-reparse-point flags, then `NtCreateFile` with a retained `RootDirectory`. Directory handles deny delete sharing. |
| Read, seek, hash, observe metadata | `O_PATH\|O_NOFOLLOW` pins the entry before type inspection. A procfs fd magic link acquires read access to the pinned regular file. The identities must match. A nonblocking shared file lock preserves writer readiness. | Handle-relative synchronous open, reparse rejection, disk-file type and stable object identity. A read lease allows the name to change while retaining the original file. |
| Enumerate a bounded directory | An independent `read_dir` cursor through the pinned procfs fd. Each returned name is inspected through its parent descriptor. | `FileIdBothDirectoryRestartInfo` and continuation batches through the retained directory. A per-handle lock serializes the native cursor, and every variable-length record is bounds-checked. |
| Apply journaled times | A separate write-authorized lease checks the current entry and link count before setting mtime through the same file. | The metadata-write lease explicitly requests `FILE_WRITE_ATTRIBUTES` and sets creation time and mtime on its handle after the same checks. |
| Stage and publish | Verified owner-only transaction directories, exclusive payload creation, identity check and `renameat2(RENAME_NOREPLACE)` against the retained destination. | An exclusively opened payload moves with `NtSetInformationFile(FileRenameInformation)`. The rename points to the pinned destination handle and forbids replacement. |
| Cancel and clean up | A private directory handle and identity check precede each `unlinkat`. The bounded 64-parent cache never unlinks an outer name from a public directory. Active operations retain their own handles after eviction. | A handle-based disposition removes the payload and then the empty transaction directory. The directory inherits the source ACL. |

Enumeration returns the complete list of immediate children for that scan or an
error. A changing tree still requires the engine's complete-inventory and durable
reconciliation rules. Timestamp repair callers must verify content and persist
their journal intent before applying the change. A hard link created after the
final link-count observation is outside the guarantee of that observation.

Windows uses the complete `FileIdInfo` volume/128-bit file identifier. For
FAT, FAT32 and exFAT a verified filesystem type permits the documented legacy
file index. An unavailable identity on other filesystems fails the operation.
The ABI declarations are limited to the supported 64-bit targets, with compile-time
layout checks. Linux uses its native dev/inode pair while the handle is live.
These identifiers cannot be persisted as stand-alone deletion authority.
Windows also checks the normalized name of a public handle for a reserved
component, including when the caller supplies an 8.3 alias. Linux requires the
legacy `statx` result mask plus ctime. Protected directories also require reported
owner and mode. Unsupported identity or protection aborts that operation.

`Download::publish` flushes the payload, checks the destination and prepares
the native request. The atomic no-replace operation handles a competing arrival
after this check. Reconciliation follows the point of failure.

| Publication result | Caller and filesystem behavior |
| --- | --- |
| `BeforeRename` | The request was never submitted. This includes an already-occupied name. Dropping the lease attempts ordinary private-stage cleanup. |
| `RenameOutcomeUnknown` | The submitted native call returned an error. The destination may already contain the payload. The implementation releases its handles and preserves the transaction exactly as found. The caller must reconcile its transfer intent and destination before retrying or recording completion. |
| `AfterRename` | The filesystem acknowledged the rename. A subsequent directory sync or cleanup failed. Reconcile the published destination and outstanding cleanup. |

Linux syncs the source and destination directories after an acknowledged rename.
A filesystem server may complete a rename and lose the acknowledgement. Any error
from the submitted operation follows the uncertain-outcome policy across both
platforms. Closing a Windows handle that was explicitly marked for deletion
after an uncertain result could remove the newly published file. The cancellation
path therefore relinquishes its payload before submitting the native request.
See the [Linux rename documentation on RPC recovery](https://man7.org/linux/man-pages/man2/rename.2.html#BUGS).

`Download::cancel` reports cleanup errors while the stage is still private.
The engine's durable intent, recovery after process death and post-activity
rollback remain RW-03 and RW-07 integration gates.

The backend uses the Rust standard library, the Linux C library, procfs and
Windows system DLLs. It introduces no third-party Cargo package. See
[Linux openat and O_PATH](https://man7.org/linux/man-pages/man2/openat.2.html),
[NT handle-relative opening](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[Windows enumeration layout](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_both_dir_info)
and [Windows file IDs](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info).
The backend also follows the [Linux statx result-mask contract](https://man7.org/linux/man-pages/man2/statx.2.html),
[atomic Linux rename flags](https://man7.org/linux/man-pages/man2/renameat2.2.html),
[Windows handle rename layout](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information),
[Windows handle-relative name query](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)
and [Windows handle disposition](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_disposition_info).

## Evidence

The [native tests](../../rust/crates/safe-fs/tests/handles.rs) create temporary
synthetic directories. They cover ordinary-directory replacement, actual junction
or symlink denial, same-length/same-time file replacement, hard-linked timestamp
refusal, repeated batched scans, reserved names, bounded enumeration, competing
publication and explicit or dropped-stage cancellation. Linux also exercises the
writer lock, a special file, changed container mode/name and active leases across
cache eviction. The Windows alias test reports whether its volume supplied a
distinct 8.3 spelling with `distinct_short_name` and actual denial with
`short_name_denial_verified`. With `IFW_RUST_REQUIRE_WINDOWS_SHORT_NAME=1`,
absence of an actual distinct alias fails the test. A successful alias check
also verifies that an ordinary OS access through that alias reaches the fixture's
marker and that the public media lease refuses the same directory.
Run `cargo test -p safe-fs`
with the [pinned toolchain](../../rust/rust-toolchain.toml). Target-specific
execution evidence belongs in the [acceptance record](acceptance.md).

On 2026-11-20, Rust 1.100.0 on native Linux x86_64 ran all 13 Linux integration
cases on tmpfs in the debug profile. The optimized build ran the same 13 cases
on Btrfs with a temporary directory inside ignored build artifacts. Both runs
passed without skips. Locked offline Clippy on all crate targets with
`-D warnings` and the crate's rustfmt check passed. The host kernel reported
`7.3.4-300.fc45.x86_64`.

Following independent review of `2ff9880`, both local Linux filesystems passed
the updated 16 checks on 2026-11-20. The suite includes two unit cases and
14 integration cases in each profile. One test injects a lost acknowledgement
after a real native rename and verifies the published bytes and retained
transaction after all handles close. Another inserts a successful competing
publication between preflight and the actual native no-replace call. Both
the incumbent and the losing stage survive. A nonempty transaction directory
exercises acknowledged publication followed by a real cleanup failure. Locked
offline Clippy with warnings denied and rustfmt also passed. The injected fault
models the acknowledgement boundary. Actual SMB and portal/FUSE recovery
remain native-environment acceptance items.

### Four native hosts

On 2026-11-20 all four native jobs completed at clean source
`4dcccb766e358db32daa266bf851efcaf51dbf9b`. Both Windows hosts read the
controlled marker via an actual distinct NTFS 8.3 alias and recorded the
protected directory lease's denial. All four hosts exercised a successful
rename followed by a lost acknowledgement. The destination contained the
staged bytes after handle cleanup, and the transaction directory remained
available for recovery. Each archive was downloaded and verified against
GitHub's SHA-256 digest. [Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44811901356).

| Host | FS tests / total Rust tests | Evidence artifact ID | ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Linux x64 | 16 / 30 | 14668096001 | `502dc539a5524069332a4a720b4a66e37494ae213af00ba0aede646ee454c5ac` |
| Linux ARM64 | 16 / 30 | 14668875738 | `23bd737458911d089c546d8064e3f30971fde10657127fd0f0efa4ea9ae9e5ef` |
| Windows x64 | 13 / 27 | 14666168586 | `e09e397e859199c09fc806f8ce35025ad6f7fae72687a93b430ec9602ddbe7de` |
| Windows ARM64 | 13 / 27 | 14668666642 | `32dee47d5fbd8e29ff5f8d2e2ffa3a25c6462584d4f3155e7f03ecb65cbef5d1` |

Every archive also contains five matched window-policy traces, 5,844 C#/Rust
codec comparisons and its original compiler, format, Clippy and build logs.
The initial run used local volumes. Later UNC and portal/FUSE results follow.
Verified destructive cleanup, directory moves, engine call sites and their
independent review remain RW-03 and subsequent integration gates.

The Windows [SMB fixture](../../tools/rust-qa/test-windows-smb.ps1) creates
an empty temporary share on a disposable host. It verifies its encryption,
single-account ACL and backing directory before populating it. A read through
the loopback UNC and the Windows client's negotiated SMB dialect establish
the path used by the tests. A Rust-only fixture selector accepts a random
32-hex identifier and constructs the localhost share name. Each test owns a
new directory there. The junction setup uses the local backing directory
because cmd.exe cannot take a UNC working directory. The production leases
operate through the UNC path. Evidence includes cleanup outcomes. Hosted
results must verify that these operations are supported by each Windows host.

Both native Windows hosts at `49617467a73901fb10b9735dcf7bf727e6d0b2d1`
passed all 13 filesystem tests again through encrypted SMB 3.1.1. Each report
recorded 13 opened UNC fixture roots, a successful local-to-UNC marker
readback, removal of the share and removal of its owned scratch directory.
The artifact ZIPs matched SHA-256
`64ba3b7a3a9ddc8155aac62bc603b09f2e2b2f2599ca47714d734bc6df106792`
on x64 and `4292e401d20f84e73f65e16c8c34d7aee279fedd3b6ed261cba071320bef5502`
on ARM64. [Native SMB run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44820760908).

The real Fedora Documents grant allowed enumeration, private staging,
no-replace publication, cancellation and revocation. Its distro daemon
returned `ENOSYS` for the shared media read lock. A private build containing
the upstream fix enforced the lock on the underlying file while retaining
the grant boundary. [Rust and shipping .NET observations](rw02-linux-services.md).

## Independent review of the feasibility boundary

The independent review of `2ff988095045739b6eeb0735750f5ec9aa9baca6`
identified two issues. A filesystem can complete a rename and return an
error before its acknowledgement reaches the process. Windows may also return
the original spelling from `GetShortPathNameW`. A successful generic denial
could then conceal missing 8.3 coverage.

The reviewer examined the corrected staging state machine and native handle
cleanup. A submitted call that loses its acknowledgement consumes the stage
and requires reconciliation. Plain handle disposal leaves the destination and
the protected transaction intact. The real-rename fault-injection test
observes both after the handles close. The Windows fixture checks access
through an actual distinct alias and requires the protected API to deny it.
The native workflow requires and retains both observations on Windows.
The re-review found both source issues resolved. Its reviewed staging file
has SHA-256 `42ae0f4f31f3bd0553abd53357ee8bfd039bdaf13f282ddd24707ac17a3594a4`.
Native SMB/FUSE interruption and future engine call sites
have separate acceptance records.
