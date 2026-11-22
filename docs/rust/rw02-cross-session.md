# RW-02 same-account writer ownership across Windows sessions

The native writer opens one pre-existing empty file and calls Rust’s `File::try_lock`. The test requires two processes with the same account SID in distinct Windows OS sessions, refusal in both directions and orderly release followed by reacquisition. The historical old/new coordinator and installed handover have their own evidence. [Rust guard](../../tools/rust-qa/instance/main.rs) · [Old/new activation](rw02-instance.md)

## What the hosted machines established

At `8a8adaa400abc7303335c624ea68abed197158da`, Windows Server x64 and Windows 11 ARM64 both reached a genuine second session through their own on-demand Task Scheduler S4U logon. The original controller and first Rust holder were in session 2. The scheduled Python process was in session 0 and independently returned the same account digest. On each host, both tokens reported elevation with type Default. Task Scheduler recorded the requested LUA level. The original fixture stopped before the scheduled holder or contender opened the guard. Both runs verified unchanged batch-logon assignments, task deletion and removal of the synthetic directory. The scheduled action returned 1. Every file in each evidence index was checked. [Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642)

| Native archive | SHA-256 of `cross-session/evidence.sha256` |
| --- | --- |
| Windows x64 | `e171450f2f920bf3705e0f8467f77988d2be1ebc02fcdfc10bbb5e61a9d805ea` |
| Windows ARM64 | `1db2eb47abc199ae645e787ee7b21ef3b0fdad5a1aefaece4a26968447bc1a4f` |

## Two independent Windows trials

The hosted controller builds the pinned native Rust image once. Each trial gets a fresh marked profile, a new guard file and a unique task. Both tasks request the same on-demand S4U logon at LUA level. Each trial records the actual process rights Windows supplied. The first task, its known processes and its profile must be gone before the second trial starts. A failed lock sequence with verified cleanup still permits the independent second trial. [Controller](../../tools/rust-qa/instance/cross-session/observe.py) · [Scheduled action](../../tools/rust-qa/instance/cross-session/scheduler.ps1)

| Result | Qualification |
| --- | --- |
| `ambientGuardPassed` in `ambient-case.json` | All five native writers inherit the existing process rights of the bootstrap in their own session. An elevated Default token can qualify here. |
| `standardUserGuardPassed` in `standard-case.json` | Both participants and every native writer meet the ordinary-user rules below. An elevated Default token fails here. |
| `lockSequenceObserved` in either case | Both refusals, both handovers and the final release were observed against the original file identity. A case also requires verified cleanup to pass. |
| `passed` in `result.json` | Both hosted trials passed and the shared build directory was removed. The two separate guard results remain available when one trial fails. Installed handover retains its own acceptance evidence. |

For the ambient trial each bootstrap runs the fixed participant directly. The controller matches the participant to the same live process and checks each writer against its own session’s participant. It compares the account and session, elevation and type, integrity, UIAccess and restrictions, and a digest of the groups, restricting SIDs, capabilities and privilege attributes. A cross-session difference between the logon groups is expected. The reports retain digests and counts for these private inventories. [Authority inspection](../../tools/rust-qa/instance/cross-session/standard.py) · [Windows token information](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class)

For the standard-user trial each primary token must report no elevation, default or limited elevation type, no enabled local administrative/operator aliases, no application capabilities or UIAccess, and integrity at or below Medium. The privilege inventory must fit the ordinary-user set, including disabled privileges. A participant meeting these checks can run the fixed test directly. If a hosted bootstrap has administrative authority, it records its original token facts. It can invoke the system `runas.exe` with the listed Basic User level `0x20000`, a profile-free launch and the exact hashed Python image/script for its role. This requires an already-running Secondary Logon service. A refused launch or insufficient effective token preserves its reason in the raw evidence. The test uses existing account and service settings. [Fixed participant](../../tools/rust-qa/instance/cross-session/worker.py) · [Mandatory integrity](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control) · [Windows Runas](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2012-r2-and-2012/cc771525%28v%3Dws.11%29)

Each Rust process starts suspended and belongs to its owner’s private kill-on-close job. Before the first thread resumes, the controller checks its exact image, creation time, PID, account, native session and authority. It inspects each live holder again after its `WRITER_HELD` response. In order, the first process holds, its peer refuses, the first releases, the peer holds, the original side refuses, the peer releases, and the original side reacquires and releases. Each completion ties the actual response and exit code to the exact process and volume/file ID. The ordered events appear in `observedWriterEvents`. The managed oracle only reads the account identity. [Rust guard](../../tools/rust-qa/instance/main.rs) · [Independent observation](../../tools/rust-qa/instance/cross-session/observe.py)

