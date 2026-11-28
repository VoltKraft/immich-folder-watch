# RW-02 same-account writer ownership across Windows sessions

The [Server 2025 x64 console and RDP trial](#standard-user-console-and-rdp-handover-on-windows-server-2025-x64)
passed under an ordinary account. The corresponding ARM64 result remains open.
The [installed 3.0.4 comparison](#installed-304-worker-in-another-session)
found that admission also depends on which version starts first.

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

For the standard-user trial each primary token must report no elevation, default or limited elevation type, no enabled local administrative/operator aliases, no application capabilities or UIAccess, and integrity at or below Medium. The privilege inventory must fit the ordinary-user set, including disabled privileges. A participant meeting these checks can run the fixed test directly. If a hosted bootstrap has administrative authority, it records its original token facts. It can invoke the system `runas.exe` with the listed Basic User level `0x20000` and the exact hashed Python image and script for its role. This requires an already-running Secondary Logon service. A refused launch or insufficient effective token preserves its reason in the raw evidence. The test uses existing account and service settings. [Fixed participant](../../tools/rust-qa/instance/cross-session/worker.py) · [Mandatory integrity](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control) · [Windows Runas](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2012-r2-and-2012/cc771525%28v%3Dws.11%29)

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

A separate test uses two **already logged-on standard sessions of the same account** on a disposable Windows VM. Prepare a new shared local scratch directory accessible to that account in both sessions. Its marker `.ifw-existing-session-test` contains exactly the UTF-8 text `Immich Folder Watch isolated Windows test VM; synthetic data only` followed by LF. The two shells use the same checkout, Python executable and native target. Run the controller first, then give its printed unique directory to the peer within 110 seconds. Both validate their existing console or RDP session through Windows Terminal Services. The controller reads back the second connection state and protocol. This mode uses no scheduled task or alternative launch, and records its origin as `existing-standard-sessions`. The local controller identifies its environment explicitly. Only the file-only Rust writer and read-only managed SID query accept the local mode. The legacy activation endpoints require the hosted rewrite environment. [Two-session runner](../../tools/rust-qa/instance/cross-session/existing.py)

```powershell
python tools/rust-qa/instance/cross-session/existing.py controller x86_64-pc-windows-msvc $MarkedVmScratch
python tools/rust-qa/instance/cross-session/existing.py peer x86_64-pc-windows-msvc $PrintedFixtureDirectory
```

The native feasibility job retains the Windows build it actually exercised
with the legacy coordinator. A VM with the matching native .NET 10 runtime
and Python can reuse that build. Supply the original Actions artifact ZIP
and its published SHA-256 to the controller. The loader verifies the build
against the local source checkout, target and original coordinator, including
the managed runtime configuration. The peer uses the controller's staged
writer. A native compile on the VM remains available with the original
command. Both routes require the two independently logged-on sessions.

```powershell
python tools/rust-qa/instance/cross-session/existing.py controller x86_64-pc-windows-msvc $MarkedVmScratch --native-archive $WriterZip --archive-sha256 $ActionsDigest
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

At `6af7100` both hosts again excluded a competing writer and reacquired
the original guard in elevated sessions 2 and 0 of one account. Each
original console advertised Basic User. The launch returned 1 and the
scheduled peer stopped before its own trust-level query. Both hosts
confirmed task and profile cleanup. The independent readback of all 37
indexed files and 23 source inputs per host has SHA-256
`1257850dc5935a1a061c8aecca59e5e0648d355d56d2dd584525c7c297f5610d`.
The two-session standard-user case remains open.
[x64 writer archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14802979009)
· [ARM64 writer archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14804440869).

At `8566f81` each original session again saw Basic User in the 280-byte
listing. Its single fixed launch returned exit code 1. In both scheduled
sessions the controller stopped the trial before the launch. All 39 files
in each early archive matched the full desktop archive. Only the earlier
list command's output was preserved. The utility's exit code gives no
specific reason for the refusal. The observer now records the byte count
and SHA-256 of the same launch's combined output, plus its first 4 KiB in
Base64. An empty pipe and a truncated message have distinct receipts.
[x64 writer](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14809952468) · [ARM64 writer](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14810906705).

At `1b95ba0` the original launch again returned 1 on both architectures.
The new recorder captured zero output bytes on each host. Both digests
matched the empty byte string and neither capture was truncated. The
original records therefore supply no more specific failure reason. No
standard-session writer started. The elevated control recorded all eight
events and removed its synthetic resources on both hosts. Replay verified
37 evidence files and 23 source inputs per target. Its SHA-256 is
`66188c5cb5311983f19d80ec18b7d4d4e67f62f4af6155bad020dd66277bb50c`.
The ordinary-user handover still requires two existing sessions of the
same account on a disposable Windows host.
[x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14836851751) · [ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14836122324).

## Basic User launch on a private console

At `e796d30` both original sessions again reported the Basic User level on
their private consoles. Each screen contained 280 UTF-16LE bytes with SHA-256
`6d1f89626bf104dceb243134d5b5359d115891768722aa3753685ca8e7423ace`.
The subsequent detached launch returned 1 on each host, with zero bytes on its
combined output pipe. Both ambient writer trials passed. The cause of the
ordinary launch refusal remains unknown.

| Target | Original Basic User receipt SHA-256 |
| --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14874798632) | `c94e451bb0b91fe5afdbb9c12e92d86796276a81bd4f7547e9e57242da04b79f` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14873982830) | `f6285eb76e7ea40d8bc58ee646e90a2bf354589d2fff5e6eecc68ebfb39ad96c` |

After confirming the level, the hosted trial now executes the same-account
form `runas /trustlevel:0x20000 <fixed participant>` once per role. The
helper checks its bootstrap's live PID, creation time, image and session
against the original receipt and rechecks the system utility's digest. It
opens the fresh hidden console's own input and output handles, checks that
the screen is blank and claims the role before starting the utility. It reads
the screen only while it is the sole attached process. A participant that
inherits the console can finish the guard exercise independently before that read.
[Microsoft's documented same-account launch](https://devblogs.microsoft.com/premier-developer/how-to-force-vista-to-not-elevate-an-application/)

Run the existing native hosted command above. For each attempted role its
`*-basic-user.json` records `launchSource`, `consoleHelperExit` and the
utility's own `launchExit` when available. The claim records that exit
before the screen read, including when the capture subsequently fails.
Cleanup verifies the console helper's PID and creation time along with the
other participants. The evidence includes the helper identity and the claim's
raw bytes, including an empty claim when the utility's exit is unknown.
Decode `launchScreenUtf16LeBase64` and compare its complete length and
SHA-256 with `launchOutput`. A helper error has its own diagnostic. The
controller must still verify the participants' actual rights, distinct
sessions, five writers, ordered guard events and cleanup before the
standard-user case can pass. The 29 portable writer tests include ten
console controls. Seven hosted-service and six scheduler cleanup controls
passed under PowerShell 7.7.0.

### Native Basic User console results at 13e4af8

Both Windows hosts ran the private-console launch at
`13e4af8f5e6826324afbb5de4d34aeb2ba6a27fb`. On each host the original
bootstrap ran in session 2 and the scheduled bootstrap in session 0.
They shared the account SID and had elevated Default primary tokens at
High integrity. Each private console listed `0x20000 (Basic User)` in the
same 280 UTF-16LE bytes. All four fixed launches returned exit 0 from
both `runas.exe` and the console helper. Each raw launch claim independently
recorded that exit. The four launch screens contained zero bytes and supplied
no Windows error code or diagnostic. [Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847).

Neither role produced an ordinary participant's attempt, readiness or
completion receipt on either host. The controller timed out after 110 seconds
waiting for `original-ready.json`. Cleanup reported
`The named Basic User action has no verifiable shutdown receipt`. Both
standard-user profiles were retained. The scheduler removed both task
registrations on each host, the shared build was removed, batch-logon assignments
were unchanged and Secondary Logon returned to Stopped with Manual startup.
The records establish neither the cause of the missing participant nor its
authority or exit. The standard-user handover remains open.

The separate elevated trial passed on both hosts. Five identified Rust
writers per host produced all eight ordered lock events against the original
file. Independent replay matched each ZIP's Actions digest, all 41 indexed
member hashes and 23 source hashes to the measured revision and pinned
reference. The replay at `artifacts/rust/hosted-writer/45476186847/replay.json`
has SHA-256 `e206e1c3a63b58f16b670b24f850ddb98602091e45f31f453cc3b1af5de6d420`.

| Original writer archive | ZIP SHA-256 |
| --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14965426353) | `d0a944240bac0f67e11a52f857654f927174e726d5000e7728700b80ef7f45b4` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14964748110) | `7073381142cc72bd54948cd1d6ac37f31ca6909c363ea11014a46afb819beb21` |

## Standard-user console and RDP handover on Windows Server 2025 x64

On November 27, 2026, the same ordinary account held two active sessions in
a disposable Server 2025 x64 guest. Windows Terminal Services reported
session 1 on the console (protocol 0) and session 2 over RDP (protocol 2).
The controller independently identified each suspended native writer before
letting it run. All five had the same account SID, a non-elevated primary
token at Medium integrity, zero enabled administrative groups, zero
privileges outside the ordinary set, zero capabilities and no UIAccess.

| Order | Console session 1 | RDP session 2 |
| --- | --- | --- |
| 1–3 | PID 4116 acquired the file and released it after the refusal | PID 8404 received `WRITER_BUSY` |
| 4–6 | PID 576 received `WRITER_BUSY` | PID 5536 acquired the file and released it after the refusal |
| 7–8 | A new PID 2068 acquired and released the file | |

All eight events identified the same volume `13001045781266693700` and
file `844424930293195`. Each exit succeeded. The controller verified
participant exit and removed the synthetic profile. The five processes ran
the same Rust file-lock probe. The C# oracle ran its read-only `identity`
command and returned the Windows account SID. Installed legacy/candidate
handover and the ARM64 standard-user guard retain their own acceptance
checks. [Rust writer](../../tools/rust-qa/instance/main.rs) ·
[C# oracle](../../tools/rust-qa/instance/Program.cs) ·
[Installed handover observations](rw02-instance.md)

### Repeating the x64 run

1. Use a disposable Server 2025 Desktop Experience guest with RDP enabled
   for the synthetic ordinary account. In the guest copy, set the Remote
   Desktop Session Host policy **Restrict Remote Desktop Services users to a
   single Remote Desktop Services session** to Disabled. Sign in as that
   account on the console and over RDP. Run `query user` and confirm two
   distinct, active session IDs for the same account.
2. Use the source checkout at `c1867dbecad51fc69a07649259b5331293d98596`
   with unmodified source bytes in both sessions. Put the same native Python
   and Microsoft x64 .NET 10 runtime on the path in both. The trial verified
   the 10.0.12 runtime ZIP against Microsoft's SHA-512. Preserve the original
   x64 ZIP from Actions run `46062734833` at
   `1c9a7ee6388450a0bcbf9afa947ea4138a6441df`. Its SHA-256 was
   `e432f3837570752f9806891195def9e88bc0befef82375a1327953d3a403bf95`.
   [Native writer artifact](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46062734833/artifacts/15230355213)
3. From the standard-user console, create a fresh test directory as shown
   below. Set `$WriterZip` to the original ZIP's local path and run the
   archived-build controller command above with the Actions digest.
   From the RDP session run the peer command with the printed directory.

```powershell
$MarkedVmScratch = Join-Path $env:LOCALAPPDATA ("IfwWriter-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory $MarkedVmScratch | Out-Null
$marker = Join-Path $MarkedVmScratch ".ifw-existing-session-test"
[IO.File]::WriteAllBytes($marker, [Text.Encoding]::UTF8.GetBytes("Immich Folder Watch isolated Windows test VM; synthetic data only`n"))
$ActionsDigest = "e432f3837570752f9806891195def9e88bc0befef82375a1327953d3a403bf95"
```

The first attempt stopped before `WRITER_HELD`. The harness had dropped the
local fixture flag from the child environment. At `c1867db` it forwards the
selected fixture identity and retains both participants' completion records.
The retry used the original Rust binary and oracle. All 33 portable
cross-session tests passed. An independent replay checked four native files,
nine native source files, eleven observer source files and all seven indexed
guest observations. The local evidence directory
`artifacts/rust/local-windows-server-2025-x64/20261127/writer-c1867db/`
contains both attempts, the original build ZIP, guest session receipts and
`replay.py`. Run the replay from the repository root.

| Successful run | SHA-256 |
| --- | --- |
| Original observation ZIP | `bea955d0b5fc9c60afc84723c728020fccfbbed624e1daebc3e1d03fd1b1a94f` |
| Guest `result.json` | `fffc44bd377fce4c996ed4e49d92a2d00de057a2ae41dee1bbb15357836b968c` |
| Independent `replay.json` | `e490c9afa9d4e17251d36a82a37d48adf343602f99b636f16c932308eb6fd517` |

## Installed 3.0.4 worker in another session

On November 27–28, 2026, the original 3.0.4 x64 MSI ran on a local Windows
Server 2025 VM. The same ordinary user had an active console (session 3)
and RDP desktop (session 2). WTS confirmed both desktops and each process
token confirmed the SID, session, medium integrity and ordinary privileges.
The MSI SHA-256 was
`419938c3fec0c113bf0f33dbf1a9bd4a6748df1e7930acb20fec5fc3f265a187`.
The installed executable SHA-256 was
`b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675`.
The native Rust probe used the shared GUI admission functions. An
administrator provisioned the synthetic VM. Both applications ran as
the test user. [Shared admission code](../../tools/rust-qa/gui/src/win32_instance.rs)
· [Native probe](../../tools/rust-qa/instance/cross-session/msi_endpoint.rs).

| First process | Observed outcome |
| --- | --- |
| Rust in the console | Rust PID 4488 owned the admission endpoint and Rust PID 8388 held the separate writer guard. While both were alive, the installed WPF process in RDP (PID 6808) uploaded the synthetic PNG. The loopback peer returned HTTP 201 and the installed worker committed the matching SQLite row. |
| Installed WPF in RDP | During the original WPF upload, the Rust process in the console (PID 9136) observed Win32 error 231 (`ERROR_PIPE_BUSY`). Windows identified the existing pipe server as PID 8728, the installed process which owned the active upload. That worker completed the request and committed the matching row. |

The detached readback decoded the native TCP owner rows, parsed the original
multipart bodies, verified the 69-byte PNG, and reopened each captured
SQLite database with its original WAL. It matched the MSI installer log,
observer sources and native executables to each archive. The initial WPF-first
observer stopped when it encountered error 231. The repeat also checked the
existing server PID before accepting that result.
[Observer](../../tools/rust-qa/instance/cross-session/msi_sessions.py)
· [Detached readback](../../tools/rust-qa/instance/cross-session/replay_msi_sessions.py).

| Launch order | Original native compiler ZIP SHA-256 | Original VM observation ZIP SHA-256 |
| --- | --- | --- |
| Rust first | [`f14e064f7246e5e386dc2b4d0d793ea80f28e5293d5f90445d6dc3b967b6b31d`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46066266349/artifacts/15230643789) | `88595311660227babaa15d749288ab91a917d75e34ccdb544279d3b1909611c6` |
| WPF first | [`c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46096614452/artifacts/15242684323) | `080b802b519132f1da1fe526d6f77f68502873277df8b542a39cd3310ca9b424` |

To verify the preserved evidence, run these commands from the rewrite checkout.
The original ZIPs retain their Windows member paths. The verifier reads
them directly and writes its report to standard output.

```bash
qa=tools/rust-qa/instance/cross-session
base=artifacts/rust/local-windows-server-2025-x64
first=$base/20261127/msi-cross-session
second=$base/20261128/msi-cross-session
python3 "$qa/replay_msi_sessions.py" "$first/initial-observations.zip" "$first/endpoint.zip" \
  f14e064f7246e5e386dc2b4d0d793ea80f28e5293d5f90445d6dc3b967b6b31d rust-first
python3 "$qa/replay_msi_sessions.py" "$second/first-config-observer/observations.zip" "$second/endpoint.zip" \
  c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf wpf-first
```

The shipping WPF executable decides primary ownership through a
session-local mutex. It starts its pipe listener and its host separately.
A new session can therefore pass the mutex check even while another
session owns the Rust endpoint. A migration which enables Rust sync for
an existing profile must first drain and close every old worker that can
use that profile. The installer must also complete the transactional
replacement of the old launch paths before enabling the new worker.
If either prerequisite cannot be confirmed, leave synchronization with
the existing installation and keep Rust sync disabled. Preserve the
user's configuration and database and verify a rollback with the
original installed worker. This is a proposed release gate. The two
process observations cover admission and the synthetic upload.
[Shipping coordinator](../../src/ImmichFolderWatch.App/Services/SingleInstanceCoordinator.cs)
· [WPF startup](../../src/ImmichFolderWatch.App/App.xaml.cs)
· [Installer upgrade and rollback contract](../../packaging/windows/README.md#upgrade-process-safety).

### An exclusive configuration handle during WPF startup

On November 28, 2026, a separate local test used the original installed
3.0.4 executable, the same x64 native compiler archive at `868739f`, and
the observer at `da25bf2`. The native probe opened the existing synthetic
`config.yaml` for reading with Windows share mode zero. It held the same
handle until the observer explicitly released it. Both participants used
ordinary tokens for the same account on active console 3 and RDP 5.
[Native handle](../../tools/rust-qa/instance/cross-session/msi_endpoint.rs)
· [Configured WPF comparison](../../tools/rust-qa/instance/cross-session/config_guard_msi.py).

| Phase | Observed outcome |
| --- | --- |
| Rust held the original config | Windows returned `ERROR_SHARING_VIOLATION` (32) for independent read and read/write opens. The installed WPF process (PID 1132) showed its normal window. Across 12.002 seconds after the window appeared, the peer received zero asset POSTs and the profile contained no sync database. |
| The Rust probe released the config | A fresh WPF process (PID 5540) on the same RDP desktop uploaded the original PNG to the same local peer. Its TCP owner, HTTP 201 response, exact multipart payload and one committed SQLite row matched. |

The 429-byte config retained volume ID `13001045781266693700`, file ID
`844424930294279`, and SHA-256
`d43d39ac31ab7e7bff00cfbd3ed904a5c5a6a11b1bd2cb2eeb43c3478db2e987`
before the native open, after release and after the positive control.
The initial observer stopped when the Python runtime returned only
`EACCES`. Another attempt timed out waiting for the next RDP login.
The recorded comparison used Win32 `CreateFileW` directly and waited for the
normal RDP startup hook. Both observers exited zero. The fixture ended only
its own identified WPF processes after preserving each observation.
After the evidence was copied and replayed, the guest shut down through
ACPI. The host confirmed the QEMU process had exited, the loopback RDP
port was closed, and the scratch disks had no open handles before disposal.

The guest archive SHA-256 is
`9e7c32042e40d162a89a4a442eaba9c98b2ed02ce3395edc1165fc4fa7f9ac01`.
The detached readback SHA-256 is
`3449724f36c3ace3364cfccceebab87c6422cd5746e9d7d122724a55be33244e`.
The pre-marker refusal came from the earlier run in this installation.
The readback checks the same original MSI log, ordinary account and native
binary across the two guest archives. Run it with the shell variables from
the previous command.

```bash
python3 "$qa/replay_msi_sessions.py" "$second/config-guard/guard4-observations.zip" "$second/endpoint.zip" \
  c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf config-only \
  --prior-unmarked "$second/first-config-observer/observations.zip"
```

The result applies to starting a new WPF process with an existing config.
The shipping code reads that file before it starts its host. A worker
which already loaded its configuration can keep running. Applying settings
also writes the file before restarting the worker. The comparison did not
exercise Apply, an absent config, or Rust's own atomic config replacement.
An exclusive handle also denies delete sharing, which an atomic replacement
of its path needs. Releasing that handle introduces a transition that this
test did not measure. Keep the installer and worker-drain gate above for
real profiles. [Shipping config reader](../../src/ImmichFolderWatch.Core/Configuration/AppConfigLoader.cs)
· [Shipping Apply path](../../src/ImmichFolderWatch.App.Shared/Services/ConfigApplyService.cs).

### Save and Apply on the installed WPF window while the config is held

On November 28, 2026, a local Windows Server 2025 x64 guest ran the
original 3.0.4 MSI application and the archived Rust config holder. Both
used ordinary tokens for the same account. The holder (PID 6284) ran in
console session 2. The installed WPF process (PID 3576, HWND 459362)
ran in RDP session 3. The observer at `92b26c2` followed its original
window, process creation time and Save and Apply button through both actions.
[Archived native holder](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46096614452/artifacts/15242684323)
· [WPF window observer](../../tools/rust-qa/instance/cross-session/apply_window.ps1)
· [Worker and local HTTPS peer](../../tools/rust-qa/instance/cross-session/apply_msi.py).

| Phase | Configuration, UI and worker observations |
| --- | --- |
| WPF started with the file held | WPF reported that it could not load `config.yaml` and opened defaults. The URL and key fields were empty. The observer entered a synthetic HTTPS endpoint, key and watch folder into that window. |
| Save and Apply with the file held | The peer saw an empty multipart permission check. WPF then reported that another process was using `config.yaml`. Win32 returned sharing violation 32 before and after an additional 12.002-second observation. During that interval the profile contained no sync database and the peer saw no image upload. Immediately after release, the original file still had the same volume, file ID, 416 bytes and SHA-256. |
| Save and Apply after the holder exited | The same button on the same HWND applied the draft successfully. The saved config grew to 1,519 bytes on the original file ID. A database appeared and the peer received the worker's initial Socket.IO polling requests. The observer then created the 69-byte PNG. Windows attributed its HTTPS connection to WPF PID 3576. The peer accepted the exact image with HTTP 201 and acknowledged album membership. The original SQLite database and WAL contained one matching row for `signed-worker.png`. |

The independently replayed evidence includes the two button invocations,
original config bytes, captured multipart bodies, Windows TCP owner row and
SQLite files. The guest ZIP SHA-256 is
`0ca760ea458162853fb8417bd07ac29f61d3f8693fe0438f7d31a15784238a61`.
The observer checkout SHA-256 is
`e798d92e70aea3c514f78a0cdb3cdf1046e2b61194be516838bae96a83622915`.
Run the replay from the repository root using the variables defined above.

```bash
apply=$base/20261128/msi-apply
python3 "$qa/replay_apply_msi.py" "$apply/apply-06.zip" "$second/endpoint.zip" \
  "$apply/checkout-06.zip" c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf
```

The replay JSON SHA-256 is
`14ed534c4bbb8d95fd001a4324a30172640f0bea4dc533fce77ccab1c1c9c64a`.
The guest removed its temporary loopback CA and test logon hook before
shutdown. The host confirmed that QEMU exited and the loopback RDP port
closed, then discarded the overlay. QMP reported 4 GiB of base memory
and zero hotplugged bytes. Admission of a previously running configured
worker, startup with an absent file and atomic config replacement remain
separate cases.

### Ordinary replacement of two Rust-owned config files on NTFS

On November 28, 2026, the native x64 probe built at `fa337fa` attempted
an atomic save with the ordinary Win32 `FileRenameInfo` operation. In a
fresh marked NTFS profile it created both `config.yaml` and
`.ifw-atomic-config.tmp` with `CREATE_NEW`. It wrote different fixed
83-byte YAML documents, flushed both and read each back from its original
handle. Both handles explicitly allowed delete sharing. An independent
ordinary process read each file's ID by name and received Windows
sharing violation 32 for each attempt to open either file for data reads
or writes. All components ran on the isolated x64 Windows Server 2025
console. [Native input and compiler receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46108513570/artifacts/15248398639)
· [Owned-file probe](../../tools/rust-qa/instance/cross-session/atomic_config.rs)
· [Win32 rename information](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info).

**The save failed.** Windows returned `ERROR_ACCESS_DENIED` (5). The
probe closed its handles. The independent observer at `e736a9a` then
reopened both original names on volume `13001045781266693700`,
confirmed their identities and archived their contents before removing
the synthetic profile.

| Name after the failed save | File ID before and after | SHA-256 of the original bytes recovered |
| --- | --- | --- |
| `config.yaml` | `281474976904777` | `9290676e2f5c40cb774b387a3401e748e827daf2203235f7aa3be1c126c85222` |
| `.ifw-atomic-config.tmp` | `281474976904778` | `7488fdeaf9744a2c50a3bc1ac0ef57fe0eec9006806c78e40b09b495582f6297` |

The guest returned the original ZIP through its serial port after Windows
could not find the dedicated result volume. Its SHA-256 is
`cc669cc8be349bea8b329d2eeee39177aa2b4b259f04466cafe6ef91c8044e4c`.
The replay checks the original AMD64 executable and source receipt,
ordinary process identities, the two native access results per filename,
the raw Windows file IDs and both complete YAML documents.

```bash
atomic=artifacts/rust/local-windows-server-2025-x64/20261128/atomic-fa337fa
python3 tools/rust-qa/instance/cross-session/replay_atomic_config.py \
  "$atomic/original-guest-results.zip" "$atomic/compiler.zip" "$atomic/checkout.zip" \
  c868e67350c4d3a75eca7c73483dbed9734631f212d7ec2d114f8474fc6522a6
```

The replay JSON SHA-256 is
`c9f55f37874a36d86cdb2eabb539df372bcb43bead50d96395ccc96e843e15a0`.
QMP recorded 4 GiB of base memory and zero hotplugged bytes. The guest
had no network adapter. After ACPI shutdown, the host confirmed that
QEMU had exited and the scratch files had no open handles before
discarding the overlay. A successful guarded atomic save remains open.

### Ordinary WPF shutdown before Rust writer admission

The separate `wpf-handover` trial uses the installed 3.0.4 application
on the local standard user's RDP desktop. During a synthetic upload the
Rust endpoint in the console must identify the WPF pipe owner and refuse
admission. After the upload commits, the observer selects Quit in the
original WPF menu. It checks the exit time and code of that process
before the Rust endpoint and writer acquire ownership. It retains the
config identity, the upload and the SQLite row across the handover.
The original two launch-order trials keep their own evidence.
[Native setup, compiler inputs and replay](../../tools/rust-qa/instance/cross-session/wpf-handover.md).

On the 4 GiB Server 2025 x64 guest at `bfd99b2`, Rust initially identified
the installed WPF uploader (PID 9076) as the occupied pipe's server.
The original worker uploaded one synthetic PNG and committed one SQLite
row. The ordinary tray Quit ended WPF with code 0. Rust then acquired the
endpoint in the console and took the writer guard. The original 441-byte
configuration retained its file ID and contents. WPF recorded shutdown and
the start of flushing. Its log contains no separate flush-complete event.
The independent replay used the 22 source hashes captured during the test
and three modules read from the same guest checkout afterwards.
[Guest ZIP, source supplement and replay](../../tools/rust-qa/instance/cross-session/wpf-handover.md#local-server-2025-handover-at-bfd99b2).
