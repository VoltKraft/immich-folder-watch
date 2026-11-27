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

## Synchronous messages during a direct reopen

The existing frame-cost scan records the public winit window procedure while the UI thread calls `ShowWindow` on its retained root. The same thread brackets the calls to `DefWindowProcW` from that procedure. The `WND` rows in `rust-1-scan.log` carry ordered QPC endpoints, parent row numbers and system message IDs. IDs at or above `WM_USER` share one category. The recorder reads neither message parameter. It keeps up to 65,536 rows in thread-local memory and flushes them after the workload. The replay rejects lost rows and requires a marker for every matching direct show, including those with zero messages.

`cost.windowMessages.shows` reports native QPC ticks for each direct call. `wndprocUnionTicks` is the union of its observed callback intervals. `outsideWndprocTicks` is the time inside `ShowWindow` outside that union. Within the union, `wndprocOtherTicks` and `defaultProcTicks` charge elapsed time to the innermost measured scope. `byMessage` groups those ticks by message ID. A nested window procedure reached during default processing therefore receives its own time. `slowReopens` clips the same intervals to each independent visibility request and response. These wall times include any suspension within the recorded scope. Earlier source-bound traces replay their original frame measurements and omit the `windowMessages` field.

## Deferred readiness on the Windows x64 CPU adapter

Run the bounded comparison after a successful same-host frame-cost diagnosis.

```powershell
python tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --deferred-frame
python tools/rust-qa/windows-frame-cost/deferred_case.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/deferred-frame
```

This separate PE selects wgpu 30.0.0 with the audited wgpu-types and wgpu-hal 30.0.2 `DontWait` descriptor on the private Windows fixture. A paintable, visible root using the DX12 CPU adapter and one-frame Mailbox queries its own swapchain handle with a zero timeout. When the handle is busy, eframe schedules the next attempt after 16 ms before consuming input, textures or draw data. An early callback reuses the pending deadline. Hiding the window clears the deadline. A continuously unavailable swapchain fails the comparison after two seconds.

The experiment takes one idle resource trial, one two-pass 100,000-file inventory and one native editor observation. Keep the complete `deferred-frame` output, the preceding `frame-cost` originals and the sibling `measured/result.json`, `observed/result.json` and `build.json`. The supplement records the changed source files, both complete modified library tree digests, the selected compiler units, the separate executable and its source reconstruction. The reader requires two successful idle calibration reopens, zero idle presents, an externally observed reopened HWND displaying edited text, and a successful interval-zero DXGI call on the same GUI process and thread inside each measured first-pass resumed present. At least one resumed frame must lie wholly between an independently observed reopen and the next close request. The eleven single-trial observations are compared with the three ordinary trial medians and the original same-host WPF limits. Stack qualification continues to use the ordinary retained build.

## One-shot frame readiness in the Windows message loop

Run the private PE on the same hosted Windows x64 desktop that recorded the three WPF, canonical and ordinary retained trials, using their original compiler receipts, executables, budget, worker and native observers. The [focused workflow](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-transitions.yaml) prepares those inputs. Run the first command on that host. To repeat the second command on a different machine, restore the native artifact under its original `artifacts/rust` layout and use its recorded checkout revision.

```powershell
python -B tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --frame-ready
python -B tools/rust-qa/windows-frame-cost/frame_ready_case.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/frame-ready
```

The visible WARP root uses a depth-one Mailbox swapchain. Its painter queries the configured DXGI frame-latency handle before taking egui input or texture changes. If the zero-time query finds it busy, the painter duplicates that handle while it owns the original surface. Winit appends the duplicate after its optional timer in the existing `MsgWaitForMultipleObjectsEx`. The original input mask, display policy, message dispatch and repaint machinery continue to operate. A successful frame wake requests one redraw on the original window. Wgpu's `DontWait` option leaves acquisition of this frame slot to the application. The two-second watchdog fails an unresponsive registration. [DXGI frame-latency handle](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_3/nf-dxgi1_3-idxgiswapchain2-getframelatencywaitableobject) · [Win32 message wait](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-msgwaitformultipleobjectsex) · [DuplicateHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-duplicatehandle)

Hiding the HWND cancels its pending redraw. If DXGI already granted a slot for the same swapchain, the next full paint can use it once. A real present spends the slot. Reconfiguration and surface destruction retire the generation and its credit. The token and generation prevent a superseded registration from waking a later window. The portable Rust tests cover timer and queue results, overdue signals, hide before drawing, hide during present and swapchain replacement.

