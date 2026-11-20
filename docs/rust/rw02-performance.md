# Linux GUI performance reference

The Linux reference runs the production desktop entry point on the same machine and workload intended for the Rust comparison. The launcher uses Python 3.11+, Bubblewrap, D-Bus, Xvfb or TigerVNC Xvnc, libX11 and libXdamage. The existing pinned .NET SDK compiles the development-only frame observer inside the sandbox. [GUI acceptance](../rust-rewrite-plan.md#gui-acceptance-before-full-commitment) · [Linux launcher](../../tools/rust-qa/performance/linux.py)

## Executed reference on 2026-11-20

The Release build of Immich Folder Watch 3.0.4 mapped its window in a median **906.63 ms**. All three 100,000-file scans traversed all 100 fixture directories. During those traversals the driver recorded 35 close and 37 activation responses. Across three 15-second intervals in each visibility state, the diagnostic meter observed zero idle target render passes. Every instrumented reopening produced a new compositor pass and a visible XDamage event.

| Metric | .NET median | Candidate maximum on this host |
| --- | ---: | ---: |
| Startup to mapped window | 906.63 ms | 1,087.957 ms |
| Visible idle CPU, one core | 1.333% | 2.333% |
| Hidden idle CPU, one core | 2.733% | 3.733% |
| Visible median RSS | 230.574 MiB | 253.632 MiB |
| Hidden median RSS | 233.262 MiB | 256.589 MiB |
| Visible / hidden XDamage rectangles per second | 0 / 0 | 0.067 / 0.067 |
| Visible / hidden compositor render passes per second | 0 / 0 | 0.067 / 0.067 |
| Close-to-hidden during scan, p95 | 5.61 ms | 15.61 ms |
| Activate-to-visible during scan, p95 | 10.55 ms | 20.55 ms |

| Trial | Initial scan | Close / activation samples | Close / activation p95 | Startup |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2.6462 s | 12 / 12 | 5.37 / 10.55 ms | 904.52 ms |
| 2 | 2.7145 s | 12 / 13 | 5.61 / 10.83 ms | 937.89 ms |
| 3 | 2.5941 s | 11 / 12 | 5.91 / 7.77 ms | 906.63 ms |

The benchmark ran on Fedora 45 x86_64, kernel `7.3.4-300.fc45.x86_64`, Core i7-1370P, 20 available logical CPUs, tmpfs media, Xvnc 1.16.2, XDamage 1.1 and .NET 10.0.12. Host load and CPU frequency were uncontrolled. The application assembly carries `3.0.4+8d517342b0ebc9d0a6379be67ac32272269abded`. The complete diff from the frozen source `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc` to that build revision contains only documentation. The later `3ca5b0a` reference tests are development checks.

The ignored report is `artifacts/rust/performance/dotnet-linux-x64-xvnc-20261120.json`. Its SHA-256 is `b9053259a00df1e783ddb34af05d1ec7cb584c984f52cb9f0fe1e224dda384d1`. The recorded driver digest is `b99cae9686dc2828fac37ffb5879272542e748a8dbd08f318a60a248c2561997`, and the application DLL SHA-256 is `a308f1fa1ef1cce3f4c8db9356dab59253c1a0ab6f66257265f4a2594915a1c1`.

## Workload and isolation

Each invocation creates new mount, user, PID, IPC and network namespaces. The runner creates a software-rendered X11 screen of 1280 × 900 at depth 24 and a D-Bus session with no activation directories. It binds the system libraries, fonts, the selected build output, the driver, and the selected .NET runtime components read-only. The only writable mounts are disposable test storage, private temporary files, private device nodes and the namespace's procfs. The application has its own empty HOME, all XDG locations, and a per-user activation socket for every launch. There is no portal, tray, compositor or external network endpoint. Port 9 on the private loopback is deliberately closed. This exercises the offline path, including real status updates, reconnects and update-check failure.

1. Launch with one empty recursive `uploadNew` source, wait for its startup reconciliations and give the UI three seconds to settle. Measure the visible window. Send the window-manager close request, observe the unmap, allow another three seconds to settle and measure the hidden application. Finally send the normal `SHOW_GUI` activation message and require XDamage on the private display as a positive measurement control.
2. In a fresh profile, start the same binary with 100,000 pre-existing synthetic, zero-length `.jpg` files arranged in 100 directories. The upload-new contract leaves these files in place. A separate observer listens for Linux directory-access events in every fixture subdirectory between the worker's start and completion markers. Drive alternating close and activation requests during that scan. Time each request issued between the first and last observed directory read through its X11 unmap or map, including a response that arrives after the scan. The observer checks visibility at five-millisecond intervals.
3. In a third profile, enable the framework's existing compositor meter. Observe the same visible and hidden idle phases. Require both a working meter during initial display and a fresh render after reopening. The normal startup, CPU, RSS, and scan timings come from the first two processes, with diagnostics disabled.
4. Repeat all three launches three times. The filesystem tree and OS page cache can be warm. Each application configuration and database starts fresh. Only the subject process contributes to CPU and RSS. The X11 and D-Bus servers run separately.

Startup is elapsed wall time from process launch to the first mapped application window. CPU is combined user and system time reported by Linux as a percentage of one core. Memory is resident set size sampled every 100 ms. XDamage counts drawing notifications on the private framebuffer. A drawing operation can cover several rectangles. [X11 DAMAGE protocol](https://xorg.freedesktop.org/archive/current/doc/damageproto/damageproto.txt)

The .NET probe sets the framework's diagnostics switch in the dedicated third process and listens for `Avalonia.Diagnostic.Meter` / `avalonia.comp.render.time`. In the project's pinned Avalonia source, `ServerCompositionTarget.Render` records this histogram after acquiring a drawing context. The idle early return happens before this scope. Each observation counts a completed compositor render pass. The observer subscribes to existing instrumentation and schedules no redraw. [Reference probe](../../tools/rust-qa/performance/StartupHook.cs) · [Audited framework source pin](../../packaging/avalonia-reduced/inputs.json)

The Fedora package receipts for the executed test host identify Python 3.15.2 (`Python-2.0.1`), Bubblewrap 0.13.1 (`LGPL-2.1-or-later`), D-Bus 1.16.4 (`(AFL-2.1 OR GPL-2.0-or-later) AND GPL-2.0-or-later`), TigerVNC 1.16.2 (`GPL-2.0-or-later`), libX11 1.8.13 (`MIT AND X11`) and libXdamage 1.1.6 (`HPND-sell-variant`). The driver uses the installed tools and libraries. The reference hook compiles against the existing .NET runtime libraries. Candidate package inputs are independent of this test harness.

## Replay

Use a release build of the Linux desktop application from the source reference. The command below uses this checkout's isolated reference build and SDK. Supply a fresh output label for each run. Source provenance and the generated report identify the benchmarked binary.

```sh
python3 tools/rust-qa/performance/linux.py measure \
  --name dotnet-linux-reference \
  --entry artifacts/rust/linux-reference/bin/ImmichFolderWatch.App.Linux/release/immich-folder-watch.dll \
  --runtime-root artifacts/flatpak-local-2.11.2/sdk \
  --revision 8d517342b0ebc9d0a6379be67ac32272269abded
```

Run `measure` again with the native candidate executable, its full source revision, a fresh label, and without `--runtime-root`. The Rust application must actually read the same configuration and traverse the synthetic media tree. Its development log can use different start and completion messages. Supply exact strings via `--start-marker`, `--finish-marker`, and the actual `--passes` count. Equivalent start/end events must delimit the initial scan of the entire source. If a scan finishes too quickly to produce enough qualified input samples, the report identifies insufficient coverage.

For the native repaint comparison, `--frame-counter` enables the additional paint-only launch. Its inherited private descriptor number is in `IFW_QA_RENDER_FD`. A native test observer writes the single ASCII byte `R` on attachment and `F` once per completed target render. The driver verifies at least one pass on initial display and reopening. A candidate without this observer can still produce the external metrics. The comparison marks missing render evidence. Matching the presented-frame concept and checking the absence of hidden frame requests belong to the native renderer review.

```sh
python3 tools/rust-qa/performance/linux.py compare \
  artifacts/rust/performance/dotnet-linux-reference.json \
  artifacts/rust/performance/rust-linux-candidate.json
```

The report stores individual trials, input samples, the application binary/build-output hashes, the driver hash and the host comparison fields. The comparison uses the median of trial results. Scan latency uses each trial's nearest-rank 95th percentile for each direction before taking its median. The steady-state windows last 15 seconds each by default. A short smoke run exercises the protocol and remains ineligible for budget selection.

## Budget selection and desktop coverage

The comparison fixes maximums from the reference before measuring the candidate. Startup and input latency allow 20% above the observed median or an additional 10 ms, whichever gives more headroom. The absolute timing allowance covers two visibility polling intervals. CPU allows 20% or one percentage point of one core. Resident memory allows 10% or 4 MiB. The latter two allowances accommodate scheduling and sampled working-set variation. Each visible/hidden rendering metric allows one additional event within the measured idle interval. A continuously repainting window would exceed this allowance.

Compare the two reports with the same driver, workload, private X server build, filesystem, CPU affinity, kernel and host identity. On a fresh hosted runner, run the reference and the candidate within the same job. A candidate with a separate worker process also needs resource measurements of that worker before comparing the total application cost.

This lane covers an offline, single-process Linux X11 desktop using software rendering and warm synthetic files. Windows x64/ARM64, Linux ARM64, Wayland/compositor integration, hardware GPU behavior, assistive technology, keyboard editing and physical interaction remain separate native evidence. Native lifecycle, worker health during hidden operation, and the full UI gate remain open until the candidate runs.
