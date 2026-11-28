# Windows WPF and Rust resource comparison

The recorder runs the shipping WPF entry point and the reviewed Rust GUI on
the same disposable Windows runner. It selects a self-contained Release build
from shipping revision `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`, with the
native runtime identifier and .NET SDK 10.0.401 used for that revision.
It verifies the 136 extracted reference files against source digest
`74f1702ebd09511da3b8853342a776a12f4c7f8b458a1dd2d0e066add75fce3d`
and records the source archive and the complete publish output by SHA-256.
The Rust executable must match the canonical GUI build receipt. The PE
headers and the actual processes must match the native target architecture.
The first native x64 comparison measured nine idle/startup metrics at
`8a8adaa`. Six passed. The visible working set was 177.00 MiB against a
143.18 MiB limit. Idle close and reopen took 139.33 and 217.50 ms at p95,
against limits of 14.79 and 14.76 ms. Visible and hidden CPU use and
presentation rates were zero. The hidden working set was 26.69 MiB.
The worker-integrated scan comparison is a separate native trial.
The ARM64 host also met six of nine limits. Its visible working set was
178.35 MiB against 146.62 MiB. Idle close and reopen took 135.77 and
192.82 ms against 13.12 and 13.52 ms. Its retained hidden working set was
26.84 MiB, with zero visible or hidden CPU and presents per second.
[Windows x64 run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642/job/136960549014)
and [Windows ARM64 run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642/job/136960549022).
[Shipping publish recipe](../../packaging/windows/build-msi.ps1) · [Desktop standard](../rust-desktop-standard.md).

## Completed paired inventories

The Windows x64 and ARM64 jobs in two subsequent runs completed all eleven metrics. Each host ran three WPF trials, three Rust trials that recreated the renderer, and three trials that retained the HWND and DX12 device. Replaying the 36 archived file-ETW logs against their recorded QPC request timelines recovered the same per-pass file counts, eligible requests, p95 values and WPF-derived thresholds. Each of the 72 passes saw all 100,000 distinct expected files. [Run 44950398558](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44950398558) · [Run 44953046306](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306).

Values below are the three-trial median of each first-pass p95 in milliseconds. The first value is close and the second is reopen.

| Run and architecture | WPF | WPF maximum | Rust, recreated device | Rust, retained device |
| --- | ---: | ---: | ---: | ---: |
| 44950398558 x64 | 13.75 / 9.13 | 23.75 / 19.13 | 99.36 / 171.86 | 35.85 / 65.78 |
| 44950398558 ARM64 | 4.57 / 5.59 | 14.57 / 15.59 | 224.47 / 176.15 | 20.85 / 4.56 |
| 44953046306 x64 | 16.49 / 10.15 | 26.49 / 20.15 | 107.73 / 196.85 | 42.59 / 65.56 |
| 44953046306 ARM64 | 4.08 / 5.24 | 14.08 / 15.24 | 209.13 / 163.74 | 17.98 / 4.11 |

The retained candidate met nine of eleven limits on x64 and ten on ARM64 in both runs. On x64 in run `44953046306`, the median individual reopen across each trial was 39.70–41.20 ms. On ARM64 the median individual close was 2.77–2.83 ms and its p95 reached 17.57–18.32 ms. Startup, idle transitions, both working sets, both CPU measurements and both idle presentation rates passed on both machines. The remaining regression concerns transitions during active inventory. [Window lifetime, memory and presentation comparison](rw02-windows-window.md).

| Downloaded desktop archive | SHA-256 |
| --- | --- |
| `44950398558/windows-x64.zip` | `c01bebb040e54f617098a76c7f4c8151503d8427ed841cff9405b7dc2c2cc257` |
| `44950398558/windows-arm64.zip` | `4d36f5aba113af7c32fb72d74b7ba145be147c851dd3cc0fa91bad6af6c844b6` |
| `44953046306/windows-x64.zip` | `6e4391e0eebe43292f538115201178642a8395fba1aaece3900733fa20387c17` |
| `44953046306/windows-arm64.zip` | `454cf16b2d6a637d0fcce5b20c9bb082bd3e7fcc68c052e2f951bd46be9455ca` |

## Worker-integrated Windows run

At `72fff407a964b9e28b16de45fb890018832ecb53`, each host completed
three WPF and three Rust startup/idle trials. Each passed six of nine
measured limits. The table gives the candidate and its frozen maximum.
The source input and reference-budget digests in both result archives
match the included files. [Native x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350/job/136971561540) · [Native ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350/job/136971561498)

| Native host | Visible working set, MiB | Idle close p95, ms | Idle reopen p95, ms | Reference-budget SHA-256 |
| --- | --- | --- | --- | --- |
| x64 | 190.191 / 142.107 | 66.274 / 14.383 | 174.066 / 18.337 | `3e1c65e20ce6eaca1f5b0ec30960316e48c296a021efeaa52770dee3b4633d05` |
| ARM64 | 193.258 / 147.506 | 134.435 / 13.236 | 182.427 / 14.999 | `819afe77d9a14202944bb590b762212dbce3b639828a567a2faabaef1c7d5a60` |

All twelve scan trials stopped before file tracing began. Windows SDK
10.0.26100.0 rejected the file observer's const handle pointer at
`ProcessTrace` with MSVC C2664 on both targets. Both scan entries in each
reference budget and candidate comparison remain null. The corrected
consumer uses a mutable `TRACEHANDLE`, matching the presentation observer
that compiled in each job. Replaying the original call against the SDK's
pointer signature also reproduced the qualifier error with a portable C++
compiler. The recorder now includes each unmeasured metric in its list of
outstanding evidence. A native run must still demonstrate the corrected
build and two complete inventories per subject in every trial.
[File consumer](../../tools/rust-qa/windows-inventory/file-observer.cpp) · [Microsoft ProcessTrace signature](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-processtrace)

