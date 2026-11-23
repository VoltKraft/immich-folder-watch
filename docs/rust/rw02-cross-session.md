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

At `3b4854d` both native hosts repeated the elevated lock sequence and
verified its cleanup. On each host Secondary Logon was initially stopped
with manual startup, ran for the tests, and returned to the original stopped
state with the same startup type. In both sessions on both hosts the
system query failed to confirm Basic User. Neither standard-user participant
launched. The original receipt kept only the result of combining the
command exit code and the advertised level check. The current observer
records the exit code, numeric level codes, output byte count and SHA-256
individually. The already-logged-on ordinary-user route below remains
available on a disposable VM.

| Early writer archive | ZIP SHA-256 | Indexed files verified |
| --- | --- | ---: |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/artifacts/14761630150) | `63e8cc2212ee5452caad334cff4b1b742c2b7a9306e6d981b421256b57860b05` | 37 |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/artifacts/14761152466) | `5849a2df9e81cc26cf37f7fcfa15195dcc0717cd1111166fa71fb26c6bba2550` | 37 |

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

## Trust-level query on the hosted machines

At `0a2b5ca` the original and scheduled sessions on each Windows
architecture reached the running Secondary Logon service. All four
`runas /showtrustlevels` calls returned zero with a zero-byte output pipe.
The standard-user participants never started. Both ambient guard sequences
passed. Each host restored Secondary Logon to its original stopped state
and manual start type. The x64 and ARM64 writer ZIPs have SHA-256
`05d3ec9ccc0aeb9d3b794122aed3b71123e200bd9a1a87f60fea525fab6b3cc6` and
`6e35af637ae38cadbb5a22e1717fa89120493437eb0e9564ea606bee9776ef40`.
The independent two-host readback has SHA-256
`5067eb43c001a4aa85e383bb42c98ebd0b681ce55d70fbae0dc60e708f9fb728`.
[Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235).

