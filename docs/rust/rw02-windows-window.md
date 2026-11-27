# Windows window lifetime and DX12 allocation

The canonical Windows GUI tears down its root window and renderer on ordinary close. In native x64 run `44941845642`, each of the three Rust logs recorded 11 DX12 generations. The GUI ran under the Microsoft Basic Render Driver at 1024 × 768 and 96 DPI. A first-party comparison retains the window and requests smaller allocator blocks. With Mailbox presentation it passed all eleven WPF-derived limits on ARM64 in run `45039099730`. Windows x64 exceeded the idle close, idle reopen and active inventory reopen limits. [Original Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642/job/136960549014) · [Earlier paired WPF results](rw02-windows-performance.md#completed-paired-inventories).

| Historical x64 metric | Rust | WPF-derived maximum |
| --- | ---: | ---: |
| Startup to first visible HWND | 196.24 ms | 1052.318 ms |
| Visible working set | 177.00 MiB | 143.177 MiB |
| Hidden working set | 26.69 MiB | 140.749 MiB |
| Idle close, p95 | 139.33 ms | 14.793 ms |
| Idle reopen, p95 | 217.50 ms | 14.762 ms |

Both idle intervals recorded zero CPU and zero successful presentations. The 150.30 MiB difference between the visible and hidden medians occurred with renderer teardown. The historical GUI ran before integration of its inventory worker. The source revision was `8a8adaa400abc7303335c624ea68abed197158da`, the x64 archive SHA-256 was `ce09fae0f455e589a50971c8db1aca44aa3f8a58171c7b149563941991c083f6`, and its `windows-performance/native-x86_64-pc-windows-msvc/result.json` had SHA-256 `45aa56a15810b8ee301fcd060ba53f531879269de19a2329c8041847838c9b97`. The new paired comparison obtains its own reference on the same runner.

## Window and renderer ownership

On ordinary `WM_CLOSE`, the native handler records the user's hidden intent and calls winit's `set_visible(false)`. The same UI thread owns the HWND, eframe application, surface and device until an explicit quit or graphics failure. Activation restores a minimized window if needed, shows it, requests native focus and repaints. The edit control's logical focus survives hide and recovery. On background startup the supervisor waits for an activation before creating the first window. [First-party variant](../../tools/rust-qa/windows-warm-window/candidate.patch).

An event-loop proxy wakes the dispatcher for private control commands and for a confirmed device loss. The handler drains the command queue before eframe processes a repaint. It uses `ControlFlow::Wait` while hidden. The control reader preserves queued commands under backpressure. A failed device exits its generation and follows the existing bounded recreation policy. Hiding a healthy window and releasing an invalid device are separate observed transitions. [Dispatcher integration](../../tools/rust-qa/windows-warm-window/loop_wake.rs) · [winit event delivery](https://docs.rs/winit/0.30.13/winit/event_loop/struct.EventLoopProxy.html).

The variant calls egui-wgpu's existing device-descriptor builder with the actual adapter and changes `memory_hints` to `MemoryUsage`. The default descriptor uses `Performance`. In the pinned wgpu-hal 30.0.2 source, the device/host minimum block sizes are 128/64 MiB for `Performance` and 8/4 MiB for `MemoryUsage`. The DX12 backend consumes those values when configuring suballocation. The variant preserves the original feature requests, limits and adapter selection. [DX12 allocator and report](https://github.com/gfx-rs/wgpu/blob/v30.0.2/wgpu-hal/src/dx12/suballocation.rs) · [Pinned GUI packages and features](../../rust/audit/gui-profile.json).

## Native evidence

The observer runs each case in a new synthetic profile on a disposable native runner. It installs WinEvent hooks for the tested PID before releasing its startup pipe.

| Case | Required observation |
| --- | --- |
| Background startup and quit | No window-show event or renderer attempt before activation. Quit drains the never-shown supervisor. |
| Background activation and unavailable tray | Initial activation opens a DX12 HWND. The unavailable-tray case starts visible. A subsequently hidden window can receive quit. |
| Ordinary close and reopen | A PID- and caption-verified HWND emits hide and show events, retains ownership while hidden and returns with the same ID. Its lifetime hook sees no destroy or recreate across the transition. The DX12 generation count stays constant. |
| Edit across close and reopen | Owned foreground UI Automation and real keys seed the ordinary filename. Reopen restores focus and the draft. A further edit changes both the value and the captured field pixels. |
| Visible and hidden device loss | The test destroys the actual logical wgpu device. The loss callback wakes the supervisor and a CPU-policy replacement creates a different HWND and a new generation. Hidden loss waits for user activation. A separate visible-loss run checks retained text, focus and editable pixels. |
| Memory attribution | Compare the ordinary teardown executable, a retained window with the original `Performance` descriptor, and the same retained executable with `MemoryUsage`. Each supplies visible, hidden and reopened snapshots after a three-second settle. |

The independent Win32 observer counts resident private, image and mapped pages for its owned GUI process and groups image bytes by module basename. The two retained-window runs also ask the live wgpu device for allocated bytes, reserved bytes and allocation/block counts. An unsupported allocator report is recorded explicitly. The OS and device figures have different accounting boundaries. The timed comparison samples the whole process tree and never sends the diagnostic command. These hosted cases exercise logical-device destruction and synthetic tray availability. [Native observer](../../tools/rust-qa/windows-warm-window/observe.py) · [QueryWorkingSet](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-queryworkingset) · [VirtualQueryEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualqueryex) · [Device allocator report](https://docs.rs/wgpu/30.0.0/wgpu/struct.Device.html#method.generate_allocator_report).

Both Windows architectures passed all ten observer cases in runs `44950398558` and `44953046306`. The measured whole-tree visible working set fell from 189.18–189.22 MiB to 60.25–60.29 MiB on x64 and from 192.42–197.61 MiB to 69.68–69.70 MiB on ARM64. Each successful calibration included a real DXGI present. The 15-second visible and hidden intervals recorded zero successful presents for both Rust executables. [Earlier paired run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44950398558) · [Later paired run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306).

The independent GUI-only snapshots distinguish device lifetime from reserved capacity. Both retained descriptors used 2,490,368 bytes across 16 allocations in two blocks. `Performance` reserved 192 MiB and `MemoryUsage` reserved 12 MiB. Their visible resident sets were within 0.5 MiB of each other on each host. On reopen in the later run, the recreated renderer used 77.8 MiB of private resident pages on x64 and 141.4 MiB on ARM64. The retained renderer with its original descriptor used 12.4 and 12.7 MiB respectively. Most of the observed difference arose with device recreation. A direct process-working-set saving of 180 MiB from the allocation hint alone is unsubstantiated.

## DX12 presentation during inventory

The earlier ETW presentation traces covered idle and two deliberate reopens. On each x64 trial they recorded five or six successful presents in the first reopen control and three in the second. On ARM64 they recorded one in each. Their corresponding inventory records independently identify file operations and HWND responses. Those captures lack per-present start times and synchronization intervals during the scan, so they cannot identify time spent inside DXGI as the cause of a slow response.

The retained executable, allocator, permitted frame latency of one, WPF budget and file workload are identical for both presentation modes. On the actual DX12 CPU adapter the candidate queries the capabilities of an unconfigured wgpu surface for the same owned HWND. wgpu-hal creates its swap chain when the surface is configured. An advertised `Mailbox` requests `Present(0, 0)` and `Fifo` requests `Present(1, 0)`. Both modes preserve composition without the tearing flag. Hardware adapters keep the ordinary policy. The scan observer matches successful DXGI starts and stops to the GUI PID on the native performance-counter clock used by the inventory and HWND observer. It reports each trial’s longest overlap per request. [CPU adapter and HWND policy](../../tools/rust-qa/windows-warm-window/windows_present.rs) · [Pinned DX12 implementation](https://github.com/gfx-rs/wgpu/blob/v30.0.2/wgpu-hal/src/dx12/mod.rs) · [Microsoft DXGI presentation parameters](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-idxgiswapchain-present) · [QPC and file-work correlation](../../tools/rust-qa/windows-warm-window/scan_present.py).

Run `45039099730` tested revision `3b4854d867f614a956042dfe987ecc7c008e53ec`. Times are paired close/reopen p95 values in milliseconds, computed as the median of three trial p95s. Each trial completed two independently observed inventories of 100,000 distinct files. [Native run and source revision](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730).

| Native target | WPF | WPF maximum | Canonical Rust | Retained Mailbox | Retained FIFO |
| --- | ---: | ---: | ---: | ---: | ---: |
| x64 | 20.85 / 11.92 | 30.85 / 21.92 | 252.12 / 213.86 | 22.23 / 124.14 | 69.66 / 159.22 |
| ARM64 | 3.94 / 5.09 | 13.94 / 15.09 | 212.18 / 161.65 | 7.00 / 4.20 | 18.49 / 4.32 |

On ARM64, Mailbox met all eleven WPF limits, FIFO met ten and the canonical renderer met six. The three Mailbox scans recorded 585 successful presentations with interval zero during verified work. The three FIFO scans recorded 586 with interval one. The p95 duration of a successful call on either mode was at most 0.174 ms in every trial. None of the 82 FIFO close requests above 13.938 ms intersected a successful presentation call. Changing the interval improved observed close latency on this host. The trace does not locate time spent acquiring a frame, dispatching a window message or waiting for the compositor. [ARM64 job archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730) · [DXGI frame latency waitable object](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_3/nf-dxgi1_3-idxgiswapchain2-getframelatencywaitableobject).

On x64, Mailbox met eight limits, FIFO seven and the canonical renderer six. Mailbox idle close/reopen reached 25.28 / 21.08 ms against 14.319 / 16.524 ms. Every one of the 611 work-qualified Mailbox reopens exceeded 21.920 ms. Each overlapped successful DXGI calls for at most 0.661 ms in total. In 587 reopens the GUI completed exactly two presentations between the request and the external visibility observation. The trial medians for the gap between consecutive calls in those request windows were 47.4–48.1 ms. The median time from the last successful call to the external observation was 44.0–44.8 ms. These timestamps establish where to measure the remaining delay. The source of the gap is open. [Native x64 and ARM64 results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730).

The SHA-256 digests below identify the downloaded archives and the frozen per-host budgets. Replaying the 24 decoded file traces, 12 DXGI timing traces and external request clocks reproduced the results above. All ten retained-window observation cases exited successfully on each architecture.

| Target | Native archive SHA-256 | WPF budget SHA-256 |
| --- | --- | --- |
| x64 | `eb9cb84546da440577f10018dc09882a0ba8983989a12bfef6ff87b862b35f46` | `2bbb3a79af7af63b5022dd8db4e0ceb1fc9a338f16b945577b529b2fe9a513d8` |
| ARM64 | `cbbeaafadbfa07160aaf83f38a0157e6aa20ba960874d28be41cbd4204982257` | `a88b13a4d189c028d2609dd37291b4689df89453b7698c24bced2f28b0a56b2c` |

## Timing the activation wake

The private pipe wakes winit with a root viewport repaint event. Activation also calls `window.request_redraw()` after restoring native visibility and focus. Forwarding the original root event to eframe can schedule another redraw for a current pass. The DXGI events above do not identify which callback produced an individual frame. A separate comparison uses the original Mailbox behavior as its control. Its second scan gives the private wake an unused viewport ID, drains the same command queue, and consumes that event after activation requests the root redraw. Normal eframe repaints and accessibility actions still reach eframe. The extra observer cases exercise focus, real text editing and hidden device recovery with that change. Native results for the single-wake variant are pending. [First-party dispatch integration](../../tools/rust-qa/windows-warm-window/dispatch.patch) · [eframe dispatcher](https://github.com/emilk/egui/blob/3c6eb8261c3293ad9c7ea1ed58487e038860ebef/crates/eframe/src/native/run.rs#L348-L394).

Both diagnostic scans record raw Windows performance-counter ticks on the pipe and UI threads. The window code samples the actual HWND visibility before and after `set_visible`, records the return of that native call, and times focus, the explicit redraw request and the winit callbacks. The independent scan driver times its own first matching HWND observation. It can finish while the native call is still returning. The report preserves the signed difference between that observation and the UI thread’s subsequent visibility sample. For each successful presentation the report records its process and thread. It attributes calls on the UI thread to an enclosing callback where available. Callback durations include wall-clock waits. Each diagnostic process buffers at most 65,536 spans and writes them after its workload drains. A missing span, mismatched identity or lost trace leaves the diagnostic unqualified. The ordinary three-trial budgets use processes with diagnostic collection disabled. [Counter adapter](../../tools/rust-qa/windows-warm-window/win32_clock.rs) · [Native recording](../../tools/rust-qa/windows-warm-window/ui_trace.rs) · [Timeline correlation](../../tools/rust-qa/windows-warm-window/dispatch.py) · [Windows performance counter](https://learn.microsoft.com/en-us/windows/win32/api/profileapi/nf-profileapi-queryperformancecounter).

## Reproduction

Build the canonical native GUI first on the same revision. Use the job's pinned Rust and native Visual Studio environment for the following commands. Run each entry point as a separate step so its exit status and evidence remain available.

```powershell
. ./tools/rust-qa/enter-windows-build.ps1 -Architecture $env:NATIVE_ARCH
python tools/rust-qa/windows-warm-window/build.py $env:NATIVE_TARGET
python tools/rust-qa/windows-warm-window/observe.py $env:NATIVE_TARGET
```

After the canonical WPF performance recorder has frozen its three-trial `reference-budget.json`, run the comparison in the same native toolchain environment. It checks the source inputs, run, attempt, host, runner image and reference hash, then independently derives all thresholds from those WPF trials. It uses the ordinary recorder's process ownership, inventory worker, 100,000-file workload, timing, ETW controls and completion checks. A missing metric stays open. Three complete candidate trials must each report one `MemoryUsage` device.

```powershell
python tools/rust-qa/windows-warm-window/measure.py $env:NATIVE_TARGET
python tools/rust-qa/windows-warm-window/measure.py $env:NATIVE_TARGET --fifo-control
python tools/rust-qa/windows-warm-window/measure.py $env:NATIVE_TARGET --dispatch
```

Preserve `build.json`, `compiler.jsonl`, `eframe-source.zip`, `observed/**`, `measured/**` and `measured-fifo/**` under `artifacts/rust/windows-warm-window/<target>/`. The first timed command enforces all eleven WPF-derived maximums. The second records the earlier FIFO policy and binds both complete three-trial comparisons to the same revision, binary, host run, budget and workload. An over-budget control remains visible in its result. Build receipts identify the canonical and retained executables, their sources, the reviewed features and the fonts. The source archive supplies the inputs for rebuilding the retained eframe and winit libraries. [Build](../../tools/rust-qa/windows-warm-window/build.py) · [Timed comparison](../../tools/rust-qa/windows-warm-window/measure.py).

Keep `dispatch/*.json` and `dispatch/*.log` from the third command. The same retained executable exercises the root repaint wake, a single wake and the original hidden-window painting policy in three instrumented inventories. Each uses the first-party worker, 100,000 files and the same native references. The recorder counts successful DXGI calls starting between a confirmed hide and the next show of that HWND. Qualification also requires the ordinary three-trial budget comparison and native behavior checks.

Nine portable tests covered staged source, resident pages, the shared WPF budget and timing correlations, including overlapping callbacks, asynchronous observations and presents from a different thread of the same process. Rust 1.100.0 passed rustfmt and Clippy for both MSVC targets, including test targets. On each Windows target the staged diagnostic and original manifests resolved to the same 135 package/version/feature entries. The pinned external egui source emitted its existing `std::f32::EPSILON` deprecation. [Variant and budget checks](../../tools/rust-qa/windows-warm-window/test_variant.py) · [Dispatch timeline tests](../../tools/rust-qa/windows-warm-window/test_dispatch.py).

## Repeat measurements before the dispatch trace

Runs `45041728291` and `45047460092` used the same GUI, worker and warm-window sources as `45039099730`. Each host froze its eleven WPF limits before measuring the candidates. Mailbox and FIFO used the same native executable within each job. The table gives the count of limits met by each candidate and the retained Mailbox p95 versus its WPF-derived maximum in milliseconds, using the median of three trials. [Run at 8b64330](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45041728291) · [Run at 7517e3b](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460092).

| Revision and target | Limits met, canonical / Mailbox / FIFO | Idle close | Idle reopen | Scan close | Scan reopen | Archive SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `8b64330` x64 | 6 / 9 / 7 | **23.08** / 14.214 | 6.95 / 16.841 | 22.79 / 30.464 | **121.49** / 22.029 | `635f8cfcf6419e952b1ed64106b5d4b11eb1dadcc714145057cad898cf0add89` |
| `8b64330` ARM64 | 6 / 11 / 10 | 3.04 / 13.234 | 4.60 / 13.622 | 8.45 / 13.856 | 3.90 / 15.171 | `51d2352ae85f03a8dacdaaf08a44b940ec5f793823a5b897cbaff10ad9e50554` |
| `7517e3b` x64 | 6 / 7 / 7 | **18.84** / 13.811 | **56.34** / 16.207 | **47.58** / 18.731 | **122.81** / 19.555 | `7077364108250c99d95f6de2680d4404b1aacc1a1c3cfe3f3b06c2f29ebe658b` |
| `7517e3b` ARM64 | 6 / 11 / 10 | 2.95 / 13.104 | 3.34 / 14.888 | 3.96 / 13.714 | 3.97 / 14.935 | `d13678adf699c7e9fed734fd7ce9324ec182149f317aa7a53b1a4258caf0108c` |

Replaying 48 PID-bound file traces verified two passes over 100,000 distinct files in every trial. All 40 retained-window observation cases passed. The x64 Mailbox candidate exceeded idle close and scan reopen in all three runs. Idle reopen and scan close varied between runs. ARM64 Mailbox met all eleven limits three times. In the two repeats, all 1,205 ARM64 scan reopens finished within their respective limits.

The active-scan request clocks place 607 of 607 and 396 of 397 x64 Mailbox reopens above their respective limits. Replaying the 24 retained-mode DXGI traces showed that exactly two successful presentations fell entirely between request and external HWND observation in 950 of those 1,004 reopens. The largest total overlap with successful DXGI calls during an over-budget reopen was 0.5522 ms. The two revisions predate the dispatch trace introduced at `d716245`.

## Presentations while the root HWND was hidden

At `8091469` both architectures completed all ten retained-window behavior checks and all three Mailbox and FIFO trials. Each timed trial observed two passes over 100,000 distinct files. The table gives the median of the three trial p95s in milliseconds, followed by the WPF-derived limit for that job. [Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343500).

| Target | Mailbox limits met | Idle close | Idle reopen | Scan close | Scan reopen |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows x64 | 8 / 11 | **43.83** / 14.509 | **17.59** / 14.661 | 22.55 / 31.325 | **119.95** / 21.987 |
| Windows ARM64 | 11 / 11 | 3.16 / 13.470 | 4.84 / 15.036 | 9.11 / 14.490 | 4.91 / 15.522 |

In the separate dispatch trial, both the Win32 observer and the UI thread recorded the same HWND and process on a common performance-counter clock. All 238 x64 root-repaint and 201 single-wake reopens had exactly two successful DXGI calls after the native hide completed and before the next show began. Each pair ran on the UI thread during one generic window callback and one focus callback. Neither trial recorded a resize during reopening. On ARM64, all 207 and 195 corresponding intervals contained zero successful presentations. The old trace grouped modifier changes with other window events.

The x64 pipe reader received the request in about 0.05 ms. Median time from that read to the UI handler was 50.80 ms with the root repaint and 69.71 ms with the single wake. The native show calls took a further 35.06 and 33.11 ms at the median. ARM64 delivered the same wakeups in 0.17 and 0.16 ms, then spent 3.06 and 3.03 ms in the show call. These are separate phase medians. The independent archive readback is `windows-dispatch-readback.json`, SHA-256 `547b16a849947cce165b555ea67a1ca91f6978398ac52ecbc91996b35c4a2b4a`. Replaying both original timelines on both architectures reproduced every original dispatch result and all 841 hidden intervals. [Native archives](rw02-native-gui.md#native-follow-up-at-8091469).

The comparison build now tells eframe when the application deliberately hides its root. It checks the actual Win32 visibility before using the existing logic-only path. Native input, accessibility and application logic continue to run. Showing the root requests a fresh frame. Source review confirms eframe honors already pending pixel requests and visible descendants. The single-window host exercises its root. Focus and modifier transitions have distinct trace labels. The original policy is selectable in the same isolated executable. Its native behavior and response budgets require a new run. [eframe change](../../tools/rust-qa/windows-warm-window/eframe-hidden-input.patch) · [Application change](../../tools/rust-qa/windows-warm-window/retained-hidden-input.patch) · [Dispatch readback](../../tools/rust-qa/windows-warm-window/dispatch.py).

At `fe8d43c` two offline reconstructions produced the same twelve-member
source ZIP, SHA-256 `3e53af63d808cfde90c44bd6142aeadcde83e04997bef4edb464733f342cd325`.
It contains the published eframe crate, four original license texts, both patches
and the two Cargo manifests and lockfiles. The Cargo-generated lock changes
only eframe's source and checksum entries. The Windows profiles each retain
their original 135 package/version/feature entries. Both MSVC targets passed
cross-Clippy. A native Fedora release build confirmed the private eframe crate
root and produced the rlib with SHA-256
`3bc298723fbb0d0038cd7dd3c9ac88858ce0bee923b35ed868b8199e58b49190`.
The 13 portable comparison tests passed, including altered input and compiler
path refusals. [Pins and license origins](../../tools/rust-qa/windows-warm-window/eframe-source.json)
· [Reconstruction](../../tools/rust-qa/windows-warm-window/eframe_source.py).

Independent review found that a delayed visibility sample after show could
exclude a previously confirmed hidden interval. A six-reopen regression
put one successful DXGI call in that interval. The corrected recorder
counts it, requires coverage of every eligible reopen and reports whether
the original-paint control reproduced a hidden presentation. A second
regression inserted an unsolicited show and hide on the same HWND between
two external requests. The recorder binds the start of each interval to the
actual preceding external close and declines a trace with an intervening
visibility change. Fifteen portable tests passed. Replaying all 841
historical intervals reproduced the same counts and native timings.

## Native retained-window results at 0a2b5ca

The retained Mailbox build met all eleven WPF-derived limits on both Windows hosts at
`0a2b5ca19bcd7cb7be7a5f77415e05b8237ca47a`. Each four-core runner measured its
own WPF reference before timing the Rust processes. Windows Server 2025 x64 and
Windows 11 ARM64 both used the DX12 Microsoft Basic Render Driver. The table gives
the median of three trials per subject with UI dispatch tracing disabled. For close and reopen, each
trial contributed its own p95. The limits were recomputed from the original WPF
records before rounding the displayed values. [x64 native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235/job/137378911450) · [ARM64 native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235/job/137378911693).

| Metric | x64 WPF | x64 limit | x64 retained | ARM64 WPF | ARM64 limit | ARM64 retained |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Startup (ms) | 814.989 | 977.987 | 202.899 | 769.519 | 923.424 | 206.415 |
| Visible CPU (% of one core) | 4.007 | 5.008 | 0 | 3.080 | 4.081 | 0 |
| Hidden CPU (% of one core) | 3.905 | 4.905 | 0 | 3.795 | 4.796 | 0 |
| Visible working set (MiB) | 130.020 | 143.022 | 60.281 | 133.492 | 146.842 | 69.676 |
| Hidden working set (MiB) | 128.113 | 140.925 | 59.008 | 129.004 | 141.905 | 68.203 |
| Idle close p95 (ms) | 6.411 | 16.411 | 4.319 | 3.077 | 13.077 | 2.802 |
| Idle reopen p95 (ms) | 7.439 | 17.440 | 7.670 | 3.462 | 13.463 | 3.455 |
| Scan close p95 (ms) | 19.355 | 29.356 | 19.144 | 4.214 | 14.215 | 4.084 |
| Scan reopen p95 (ms) | 12.096 | 22.096 | 11.343 | 5.175 | 15.175 | 4.261 |
| Visible presentations/s | 0.066 | 0.133 | 0 | 0.066 | 0.133 | 0 |
| Hidden presentations/s | 0 | 0.067 | 0 | 0 | 0.067 | 0 |

The canonical teardown executable met six limits on each host. The retained FIFO
control met ten on each, exceeding the scan-close limit at 37.438 ms on x64 and
19.185 ms on ARM64. All twelve retained-window behavior cases passed on each host,
including restoring a focused draft after hide and after device replacement.
The archived pixel captures matched the focus and editing records.

The three instrumented Mailbox inventories used the same executable on each host.
The external HWND observations and UI-thread samples confirmed both ends of every
eligible hidden interval within the ETW recording.
The table counts successful DXGI calls that started after the native hide and
before the next show. The last column measures when the external observer saw the
window again.

| Host and policy | Verified / eligible intervals | Hidden presents | Pipe read to UI dequeue, median (ms) | Reopen p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| x64 root repaint | 303 / 303 | 0 | 0.150 | 11.652 |
| x64 single wake | 292 / 292 | 0 | 0.141 | 11.459 |
| x64 original hidden painting | 204 / 204 | 423 | 20.706 | 56.242 |
| ARM64 root repaint | 216 / 216 | 0 | 0.142 | 4.740 |
| ARM64 single wake | 216 / 216 | 0 | 0.135 | 4.701 |
| ARM64 original hidden painting | 211 / 211 | 0 | 0.147 | 4.640 |

The x64 original policy presented once in each empty-modifier callback and once
in each focus-loss callback. Fifteen intervals included a third presentation in
another window callback. Both corrected policies still delivered both native
input callbacks in every interval. Median callback wall time for empty modifiers
and focus loss fell from 26.866 and 11.993 ms under the original policy to
0.042 and 0.010 ms with the regular root wake. The successful DXGI call itself
took 0.176 ms at p95 in the original first pass. Separating frame production
from the invisible-window sleep would require timings inside eframe. On ARM64,
all three policies recorded zero hidden presentations. The ordinary root wake
provides the measured Windows configuration for the next integrated build.

The independent replay checked 30 file-I/O traces, each covering two passes
over 100,000 distinct files, and all 18 retained DXGI timing traces. Every
decoder completed without reporting a lost event or buffer. Both job archives
contain the same 12-member `eframe-source.zip`, SHA-256
`3e53af63d808cfde90c44bd6142aeadcde83e04997bef4edb464733f342cd325`. Reapplying
the patch reproduced the 36-file compiler tree recorded by both native builds.
The two independent JSON readbacks are stored beside the original archives
under `artifacts/rust/hosted-desktop-storage/45077818235/`.

| Target | Actions archive SHA-256 | Independent retained readback SHA-256 |
| --- | --- | --- |
| [x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235/artifacts/14778955008) | `589f02834ed6fe5227a087a92db8a575c5daa5208ae72753e307788183ae7074` | `e65c12aa50d665def1c0634cb8deec4fdd665b52b76cf6f112eb3997756f0f9c` |
| [ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235/artifacts/14778472175) | `9a7b632c69fb4979982f72b758a6356cc5475e8ccf2b766d27e849b0145e8661` | `372dd4c7a66e1d1ac3fa04df818f2c1c0db386b2ea228ec3ed1956079c914e20` |

## Native retained-window repeat at 93ecc35

The retained Mailbox GUI passed eight of eleven limits on Windows Server 2025 x64
and all eleven on Windows 11 ARM64 at `93ecc354f9be40ad0c76e33c46bdadb55f2e2fb8`.
Each host supplied its own three WPF reference trials. The table shows every
metric that exceeded a limit in any configuration. Bold measurements exceeded
the same-host limit before display rounding. Close and reopen values are the
median of three trial p95s with UI dispatch tracing disabled. All three x64
Mailbox trials exceeded the same three timing limits. Startup, hidden working
set and both idle CPU and presentation rates passed for all three Rust configurations.
[x64 native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275435) · [ARM64 native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275454).

| Host and configuration | Visible working set (MiB) | Idle close (ms) | Idle reopen (ms) | Scan close (ms) | Scan reopen (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| x64 WPF-derived limit | 142.897 | 14.264 | 16.755 | 31.576 | 22.786 |
| x64 canonical teardown | **189.133** | **190.814** | **172.123** | **259.601** | **211.306** |
| x64 retained Mailbox | 59.895 | **46.724** | 6.554 | **37.553** | **39.102** |
| x64 retained FIFO | 59.945 | **70.849** | 7.028 | **72.071** | **41.997** |
| ARM64 WPF-derived limit | 147.014 | 13.209 | 15.665 | 14.414 | 15.441 |
| ARM64 canonical teardown | **197.449** | **140.720** | **161.851** | **212.401** | **166.273** |
| ARM64 retained Mailbox | 69.754 | 2.893 | 3.930 | 8.067 | 4.633 |
| ARM64 retained FIFO | 67.805 | 2.756 | 4.457 | **18.373** | 4.806 |

All twelve window-behavior cases passed on each host. The create, destroy,
hide and show records confirmed reuse of the owned HWND and renderer on
ordinary retained reopen, replacement after device loss and no root window or
renderer on background quit. The editing cases also restored the focused
filename draft. The observer issued these reopens over the fixture input.
[Separate ordinary second-launch evidence](rw02-instance.md#ordinary-second-launch-and-private-desktop-at-93ecc35).

The three instrumented scans covered every eligible hidden interval. On x64,
root repaint and single wake recorded zero hidden presentations across 547 and
518 intervals respectively. The original hidden-paint control recorded 418 in
209 intervals, one in each empty-modifier callback and one in each focus-loss
callback. Both corrected configurations still delivered those callbacks in
every interval. On ARM64 all three counts were zero across 201, 187 and 200
intervals respectively.

The x64 root-repaint trace located two delays during inventory. In all 54
close requests above the same-host scan limit, visible redraw callbacks
occupied at least half the time between issuing the request and entering the
close callback. Median overlap was 33.230 ms across those requests. For
177 of 179 over-limit reopens, the native show call overlapped at least half
the time to the external visibility observation. Pipe read to UI dequeue was
0.561 ms at p95 across all 547 reopens. Single wake showed the same pattern
in all 36 over-limit closes and 172 of 176 over-limit reopens. The traces
leave the work inside the visible redraw and native show calls unresolved.
Idle close was timed from the external HWND observer.

Replay from the tested Git revision checked 21 canonical and 21 reconstructed
retained application inputs per host. Each of the 30 file-I/O traces covered
two passes over 100,000 distinct files. All 18 timed DXGI traces completed
their decoder and session-loss checks. Both hosts archived the same eframe
source ZIP, SHA-256 `ce55769b1e721136161c6bf19fdd46665ccb6b00cca5f0b3290c23f1f8a06b7f`.
The replay and its JSON reports are in `artifacts/rust/hosted-desktop-storage/45083264235/`.

| Target | Actions archive SHA-256 | Independent retained readback SHA-256 |
| --- | --- | --- |
| [x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14782395756) | `f7fe684395b02e0d05c20eec390aa17a2ad811c35964097b5c9b4c9c94cd2769` | `35b2018c94bbfaaac000bb42e90af81b218ae74287c71b9ed5d4cebc14afb35b` |
| [ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/artifacts/14782220563) | `f22eea1c70b66207a7646f2557ee169037d2d7418611dd0108b0581aabf6b1ae` | `dc58618ed23534a168c3f4747f8fa114dbe818b96ab81e903b88db162930179d` |

## Retained measurements with explicit foreground requests at 1e58541

At `1e58541a784c909ad772ba47fb35515844552fb2`, the uninstrumented Mailbox
build again passed eight of eleven Windows x64 limits and all eleven ARM64
limits. Every x64 trial exceeded the same three timing limits. Each host
supplied a fresh three-trial WPF reference. Bold values exceeded the
limit before display rounding. [x64 native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/job/137525629804) · [ARM64 native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/job/137525629530).

| Metric | x64 Mailbox | x64 limit | ARM64 Mailbox | ARM64 limit |
| --- | ---: | ---: | ---: | ---: |
| Startup (ms) | 131.187 | 692.233 | 208.928 | 1059.079 |
| Visible working set (MiB) | 60.371 | 143.357 | 69.711 | 147.325 |
| Hidden working set (MiB) | 59.105 | 140.281 | 68.328 | 144.000 |
| Visible CPU (% of one core) | 0 | 3.787 | 0 | 4.122 |
| Hidden CPU (% of one core) | 0 | 3.892 | 0 | 4.531 |
| Visible presentations/s | 0 | 0.133 | 0 | 0.134 |
| Hidden presentations/s | 0 | 0.067 | 0 | 0.067 |
| Idle close p95 (ms) | **24.488** | 13.426 | 2.997 | 13.477 |
| Idle reopen p95 (ms) | 5.176 | 15.866 | 3.144 | 15.506 |
| Scan close p95 (ms) | **23.011** | 16.143 | 5.087 | 14.209 |
| Scan reopen p95 (ms) | **27.737** | 19.055 | 4.755 | 15.393 |

The canonical teardown build exceeded the visible working-set limit and
all four close/reopen limits on each host. FIFO exceeded the three x64
limits for idle close, scan close and scan reopen at 46.348, 66.352 and
24.785 ms respectively. Its single ARM64 miss was scan close at 18.342 ms.
All twelve window-lifetime, editing and recovery cases passed per host.

The file-I/O traces confirmed both 100,000-file passes in all 30 inventories.
All 18 timed DXGI traces completed their decoder and session-loss checks.
On x64 the regular root wake had zero hidden presents in 244 verified
intervals and the single wake had zero in 285. The original hidden-paint
control had 188 in 94 intervals, one per empty-modifier and focus-loss
callback. ARM64 recorded zero in all 222, 221 and 209 intervals respectively.

During the x64 root-wake scan, visible redraw callbacks accounted for at
least half the time to enter the close callback in all 58 over-limit closes.
The native show call overlapped at least half the external response time in
78 of 81 over-limit reopens. The observer saw the HWND before the focus call
started in 200 of 244 reopens. Across the 81 slow reopens, that call's overlap
with the measured response was 0.0173 ms at p95 and 0.7134 ms at maximum.
The focus call itself took 0.0525 ms at p95 on x64 and 0.0741 ms on ARM64.
The preceding run measured 0.0014 and 0.8454 ms. The two runs used separate
WPF baselines. This fixture sends Open through the GUI's standard input and
measures visibility. Ordinary second-launch foreground and keyboard focus have their
own observations. [Explicit Windows foreground requests](rw02-instance.md#explicit-windows-foreground-requests).

Per host, the replay verified 22 canonical and 22 reconstructed application
inputs. The archived Cargo stream contained 153 compiler artifacts covering
all 135 expected package and feature combinations. It identified the local
GUI executable and retained eframe library. The native build receipt supplies
the executable digest. The replay and reports are in
`artifacts/rust/hosted-desktop-storage/45124494708/`.

| Target | Actions archive SHA-256 | Independent retained readback SHA-256 |
| --- | --- | --- |
| [x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14797058450) | `85eaf2cbf71148aa4f4052345ea214ab904c9a5237872cb364c3304c9273fabb` | `1600feda6b48d8d2ca25ca0eb7ed95627179a6448197a68acfc2af2003d12324` |
| [ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708/artifacts/14798644285) | `09ba75b8bb7d0fc3efc338f184c4f6f24b5e694a9464c4ffab7042132ff8920f` | `8d7ede78aa041bb50cd5b27ac2e966e1b39413bbc1e093309d7968dc16493a1b` |

## Testing visibility changes without resetting the window frame

At `1e58541` the Win32 show call overlapped most slow x64 reopens. The
original winit 0.30.13 implementation updates both style words and requests
a frame recalculation even when visibility is the only changed flag. The
retained candidate now uses the existing Win32 show or hide command alone
for that transition on an ordinary decorated, taskbar-visible top-level
window. Before every eligible hide or show, the actual style and extended
style must match the previous cached flags. This also detects a window
minimized or maximized externally. The candidate commits the new cached
flags and releases winit's mutex before calling Windows, which can
synchronously deliver window messages. Initial placement and transitions
involving minimization, maximization, fullscreen or a drag use the upstream
code. [Source change](../../tools/rust-qa/windows-warm-window/winit-retained-visibility.patch) · [ShowWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindow) · [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos).

The source bundle rebuilds the 217-file winit tree from its published crate
and one changed file. The crate and the pinned upstream revision supply the
same Apache-2.0 license bytes. Two offline reconstructions produced the same
16-member `eframe-source.zip`, SHA-256
`9881edc6683df62a5d804ac6a1062e000c7f348a28193f10eb92d07fbacf7ec7`.
The frozen Windows and Linux target graphs retained 135 and 240 package and
feature combinations respectively. Both Windows MSVC targets passed
cross-Clippy. A native Fedora release build recorded both local libraries
and the final executable in 289 Cargo compiler entries.
[Published source and checksum](../../tools/rust-qa/windows-warm-window/winit-source.json) · [Original license](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/LICENSE) · [Offline reconstruction and controls](../../tools/rust-qa/windows-warm-window/test_variant.py).

On each Windows host the retained launcher checks the compiled eframe and
winit library outputs against the original Cargo stream. In an ordinary
launcher trial the first eligible hide and show each identify the actual
HWND. The observer records `hidden.winitVisibilityShortcut` and
`reopened.winitVisibilityShortcut` against the independently observed
window and its native events. The completed primary log distinguishes a show
that returns after the external observer first sees the HWND. Attribution
requires a positive match for the relevant transition. The separate three-trial comparison
uses the same binary, WPF budget calculation and 100,000-file workload with
launcher diagnostics disabled. At `6af7100` the ordinary launcher on each
architecture observed the shortcut on both hide and show, on its original
and private desktops. Each pair retained its worker and first DX12 renderer.
The x64 original desktop confirmed foreground and keyboard focus on the
first sample. On ARM64 all 41 samples over 2,020 ms found the retained
window visible in the background.
[x64 activation](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14806170882) · [ARM64 activation](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14805618878) · [Window and focus observations](../../tools/rust-qa/windows-launcher/retained_window.py).

## Native retained-window results at 6af7100

The uninstrumented Mailbox executable met eight of eleven WPF-derived
limits on x64 and all eleven on ARM64. The three x64 misses occurred in
each of the three trials. The table gives the median of trial p95 values
in milliseconds, followed by the maximum set by that host's WPF trials.

| Target | Idle close | Scan close | Scan reopen | Raw readback SHA-256 |
| --- | ---: | ---: | ---: | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14809775806) | 26.561 / 14.571 | 35.398 / 30.582 | 35.614 / 22.003 | `618ac826060e28f30a5922c3a7afc7d136d61bbc97a652bbf8eaa468b9999c2a` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858/artifacts/14809461061) | 2.813 / 13.262 | 4.755 / 14.178 | 4.735 / 15.208 | `26d6633456696f2cd8cc4a760be054b53c49dc2a9f46c40146dcafc0b7b8585c` |

Independent replay verified 12 window controls, 15 complete two-pass
inventories over 100,000 files, nine DXGI traces and the native Cargo
stream on each host. In the regular x64 dispatch trace, visible redraw
occupied at least half the time to the close callback in 82 of 83 slow
closes. The native show call occupied at least half the external response
in 130 of 131 slow reopens. The response preceded the focus call in 540
of 585 reopens. The focus call overlapped slow reopens by at most 0.199 ms.
The corrected root and single-wake modes recorded zero presentations in
585 and 532 hidden intervals on x64. The original-paint control recorded
451 presentations in 225 intervals. ARM64 recorded zero in all three modes.
The diagnostic timings and the uninstrumented budget measurements came
from separate trials of the same retained binary on each host.

## Retained window at 8566f81

The same-machine WPF controls again set the limits below. Each cell shows
the median of the three trial p95 values in milliseconds and its limit.

| Retained Mailbox target | Idle close | Idle reopen | Scan close | Scan reopen | Limits met |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows x64 | 24.989 / 14.327 | 6.598 / 16.845 | 38.986 / 29.888 | 25.888 / 21.996 | 8/11 |
| Windows ARM64 | 2.842 / 13.332 | 3.619 / 13.758 | 4.809 / 14.422 | 4.607 / 15.530 | 11/11 |

Independent replay on each target recovered 12 window controls, 15 two-pass
inventories of 100,000 files and nine DXGI traces. The canonical build met
six limits on each target. FIFO met eight on x64 and ten on ARM64. In the
separate x64 dispatch trace, all 54 slow closes overlapped a visible redraw
with a successful DXGI Present on the GUI thread. In 48 cases drawing had
already begun when the observer recorded its request time. The median time
inside the callback before Present was 32.985 ms, with 0.060 ms inside
Present. The trace does not subdivide the earlier work. The observer
checked window visibility before posting the close message, so the exact
time it spent queued is unknown. The synchronous `set_visible` span
accounted for at least half the response in 171 of 172 slow reopens. The
corrected root recorded zero presentation starts across 600 verified hidden
intervals. Its single-wake variant recorded zero across 467. The original
drawing control recorded 486 starts in 243 intervals. The follow-up at
`549066f` includes a same-host GDI renderer control.
[x64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14818067206) · [ARM64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037/artifacts/14817086899) · [GDI comparison](../../tools/rust-qa/windows-gdi-control/README.md).

## Renderer comparison with iced 0.14.0

At iced revision `3997291f318a8bc06fa522f5579836fb3feb94df`, the
application can keep a window alive on close and change its mode between
hidden and windowed. The backend calls winit's `set_visible`. Its locked
winit 0.30.12 has byte-identical Win32 `window.rs` and `window_state.rs`
to the published 0.30.13 used by the eframe control. The software rendering
paths do differ. iced's tiny-skia 0.11.4 uses softbuffer 0.4.6 to present
a DIB through GDI `BitBlt`. The existing Windows recorder measures DXGI
and D3D9. A software-path timing comparison requires independent evidence
of changing visible pixels and live inventory work on the same host.
[iced window dispatch](https://github.com/iced-rs/iced/blob/3997291f318a8bc06fa522f5579836fb3feb94df/winit/src/lib.rs#L1562-L1570) · [Pinned graph](https://github.com/iced-rs/iced/blob/3997291f318a8bc06fa522f5579836fb3feb94df/Cargo.lock) · [GDI presentation](https://github.com/rust-windowing/softbuffer/blob/ad3bd6d2f930391e5840752a0f4514874821d5ea/src/backends/win32.rs#L174-L201).

The comparison inspected 274 application, shell, widget and renderer
sources and manifests and found no native accessibility provider for
the tested NVDA and Orca flows. Upstream tracks AccessKit integration.
The graphics crate always embeds the 5,700-byte `Iced-Icons.ttf`
(SHA-256 `2289860dbd2201295bf451deb155561abf4b1fb06899d6f1f81eb294bfebb7ec`).
The font names the original Fontello authors and lacks a license statement
in its name table. Its glyph provenance needs resolution before adoption.
Seven published source archives matched the Cargo index. Native iced
performance and reader behavior remain unmeasured.
[Accessibility issue](https://github.com/iced-rs/iced/issues/552) · [Embedded fonts](https://github.com/iced-rs/iced/blob/3997291f318a8bc06fa522f5579836fb3feb94df/graphics/src/text.rs#L110-L129) · [First icon font revision](https://github.com/iced-rs/iced/commit/2c8ba652a7929ac6c2af28ac60a8bd4b8e8e2f10).

The 0.14.0 font contains seven mapped symbols. In the official Fontello
catalog, `down-dir` derives from Font Awesome U+F0D7. The iced U+E800
outline and Fontello U+25BE have the same 15 integer points and curve
flags after translation in a 1,000-unit em. The compared Fontello TTF
has SHA-256 `95a8828ad76d680a991877ff38545458232f486a34aadbb7733fbb3951a8acef`.
The two checkmarks have
matching 865 × 663 bounds but different point counts (22 and 23).
Upstream documents the addition of the iced logo and four scroll icons
in separate changes. The complete font still lacks verified glyph-level
redistribution evidence. The native accessibility trial remains an
independent prerequisite for this alternative.
[Fontello catalog and source mapping](https://github.com/fontello/awesome-uni.font/blob/29d4e3ff028fc850a21b5eaafde0a83f22f59cf1/config.yml) ·
[Logo change](https://github.com/iced-rs/iced/pull/2902) ·
[Scroll icon change](https://github.com/iced-rs/iced/commit/99748b89dea3dc24db24a73d79d5fa3e410b73a4).

The November 25 follow-up found 0.14.0 was still the latest official iced
release. The published `iced_winit` 0.14.1 and `iced_widget` 0.14.2
feature sets expose no AccessKit option. Upstream still
tracks this work in issue 552. The development tree at `98bd48f` contains
the same 5,700-byte icon font as the stable release. These inputs leave
native screen-reader support and the complete font attribution unresolved.
[Official release](https://github.com/iced-rs/iced/releases/tag/0.14.0) ·
[iced_winit features](https://docs.rs/crate/iced_winit/0.14.1/features) ·
[iced_widget features](https://docs.rs/crate/iced_widget/0.14.2/features) ·
[AccessKit tracking](https://github.com/iced-rs/iced/issues/552) ·
[Development font source](https://github.com/iced-rs/iced/blob/98bd48fe011efc0ec5819fee0fa7673a7169ff11/graphics/src/text.rs#L126).

## Visible GDI and retained egui under the same inventory

The x64 GDI surface met the four WPF window-response limits twice.
Each cell below gives the median of three trial p95 values, in
milliseconds. The WPF controls ran on the same desktop as both Rust
subjects. The retained egui Mailbox window met nine of eleven total
resource limits at `549066f` and eight at `ba02f8b`. It met all eleven
on ARM64 at both revisions.

| Windows x64 | GDI scan close / reopen | Retained egui scan close / reopen | WPF maximum close / reopen |
| --- | ---: | ---: | ---: |
| [`549066f`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471/artifacts/14821874640) | 4.069 / 9.608 | 23.703 / 32.348 | 20.175 / 20.677 |
| [`ba02f8b`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14828200604) | 3.920 / 9.765 | 25.047 / 31.380 | 16.108 / 19.740 |

Each of the six x64 GDI trials inventoried 100,000 files twice. Independent
replay matched 184 close and 182 reopen requests at the first revision,
and 131 close and 129 reopen requests at the second, to original HWND
observations, screen pixels and active file work. Each reopen
also had its own completed BitBlt and GdiFlush. Across these trials,
the p95 from the reopen request to GdiFlush was 12.50–13.80 ms. The
external window-visibility timer ends when the HWND becomes visible.
Separately reading both colors took 53.79–69.45 ms per trial at the median.

Both ARM64 GDI traces contain a first flushed frame. Both stopped at the
external witness before the first close. No ARM64 GDI response timings were
obtained. The observer now retains the last sampling stage on timeout. It
discards colors whenever either test position loses HWND ownership.
The GDI result measures the small drawing workload. Full egui, text,
accessibility and editing require the actual application path.
[ARM64 at `549066f`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471/artifacts/14821439705) · [ARM64 at `ba02f8b`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804405/artifacts/14829680035).

## One or two queued frames on the Windows software adapter

The additional `--mailbox-two` trial uses the retained executable, its
existing egui editor and the same advertised DX12 CPU Mailbox surface as
the one-frame reference. It changes maximum frame latency to two.
On the pinned DX12 backend this configures three swap-chain buffers
instead of two and passes two to `SetMaximumFrameLatency`. Both
measurements check the actual `Wait` instance option and the selected
surface configuration. A successful DXGI event proves presentation. Time
spent waiting for an individual surface texture is unmeasured.
[Surface policy](../../tools/rust-qa/windows-warm-window/windows_present.rs) · [Pinned DX12 implementation](https://github.com/gfx-rs/wgpu/blob/v30.0.2/wgpu-hal/src/dx12/mod.rs).

Each mode runs three original WPF-budget comparisons with two inventory
passes over 100,000 files. The paired readback validates each process's
original file events, window requests and DXGI start/stop events. A
separate editor test requires the same retained HWND and input field,
readable text, keyboard focus and changed glyph pixels after reopening.
It records native timing results even if the separate desktop cannot
supply keyboard input. Independent replay on twelve original one-frame
scan trials verified the new reader. [Paired readback](../../tools/rust-qa/windows-warm-window/frame_latency.py).

### Native results at 1b95ba0

Both retained frame depths met all eleven preselected WPF limits on both
native Windows systems. Each depth ran the same full egui executable on
its host in three trials, each with two complete 100,000-file inventories.
The teardown GUI met six limits on each host. Each value below is the
median of the three trial p95s, in milliseconds.

| Host | Frame depth | Idle close / reopen | Scan close / reopen | WPF scan maximums |
| --- | ---: | ---: | ---: | ---: |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14843990978) | 1 | 4.43 / 6.83 | 16.21 / 11.34 | 29.932 / 21.364 |
| Windows x64 | 2 | 4.43 / 8.86 | 14.03 / 12.41 | 29.932 / 21.364 |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209/artifacts/14845081343) | 1 | 2.79 / 3.61 | 5.79 / 4.48 | 14.259 / 15.063 |
| Windows ARM64 | 2 | 3.22 / 3.83 | 6.19 / 4.77 | 14.259 / 15.063 |

Detached replay checked the 153 compiler units per host, original window
requests, file activity and successful DXGI events. All twelve retained
trials recorded zero idle presentations in both window states, with
positive reopen controls. Four independent edit observations kept the
same HWND, renderer generation, focused filename field and draft through
hide and reopen. Decoding the two post-reopen PNGs reproduced 209 changed
pixels in 29 columns on x64 and 177 in 28 columns on ARM64 at both depths.
The detached reports' SHA-256 values are
`7579902a60c486f89a7b487922d88764a16f27db5f890113f6f14873262d17ab`
(x64) and `1a7b3f9c4e5f447591d90a0aea990e98b6cf8494338f43523de9b8b4fea6be71`
(ARM64).

Keep the existing one-frame Mailbox policy for the retained GUI. A second
frame improved x64 scan close in this run. Scan reopen took longer on
both hosts. Prior x64 runs exceeded their own WPF limits. The small GDI
control met the four window-response limits on x64. On ARM64 neither
observed sample point belonged to the GDI window on the final attempt
before its first close. That control collected no ARM64 scan timing.

### Native results at 653f255

Both retained frame depths again met all eleven same-host WPF limits on
both targets. All twelve timed trials made two complete 100,000-file
inventory passes and recorded zero visible and hidden idle presents.
The canonical GUI that releases its window met six limits per target.
The original exported images at both retained depths showed 209 changed
pixels in 29 columns after editing the reopened field on both systems.

| Host | Scan close / reopen at depth 1, ms | Scan close / reopen at depth 2, ms | Same-host WPF maximums, ms |
| --- | ---: | ---: | ---: |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14849309986) | 12.971 / 11.700 | 8.416 / 10.019 | 24.445 / 20.065 |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14849584396) | 5.412 / 4.176 | 6.417 / 4.266 | 14.103 / 15.333 |

The detached reports bind the 153 compiler units per target, the PE
hashes, the original window and file events, the WPF budgets and the
decoded field images. Their SHA-256 values are
`b9078631c4b8c5db0d0c7613668a6e8a9fd9389cce74492090e788b6f228f7c7`
on x64 and `9761aba2ce38f58571d56744e61991b1ac280fdfd34f2b4fe3b2960b8379f0e7`
on ARM64. The separate ordinary-filename tests completed all three edits
on each host and failed at the caret-free capture with the older focus
check. [Corrected focus check](rw02-windows-text.md#focus-when-capturing-the-caret-free-field).

### Native results at 1904be7

Windows ARM64 again met all eleven WPF limits at both retained Mailbox
depths. On x64 the default one-frame profile exceeded both response limits
during scans. Each of the three uninstrumented trials completed two
100,000-file inventories. The median of their close p95 values was
38.7492 ms against a 29.882 ms limit. Reopen took 39.3171 ms against
21.083 ms. The two-frame profile also exceeded idle close. Its scan
close/reopen took 38.9101/45.5639 ms. FIFO with one frame exceeded the
same three x64 limits. ARM64 FIFO exceeded scan close at 17.5066 ms
against 13.774 ms. Keep the one-frame Mailbox measurement open on x64.
[Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14859761846) · [Original ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14857840215).

Detached comparison of the original x64 traces from `1b95ba0`,
`653f255` and `1904be7` matched the compiler and renderer inputs and
54 two-pass inventory traces. In the separate instrumented one-frame
trial at `1904be7`, all 64 over-limit closes out of 566 overlapped a
visible redraw. In 50, that redraw occupied at least half the observed
response. Within those slow redraws the median times before, inside and
after DXGI Present were 39.2886, 0.0650 and 0.0243 ms respectively.
Of the 153 over-limit reopens, 152 spent at least half the response
inside the synchronous visibility call. Focus took at most 0.8195 ms.
There were no presents in the 566 confirmed hidden intervals. The trace
locates the delay before Present and during ShowWindow. Separating frame
acquisition, rendering and scheduling requires further native observations.
The x64 dispatch report SHA-256 is
`e8f2cc88e2d1e933aa7145e5a2fb53d8f2b477a937fe26a861d558b74f8973fd`.

### Native results at 6084b23

The uninstrumented retained x64 GUI met eight of the eleven same-host
WPF limits with either Mailbox depth. Independent replay matched the
original 10 MHz counter timestamps to the ETW file work during each
pair of 100,000-file inventories. It recovered 1,474 eligible requests
at one frame and 1,150 at two frames. The following values are the median
of the three trial p95s in milliseconds.

| Windows x64 | Idle close | Scan close | Scan reopen |
| --- | ---: | ---: | ---: |
| WPF-derived limit | 14.058 | 15.793 | 18.823 |
| Retained Mailbox, one frame | 17.7725 | 22.6957 | 42.5934 |
| Retained Mailbox, two frames | 15.8489 | 30.5098 | 42.7237 |
| Visible GDI control | 3.4028 | 3.7782 | 8.4865 |

The x64 dispatch control recorded zero presentations in 277 hidden
intervals. Its single-wake variant recorded zero in 234. The older
drawing policy recorded 190 in 95. The ordinary second launch returned
the original visible window and worker with keyboard focus. The panel
icon click remained unobserved. Both ordinary and reopened filename
images matched the earlier originals. The x64 readback SHA-256 is
`c4262e92348ce80241a4dba00d2805ab5a340eebcbd6c67b909fddc6c02ffd0e`.
[Native Windows x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14864735127).

The native ARM64 retained GUI met all eleven limits with either Mailbox
depth. FIFO met ten. Its scan close p95 was 17.0024 ms against a
14.022 ms limit. [Native Windows ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14864132829).

### Separating visible frame and window timing

The x64 assessment runs an additional, instrumented executable after the
ordinary timings. It uses the same inventory and captures the actual DX12
frame-latency wait, egui update and tessellation, command preparation and
submission, DXGI presentation and Win32 visibility transitions. Each sample
is tied to its thread and native clock. The reader compares the span with
independent window, file and presentation events. The ordinary executable
supplies the eleven WPF comparisons. [Native command and required originals](../../tools/rust-qa/windows-frame-cost/README.md).

The pinned compiler checked the instrumented sources for the x64 Windows
target. Two offline reconstructions produced identical source archives
with SHA-256 `1b9dd1bfbdc59fde4329542925d36968a0b159928d99720aa3e1cfdeae5de536`.
The external package and feature selections matched the ordinary build.
Replaying the older native trace reproduced 1,167 qualifying presents and
566 hidden intervals. It lacked the new stage samples. A native run of the
instrumented executable is required to attribute the earlier delays.

### Native process exits at a1011bf and e796d30

Across these two revisions each native host completed three shipping WPF
reference trials and compiled the retained GUI in 153 units. Both Windows
architectures stopped before completing the three ordinary one-frame Rust
trials. At `e796d30` the x64 canonical GUI exited with `0xC0000374`
(heap corruption) on its second graphics generation. The ARM64 canonical
GUI exited with `0xC0000005` (access violation). The x64 contrast capture
worker independently exited with `0xC0000374`. At `a1011bf` the same
heap-corruption code occurred in the x64 two-frame control and in the
ARM64 one-frame measurement. The older logs report several other exits
only as a failure to drain. The timing recorder now records the trial
log name, quit or forced-cleanup path, process exit code and presence of
the Rust drain marker when an idle or scan trial fails during teardown.
[First x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45257863212/artifacts/14869362811)
· [First ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45257863212/artifacts/14870570105).

The first one-frame x64 Rust trial at `e796d30` completed both
100,000-file inventories and exited normally. Detached replay recovered
1,143 work-qualified window requests. The DXGI observer recorded 1,201
successful presentations in its first-pass interval. The scan close/reopen p95 values
were 41.1427/30.6124 ms against 31.314/21.813 ms on this host. Its
second scan failed on worker drain and its third idle trial failed on
GUI drain. ARM64 completed zero ordinary one-frame trials. The x64
dispatch and frame observers stopped at their incomplete ordinary
comparison. This run produced no stage trace and no new three-trial
assessment of either renderer. The x64 and ARM64 detached reports have
SHA-256 values `77a7aef59e702fc0ea76da2c025f71deaee75fa7fe2e32379720e9c6ed5f9aa3`
and `cf52d977dcf56f65ea67544139b426a7ccfedefe3943e2756ab094079b692240`.
[Second x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14874798632)
· [Second ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266/artifacts/14873982830).

### Native results at 21e794f

The retained Windows ARM64 GUI met all eleven same-host WPF limits at
both Mailbox frame depths. The default one-frame profile's scan close and
reopen p95 were 9.1267 ms and 4.0862 ms, against limits of 13.678 ms
and 14.926 ms. Both idle intervals had zero presents. FIFO met ten limits
and exceeded scan close at 19.1586 ms. The teardown GUI met six of eleven.
The independent replay recovered 153 compiler units, three WPF and twelve
Rust two-pass inventories, and thirteen retained-window behavior checks.
The readback SHA-256 is
`0056ee78d0336735c21a1602d69a68d127d057bb7b03e41b1e2259eca7d3f376`.
[Original ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14962421675) · [Keyboard and screen-reader observations](rw02-windows-desktop.md#arm64-keyboard-reader-and-input-method-at-21e794f).

On Windows x64, three ordinary one-frame Mailbox trials met nine of eleven
same-host WPF limits. Idle close took 33.5608 ms against 14.299 ms and
scan reopen took 39.3771 ms against 22.259 ms. Scan close passed at
27.4566 ms against 28.449 ms. Both idle intervals had zero presents.
Two-frame Mailbox also met nine limits and FIFO met eight. The small GDI
control met all four window-response limits. The independent x64 readback
SHA-256 is `b88dd1c905ce5044b0be255edbff19c187d1dc675ba3812c1481b852255c9cfd`.
[Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45469433661/artifacts/14963163292).

The separate x64 frame diagnostic matched 450 successful DXGI presentations
to 450 signalled frame-latency waits and observed zero presentations in 298
hidden intervals. Of 25 over-limit closes, 24 spent at least half their
response waiting for the DX12 frame-latency handle on the UI thread. Median
overlap was 30.50 ms in this wait and 0.12 ms in presentation. Of 88
over-limit reopens, 71 spent at least half their response in the direct
Win32 `ShowWindow` call and 14 in the frame-latency wait. The median
overlap with `ShowWindow` was 26.91 ms. The x64 archive SHA-256 is
`53e2f74827d7653c64b7539c72ceeb67b98d21168d84c53655b456562921df43`.
[Frame observer and replay](../../tools/rust-qa/windows-frame-cost/README.md).

The opt-in x64 comparison builds a separate one-frame Mailbox executable
that checks swapchain readiness before consuming the next visible root's
input. A busy frame schedules a bounded retry while the GUI thread can
handle other events. The recorder requires a successful DXGI present on
the same thread after an externally observed reopen and verifies the
reopened editor's screen pixels. It takes one resource and inventory
trial against the original WPF limits. Native results for this experiment
are pending. [Commands and replay](../../tools/rust-qa/windows-frame-cost/README.md#deferred-readiness-on-the-windows-x64-cpu-adapter).

### Native results at 13e4af8

On Windows ARM64 the one- and two-frame Mailbox profiles each met all
eleven same-host WPF limits. Under the 100,000-file inventory, the default
profile's median close and reopen p95 were 4.8299 and 4.4415 ms, against
limits of 14.114 and 15.236 ms. Both its idle intervals recorded zero
presentations. FIFO met ten limits. Its scan close took 19.7652 ms. The
independent replay of the original archive has SHA-256
`a8a8e142f20ce23864c8476ee8db29065e2d9847624aef8e2eb52ec2b37383c7`.
[Original ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14970348839) ·
[Keyboard, reader and input method](rw02-windows-desktop.md#arm64-reader-and-input-method-at-13e4af8).

On x64 all three retained profiles met eight of eleven limits. The
default one-frame Mailbox exceeded three same-host WPF limits.

| x64 response, median trial p95 (ms) | Retained Rust GUI | Limit |
| --- | ---: | ---: |
| Idle close | 49.4868 | 14.616 |
| Scan close | 39.7505 | 32.032 |
| Scan reopen | 37.0320 | 22.473 |

The separate GDI control passed all four window-response limits. In the
instrumented full GUI, 42 of 53 over-limit closes spent at least half the
interval in the DX12 frame wait. For 166 of 167 over-limit reopens, the
direct Win32 `ShowWindow` call occupied at least half the interval. The
native trace contained 1,157 successful presentations and none in 569
hidden intervals. The x64 readback has SHA-256
`62e948cd60ee1cfd41e3f01d7a3e58720f523d3a55003ebcf8ec2973be4deb1f`.
[Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847/artifacts/14972721704).

None of the 166 slow reopens dominated by `ShowWindow` contained a
recorded egui, eframe or wgpu stage, a forwarded eframe callback or a
DXGI present on the same thread inside that call. Together, the direct
calls occupied 97.69% of those external response intervals. The remaining
slow reopen included a separate DX12 frame wait after `ShowWindow`
returned. The earlier recorder did not time individual synchronous
window messages. The follow-up at `86ee4bd` in the same instrumented GUI records the
message ID and time in the owned window procedure and its default
processing, limited to the retained root's direct show. The offline reader
reproduced the two older traces without attributing message times to them.
[Procedure and raw records](../../tools/rust-qa/windows-frame-cost/README.md).

### Native results at 4e3dbc4

On Windows x64 both retained Mailbox profiles met all eleven limits across
three trials each. With one queued frame, scan close and reopen p95 were
21.92 and 12.01 ms against 31.07 and 22.53 ms. The canonical GUI met six
limits. Retained FIFO exceeded the scan close budget at 41.72 ms. The
small GDI control met its four window-response limits. Of 1,091 traced
frame presentations in the dispatch comparison, none began during the
379 verified hidden intervals. The preceding x64 run at `13e4af8`
exceeded three limits on the ordinary retained configuration.
[Original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14979507507) · [Prior x64 comparison](#native-results-at-13e4af8).

The separate x64 deadline-based redraw collected 779 requests during
confirmed file reads. Independent DXGI events matched 264 resumed frame
submissions in the first inventory. Its eleven single-trial values were
within the same host's WPF limits. During the first editor capture, the
isolated Windows PowerShell host could write the PNG but could not resolve
`Get-FileHash`. The editor check ended before the close and reopen. This
leaves the deadline-based comparison incomplete.
[Diagnostic and reproduction](../../tools/rust-qa/windows-frame-cost/README.md).

At `09b3087` the editor observer hashes the saved PNG with the SHA-256
stream API available in Windows PowerShell 5.1. It reproduced the digest
of the original 1,396-byte PNG under isolated PowerShell 7.7.0. Regression
checks compared differently encoded images and exercised missing and
locked files. The reopened native comparison requires a new Windows run.

On Windows ARM64 the canonical GUI met six of eleven limits from the
same host's WPF trials. Both retained Mailbox profiles met all eleven,
with three trials per profile. Each inventory ran twice over 100,000 files.
After an ordinary filename edit, each Mailbox editor had 209 changed
pixels on its reopened window. The retained FIFO profile exceeded one
limit. Scan close p95 was 20.37 ms against 13.72 ms. The separate
two-color GDI control could not identify its two screen points as belonging
to its initial window. It produced no complete timing comparison.
[ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45496492050/artifacts/14978878237).

### Presenting the full retained view with GDI

The x64 comparison keeps the complete egui view, DX12 CPU rendering, input
and accessibility. Its separate executable paints offscreen and presents
the result through GDI. The original retained GUI uses its DXGI swapchain.
The comparison uses the same native WPF limits, inventory and window
observer. The recorder requires a reopened filename edit with independent
pixel evidence. Two offline reconstructions at `c00a863` produced the same
source archive, SHA-256 `a4c2627e8145d9a33a45466b47fdc915dd507cfa6b51f7a58015d3add0ec9ad5`.
They selected the original 135 package and feature combinations. The
complete GUI passed the Windows x64 target Clippy check on Linux. Direct
checking of the changed library and its unmodified source found the same
two upstream lint expectations. Native timings for the new output path
remain open.
[Sources, native command and replay](../../tools/rust-qa/windows-gdi-present/README.md).

### Native results at 989bb33

On x64 the two retained Mailbox profiles each met nine of eleven WPF
limits. Both exceeded scan close and reopen. The three WPF inventories
provided 1,176, 1,184 and 1,189 responses qualified by concurrent file
reads. The corresponding canonical Rust scans provided 87, 86 and 85.
Each trial inventoried 100,000 files twice.

| x64 response p95 in ms | WPF limit | Mailbox, one queued frame | Mailbox, two queued frames |
| --- | ---: | ---: | ---: |
| Close during inventory | 29.63 | 41.31 | 42.12 |
| Reopen during inventory | 21.40 | 34.88 | 44.87 |

Both ordinary Mailbox editor comparisons verified 177 changed pixels
on the reopened window. FIFO exceeded three limits. The simple GDI
control met all four window-response limits.
[Original x64 builds, captures and timing records](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14986561641).

The separate full egui GDI trial compiled 153 Cargo units from the
reconstructed sources above. It copied 369 full frames during the scan
and drew none in 353 hidden intervals. Twelve reopens during observed
file reads each produced a full frame. The single trial met nine of
eleven limits. Its scan reopen was 10.49 ms, scan close was 38.73 ms
and idle close was 27.22 ms against a 13.96 ms idle-close limit. The
deadline-based DXGI experiment also met nine of eleven limits. Both
experiments saved their initial editor PNG. The isolated Windows
PowerShell 5.1 host then failed to resolve `Get-FileHash` before the
reopened editor capture. The source correction at `09b3087` is in the
next matrix. [GDI trial and replay](../../tools/rust-qa/windows-gdi-present/README.md).

The instrumented x64 run matched 615 independent DXGI presentations and
observed none in 387 hidden intervals. The DX12 frame wait accounted for
at least half the latency of 31 of 32 slow closes. Each of the 120 slow
reopens entered `ShowWindow`. Of 2,763 ms accumulated inside that call,
2,286 ms elapsed outside the application's window procedure. The trace
does not identify a specific Windows component for that time.
[WndProc and frame observer](../../tools/rust-qa/windows-frame-cost/README.md).

On ARM64 the canonical GUI met six of eleven WPF limits. The retained
Mailbox profiles with queue depths one and two met all eleven. Each
profile ran three trials with two inventories of 100,000 files per trial.
For Mailbox with one queued frame, idle close and reopen p95 were 2.84
and 4.02 ms. During inventory they were 5.81 and 4.73 ms. The independent
reopened editor comparison found 209 changed pixels for each Mailbox
profile. FIFO exceeded the scan-close limit at 20.15 ms against 14.32 ms.
The two-color GDI control could not attribute its screen points to the
test window and produced no completed timing trial.
[Original ARM64 builds and measurements](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14985155609).

Both WPF and Rust reopened in the background on an ordinary ARM64 second
launch. Rust obtained focus on the first sample after a foreground F24
launch and kept its worker. NVDA spoke all seven cues and Japanese input
committed U+3042. The canonical and retained GUIs each ran on a single
96-DPI console display. The retained process hid its original window and
kept the first DX12 device generation. The run supplied no second display
or RDP session. [ARM64 desktop archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45512900105/artifacts/14985155609) · [Ordinary launch and Shell](rw02-instance.md#retained-windows-second-launches-at-989bb33).

### Native results at f155b65

On x64 the retained Mailbox profiles with one and two queued frames each
passed all eleven WPF limits across three trials. The canonical GUI
passed six limits. FIFO passed ten with a scan-close p95 of 36.87 ms.
The WPF inventories returned 724, 717 and 723 responses during observed
file reads. The canonical Rust counts were 70, 68 and 70. Each trial
completed two passes over 100,000 files.

| x64 p95 during inventory (ms) | WPF limit | Retained Mailbox, one frame | Full egui GDI, one trial | Deferred DXGI, one trial |
| --- | ---: | ---: | ---: | ---: |
| Close | 27.47 | 11.92 | 12.80 | 13.03 |
| Reopen | 20.78 | 9.62 | 10.74 | 9.75 |

The full egui GDI and deferred DXGI experiments each met eleven timing
limits in their single trial. Both verified an edit on the original
reopened HWND. Each independent PNG comparison found 209 changed pixels
across 29 columns and 18 rows. GDI copied 689 full frames during
inventory and none during 259 hidden intervals. All 244 reopens measured
during file reads drew a complete frame. The three-trial Mailbox results
and the earlier x64 failures above show that the timing margins vary
between hosted machines.
[x64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14991846627).

Both ARM64 Mailbox queue depths again passed all eleven same-host limits.
With one queued frame the idle close and reopen p95 were 3.02 and 5.21 ms.
During inventory these were 4.10 and 4.56 ms. The canonical GUI passed
six limits. FIFO passed ten, with a scan-close p95 of 18.13 ms against
14.37 ms. Each Mailbox editor produced 177 changed pixels after reopening.
The screenshot digest and readback ran under the system Windows PowerShell
5.1 host. The small GDI control obtained no attributable screen pixels.
[ARM64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14990910738).

### Native results at 5efe1f1

On ARM64 the canonical GUI met six WPF limits and both retained Mailbox
queue depths met all eleven. With one queued frame, closing and reopening
during observed file reads took 3.48 and 4.03 ms at p95, against limits
of 13.86 and 15.09 ms. FIFO exceeded the scan-close limit at 16.85 ms.
Both Mailbox editor controls verified 177 changed pixels. The simple GDI
control obtained no attributable pixels in 969 attempts.
[ARM64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996337844).

On x64 both Mailbox profiles met nine of eleven limits. Close and reopen
during inventory exceeded the same-host WPF limits of 19.02 and 20.32 ms.
Their p95 values were 20.69 and 28.19 ms with one queued frame and 34.34
and 44.89 ms with two. Both editors showed 209 changed pixels after the
window reopened. The canonical GUI met six limits, FIFO eight and the
single deferred DXGI trial ten. The ordinary DXGI trace recorded 370
presentations and none in 249 hidden intervals. The DX12 frame wait
accounted for at least half the response time in 50 of 52 slow closes,
and the direct visibility call did so in 53 of 62 slow reopens.

The full egui GDI trial produced a valid reopened editor and completed
219 full transfers during inventory. Of the 211 transfers in the first
pass, 210 began after the next close request. Only one completed in the
required interval between a confirmed reopen and the next close request.
The minimum was five. This run therefore has no qualified full GDI
comparison. The small GDI color control met its four timing limits.
[x64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996554328).

### Native results at e2f161b

On ARM64 both retained Mailbox profiles passed all eleven same-host WPF
limits across three trials each. With one queued frame, close and reopen
during inventory took 3.27 and 3.85 ms at p95. With two they took 3.51
and 4.02 ms. The limits were 13.53 and 14.52 ms. FIFO exceeded the
scan-close limit at 18.33 ms. Replay of the original file-read and
presentation traces reproduced the measurements. In the ordinary
second-launch trial the original window reopened and the inventory
worker kept its process identity. After 41 samples over 2.02 seconds
the window still lacked foreground and keyboard focus. Launching from
the foreground keyboard fixture passed on the same runner.
[ARM64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15004635906).

On x64 the first two WPF trials completed. During the third trial the
idle resource sampler called `OpenProcess(0x0410)` on a process selected
by the process-tree observer and received Windows error 5 (access denied).
The traceback records the failed call but omits the PID and executable.
The runner produced no reference budget or Rust timing comparison.
Ordinary second launch and the foreground keyboard launch both passed.
[x64 job and traceback](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/job/139039365305) ·
[x64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15003283547).

Replaying the original PNGs and input records verified eight distinct
glyphs and all three filename edits in both the ordinary and reopened
editors on each architecture. Each runner had one 1024 × 768 display at
96 DPI on a console session. Neither supplied a mixed-DPI or RDP trial.

### Process accounting for the same-host WPF budget

The [paired recorder](../../tools/rust-qa/windows-performance/run.py) starts
each WPF or Rust subject in its own Windows job. Idle CPU is the change in
the job's cumulative user and kernel time. This includes work by members
that exit between samples. Each working-set sample sums the live members'
bytes and records the PID, byte count and cumulative CPU ticks for replay.
The sampler retains the GUI's original process handle and the required
inventory worker's handle. It rechecks membership around each observation.
A member entering or leaving invalidates the partial sample. Failure to
read an active member or loss of a required process invalidates the trial.
[Windows job accounting](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information) ·
[Job member list](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list) ·
[Process working set](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo).

The fifteen-second interval starts after the first complete sample. The
native regression observes a child in its parent's job, releases it to
consume CPU and exit with code 259, and checks the surviving parent's
working set and the job's retained CPU time. The resource limits still
come from three complete WPF trials on the candidate's host.
[Native child and portable controls](../../tools/rust-qa/windows-performance/test_owned_subject.py) ·
[Interval and membership checks](../../tools/rust-qa/windows-performance/test_recorder.py).

### Windows results at ead9fb3

On ARM64 the child-exit regression passed on the native Windows runner.
Independent replay recovered job CPU and working-set values from all
1,860 snapshots in 30 idle intervals. Each of the WPF, canonical Rust,
Mailbox with one or two queued frames, and FIFO profiles completed
three trials. Both retained Mailbox profiles met all eleven WPF limits.
During inventory, closing and reopening took 7.60 and 4.52 ms at p95
for the one-frame profile and 4.27 and 4.65 ms for two frames. The
limits on this host were 14.03 and 15.18 ms. The canonical profile
met six limits. FIFO met ten, with a scan close of 19.67 ms.

The ordinary and reopened filename checks passed. The foreground keyboard
launch focused the original window. The ordinary second launch reopened
it in the background. The complete ARM64 desktop assessment remains red.
The renderer replay under `artifacts/rust/hosted-desktop-storage/45865602688/windows/`
has SHA-256 `d2246db7af4cecd62cf5a936c25be030719d330d9fa9fc24860ee5431a2eabaa`.
[Windows ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45865602688/artifacts/15144959389).

On Windows Server 2025 x64 all three WPF reference trials completed, including
native process accounting after child exit. Independent replay verified 2,480
working-set snapshots across 40 idle intervals. During inventory the reference
limits were 30.11 ms to close and 21.49 ms to reopen. The retained DX12
Mailbox profiles met nine of eleven limits. Both filename checks passed.
An ordinary second launch focused the retained HWND. The separate foreground
keyboard trial did not pass on this host.

| x64 profile | Trials | Scan close p95, ms | Scan reopen p95, ms |
| --- | ---: | ---: | ---: |
| Retained Mailbox, one queued frame | 3 | 39.80 | 27.08 |
| Retained Mailbox, two queued frames | 3 | 44.43 | 45.62 |
| Deferred redraw diagnostic | 1 | 40.52 | 42.07 |
| Full egui GDI diagnostic | 1 | 38.49 | 11.06 |

The separately instrumented retained window spent at least half of 81 of 98
slow closes in the DX12 wait. For all 82 slow reopens, at least half the time
was inside `ShowWindow`. For 78 of those reopens at least half was inside
that call and outside the measured window procedure. The trace cannot attribute
that time to a specific Windows component. In the ordinary one-frame trial,
584 of 593 reopens during independently observed file work reached a
presentation before the next close. The full-view GDI trial reached five
of 341. Its editor test independently observed 209 changed pixels.
The x64 renderer replay has SHA-256
`93ea510511fc76f727865c2bf7ea84fb5084e5b96c251326dde56abd4fbcfbb5`.
[Windows x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45865602688/artifacts/15147426906).

#### Native GDI readback phases

The x64 GDI presenter allocated one buffer and reused it 354 times during
the scan. Of the 341 reopens with independent file activity, all 341 spent
at least half their time waiting for mapped pixels to become CPU-readable.
The median wait was 42.59 ms. The whole first frame completed in a median
53.98 ms. Buffer checkout took 0.0001 ms and the GDI transfer and flush took
0.155 ms. The buffer reuse removed repeated allocation. The synchronous
readback still occupied the GUI thread during rendering.
[Frame and source archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45865602688/artifacts/15147426906) ·
[Native recorder](../../tools/rust-qa/windows-gdi-present/README.md#reusing-the-mapped-readback-buffer).

### Windows results at 0bb39bf

On x64 both retained Mailbox profiles met eight of the eleven WPF limits.
Alongside the two inventory limits, idle close exceeded its 13.45 ms limit.
It took 27.79 ms at p95 with one queued frame and 16.73 ms with two.
The one-frame scan closed in 22.29 ms and reopened in 28.06 ms against
limits of 16.11 and 18.97 ms. Both the ordinary and reopened filename
editors completed their three edits. The foreground keyboard trial passed.
In the frame-cost trace all 111 slow reopens spent at least half their
elapsed time inside `ShowWindow` but outside the measured window procedure.
Those intervals accounted for 2,495.89 of 2,652.82 ms in total.

The ordinary one-frame trial delivered a complete DXGI present during
257 of 276 file-qualified reopens. In the separate GDI trial the inventory
worker completed both passes and the GUI made 153 full scan transfers.
None fell entirely between an observed reopen during file activity and
the following close request across the 144 eligible reopens. Checkout of
the reused buffer took 0.0005 ms at p95. Mapping and waiting for CPU-readable
pixels took 49.13 ms. This repeat supports continuing the investigation on
the ordinary DXGI path.
[Windows x64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15148738386).

Both ARM64 Mailbox profiles met all eleven WPF limits. With one queued
frame the scan closed in 8.78 ms and reopened in 4.86 ms at p95, against
limits of 14.52 and 15.52 ms. With two queued frames the corresponding
values were 8.63 and 4.82 ms. Both filename editors and the foreground
keyboard launch passed. An ordinary second launch reopened the original
window in the background. The application requested foreground and the
observer found no focus in 41 samples over 2.02 seconds.
[Windows ARM64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15149575448).

### Closing the window during a DXGI wait

In the x64 frame-cost trace at `0bb39bf`, 59 of the 63 slow closes spent
at least half their elapsed time in a DX12 frame wait. For all 59 the
external observer started its close request after the wait began and before
it returned. In 58 cases the GUI had already presented a frame since the
preceding reopen. The per-request replay at
`artifacts/rust/hosted-desktop-storage/45874234228/windows/x64-close-during-wait.json`
has SHA-256 `1e05f7611ab8453c6634c9451ffa853ebf47e4bb9bd717c4772b6206ba2a93b1`.
In the separate 16 ms deferred-redraw
trial, scan close took 14.22 ms against the 16.11 ms limit, while reopening
took 40.23 ms against 18.97 ms. At `ead9fb3` that policy exceeded both
limits. [Original x64 trials](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15148738386) ·
[Earlier comparison](#windows-results-at-ead9fb3).

The one-shot trial registers the configured swapchain's frame-latency
handle in winit's existing message wait. A pending frame can then yield to
an actual window close. To demonstrate this, the recorder must observe
that message before the window thread consumes the DXGI frame signal, see the original window
hide during independent file activity and observe a successful resumed
presentation on the reopened window. The separate executable retains the
ordinary window transitions and the same synthetic inventory worker.
[Experiment, controls and commands](../../tools/rust-qa/windows-frame-cost/README.md#one-shot-frame-readiness-in-the-windows-message-loop).

### One-shot frame readiness on Windows x64 at c52da2d

The original window processed 238 of 245 eligible close requests while its frame registration was pending. The external observer confirmed the hide before a grant, then verified 32 resumed DXGI submissions on visible reopens during file work. A further presented frame reused a slot held over a hide. The original worker completed both 100,000-file passes, and the independent pixel reader found 177 changed editor pixels on the reopened HWND. [Native build and measurements](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45890992463/artifacts/15152852412).

The one-shot trial met nine of eleven same-host WPF limits. Scan close p95 was 22.0323 ms against 19.774 ms, and scan reopen p95 was 45.8779 ms against 21.702 ms. The ordinary GUI medians were 23.1095 and 33.0625 ms respectively. Idle CPU and presentation rates were zero in both visibility states. Of 73 individual reopens slower than the WPF p95 limit, 53 had no overlap with an armed registration. The 22 that overlapped a native DXGI present spent a combined 2.6072 ms inside those calls. Windows x64 scan responsiveness therefore remains open. [Complete comparison, trace costs and original hashes](../../tools/rust-qa/windows-frame-cost/README.md#native-one-shot-trial-at-c52da2d).

## CPU rendering of the original editor meshes

The Fedora x64 offscreen comparison used the real retained editor view,
the existing five font files and the same three frames at scale 1 and
1.5. The CPU painter and original egui-wgpu renderer produced 4,986,360
identical pixels in 4,992,000 comparisons. A single pixel in the direct
mode differed by two channel values out of 255. Both painters restored
the original frame byte for byte at both scales. The offline rerun
reproduced all 18 original BGRA files. [Full per-frame observations and
reproduction](../../tools/rust-qa/windows-cpu-paint/headless/README.md).

The additional Windows x64 trial draws into a CPU buffer on the original
HWND. The same-host WPF and ordinary retained trials supply its eleven
limits. The native test records actual transfers, worker inventory
events, process resources and visible edits on the reopened window.
The Linux offscreen result establishes image fidelity for those six
frames. Windows window response and resource acceptance require native
observations. [Native build and readback](../../tools/rust-qa/windows-cpu-paint/README.md).

### Native Windows x64 CPU renderer at dddb21a

The private CPU painter met all eleven resource limits in its first
native timing trial. Three WPF trials supplied the limits on the same
host. The ordinary retained renderer met eight. Each candidate used the
same editor, WARP adapter and workload of 100,000 synthetic files.
Detached replay at `dddb21a8ddeb06fe5fbc3653f9c0b34ccf6ce89f` checked
the original compiler stream, source and library archives, executable,
ETW file events, HWND transitions and editor captures. The original ZIP
is 87,530,049 bytes with SHA-256
`302303a5c63a77c69b55e4b63c4ab99142c0beaba27c9acf95114b04d2b63d04`.
[Native archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45901012141/artifacts/15157628525).

| Same-host metric | WPF limit | Ordinary Rust median | CPU trial |
| --- | ---: | ---: | ---: |
| Startup (ms) | 1005.63 | 210.12 | 201.30 |
| Visible / hidden idle CPU (% of one core) | 4.845 / 5.676 | 0 / 0 | 0 / 0 |
| Visible / hidden working set (MiB) | 142.72 / 140.32 | 60.36 / 59.18 | 53.52 / 52.42 |
| Idle close / reopen p95 (ms) | 14.19 / 14.37 | 19.98 / 6.12 | 3.72 / 5.99 |
| Scan close / reopen p95 (ms) | 29.83 / 21.03 | 35.54 / 29.96 | 5.71 / 9.66 |
| Visible / hidden idle presentations per second | 0.134 / 0.067 | 0 / 0 | 0 / 0 |

The inventory worker (PID 944) completed both passes while the GUI
(PID 5500) kept HWND 983560. During the first pass, 422 close and 421
reopen requests met the independent file-activity criteria. Each of
the 421 reopens had a full editor-mesh transfer before the next close.
The p95 from the request to the completed GDI flush was 24.04 ms.
Measured from the first visible HWND sample it was 18.85 ms. The WPF
reopen limit in the table applies to HWND visibility. The editor
readback found 209 changed pixels after the reopen. The process quit
through Control-Q with exit 0. Both original process logs also passed
the later check for one WARP device with no active loss through Quit.

This result qualifies one explicitly selected CPU-painter trial on a
Windows x64 software adapter. Repeatability, ordinary renderer selection,
RDP and mixed-DPI operation remain to be qualified.

### Native Windows x64 CPU repeat at 972adc6

On another x64 runner the explicitly selected CPU painter again met all
eleven WPF limits. Scan close/reopen p95 was 7.11/8.32 ms against
17.72/19.08 ms. The ordinary retained median again exceeded three
limits, with idle close at 43.70 ms, scan close at 23.33 ms and scan
reopen at 32.22 ms. Both CPU process logs retained their original WARP
device through normal Quit. The same worker completed two inventories
of 100,000 files. Edits on the reopened HWND changed 177 pixels.

Of 172 file-qualified reopens, 171 had a full CPU transfer between the
independent visible-window observation and the next close request. For
those 171 frames, request to GDI flush took 13.75 ms at p95 and visible
observation to flush took 6.76 ms. On the remaining reopen three complete
transfers preceded the first visible sample. The observer found no
further complete frame before the next close, so it excluded that
reopen from the frame-latency calculation.

The detached reader verified the 87,115,707-byte original at
`972adc6aa275282ab8c4447979c5ef9a8845e416`, ZIP SHA-256
`3fb093bd45d8b6e6d2ffaa37113683cc13e5cd771fddc350be1e9e1755e17fbd`.
[Original Windows compiler, pixels and native timings](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45905250568/artifacts/15158602743).

### Automatic WARP selection on Windows x64 at 3b488ca

The retained GUI selected the CPU painter on the DX12 Microsoft Basic Render
Driver without a painter override. All eleven same-host WPF limits passed.
Scan close/reopen p95 was 4.22/9.18 ms against 18.69/20.03 ms. The ordinary
retained renderer exceeded both limits at 21.49/26.12 ms. Startup took
171.06 ms. The CPU-painted subject recorded zero idle CPU and presentations
in both visibility states and used 56.83/55.61 MiB visible/hidden.

Worker PID 1636 completed both passes over 100,000 distinct files. For
each of the 246 file-qualified reopens, the original window (HWND 1180180,
PID 944) received a complete editor-mesh transfer after the independent
visible sample and before the next close. Request to GDI flush took 17.39 ms
at p95 and visible sample to flush took 9.99 ms. The reopened editor showed
177 changed pixels and the subject exited normally. Both process logs
retained one healthy WARP device through Quit.

The separate sampler-handoff example compiled. Its observer stopped before
starting the example. Cargo reused all 155 shared units. For the application
library it reported the promoted release `.rlib` in the primary build and
the compilation-unit `.rlib` alongside the same `.rmeta` in the example.
The observer required identical output paths. This archive supplies zero
of the three required visible texture observations.

The detached timing reader verified all 140 entries of the 87,313,592-byte
original at `3b488ca8ff817012c2f2fcb47dba46c75e598ffe`, ZIP SHA-256
`d09ac6347cbc599f7761807d739116aa65d14a84d885d44c200efb7500df0543`.
[Native build, timings, compiler streams and captures](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45908644127/artifacts/15161087080).

### Visible texture handoff on Windows x64 at 10ab0b8

Automatic WARP selection again met all eleven WPF limits. During two
inventories of 100,000 files, scan close/reopen p95 was 6.53/11.07 ms
against 29.55/21.31 ms. Of 423 file-qualified reopens, 421 had a full
editor-mesh transfer after the visible sample and before the next close.
For those frames the request-to-GDI-flush p95 was 23.41 ms. Editing the
reopened field changed 209 pixels.

On the same runner, the handoff example kept HWND 1376806 throughout
three screen captures. The original texture appeared red, then displayed
the green center from its partial update. Adding a second texture with
nearest filtering switched painting to wgpu. The final capture showed
the original red corner, green center and new blue marker. All 225
sampled pixels matched their expected RGB values. The observers counted
seven complete CPU frames and two successful DXGI presents before the
final capture. The example quit normally and left an empty job.

Cargo reused all 155 shared units. The two paths reported for the GUI
library contained identical bytes, with SHA-256
`13863e362ce80936b37efcbd9a605cc883524987ade365b940f6354677362a7f`.
The detached reader checked the archived GUI and presenter libraries
against the before- and after-link hashes.

The separate device-loss trial stopped before requesting destruction.
The original GUI drew two complete CPU frames, the worker completed two
empty inventories, and the observer captured zero editor fields. This
run ended before device recreation.

The 153-entry original ZIP for
`10ab0b8a4f490eb99392905ea73da36101cf8a57` has SHA-256
`63f272b6f05b8f4888f9da93bb637ea7cbb36022057c14c470f20c346f771591`.
[Original native compilers, timing records and screen captures](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45963591446/artifacts/15184517026).

### WARP device recovery on Windows x64 at 483f053

On the hosted x64 console, GUI PID 9300 displayed `recoverydraft` in the
filename field on HWND 2425322. The observer sent `G` to destroy the GUI's
own logical WARP device. The loss callback reported `Destroyed`, and the
CPU-policy retry selected the Microsoft Basic Render Driver again. On the
new HWND 2687384, the original GUI thread still had focus in `Dateiname`.
The observer read back the restored draft and appended `after`, producing
`recoverydraftafter`. The native trace recorded 101 complete editor-mesh
transfers during the first edit and 38 during the second. Independent
decoding of the two 276 × 18 pixel crops on the replacement window confirmed
177 changed pixels across 28 columns and 18 rows.

All three job samples identified the original GUI, its inventory worker
(PID 2480) and the worker's system console host (PID 9548). The worker
finished a third empty inventory after the recovered edit. Ordinary Quit
returned zero for the GUI and worker, destroyed the replacement HWND and
left the job empty. The observer removed the isolated profile.
[Recovery observer and replay](../../tools/rust-qa/windows-cpu-paint/recovery/README.md).

The separate timing trial used the same CPU-painted executable and met all
eleven same-host WPF limits. During two inventories of 100,000 files, all
436 file-qualified reopens had a complete editor-mesh transfer before the
next close. The p95 from request to visible HWND was 10.42 ms and from
request to completed GDI transfer was 26.26 ms. The original ZIP for
`483f0534ffdddb0f677b62fcd3b5b48cc2b0fa98` contains 160 entries and has
SHA-256 `2338eba8784f413b77493bc2d9499d2d2127b5895a748115aaf46ef20407a16b`.
[Native build, timing, device-loss trace and field captures](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45979619561/artifacts/15191997288).
