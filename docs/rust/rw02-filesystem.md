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

`Download::publish` flushes the payload before rename. Linux also syncs both
affected directories. A post-rename error is distinct from failure to publish.
`Download::cancel` returns cleanup errors. Dropping an unfinished lease attempts
the same cleanup. Crash recovery of persisted effects still requires the RW-03
and RW-07 integration tests.

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
distinct 8.3 spelling. Run `cargo test -p safe-fs`
with the [pinned toolchain](../../rust/rust-toolchain.toml). Target-specific
execution evidence belongs in the [acceptance record](acceptance.md).

On 2026-11-20, Rust 1.100.0 on native Linux x86_64 ran all 13 Linux integration
cases on tmpfs in the debug profile. The optimized build ran the same 13 cases
on Btrfs with a temporary directory inside ignored build artifacts. Both runs
passed without skips. Locked offline Clippy on all crate targets with
`-D warnings` and the crate's rustfmt check passed. The host kernel reported
`7.3.4-300.fc45.x86_64`.

RW-02 still requires native results on the other target filesystems and desktop
environments. A hosted NTFS or Linux local test cannot establish UNC or
portal/FUSE behavior. Verified destructive cleanup, directory moves, transfer
and timestamp-journal call sites and independent filesystem review remain RW-03
and engine integration gates.
