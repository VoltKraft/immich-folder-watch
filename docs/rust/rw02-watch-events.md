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
- **Windows.** Reopen the same directory object with `FILE_LIST_DIRECTORY`
  and asynchronous I/O. One 32-KiB DWORD-aligned buffer covers a flat or
  recursive subscription. A zero-byte completion or `ERROR_NOTIFY_ENUM_DIR`
  returned on either submission or completion records `NativeOverflow` and
  retires the subscription. Even the first submission exposes this state to
  the caller, which inventories and registers again. The worker exits after
  that single failure. An explicit stop cancels any outstanding request and
  waits for its final completion before releasing the buffer, event or
  directory handle. A timeout leaves the caller owning the worker.
  Windows reports changes below the subscribed directory. The periodic check
  also covers the root itself. [Windows adapter](../../tools/rust-qa/watch-events/src/windows.rs),
  [same-object reopen](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-reopenfile),
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

The standalone package and FFI declarations are first-party AGPL-3.0-only
code. The Cargo lock has SHA-256
`b9dd28af9ec3c24651b64336d0e50acd168b50eb80daef390a09bfdcc9eb953b`.
The Fedora executable loaded the system dynamic loader, glibc 2.44 and GCC's
unwind library. Each receipt identifies the actual mapped files by digest.
The Fedora glibc `LICENSES`, libgcc `COPYING.RUNTIME` and pinned Rust
`COPYRIGHT-library.html` were inspected. These host components stay in their
OS packages. The Windows adapter imports the system Kernel32 API. The native
Windows fixture inventories the DLLs loaded by its own executable. The
assessment adds only its own Rust source to the reviewed runtime inputs.
[Manifest](../../tools/rust-qa/watch-events/Cargo.toml),
[Rust licensing at the pinned revision](https://github.com/rust-lang/rust/blob/0ef1bc386059596dada8fb65b50425aab2ea637a/COPYRIGHT)
and [GNU C Library](https://sourceware.org/glibc/).

The assessment supplies authorized directory handles from a synthetic profile.
Connecting that operation to the application's safe-fs leases, applying the
shipping debounce and five-second schedule, and reconciling the resulting
state belong to the foundation and engine stages. The later package inventory
must still cover its actual binary inputs. [Stage dependencies](../rust-rewrite-plan.md#staged-implementation-proposal).
