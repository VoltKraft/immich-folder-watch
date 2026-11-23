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