The process-job and handle-bound NTFS lifecycle test passed on both
machines. On ARM64 a separate C++ ledger self-test returned successfully
and then failed cleanup when Windows twice refused to unlink the temporary
`ledger.exe` with error 5. The trace identifies the file and error but
leaves the reason for the refusal unknown. The revised test holds the
compiled image against replacement during execution. During cleanup it
uses a delete handle on the same volume/file ID in the pinned test directory,
retries Windows access and sharing errors for up to ten seconds, and requires
the name to disappear. A changed image, unexpected error or expired deadline
fails the test and preserves the private directory. This retry runs outside
the performance measurements. [Ledger test and cleanup controls](../../tools/rust-qa/windows-performance/test_recorder.py)

## Predeclared comparisons

Each subject runs three times. The WPF trials run first. The driver persists
the reference medians, thresholds and input digest before starting the first
Rust process. At the end it checks that the baseline file still has that SHA-256.
All three trials must provide a metric before it can enter a comparison.
The allowances follow the existing [Linux comparison](rw02-performance.md).

| Observed metric | Fixed allowance above the three-trial reference median |
| --- | --- |
| Process launch to first visible, caption-matched top-level HWND | Larger of 20% and 10 ms |
| Visible / hidden process CPU, percentage of one core | Larger of 20% and 1 percentage point |
| Visible / hidden median process working set, MiB | Larger of 10% and 4 MiB |
| Close to hidden / activate to visible while idle, nearest-rank p95 of eight cycles in each trial | Larger of 20% and 10 ms |
| Close to hidden / activate to visible during the first 100,000-file inventory, nearest-rank p95 per trial | Larger of 20% and 10 ms |
| Visible / hidden successful presentation calls per second | One additional present in a 15-second interval |

The driver observes actual HWND visibility by PID and caption. It posts
`WM_CLOSE` to the owned window. Reopening sends the shipping coordinator's
`SHOW_GUI` on its SID-scoped named pipe after verifying its server PID.
The Rust supervisor receives its existing `O` command through its inherited
private control pipe. Actual window visibility completes each timing. The
reference completes its two initial reconciliations against an empty synthetic
recursive JPEG source. Each idle window settles for three seconds before a
15-second measurement, with working-set samples every 250 ms. CPU uses the
change in process kernel plus user time divided by elapsed wall time.
The output records the individual samples and window transitions. The
reference retains its normal in-process engine. The Windows Rust supervisor
owns the synthetic native inventory worker and includes its PID in the CPU
and working-set measurement. The separate scan trial ties each measured
window transition to successful native operations within the source tree.
The observer pairs each regular-file open and identity query with its
completion status, requires all 100,000 expected names in each of two passes
and checks directory enumerations independently. A private Windows job owns
the tested process tree. Profile removal requires the original pinned
directory and marker and a drained job.
[Scan fixture and observations](../../tools/rust-qa/windows-inventory/README.md).
[Process CPU accounting](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) · [Working set](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo).

The source-built SDK observer starts an ETW session filtered by the owned PID
and the DXGI/D3D9 present event IDs. It pairs start and stop events by thread
and provider and counts successful, non-test presentation calls. Two deliberate
reopens must each produce a fresh present. A missing control, decoding error,
lost events or an unavailable trace leaves the frame measurements open. The
other metrics retain their results. The trace file stays in the private
workspace. The evidence directory contains counts, successful control results
and any diagnostics. Physical scanout requires separate observation.
[Windows ETW filtering](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-enabletraceex2) · [DXGI descriptors](https://github.com/GameTechDev/PresentMon/blob/main/PresentData/ETW/Microsoft_Windows_DXGI.h) · [D3D9 descriptors](https://github.com/GameTechDev/PresentMon/blob/main/PresentData/ETW/Microsoft_Windows_D3D9.h).

## Native invocation

Run after the canonical native GUI build and filtered YAML source assessment
on the same GitHub-hosted runner.
The existing native Visual Studio toolchain, Windows SDK, Python and .NET SDK
are sufficient. The step can use the job's `NUGET_PACKAGES` cache.

```powershell
. ./tools/rust-qa/enter-windows-build.ps1 -Architecture $env:NATIVE_ARCH
python tools/rust-qa/windows-performance/run.py $env:NATIVE_TARGET --output "artifacts/rust/windows-performance/native-$env:NATIVE_TARGET"
exit $LASTEXITCODE
```

The launcher requires a disposable GitHub-hosted Windows runner. WPF reads
the real known folders for the runner's SID. Before reserving its product
directory, the fixture refuses an existing product path, single-instance
mutex or product Startup shortcut. It creates a synthetic config before
launch, records filesystem/database initialization and removes its own marked
directory after the reference exits. The idle trial uses an empty media
root. The scan trial uses 100 directories of 1,000 empty JPEG files created
for this run. The configured Immich URL and the WPF
HTTP/HTTPS proxy use an exclusively reserved, non-listening loopback port.
The ordinary WPF host has no Quit CLI. The recorder terminates its owned
process after sampling. The Rust process receives Quit and must report
that it drained. Upload only the target-specific output directory.
[Windows known-folder lookup](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath) · [.NET HTTP proxy selection](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclient.defaultproxy).

`python3 tools/rust-qa/windows-performance/test_recorder.py` exercises the
fixed threshold policy, missing-control handling, reference source extraction,
PE header checks and refusal of pre-existing test paths on a development host.
Native execution supplies the measurements for the [acceptance record](acceptance.md).