Both native Windows targets at `45dc03b` and `d403fee` returned one byte for
the controller's `TokenHasRestrictions` flag. The observer attempted a four-byte
read and exited before either trial launched its Rust writer. Cleanup removed
the temporary profiles. The observer now interprets both the observed Boolean
and the documented DWORD representation, and rejects unexpected widths.
Those runs ended before either cross-session lock sequence. [Four-target run at `d403fee`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306)
and [token information classes](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class).

## Native reproduction

At `a66e045`, Windows x64 and ARM64 each exercised the same elevated
account in console session 2 and scheduled S4U session 0. While session 2
held the guard, the contender in session 0 was refused. After release,
session 0 acquired the same file and the session 2 contender was refused.
Session 2 then reacquired and released it. Both observers verified seven
participant exits, unchanged batch-logon rights and removal of the
temporary profile. All 37 indexed files matched their hashes on each host.

On both hosts Secondary Logon was stopped. Neither Basic User participant
launched, so both overall results report an elevated pass and a failed
standard-user trial. A handover between two logged-on standard desktops
remains open.

| Native host | Overall writer result SHA-256 |
| --- | --- |
| Windows x64 | `110092561468270c6980c0bfc5d536b4479703117f7f62fab4bc1281e5685032` |
| Windows ARM64 | `2914248082d7c9f59c512d5e8194bf9372ebc71df19598a2b6baf5fe18fac2e7` |

[Native archives](rw02-native-gui.md#native-follow-up-at-a66e045).

The hosted wrapper records the installed service's state and startup type.
For a stopped, startable service it requests a temporary start on the disposable
runner, executes both native lock trials, then stops the service and verifies
the original state and startup type. If preparation fails, both observations
still run with their own authority checks. A cleanup failure fails the job.
Seven portable PowerShell controls cover these paths. A fresh native result
must confirm the actual standard-user lock sequence.
[Hosted wrapper](../../tools/rust-qa/instance/cross-session/hosted.ps1),
[Start-Service](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-service)
and [Stop-Service](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/stop-service).

The existing hosted jobs run the following from the matching native architecture with the pinned Rust and .NET toolchains. The local account must already have its effective batch-logon assignment. The same output directory holds both per-case reports, prefixed `ambient-*` receipts and the standard trial’s original receipt names. The controller verifies the original logon rights and removal of the exact registered task. It checks the stamped process identities before deleting each temporary profile.

```bash
python3 tools/rust-qa/instance/cross-session/observe.py "$NATIVE_TARGET" \
  --output "artifacts/rust/instance-native/$NATIVE_TARGET/cross-session"
```

A separate test uses two **already logged-on standard sessions of the same account** on a disposable Windows VM. Prepare a new shared local scratch directory accessible to that account in both sessions. Its marker `.ifw-existing-session-test` contains exactly the UTF-8 text `Immich Folder Watch isolated Windows test VM; synthetic data only` followed by LF. The two shells use the same checkout, Python executable and native target. Run the controller first, then give its printed unique directory to the peer within 110 seconds. Both validate their existing console or RDP session through Windows Terminal Services. The controller reads back the second connection state and protocol. This mode uses no scheduled task or alternative launch, and records its origin as `existing-standard-sessions`. Only the fixed guard’s child environment receives its four expected public rewrite identifiers. [Two-session runner](../../tools/rust-qa/instance/cross-session/existing.py)

```powershell
python tools/rust-qa/instance/cross-session/existing.py controller x86_64-pc-windows-msvc $MarkedVmScratch
python tools/rust-qa/instance/cross-session/existing.py peer x86_64-pc-windows-msvc $PrintedFixtureDirectory
```

Seventeen local tests passed, including an actual two-session POSIX rehearsal using the pinned native Rust writer. They cover changed authority, false or misattributed lock responses, cleanup failures and independent reporting. The manual two-desktop route reports `standardUserGuardPassed` for its own result and leaves `ambientGuardPassed` unmeasured. [Regression tests](../../tools/rust-qa/instance/cross-session/test_fixture.py)

```bash
python3 -B -m unittest discover -s tools/rust-qa/instance/cross-session -p 'test_*.py'
```
