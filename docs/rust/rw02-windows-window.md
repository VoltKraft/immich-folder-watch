# Windows window lifetime and DX12 allocation

The canonical Windows GUI tears down its root window and renderer on ordinary close. In native x64 run `44941845642`, each of the three Rust logs recorded 11 DX12 generations. The GUI ran under the Microsoft Basic Render Driver at 1024 × 768 and 96 DPI. A first-party comparison retains the window and requests smaller allocator blocks. Two paired native runs qualified its memory and idle performance on x64 and ARM64. Active inventory transitions still exceeded the WPF thresholds. [Original Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642/job/136960549014) · [Paired WPF results](rw02-windows-performance.md#completed-paired-inventories).

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

The new comparison keeps the retained executable, allocator, permitted frame latency of one, WPF budget and file workload identical on both sides. For the actual DX12 CPU adapter it queries the capabilities of an unconfigured wgpu surface for the same owned HWND. wgpu-hal creates its swap chain when the surface is configured. An advertised `Mailbox` mode requests `Present(0, 0)`; the earlier `Fifo` requests `Present(1, 0)`. Each mode preserves composition without the tearing flag. Hardware adapters keep the ordinary policy. A new scan observer checks successful DXGI starts and stops on the GUI PID and the same native performance-counter clock as the inventory and request timeline. The report records the number of overlapping requests and the longest overlap per request. Time before frame acquisition and physical display latency remain outside this trace. Native results for this change are pending. [CPU adapter and HWND policy](../../tools/rust-qa/windows-warm-window/windows_present.rs) · [Pinned DX12 implementation](https://github.com/gfx-rs/wgpu/blob/v30.0.2/wgpu-hal/src/dx12/mod.rs) · [Microsoft DXGI presentation parameters](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-idxgiswapchain-present) · [QPC and file-work correlation](../../tools/rust-qa/windows-warm-window/scan_present.py).

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
```

Preserve `build.json`, `observed/**`, `measured/**` and `measured-fifo/**` under `artifacts/rust/windows-warm-window/<target>/`. The first timed command enforces all eleven WPF-derived maximums. The second records the earlier FIFO policy and binds both complete three-trial comparisons to the same revision, binary, host run, budget and workload. An over-budget control remains visible in its result. Build receipts include the canonical executable digest, reviewed graph, staged first-party source digests, font digests and native candidate executable digest. [Build](../../tools/rust-qa/windows-warm-window/build.py) · [Timed comparison](../../tools/rust-qa/windows-warm-window/measure.py).

The portable checks cover staged source, resident-page classification, timed device settings, the shared WPF budget and the real-clock correlation rules. The pinned Rust 1.100.0 toolchain passed rustfmt and Clippy for the Windows presentation change on both MSVC architectures, including test targets. For each Windows target the original retained-window and ordinary manifests resolved to the same 135 package/version/feature entries. The pinned external egui source emitted its existing `std::f32::EPSILON` deprecation. [Portable checks](../../tools/rust-qa/windows-warm-window/test_variant.py).
