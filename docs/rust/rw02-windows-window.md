# Windows window lifetime and DX12 allocation

The existing Windows GUI tears down its root window and renderer on ordinary close. In native x64 run `44941845642`, each of the three Rust logs recorded 11 DX12 generations. The GUI ran under the Microsoft Basic Render Driver at 1024 × 768 and 96 DPI. A first-party comparison variant retains the window and requests the graphics allocator's smaller blocks. Native qualification of this variant is pending. [Original Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642/job/136960549014) · [Paired WPF method](rw02-windows-performance.md).

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

The variant calls egui-wgpu's existing device-descriptor builder with the actual adapter and changes `memory_hints` to `MemoryUsage`. The default descriptor uses `Performance`. In the pinned wgpu-hal 30.0.2 source, the device/host minimum block sizes are 128/64 MiB for `Performance` and 8/4 MiB for `MemoryUsage`. The DX12 backend consumes those values when configuring suballocation. The variant preserves the original feature requests, limits and adapter selection. The targeted value is reserved heap capacity. Its effect on Windows process residency requires an OS measurement. [DX12 allocator and report](https://github.com/gfx-rs/wgpu/blob/v30.0.2/wgpu-hal/src/dx12/suballocation.rs) · [Pinned GUI packages and features](../../rust/audit/gui-profile.json).

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
```

Preserve `build.json`, `observed/**` and `measured/**` under `artifacts/rust/windows-warm-window/<target>/`. Build receipts include the canonical executable digest, reviewed graph, staged first-party source digests, font digests and native candidate executable digest. The builder checks the three canonical file digests before applying the variant in a fresh private source tree. [Build](../../tools/rust-qa/windows-warm-window/build.py) · [Timed comparison](../../tools/rust-qa/windows-warm-window/measure.py).

Four portable checks passed for staged source, resident-page classification, timed device settings and refusal of a modified or different-run budget. The pinned Rust 1.100.0 toolchain passed rustfmt and Clippy for the candidate on both Windows MSVC architectures and native Linux x64, including test targets. For each Windows target the staged and ordinary manifests resolved to the same 135 package/version/feature entries. The pinned external egui source emitted its existing `std::f32::EPSILON` deprecation. Native Windows execution supplies the HWND, input, allocator, latency and working-set observations. [Portable checks](../../tools/rust-qa/windows-warm-window/test_variant.py).
