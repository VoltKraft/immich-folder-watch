# Native Windows GDI visibility control

This RW-02 diagnostic measures how long the original Windows desktop takes to
show and hide one ordinary 640 × 400 client window while the reviewed Rust
inventory worker is running. It uses a private 32-bit DIB, GDI and the Win32
message loop. The existing eframe and shipping WPF trials provide comparison
values from the same runner. The result characterizes this small drawing
workload. Framework selection and the eleven application resource limits retain
their own native assessments. [Retained window measurements](../../../docs/rust/rw02-windows-window.md)
· [WPF measurement](../../../docs/rust/rw02-windows-performance.md).

## Run

From the repository root on the disposable rewrite Windows runner, use the native
MSVC developer environment and the pinned Rust compiler. Run after the normal
YAML assessment, frozen same-host WPF budget, retained-window build and complete
three-trial Mailbox measurement. The script accepts either native Windows MSVC
target. It requires a fresh target output directory.

```powershell
python -B -m unittest discover -s tools/rust-qa/windows-gdi-control -p 'test_*.py'
python -B tools/rust-qa/windows-gdi-control/assess.py $env:NATIVE_TARGET
```

The recorder validates the workflow revision, run, attempt, native architecture,
WPF budget and retained executable identity. It builds the GDI executable from
first-party Rust and the system kernel32, user32 and gdi32 APIs. The original
[worker supervisor](../gui/src/windows_worker.rs) launches the
[reviewed inventory](../windows-inventory/README.md) under the same disposable
job, synthetic profile and unused loopback endpoint. The diagnostic adds no
Cargo dependencies, fonts or graphics assets.

## What the times measure

Three idle trials each run two empty inventories. Two calibration reopens,
the existing visible and hidden settling intervals and the original process-tree
sampling warm up the control. Eight subsequent close/reopen pairs supply the
two idle p95 values. Each of three scan trials uses the existing independent
kernel-file observer to prove two complete passes over the 100,000 synthetic
files. Only close/reopen requests overlapping work in the first pass count
towards the two scan p95 values. The recorder also requires at least five
closes whose pre-close screen reads fall within file work and five reopens
whose BitBlt, flush and post-reopen screen reads all qualify on that same
pass. The retained HWND, child PID and process
identity must survive every trial. The report gives the median of each set of
three trial p95 values alongside the same host's WPF value, WPF-derived maximum
and measured retained eframe value. [Shared scan recorder](../windows-inventory/scan.py)
· [Timing budgets](../windows-performance/metrics.py).

The controller posts ordinary WM_CLOSE or writes the existing Open byte. The
timed response ends when the external observer sees the window change
visibility. The recorder separately keeps the QPC interval of every ShowWindow
call, including calls that return after the observer first sees the HWND.
For each opening the application fills the two halves of the DIB with a new
complementary color pair. The first BitBlt and successful GdiFlush for that
generation carry their own QPC interval. The previous visible frame is verified
before close, the live hidden HWND is verified before reopen, and the new
flushed frame is checked after reopen. The synthetic inventory token determines
the color sequence. [Bitmap storage](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-createdibsection)
· [Bit-block transfer](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-bitblt)
· [GDI flush](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-gdiflush).

An independent observer samples two screen pixels only after both points hit
the owned window and checks ownership again afterwards. These pixel and
generation checks run outside each measured interval. They can change the
spacing and number of scan requests. A covered display, missing generation,
changed owner, failed worker drain or incomplete ETW coverage produces an
incomplete result. The source emits the native QPC spans as part of this
diagnostic. Its actual pixels, idle warm-up and timing boundaries are recorded
alongside the values. [Window hit testing](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-windowfrompoint).

## Evidence

`artifacts/rust/windows-gdi-control/<target>/result.json` contains the source
and executable digests, WPF and retained baseline identities, per-trial window
events, worker identities, screen observations, native call times and the
four-way metric table. The scan request JSON and PID-bound file logs retain
the original event and request times. The `frames` arrays store HWND,
generation, BitBlt start, GdiFlush completion and RGB in that order.
`showWindow` holds the individual native show/hide spans. The observed
screen read uses its own `pixelQpc` interval. `visibleFrameWorkIndices`
identifies requests with independently confirmed pixels under load.
`warmupRequests`
identifies the idle calibration prefix. `evidence-hashes.json` indexes the
files in the output directory. An `observed` result requires complete coverage
even when a metric exceeds its WPF-derived limit. Iced behavior, user-input
focus, accessibility and product parity require their own native tests.
