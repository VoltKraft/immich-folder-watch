# Windows x64 WARP frame and window timing

After the ordinary one-frame Mailbox and dispatch runs on the same disposable native x64 runner, run the additional root-repaint scan from the checkout. The existing Windows performance setup supplies the exact compiler, audited assessment cache, font files, native file and presentation observers, and frozen WPF budget.

```powershell
python tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --frame-cost
python tools/rust-qa/windows-frame-cost/readback.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/frame-cost
```

The ordinary retained executable and its three dispatch controls keep their existing identity checks. Only this opt-in builds a second PE. It applies the measured-source patch to the retained eframe 0.37.0 and winit 0.30.13 sources and to the locked egui-wgpu 0.37.0 and wgpu-hal 30.0.2 archives. A local Rust crate calls documented Windows APIs. The build checks both original source archives, notices, compiler units, fonts, lock and external feature selections. The private scan uses exactly one real file-activity and DXGI trial on the synthetic 100,000-file workload.

Collect the sibling ordinary `build.json`, `compiler.jsonl`, `eframe-source.zip`, `measured/result.json` and `dispatch/result.json`. In `frame-cost`, retain top-level `*.log`, `*.json`, `compiler.jsonl`, `source.zip`, and `diagnostic.exe` from the same Actions artifact. Retain its original SHA-256 alongside the checkout revision. The archive includes the nested ordinary source bundle. With the audited offline cache and text sources prepared, `python tools/rust-qa/windows-frame-cost/prepare.py FRESH_DIRECTORY` reconstructs `source.zip` for comparison.

The reader replays the original qualifying external HWND requests, two inventoried passes, successful DXGI presents and every verified hidden interval. Each successful present in the qualified first pass must fit one real UI-thread queue present in one measured frame. That frame must have ordered update, tessellation, preparation, acquire, CPU render-pass recording, encoder finish, queue submission and presentation. The DX12 wait records its requested timeout and actual return. The backend can continue after a timed-out wait. The report preserves each such frame, the requested timeout and the observed wait and DXGI timestamps. A missing waitable object, failed wait, absent stage, foreign identity or dropped measurement makes the diagnostic incomplete. The visibility path records the public winit call, its direct or flags route and the actual HWND, ShowWindow command and return. The return reports the preceding visibility.

Slow responses use the unchanged WPF maximum for the corresponding action. Their IDs refer to raw nested spans on the one measured process and thread. `--span ID` prints the exact call QPC pair, bracketing counter samples, call argument/result and native HWND when applicable. Overlap in milliseconds uses a union within each stage label. An acquire includes its wait. Different labels can overlap. The bound is 262,144 boundary records. Raw files and the partial result are kept when an observer or readback fails.

The subject requests dispatch statistics for its own executing thread with zero hardware counters. Each boundary brackets the read with QPC and retains the Win32 return code. Successful reads supply cumulative thread cycles and context switches, plus the wait-reason bits since the preceding read. A refused read records the error and tries the ordinary thread-cycle query. Cycles and switch counts describe complete bracketing samples. They provide no exact duration per scheduling state or wait reason. The GPU execution timeline, other processes and compositor scheduling are outside this observation. Instrumentation affects this separate process's timings. The eleven acceptance metrics always come from the ordinary build. [Microsoft PERFORMANCE_DATA](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-performance_data)

## Deferred readiness on the Windows x64 CPU adapter

Run the bounded comparison after a successful same-host frame-cost diagnosis.

```powershell
python tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --deferred-frame
python tools/rust-qa/windows-frame-cost/deferred_case.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/deferred-frame
```

This separate PE selects wgpu 30.0.0 with the audited wgpu-types and wgpu-hal 30.0.2 `DontWait` descriptor on the private Windows fixture. A paintable, visible root using the DX12 CPU adapter and one-frame Mailbox queries its own swapchain handle with a zero timeout. When the handle is busy, eframe schedules the next attempt after 16 ms before consuming input, textures or draw data. An early callback reuses the pending deadline. Hiding the window clears the deadline. A continuously unavailable swapchain fails the comparison after two seconds.

The experiment takes one idle resource trial, one two-pass 100,000-file inventory and one native editor observation. Keep the complete `deferred-frame` output, the preceding `frame-cost` originals and the sibling `measured/result.json`, `observed/result.json` and `build.json`. The supplement records the changed source files, both complete modified library tree digests, the selected compiler units, the separate executable and its source reconstruction. The reader requires two successful idle calibration reopens, zero idle presents, an externally observed reopened HWND displaying edited text, and a successful interval-zero DXGI call on the same GUI process and thread inside each measured first-pass resumed present. At least one resumed frame must lie wholly between an independently observed reopen and the next close request. The eleven single-trial observations are compared with the three ordinary trial medians and the original same-host WPF limits. Stack qualification continues to use the ordinary retained build.
