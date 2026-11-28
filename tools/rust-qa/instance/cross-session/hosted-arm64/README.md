# Windows ARM64 standard-user writer trial

The dedicated Windows 11 ARM64 job exercises a new local standard account on the disposable runner. One authenticated Secondary Logon process runs from the runner's original nonzero session. The provisioning host registers a single, on-demand task for that same ordinary user. Task Scheduler authenticates its batch logon in session 0. Both participants read their own Windows logon type and authentication ID, WTS session ID, process session ID and primary token. This measures local cross-session file exclusion. Interactive console/RDP and installed MSI handover have separate evidence. [Workflow](../../../../../.github/workflows/rust-windows-arm64-writer.yaml) · [Original guard protocol](../../../../../docs/rust/rw02-cross-session.md) · [Microsoft logon API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw) · [Task Scheduler security contexts](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks)

The controller verifies the original native compiler archive from run `46062734833`, revision `1c9a7ee6388450a0bcbf9afa947ea4138a6441df`, against Actions SHA-256 `90df61bc32fa397958a5d91ad7a586e0dcbcba6c2544b668f295a9f4caf5680c` and the current source tree. Its ARM64 Rust writer and managed identity oracle run with synthetic files. Five distinct native writers must produce the eight ordered hold, refusal, release and reacquisition events on the same file ID. [Compiler archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46062734833/artifacts/15229492640)

The fixture generates the temporary account's password in a job-local SecureString. The host supplies it directly to the Windows process credentials API and the local Task Scheduler registration method. Both task and process run with the ordinary user's privileges. Only SYSTEM and local administrators can manage the private task folder. The broker verifies those trustees, checks the fixed action and least-privileged principal, then removes the registration and folder after the task exits. A temporary assignment of the batch-logon right is scoped to the newly created SID.

The Actions job evaluates the native writer and host cleanup in separate steps after the observation. The cleanup check requires removal of the temporary account, its Windows profile and directory, the scheduled task, private task folder and staging directory. It also requires that the processes exited, the original rights were restored and Secondary Logon returned to its original state. Either check can fail the job. A push changing a native fixture or compiler input starts the branch job. The workflow also accepts manual dispatch on the rewrite branch.

Verify the observation ZIP against its Actions artifact digest before extracting it. The two commands below replay its compiler ZIP, source hashes, native process events and host cleanup receipts using a checkout containing the measured commit and the same compiler inputs. Omitting `--check` runs both checks.

```sh
python3 -IB tools/rust-qa/instance/cross-session/hosted-arm64/replay.py /path/to/extracted-observation --check functional
python3 -IB tools/rust-qa/instance/cross-session/hosted-arm64/replay.py /path/to/extracted-observation --check cleanup
```

## First measured standard-user handover

At `b0fb23c`, Windows authenticated the same ordinary account in WTS session 2 (interactive logon type 2) and WTS session 0 (batch logon type 4). Their authentication IDs differed. All five original Rust processes ran at Medium integrity with zero enabled administrative groups and zero privileges outside the standard set. The C# oracle returned the same account SID. The original holder, PID 11088, excluded PID 10652 in session 0. After release, PID 8388 acquired the same guard and excluded PID 1132 in session 2. PID 8200 then reacquired and released it. The eight events identify volume `3207815611366447378`, file `281474977630089`. Both roles exited successfully and the controller verified all seven participant and writer exits. [Original run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46120848285)

The job failed its separate profile cleanup check. Windows still reported the temporary account's profile as loaded or special after the 20-second wait. The original receipt combined those two states. The scheduler task, private task folder, temporary account, batch right and staging directory were removed and Secondary Logon returned to its original state. The archive SHA-256 is `86b74a37645895673479dccd608c1dd8cd8283d7e890a3ce060bd58df26721bd`. Independent readback verified the nine compiler sources, 26 staged sources, both token observations and every event. [Original archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46120848285/artifacts/15253491948)

The earlier self-registration attempt returned `0x80070005` when the standard account called `RegisterTaskDefinition` for its own S4U task, including in a dedicated task folder. The authenticated task above was registered by the fixture administrator for the new ordinary account. [S4U observation](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46120216250)

## Repeated handover and retained Windows profile

At `8505dad`, the same ordinary account again used two distinct authenticated logons, with interactive type 2 in WTS session 2 and batch type 4 in WTS session 0. The five ARM64 writer processes matched the C# identity oracle and had Medium integrity, zero enabled administrative groups and zero privileges outside the standard set. All eight events refer to volume `3207815611366447378`, file `281474977630190`. [Original run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46121262901)

| WTS session and holder | Other session | Result |
| --- | --- | --- |
| 2, PID 7588 | 0, PID 6072 | The second writer observed a busy guard. PID 7588 released it. |
| 0, PID 8412 | 2, PID 10492 | The first handover succeeded. The contender observed a busy guard. PID 8412 released it. |
| 2, PID 11092 | | The final writer reacquired and released the same file. |

The ordinary controller and scheduler task both exited with code zero. The controller verified all seven participant and writer exits and removed the synthetic guard directory. The host removed the task, task folder and temporary local account, restored the batch right and restored Secondary Logon. It observed the Windows account profile for 720 seconds. Every sample reported `Loaded=true`, `Special=false`, and a null `RefCount`. The profile registration and its directory still existed at the final check. The host removed the staging directory and reported the profile cleanup failure. [Original archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46121262901/artifacts/15254108999)

The interactive launcher explicitly sets `LoadUserProfile=false`. The fixture supplies the writer and oracle with a synthetic home and releases the broker's Scheduler references before checking the profile. The observer did not trace the component that loaded the Windows profile or identify its last reference. Cleanup of that profile remains open. [Broker](run.ps1) · [Subject environment](../fixture.py)

The second observation archive has SHA-256 `cd6b331f56b773c06b92f07b03e868ccd361e6da7e5dce62800aff566c78d902`. Local replay of both original observation archives verified the nine compiler inputs, all 26 staged sources, both standard-user tokens and all eight native lock events in each run. For each archive, the functional check returned zero and the cleanup check returned one. The first archive has no independent profile-directory observation. The second records that directory as still present.
