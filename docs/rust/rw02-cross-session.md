# RW-02 same-account writer ownership across Windows sessions

The Windows feasibility probe runs the existing Rust `writer` on a local file shared by two processes with the same Windows account SID and distinct OS session IDs. Its second session uses an on-demand Task Scheduler S4U logon. Both directions have to reject a contender while the other session holds the guard. The replacement must then acquire and release the same file. The existing same-session old/new activation and installation evidence remain separate. [Native instance assessment](rw02-instance.md)

## Native reproduction

Run the following in the disposable `rewrite/rust` Windows x64 and ARM64 jobs with the repository's pinned Rust compiler and .NET SDK already installed. The Python fixture uses the existing `build` and `Child` functions. The only .NET invocation after building the source-pinned oracle is its identity operation. All writer processes use the same native Rust executable, which opens a pre-existing guard file and calls `File::try_lock`. [Instance builder](../../tools/rust-qa/instance/run.py) and [Rust file guard](../../tools/rust-qa/instance/main.rs)

```bash
python3 tools/rust-qa/instance/cross-session/observe.py "$NATIVE_TARGET" \
  --output "artifacts/rust/instance-native/$NATIVE_TARGET/cross-session"
```

The controller creates a unique marked directory under `RUNNER_TEMP`, a synthetic profile and one empty guard. It records the volume and file ID. It reads the current token's SID and session, checks the native SDK oracle's account identity, and checks current-account batch logon rights through a local read-only LSA policy handle. The account must already have an effective allow assignment and no applicable deny assignment. The fixture records whether the assignment comes from the account or its current token groups, and checks it again after unregistering the task. [Microsoft batch logon policy](https://learn.microsoft.com/en-us/windows/security/threat-protection/security-policy-settings/log-on-as-a-batch-job) and [account rights](https://learn.microsoft.com/en-us/windows/win32/secauthz/account-rights-constants)

The local task has one fixed action, a random single-use name, zero triggers, `TASK_LOGON_S4U`, `TASK_RUNLEVEL_LUA`, the current SID and a three-minute execution limit. The launcher gets the Python executable from the live controller and supplies the checked-in worker and the marked directory as its only action arguments. Registration uses create-only semantics. The supervisor reads back the principal, logon type, privilege level, action and trigger count before starting the task. S4U supplies a noninteractive session without a stored password. The worker checks its actual token elevation before starting a Rust writer. [Microsoft Principal.LogonType](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype), [Principal.RunLevel](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-runlevel) and [registration semantics](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertaskdefinition)

## Observations required for a pass

| Order | Controller session | S4U session |
| --- | --- | --- |
| 1 | First Rust process reports `WRITER_HELD` | Worker proves the same SID, a different session, a non-elevated token, matching guard ID and executable hash |
| 2 | Holder remains open while the controller checks the live worker process | A Rust contender reports `WRITER_BUSY` and exits successfully |
| 3 | Holder reports `WRITER_RELEASED` and exits | Replacement reports `WRITER_HELD` |
| 4 | Controller reads the live replacement's token, image and session. A Rust contender reports `WRITER_BUSY` and exits | Replacement keeps the lock through the inverse check |
| 5 | A fresh original-session writer reacquires and releases the guard with the original file identity | Replacement reports `WRITER_RELEASED` and exits |

The process session returned by `ProcessIdToSessionId` must match `TokenSessionId`. The receipt records the SHA-256 of each observed SID. The controller independently inspects the live scheduled worker and native holder. The scheduled worker forwards only the four public hosted rewrite identifiers required by the existing Rust guard. It checks the source-built executable's SHA-256 before use. There is no legacy listener, activation endpoint, media access or credential input in this probe. [Microsoft ProcessIdToSessionId](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-processidtosessionid)

Private state files coordinate bounded waits. On failure the controller signals the worker to stop. The task supervisor stops only its own instance when needed, removes the definition and verifies its absence. A second local Task Scheduler connection independently checks the exact name and can clean up an interrupted matching definition. A pass requires task exit code zero, removal readback, unchanged observed batch rights and deletion of the marked directory. The published result contains build and source hashes, session IDs, process identity evidence and the file ID. The worker and scheduler retain separate receipts. The transient manifest containing the raw SID is removed with the profile.

## Validation boundary

The pinned native Linux compiler `1.100.0 (0ef1bc386)` built the same Rust source. Two processes of the same UID in different real POSIX sessions rejected both contenders and completed orderly handover and reacquisition on one file. Five local regression tests passed, including the live Linux rehearsal, a wrong account, equal session IDs and an elevated worker. PowerShell 7.7 parsed the scheduling script. Native Windows verification depends on separate x64 and ARM64 hosted execution with the documented account privileges. By design, an S4U run exercises a batch session. Console-to-RDP behavior, two independently logged-on interactive desktops, and prevention of a shipping .NET writer restarting during an installed handover have their own prerequisites.

```bash
python3 -B -m unittest discover -s tools/rust-qa/instance/cross-session -p 'test_*.py'
```
