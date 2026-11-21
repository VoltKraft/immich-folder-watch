# Linux GUI performance reference

The Linux comparison runs the shipping desktop entry point and the Rust desktop feasibility binary on the same machine. The launcher uses Python 3.11+, Bubblewrap, D-Bus, Xvfb or TigerVNC Xvnc, libX11 and libXdamage. The existing pinned .NET SDK compiles the development-only frame observer inside the sandbox. [GUI acceptance](../rust-rewrite-plan.md#gui-acceptance-before-full-commitment) · [Linux launcher](../../tools/rust-qa/performance/linux.py)

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

## Paired X11 measurements

The native desktop feasibility binary passed **all eleven fixed Linux x64 X11 limits** on the median of three trials. The paired .NET and Rust runs used identical 25-ms intervals between successive input probes. This provides enough samples during the faster native scan. Both used driver SHA-256 `344a6146d90574eb30d46a9cb970d5f517fa7365c353ea4595069e5ad587b5d8` and the original limits. Each first close arrived immediately after the initial window mapped and counts in the per-trial p95.

| Metric | Paired .NET | Rust after mapping correction | Fixed maximum |
| --- | ---: | ---: | ---: |
| Startup to mapped window | 979.57 ms | 176.99 ms | 1,087.957 ms |
| Visible / hidden CPU, one core | 1.200 / 1.933% | 0.000 / 0.000% | 2.333 / 3.733% |
| Visible / hidden RSS | 230.430 / 233.027 MiB | 125.617 / 125.617 MiB | 253.632 / 256.589 MiB |
| Visible / hidden XDamage rectangles per second | 0 / 0 | 0 / 0 | 0.067 / 0.067 |
| Visible / hidden render passes per second | 0 / 0 | 0 / 0 | 0.067 / 0.067 |
| Close-to-hidden during scan, p95 | 5.67 ms | 10.51 ms | 15.61 ms |
| Activate-to-visible during scan, p95 | 6.12 ms | 1.44 ms | 20.55 ms |

| Rust trial | Inventory window | Close / activation samples | Close / activation p95 | Reopen presentations / XDamage rectangles |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1.0237 s | 16 / 15 | 10.45 / 1.57 ms | 3 / 3 |
| 2 | 1.1296 s | 17 / 17 | 10.51 / 1.44 ms | 3 / 3 |
| 3 | 1.0246 s | 16 / 15 | 15.76 / 1.32 ms | 1 / 1 |

Each trial visited all 100 directories and completed both 100,000-file inventories. The third trial's close p95 exceeded the fixed limit by 0.15 ms. The sampled process tree contained both the supervisor and worker. CPU values are quantized by Linux process ticks and the measurement interval. The earlier complete retained-window build ran the same pair and passed ten limits. It closed in 52.49 ms and activated in 1.33 ms.

The paired .NET report `dotnet-linux-x64-paired-20261120.json` has SHA-256 `1b77f0420ca6efaf9c2e560e8419bbfd5dc36178217120ef3be0ce780861df30`. The corrected Rust report `rust-linux-x64-paired-map-20261120.json` has SHA-256 `51da6bd468804e8579a4ee9f0a05c7e076f39d6f31555bf3fbea66f9e0f3c885`. Both reside in `artifacts/rust/performance/`. The corrected subject came from development sources on base `81de35fd787d74f6f9e56f9e84ed2dd6f26a9fe6`. Its staged `native-map-confirmed` directory holds the exact source receipts. The GUI binary SHA-256 is `5bd230d24989fc251b789bb152afdf78e5a4353fda1150e809f6a250ef61af3f` and the worker SHA-256 is `170a630b582ff3fc91716992632792c3dad7dc969aa84986617de0a60ed8aec4`.

The same GUI binary passed the four lifecycle cases and the AT-SPI keyboard, language, masked-text and clipboard observations on both Xvnc and headless Mutter. Every exercised X11 close and reopen unmapped and remapped the same window ID. Each exercised Wayland close released the original toplevel and subsequent activation mapped a new surface. Background startup followed by Quit generated zero maps on both backends. These tests used the default X11 presentation settings and the previously recorded Wayland Mesa Mailbox setting.

In a separate live-worker check, the driver hid the real window, added one synthetic JPEG, and observed the next inventory rediscover it in 4.8202 seconds. Linux independently recorded a read on its directory while the window remained unmapped. The application then reopened the same X11 window, hid it again and drained the worker on Quit with exit 0. Verify all retained local reports with `sha256sum --check tools/rust-qa/performance/evidence/linux-x64.sha256`. [Hidden-worker observer](../../tools/rust-qa/performance/worker/check_hidden.py)

## Hosted Linux results at 8a8adaa

On both Ubuntu architectures the reference and candidate each completed three
100,000-file trials on the same host. All eleven Rust metrics met the limits
from that host’s .NET run. Each pair below gives the Rust median and maximum
allowed by the reference. The startup endpoint is the first mapped window.

| X11 measurement | Ubuntu x64, Rust / limit | Ubuntu ARM64, Rust / limit |
| --- | ---: | ---: |
| Startup, ms | 187.69 / 1,226.724 | 208.62 / 1,507.081 |
| Visible idle CPU, % of one core | 0 / 2.2 | 0 / 1.667 |
| Hidden idle CPU, % of one core | 0 / 2.333 | 0.067 / 3.0 |
| Visible RSS, MiB | 124.562 / 248.661 | 119.309 / 252.610 |
| Hidden RSS, MiB | 124.562 / 251.269 | 119.309 / 255.742 |
| Visible and hidden damage rectangles and render passes, each per second | 0 / 0.067 | 0 / 0.067 |
| Show during scan, p95 ms | 0.75 / 15.89 | 0.92 / 16.18 |
| Close during scan, p95 ms | 0.30 / 11.04 | 0.38 / 15.59 |

The files are `performance/hosted-{dotnet,rust}-<target>.json` in each archive.
The four eligible reports retain every measurement window and the reference
budgets. [Archive identities](rw02-native-gui.md#native-follow-up-at-8a8adaa)
and [hosted execution](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642).

## Workload and isolation

Each invocation creates new mount, user, PID, IPC and network namespaces. The runner creates a software-rendered X11 screen of 1280 × 900 at depth 24 and a D-Bus session with no activation directories. It binds the system libraries, fonts, the selected build output, the driver, and the selected .NET runtime components read-only. The only writable mounts are disposable test storage, private temporary files, private device nodes and the namespace's procfs. The application has its own empty HOME, all XDG locations, and a per-user activation socket for every launch. There is no portal, tray, compositor or external network endpoint. Port 9 on the private loopback is deliberately closed. This exercises the offline path, including real status updates, reconnects and update-check failure.

1. Launch with one empty recursive `uploadNew` source, wait for its startup reconciliations and give the UI three seconds to settle. Measure the visible window. Send the window-manager close request, observe the unmap, allow another three seconds to settle and measure the hidden application. Finally activate the window through the normal entry point and require XDamage on the private display. The .NET application receives `SHOW_GUI` over its per-user socket. The Rust supervisor receives `org.freedesktop.Application.Activate` on the private session bus.
2. In a fresh profile, start the same binary with 100,000 pre-existing synthetic, zero-length `.jpg` files arranged in 100 directories. The upload-new contract leaves these files in place. A separate observer listens for Linux directory-access events in every fixture subdirectory between the worker's start and completion markers. Drive alternating close and activation requests during that scan. Time each request issued between the first and last observed directory read through its X11 unmap or map, including a response that arrives after the scan. The observer checks visibility at five-millisecond intervals.
3. In a third profile, enable the framework's existing compositor meter. Observe the same visible and hidden idle phases. Require both a working meter during initial display and a fresh render after reopening. The normal startup, CPU, RSS, and scan timings come from the first two processes, with diagnostics disabled.
4. Repeat all three launches three times. The filesystem tree and OS page cache can be warm. Each application configuration and database starts fresh. The original run measured the single .NET host process. The paired runner sums CPU and RSS across the entire live subject process tree, including child CPU accrued by waited-for children. Summed RSS counts resident pages shared by two subject processes in each process. The X11 server, session bus and observation process remain outside the subject tree.

Startup is elapsed wall time from process launch to the first mapped application window. CPU is combined user and system time reported by Linux as a percentage of one core. Memory is resident set size sampled every 100 ms. XDamage counts drawing notifications on the private framebuffer. A drawing operation can cover several rectangles. [X11 DAMAGE protocol](https://xorg.freedesktop.org/archive/current/doc/damageproto/damageproto.txt)

The .NET probe sets the framework's diagnostics switch in the dedicated third process and listens for `Avalonia.Diagnostic.Meter` / `avalonia.comp.render.time`. In the project's pinned Avalonia source, `ServerCompositionTarget.Render` records this histogram after acquiring a drawing context. The idle early return happens before this scope. Each observation counts a completed compositor render pass. The observer subscribes to existing instrumentation and schedules no redraw. [Reference probe](../../tools/rust-qa/performance/StartupHook.cs) · [Audited framework source pin](../../packaging/avalonia-reduced/inputs.json)

The Fedora package receipts for the executed test host identify Python 3.15.2 (`Python-2.0.1`), Bubblewrap 0.13.1 (`LGPL-2.1-or-later`), D-Bus 1.16.4 (`(AFL-2.1 OR GPL-2.0-or-later) AND GPL-2.0-or-later`), TigerVNC 1.16.2 (`GPL-2.0-or-later`), libX11 1.8.13 (`MIT AND X11`) and libXdamage 1.1.6 (`HPND-sell-variant`). The driver uses the installed tools and libraries. The reference hook compiles against the existing .NET runtime libraries. Candidate package inputs are independent of this test harness.

## Replay

The integrated Linux x64 GUI at `417a897` passed all 11 original budgets
in three further 100,000-file trials on the same Fedora X11 host. The median
startup was 177.91 ms and both visible and hidden median RSS were 127.355 MiB.
The idle windows recorded zero CPU ticks, render passes and XDamage events.
During the scans, the median of the trial p95 latencies was 1.50 ms to reopen
and 10.66 ms to close. The native executable SHA-256 was
`80898c73bf97c9d6622ef837cd5361810b041e5d007a1fe742d32ad7921c1002`.
The report `rust-linux-x64-integrated-graphics-final.json` in the performance
artifact directory has SHA-256
`eb5813215acc30fa22fd9f436001a9f4060da7fabf85a8c4af1b6658fe1da986`.
The Ubuntu jobs build the shipping .NET reference on each fresh host, save
its measured budgets, then run the same workload on the Rust subject.

At `8b071ab` both Ubuntu hosts built the shipping reference. Their installed
.NET packs made the old runtime-directory search ambiguous or unmatched, so
the timing trials never started. The driver now obtains the reference pack
from the pinned SDK's own `KnownFrameworkReference` for `net10.0`. Its
20,000-file Fedora smoke run built the reference frame counter, completed
the idle and scan trials, and recorded render passes. This short run is
ineligible for budget selection. [Hosted assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452).

Use a Release build of the Linux desktop application from the source reference. The commands below use this checkout's isolated reference build, SDK, checksum-pinned Rust toolchain, inspected GUI registry and filtered YAML sources. Each run requires a fresh output label. Preserve the original fixed-budget report and verify its SHA-256 against the value above before replaying the pair. Select the full Git revision of the built Rust source. Each staged binary also carries a receipt binding its exact source-file hashes.

```sh
python3 tools/rust-qa/performance/linux.py measure \
  --name dotnet-linux-reference \
  --entry artifacts/rust/linux-reference/bin/ImmichFolderWatch.App.Linux/release/immich-folder-watch.dll \
  --runtime-root artifacts/flatpak-local-2.11.2/sdk \
  --revision 8d517342b0ebc9d0a6379be67ac32272269abded \
  --input-interval-ms 25 \
  --budget-from artifacts/rust/performance/dotnet-linux-x64-xvnc-20261120.json

python3 tools/rust-qa/gui/build.py
python3 tools/rust-qa/performance/build_worker.py --name gui-with-inventory
python3 tools/rust-qa/performance/linux.py measure \
  --name rust-linux-candidate \
  --entry artifacts/rust/performance/subjects/gui-with-inventory/native-gui-assessment \
  --revision "$(git rev-parse HEAD)" --desktop-spike --frame-counter \
  --input-interval-ms 25 --start-marker INVENTORY_STARTED --finish-marker INVENTORY_COMPLETE
python3 tools/rust-qa/performance/worker/check_hidden.py gui-with-inventory
```

Run `measure` again with the native candidate executable, its full source revision, a fresh label, and without `--runtime-root`. The Rust application must actually read the same configuration and traverse the synthetic media tree. Its development log can use different start and completion messages. Supply exact strings via `--start-marker`, `--finish-marker`, and the actual `--passes` count. Equivalent start/end events must delimit the initial scan of the entire source. If a scan finishes too quickly to produce enough qualified input samples, the report identifies insufficient coverage.

For the native repaint comparison, `--frame-counter` enables the additional paint-only launch. Its inherited private descriptor number is in `IFW_QA_RENDER_FD`. A native test observer writes the single ASCII byte `R` on attachment and `F` once per accepted target presentation. The isolated Vulkan observer forwards the pinned ash loader's dispatch to the system Vulkan loader. It counts only successful or suboptimal `vkQueuePresentKHR` return values. The driver requires an initial presentation and a fresh one after reopening, with independent XDamage evidence. The ordinary Rust startup, CPU, memory and latency runs use the system loader directly. The .NET diagnostic counts completed compositor drawing scopes. Neither counter measures physical display scanout. [Vulkan presentation contract](https://docs.vulkan.org/refpages/latest/refpages/source/vkQueuePresentKHR.html)

```sh
python3 tools/rust-qa/performance/linux.py compare \
  artifacts/rust/performance/dotnet-linux-reference.json \
  artifacts/rust/performance/rust-linux-candidate.json
```

The report stores individual trials, input samples, the application binary/build-output hashes, the driver hash and the host comparison fields. The comparison uses the median of trial results. Scan latency uses each trial's nearest-rank 95th percentile for each direction before taking its median. The steady-state windows last 15 seconds each by default. A short smoke run exercises the protocol and remains ineligible for budget selection.

## Budget selection and desktop coverage

The comparison fixes maximums from the reference before measuring the candidate. Startup and input latency allow 20% above the observed median or an additional 10 ms, whichever gives more headroom. The absolute timing allowance covers two visibility polling intervals. CPU allows 20% or one percentage point of one core. Resident memory allows 10% or 4 MiB. The latter two allowances accommodate scheduling and sampled working-set variation. Each visible/hidden rendering metric allows one additional event within the measured idle interval. A continuously repainting window would exceed this allowance.

Compare the two reports with the same driver, workload, private X server build, filesystem, CPU affinity, kernel and host identity. On a fresh hosted runner, run the reference and the candidate within the same job. For the development Rust subject the driver requires at least two processes in the resource samples and checks the actual file and change counts for both initial inventories.

## Rust feasibility workload

The development GUI launches the optional native inventory worker only when the private launcher selects `--desktop-spike`. It owns the worker's control pipe through shutdown. The worker reads the same generated YAML as .NET through the audited serde-saphyr 2.2.0 deserialize feature. It opens the authorized root once, enumerates each real child directory through `safe-fs`, opens regular JPEGs through their parent handles and records length and modification time from each open file. Both initial passes rebuild and compare all fingerprints. Five-second polling sweeps continue while hidden, and a bounded TCP connection to the closed synthetic loopback endpoint checks offline status every 30 seconds. The worker does no transfer. This exercises real configuration decoding and inventory/control-plane costs. The shipping .NET database, realtime client, watcher event handling and full GUI remain additional workloads for the final candidate comparison.

The stage builder checks the published package hashes, source-file manifests and exact enabled features against the existing filtered YAML review. It builds with the pinned compiler, frozen lockfile and read-only vendor tree inside Bubblewrap. The native GUI binary and its prior build receipt are copied into the staged subject. A second receipt binds the worker, optional observer and source files. The Fedora host uses Vulkan loader 1.4.350.0 (`Apache-2.0`), Mesa Vulkan drivers 26.2.7 (`MIT AND BSD-3-Clause AND SGI-B-2.0`) and PyGObject 3.58.1 (`LGPL-2.1-or-later`). All are host-side or development-only inputs. [Worker build](../../tools/rust-qa/performance/build_worker.py) · [Inventory worker](../../tools/rust-qa/performance/worker/src/main.rs)

The first Rust pilot destroyed its X11 window and GPU surface on every close. During a 1.0302-second inventory the observer measured an activation p95 of 38.65 ms. Retaining that window and sending an egui repaint through the hidden viewport raised the pilot's activation p95 to 86.42 ms. Waking the native event loop directly brought it to 6.27 ms. The supervisor still creates the first window only after the lifecycle requests visibility. Winit's X11 backend implements `Window::request_redraw` by sending the window ID to the event loop. The D-Bus thread uses this wake after enqueueing a command. The native window handler on the main thread owns close, map, unmap, focus, shutdown and the lifecycle transitions. On Wayland, winit 0.30.13 implements `set_visible` as a no-op and reports `None` for visibility. Closing a Wayland toplevel releases it and activating creates another toplevel. [Native window handler](../../tools/rust-qa/gui/src/native_window.rs) · [Window supervisor](../../tools/rust-qa/gui/src/main.rs)

Two separate traces of the first slow close recorded the main thread's OS wait state and the corresponding native event sequence. Four successive sleeps of approximately 10 ms coincided with initial rendering and the IME, focus and visibility notifications. Winit updates its X11 visibility cache after the `Occluded` callback returns. Eframe renders synchronously when that cache reports a hidden window, then sleeps for 10 ms. The handler now retains up to eight pending mapping notifications in arrival order and dispatches them when winit has processed the server's visibility acknowledgement. Controls stay on the UI thread, and ordinary input such as key events flushes pending state before dispatch. An X11 expose or a deferred redraw runs the normal eframe renderer after mapping. [Winit event dispatch](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/src/platform_impl/linux/x11/event_processor.rs) · [Eframe redraw handling](https://github.com/emilk/egui/blob/3c6eb8261c3293ad9c7ea1ed58487e038860ebef/crates/eframe/src/native/run.rs) · [Eframe visibility wait](https://github.com/emilk/egui/blob/3c6eb8261c3293ad9c7ea1ed58487e038860ebef/crates/eframe/src/native/winit_integration.rs)

The Linux handler imports the same winit 0.30.13 that eframe already selects. Cargo added one local dependency edge to the lockfile. Regenerating the four unpacked-source graph reports yielded the prior package versions, features, checksums, native declarations and license findings. Replacing only the new `lockSha256` in each report reproduces its previous report SHA-256. The resulting lock SHA-256 is `3d266972f104fae3eb992e8198d25eace401f5c9fe1ed282aa180612fe12cc4a`. [GUI source review](rw02-gui-dependencies.md) · [Profile](../../rust/audit/gui-profile.json)

This performance lane covers offline Linux x64 X11 with software rendering and warm synthetic files. Eframe's public `create_native` wrapper exposes the winit loop result. After the first completed frame, a renderer failure can also cause an internal eframe exit. Propagating and recovering such a failure requires a separate graphics test. Windows x64/ARM64, Linux ARM64, Wayland resource consumption, hardware GPU behavior, assistive technology and physical interaction have their own native evidence requirements. [Native desktop observations](rw02-native-gui.md)