The hosted fixture now repeats just that successful empty query on a new
hidden console. Windows documents separate behavior for console handles
and redirected pipes. The query helper requires a blank screen and verifies
it is the sole attached process before and after the fixed system utility
runs. Its bounded screen read returns the utility's actual status and
UTF-16 text. The receipt preserves the original pipe observation and the
private screen's exact UTF-16LE bytes in `screenUtf16LeBase64` for replay.
Only an explicit listed Basic User level can
start the existing standard-user trial. Its two participants and every
writer still have their actual authority checked. Twenty-four portable
tests passed, including the two-process Unix rehearsal and five private
console controls. Seven simulated service lifecycle cases passed in
PowerShell 7.7.0. Native execution of the private console query is pending.
[Private query](../../tools/rust-qa/instance/cross-session/console_levels.py)
· [Windows console handles](https://learn.microsoft.com/en-us/windows/console/console-handles)
· [Windows console screen-buffer read](https://learn.microsoft.com/en-us/windows/console/readconsoleoutputcharacter).

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

## Task cleanup after a normal instance exit

During x64 cleanup at `93ecc35` the Scheduler returned
`SCHED_E_TASK_NOT_RUNNING` (`0x8004130B`). The archived exception identifies
the cleanup block. The separate verification pass found the owned
registration, removed it and verified that it was gone. The first pass now
handles an enumerated member exiting before its identity or stop is read. A fresh enumeration must
find zero running instances. A different instance, a different HRESULT
or a still-running instance fails the check. Registration ownership,
the bounded wait and final removal readback are checked separately.
Six portable PowerShell controls cover ordinary stop, disappearance
during enumeration or stop, surviving members, access denial and a
different instance. [Task Scheduler error codes](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-error-and-success-constants)
· [Regression controls](../../tools/rust-qa/instance/cross-session/test_scheduler_cleanup.ps1).

## Hosted private-console and lock results at 93ecc35

Both native Windows hosts passed the elevated writer handover at
`93ecc354f9be40ad0c76e33c46bdadb55f2e2fb8`. The standard-user handover remains
open. On each host the original participant in session 2 and the scheduled
participant in session 0 had the same account SID. Both reported elevated Default
primary tokens at High integrity. The controller verified each of five Rust
writers before its first thread resumed. Their PID, process creation time, token
and session matched the independent participant receipts. Across eight ordered
events, each side held the original guard file and refused its peer while it held
the lock. The original side reacquired and released the same file after its peer
exited. [Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235).

All four redirected trust-level queries again exited zero and returned zero bytes.
This time the original session on each host also recorded 280 UTF-16LE bytes in
its private console. Both captures listed `0x20000 (Basic User)` and had SHA-256
`6d1f89626bf104dceb243134d5b5359d115891768722aa3753685ca8e7423ace`.
The fixed Basic User action then returned 1 in both original sessions. The receipt
records only the action's exit code, leaving the reason unknown. Each scheduled
console helper saw the controller's abort marker and exited 1 before the system
query, with an empty screen and a diagnostic on stderr. Both standard-user trials
ended before a participant or writer started. The documented test in two already
logged-on ordinary sessions can exercise the outstanding handover.
[Prior pipe evidence](#trust-level-query-on-the-hosted-machines) · [Private-console reader at the measured revision](https://github.com/VoltKraft/immich-folder-watch/blob/93ecc354f9be40ad0c76e33c46bdadb55f2e2fb8/tools/rust-qa/instance/cross-session/worker.py).

Both jobs verified seven process exits for the elevated trial and two bootstrap
exits for the standard-user trial. Both removed the tasks, both synthetic profiles
and the shared build directory. The account's observed batch-logon assignments
matched before and after. Secondary Logon returned from Running to its initial
Stopped state with Manual startup. On x64, the standard trial's first cleanup
reported `0x8004130B` (no running instance) and left its task registered. The
separate cleanup pass checked ownership, recovered the registration and verified
its removal. ARM64 verified removal on the first pass. The x64 log identifies
the cleanup handler. Its per-instance enumeration, identity check and stop can
race normal process exit. A focused fix can accept that specific HRESULT after a
fresh enumeration confirms the owned instance is gone, then keep the existing
checks for all process exits, task deletion and absence. [Scheduler cleanup at the measured revision](https://github.com/VoltKraft/immich-folder-watch/blob/93ecc354f9be40ad0c76e33c46bdadb55f2e2fb8/tools/rust-qa/instance/cross-session/scheduler.ps1#L114-L146).

Each downloaded archive matched its Actions digest. The independent readback
verified all 37 indexed files per host, the native and observer inputs against
20 source hashes per target, and all four private-console returns against their
byte counts and digests. The combined `writer-raw-readback.json` beside the job ZIPs
has SHA-256 `b249389c3c275697ba7ecca565c05c59acd362b6baf66d8bd1d511225035994d`.

| Target | Writer ZIP SHA-256 | Evidence index SHA-256 |
| --- | --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14778841782) | `dbdc6535df3775f20d3bba300a3ce8f90a85bf18b3bcfecd4ee7679e8cac19c2` | `72df5c7d667641e0138e4aab0b858f176003c9ff0e70948dca189a14d1854baf` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14778658716) | `5d414bc903795abd7508802e0a912decc1d579e872e0c1e849d641665709a5ab` | `71311eb3abae34999bf62be7d976585e258e673f7e69b3a953fe6b58ee16cfe4` |

## Native writer and scheduler cleanup at 1e58541

On each Windows architecture the original and scheduled participants again
demonstrated all eight guard events in elevated sessions 2 and 0 of the same
account. The controller observed five distinct writers and verified seven
process exits. Both hosts removed the disposable profiles and tasks. The x64
instance exited during the scheduler's stop operation. The updated cleanup
confirmed its absence and returned zero. ARM64 found the task already
finished. [x64 writer archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14794934085) · [ARM64 writer archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14795496216).

The separate ordinary-user prerequisites produced three private consoles
advertising `0x20000 (Basic User)`, both x64 participants and the original
ARM64 participant. Each fixed launch returned 1. The scheduled ARM64 query
stopped after its peer's refusal. No standard-user writer started on either
host. The checked run in two existing, ordinary sessions is still needed.
Independent replay matched each archive to the Actions digest, all 37 indexed
files per host, 23 source inputs and the private-console bytes. The combined
`writer-raw-readback.json` has SHA-256
`aaa7b803f2f6024bea9f5b79b8900ca607d3ecc04161865d752d2b760eeac4a1`.
[Two-session procedure](#native-reproduction).
