# Per-window DWM transitions on the retained Windows x64 root

The x64 frame-cost observation at `ead9fb3` found 78 of 82 slow reopens spent most of their response interval inside `ShowWindow` outside the observed window procedure. This elapsed time also counts any interval when Windows did not schedule the GUI thread. The paired experiment measures the change in **externally observed close and reopen latency during real file work** when the same retained executable asks DWM to disable transitions on its own root. [Native message timing](../windows-frame-cost/README.md#synchronous-messages-during-a-direct-reopen)

Run the existing canonical and retained measurements first, on one disposable Windows x64 runner. The fixed budget comes from its three shipping WPF trials. The ordinary retained comparison must contain three complete trials with all eleven metrics. The pair then runs one fresh ordinary GUI followed by one fresh GUI with transitions disabled. Both legs use the same pinned executable, worker, native ETW decoders, files and WARP Mailbox policy with a frame latency of one. The control records its original root without setting a DWM attribute.

```powershell
python -B tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --dwm-transitions
python -B tools/rust-qa/windows-warm-window/dwm_transitions.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/dwm-transitions
```

The x64-only setter takes the root borrowed from winit during the first device setup. It verifies the creating GUI process and thread and the top-level ancestor. The treatment requests `DWMWA_TRANSITIONS_FORCEDISABLED` with a four-byte true `BOOL` and records the returned `HRESULT`. The check requires `S_OK`. Microsoft describes this attribute as a per-window setter. Its scope ends with the window. [DWM window attributes](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute) · [DwmSetWindowAttribute](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmsetwindowattribute)

Each leg retains the independently timed requests and responses, both 100,000-file inventories and the raw decoded successful DXGI calls. At least five distinct file-qualified reopens must each contain a complete Mailbox present on the original GUI thread after the observed show and before the next close request. The file observer must also verify activity near both ends of each selected present. The replay checks every acknowledged hidden interval for drawing. A successful DXGI call measures submission to the presentation system. The separate pixel check edits the original window after both traces close, hides and reopens it, verifies its retained text and native focus, then checks the changed filename pixels from the input desktop. The root's native creation history, PID, thread and process creation time connect both observations to the same measured leg.

The standalone command reads the extracted artifact in its original layout, including both GUI executables, the retained build, compiler and source receipts, the three ordinary retained measurements and the sibling WPF directory. It recomputes both arms and prints the individual close and reopen p95 values and the frozen same-host limits. `pair.ordinaryThree` preserves the ordinary three-trial result. `pair.legs` contains the frame timestamps and field observations for each fresh process. A complete diagnostic can exceed the limits. One fixed-order pair measures the effect observed on that runner and includes scheduling and cache differences between runs. A causal attribution of earlier time inside `ShowWindow` to an animation requires more evidence.

## Native Windows x64 result at de3eec4

The ordinary and disabled instances exceeded both WPF inventory limits on the same Windows Server 2025 runner. Each process completed two 100,000-file inventory passes. Only the second process set the per-window attribute. DWM returned `S_OK` on its original root. Each window quit normally after the editor check.

| Native measurement | Ordinary | Transitions disabled | WPF maximum |
| --- | ---: | ---: | ---: |
| Scan close p95, ms | 41.4002 | 41.3420 | 30.713 |
| Scan reopen p95, ms | 30.4080 | 30.4883 | 21.942 |
| Closes observed during file reads | 563 | 587 | — |
| Reopens observed during file reads | 558 | 587 | — |
| Reopens with a complete visible present during file reads | 542 | 571 | — |
| Hidden intervals with a present | 0 of 572 | 0 of 594 | — |
| Changed editor pixels after reopening | 177 | 209 | — |

The three separate ordinary retained trials met eight of eleven limits. Idle close took 34.45 ms against 14.55 ms. Scan close and reopen took 41.85 and 29.35 ms. On this runner the per-window setting changed either inventory p95 by less than 0.1 ms. Keep the ordinary policy for the next experiment.

The detached reader from `de3eec4267f739a325354fe32f4ce8a3ff411108` reproduced both legs from the 88 original archive entries. Independent decoding confirmed the changed glyph pixels in both 276 × 18 crops at 96 DPI. The archive SHA-256 is `ae34e299c1f482d5c485fd0784a22befdd801d61355bd17dc887d227a5f8332d`. The local replay at `artifacts/rust/hosted-windows-transitions/45885538844/review.json` has SHA-256 `0f7a42267a683f110b675382ff6467f0645982a10098badfd8a0c8496f58ae73`. [Native workflow and original archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45885538844/artifacts/15150733361).
