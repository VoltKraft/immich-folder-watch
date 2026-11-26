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