Keep both source archives, the native compiler stream, the diagnostic PE, both subject logs, original file and DXGI traces, HWND requests and editor images under `frame-ready`, together with the workflow’s ordinary and WPF outputs. Replay matches a pending registration to a real `WM_CLOSE` on the original UI thread during inventory. It also looks for an independently visible reopen with a successful DXGI call completed inside the resumed renderer submission before the next close. It reports any reuse of a previously granted slot separately. The editor control checks changed pixels on the reopened HWND. An unobserved opportunity leaves the mechanism unverified. The eleven single-trial resource measurements are reported against the frozen WPF limits and the three ordinary trial medians.

### Native one-shot trial at c52da2d

The one-shot Windows x64 trial at `c52da2d2e33b9946871c5696727a3d4e4bb6c80f` serviced 238 of 245 file-qualified close requests issued while the original frame registration was pending. In each of the 238 cases the UI thread entered `WM_CLOSE`, cancelled the ungranted token and the external observer saw the same HWND hidden. The scan recorded 302 registrations, 62 grants, one reused slot and 941 message-queue returns while armed. Thirty-two resumed submissions contained a successful DXGI present after an externally observed reopen during file work. One further submission reused a slot granted before a confirmed hide. [Original source](https://github.com/VoltKraft/immich-folder-watch/tree/c52da2d2e33b9946871c5696727a3d4e4bb6c80f/tools/rust-qa/windows-frame-cost) · [Native archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45890992463/artifacts/15152852412).

The original GUI used HWND 2032162, PID 2400 and TID 2056. Worker PID 8828 completed both 100,000-file passes. The external observer recorded 521 successful DXGI pairs, 238 file-qualified first frames after a reopen, and zero presents during 257 hidden intervals. The editor preserved its draft and focus on the same window. Typing after the reopen changed 177 pixels across 28 columns and 18 rows at 96 DPI. The native subject exited through its normal quit command with code zero.

| Metric | Three ordinary trials, median | One-shot trial | WPF maximum |
| --- | ---: | ---: | ---: |
| Startup (ms) | 136.4134 | 153.6636 | 683.811 |
| Visible CPU (% of one core) | 0 | 0 | 3.702 |
| Hidden CPU (% of one core) | 0 | 0 | 4.221 |
| Visible working set (MiB) | 60.7031 | 62.2422 | 143.026 |
| Hidden working set (MiB) | 59.4844 | 61.0234 | 140.624 |
| Idle close p95 (ms) | 15.9681 | 4.7535 | 13.731 |
| Idle reopen p95 (ms) | 5.5214 | 5.8066 | 17.665 |
| Scan close p95 (ms) | 23.1095 | **22.0323** | **19.774** |
| Scan reopen p95 (ms) | 33.0625 | **45.8779** | **21.702** |
| Visible idle presents/s | 0 | 0 | 0.134 |
| Hidden idle presents/s | 0 | 0 | 0.067 |

Nine of the eleven measurements met the frozen same-host limits. The single experimental trial includes the instrumented event loop and renderer. Its step took 4 min 21 s for the private build, measurement and replay combined. The run provides no separate measurement of instrumentation overhead.

Among 253 file-qualified reopens, 73 individual request-to-visible times exceeded the 21.702 ms WPF p95 limit. Those 73 intervals totaled 2,530.9571 ms. Twenty overlapped an armed registration for a combined 169.2054 ms. None received a frame grant during the request. Twenty-two overlapped a native DXGI present for a combined 2.6072 ms. Of these 73 reopens, 68 had a file-qualified first present after visibility, with a further median delay of 1.9744 ms. The readiness intervals can also service window input. The time spent inside `ShowWindow`, in dispatch and in the external visibility poll cannot be separated with this trace.

The source-bound detached reader returned 0 for the observed mechanism and recorded `over-limit` for resources. Actions archive 15152852412 contains 112 CRC-verified entries and 64,690,760 bytes, with SHA-256 `181b806f08feaeba5479aa4bef38cc45ab7d1784512df54907116fb85c1f28af`. The independent request-by-request calculation is retained in `artifacts/rust/hosted-windows-transitions/45890992463/reopen-intervals.json` with SHA-256 `d00687ae376d8358fc44c2d9b39f2b8824ef1b178f71ab1c35c9128d3fe3dc84`. [Original native job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45890992463/job/140153319371).
