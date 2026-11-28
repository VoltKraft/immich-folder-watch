# File tracing during the installed WPF secondary launch

Two Windows x64 runs reopened the original Rust window and reported both
inventory passes in the application log. The kernel file observer exited
with code 4. Its session reported 134 and 1,273 lost events, respectively,
zero lost log buffers, and 33 and 32 buffers written. Both sessions had 128
allocated 256 KiB buffers. These final counters leave the timing and source
of the losses unknown.
[First x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825893/job/140176006230).
[Second x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285022/job/140180800969).

The sparse x64 MSI observation selects the file observer's `msi-rust` mode.
It records a sequential ETL using the held worker's PID filter and an
independent session. This mode isolates event delivery from write failures
in another session receiving the same provider's events. After the second
inventory acknowledgment, the controller disables its own provider with a
five-second timeout. It reads the session counters while the buffers are
still live, then stops the session and decodes the finalized ETL.
[Windows logging modes](https://learn.microsoft.com/en-us/windows/win32/etw/logging-mode-constants).
[EnableTraceEx2](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-enabletraceex2).

The detached reader requires four ordered, zero-loss samples in `files.log`
covering attachment, both inventory passes, provider disable and session
stop. It checks the ProcessTrace return code and the finalized file
header's EventsLost and BuffersLost counts. The separate EventsLost
member of EVENT_TRACE_LOGFILEW is reserved and supplies no independent
loss measurement. For each pass the reader requires both the directory
enumeration and the completed file identity query for the original worker,
inside the challenge's recorded time bounds. The ordinary 100,000-file
trials and the ARM64 MSI observation use their existing recording mode.
[Windows ETL header fields](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-trace_logfile_header).

## Native Rust-primary results at 69b3ddd

On both architectures, a second launch of the installed WPF 3.0.4 executable
reopened the original Rust window. The original worker completed both file
queries after the reopen. Both Rust primaries exited with code 0 on Quit,
their jobs drained, and the recorded MSI, profile and scratch cleanup passed.
The detached reader at `69b3ddd5cc7048f209f8f0202d65dd3118d7cad0` verified
both archives after ZIP CRC and Actions SHA-256 checks.

| Original archive | ZIP SHA-256 |
| --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45902089309/artifacts/15157450469) | `7d050656a06ed04c0ccd79b4947575a80d144d67709a1d43e7e4ce6ebbc1e94d` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45902089309/artifacts/15157270904) | `5a0500abd16428f7d6aeb3a90c655ef655fd39cb1de986f7c6f2d78bcb67953b` |

On x64, WPF PID 8132 reopened HWND 524696. Worker PID 2540 completed its
file identity queries at QPC ticks 10830478626 and 10880582841. Its
independent ETW session reported zero lost events, log buffers and
real-time buffers at all four observations.

| x64 session phase | QPC ticks | Buffers allocated | Buffers written |
| --- | ---: | ---: | ---: |
| Attached, before the challenge | 10783408075 | 128 | 1 |
| Captured, after the second pass | 10880637124 | 128 | 43 |
| Provider disabled | 10880638495 | 128 | 43 |
| Session stopped | 10880671071 | 128 | 47 |

Provider disable and `ProcessTrace` both returned zero. The finalized ETL
header recorded zero lost events and zero lost buffers. This verifies one
loss-free x64 capture. The preceding x64 run also passed with the earlier
recorder. The cause of the two earlier losses remains unresolved.
[Preceding native comparison](../../../docs/rust/rw02-instance.md#installed-windows-activation-at-d7c084c).

On ARM64, WPF PID 2368 reopened HWND 197222. Worker PID 6652 completed its
file identity queries at QPC ticks 13455683555 and 13505799912. The ordinary
file observer emitted `COUNTS 8 76 0 0 0 0 0 0` and `COMPLETE`. The four
session samples above apply to the x64 run.
