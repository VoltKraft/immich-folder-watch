# Watch-root filesystem security

This is the contract for the handle-bound filesystem implementation introduced by
`M-WATCH-ROOT-ATOMICITY-20261110`. Its current validation status is in
[project status](status.md); the original finding is
`csf_77f3e84ec9b70e5aff765235` in [the remediation record](security-remediation-20261109.md).

## Authorization and lifetime

A worker pins each configured source directory before synchronization starts.
Authorization follows that opened directory's identity, not a mutable pathname.
A rename may fail or an operation may continue against the already-authorized
original directory; replacing the old pathname with another directory, symbolic
link or Windows junction never authorizes that replacement. This is not a claim
that Linux prevents an already-open directory from being moved elsewhere.

Filesystem notifications are hints. Enumeration and absence checks must use the
pinned source too: a replacement empty directory cannot establish that an asset
was deleted locally. Queued transfers and retries must retain their source
capability until their operations finish. No sensitive operation may fall back
to opening a previously validated absolute path.

The threat boundary is the application's existing per-user OS security model.
It is not process isolation from a malicious process with equivalent access to
the user's memory, credentials and private files, or a privileged administrator.

## Operations

- Upload data and its metadata come from a retained, no-follow file handle.
  Hashing and timestamp recovery use the same retained file object rather than
  reopening its pathname between checks and writes.
- Local deletion is confined to the pinned parent and verifies the selected file
  identity. Replacement files must not be mistaken for the verified upload.
  A later retry or restart without the successful upload's live file handle must
  upload again before cleanup; stored size and modification time are not deletion
  authority. The legacy upload identifier includes a digest from that same file
  handle, so equal size and timestamps cannot make replacement contents inherit
  an earlier upload's identifier.
- Downloads create staging data within a protected internal namespace, retain
  the output handle, publish without replacing a destination, and clean up through
  retained directory handles. Neither publication nor cancellation may follow a
  substituted staging name into an unrelated tree.
- Directory creation and rename protect both sides of the operation. Timestamp
  writes reject files observed with multiple hard links. This check does not
  prevent another process from subsequently adding an alias to an authorized file.
- `.ifw-internal-` path components are reserved for the filesystem implementation.
  Watcher callbacks, album handling and enumeration must ignore them.

## Platform behavior

Linux uses descriptor-relative operations and refuses symbolic-link traversal.
Internal staging/quarantine directories require effective owner-only protection;
publication/restoration requires an atomic no-replace operation. Portal/FUSE and
mounted directories are evaluated by their actual capabilities, not a filesystem
name allowlist. Filesystems that cannot provide the required operation fail
closed, without a pathname-based fallback. A protected quarantine may retain a
mismatched entry after a failed safe restoration; this preserves data rather than
silently replacing a newly created path.

Linux reuses protected outer containers in a per-root cache of up to 64 parent
directory identities. Eviction closes cached handles; active operations retain
their own handles. Revisiting an evicted directory creates a fresh container
instead of reopening its old pathname. Inner transaction directories are cleaned
through their private parent. Outer containers remain after eviction or shutdown
because Linux cannot atomically remove a name conditional on its inode identity.
Normally these retained containers are empty; a failed safe restoration can leave
quarantined data. They can accumulate across restarts or cache turnover. Do not
blindly delete them: stop synchronization and inspect retained contents before
manual cleanup.

Windows retains directory handles that deny delete sharing while needed and
checks reparse points. Staging files use exclusive handles; transaction directories
inherit the source ACL, so this does not claim directory-name confidentiality.
External attempts to rename a pinned source or an active
intermediate directory can therefore fail with a sharing violation until the
worker or operation releases its handles. File deletion and metadata changes
operate on retained handles. UNC and ARM64 runtime acceptance must be distinguished
from Windows x64 tests and native package compilation.

## Acceptance evidence

Regression coverage must exercise root, intermediate-directory and leaf changes;
include ordinary directory replacements as well as links/junctions; and assert
that outside sentinel contents, existence and timestamps remain unchanged.
Test upload/retry paths, verified cleanup, remote cleanup, download publication and
cancellation, timestamp recovery and local directory renames. Windows refusal to
rename a locked directory is a valid security outcome, not a reason to skip the
platform regression. Independent review must check the actual worker/API call
sites as well as the filesystem primitives.

The exact passing checks and any remaining runtime limitations belong in
[status](status.md), not in claims inferred from this contract alone.
