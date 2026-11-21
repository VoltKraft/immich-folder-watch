# Intel Wayland device-loss recovery

The original private x64 Intel trace stopped while editing the filename on
graphics generation one. Its outstanding Wayland frame callback received no
completion before the editor timed out. The application's loss action had
yet to run. A separate Mesa Mailbox override allowed the original GUI to
reach recovery. The repeated assessment uses the application default and
observes each adapter's advertised presentation modes.
[Earlier Intel comparison](rw02-graphics.md#intel-input-on-a-virtual-mutter-output).

The Linux adapter selector queries wgpu for the selected Vulkan adapter and
its compatible surface. For a Wayland window with Mailbox in that response,
eframe requests Mailbox for that surface. This covers the first hardware
window as well as the new software window after a loss. An adapter with
different capabilities retains eframe's original configuration. The
Wayland window check uses winit's native window handle.
[Reviewed wgpu-types 30.0.2 source archive, `src/surface.rs`](https://static.crates.io/crates/wgpu-types/wgpu-types-30.0.2.crate).

## Native observation

Each trial creates a private Mutter virtual output, a private session bus
and a new synthetic home. The existing graphics observer exposes one Intel
render node and follows the application surface on the virtual output
using PipeWire and GStreamer. It writes a real filename through the Mutter
virtual keyboard, destroys only the application's logical device, observes
the second renderer and types another key. An independent AT-SPI reader
checks the restored draft and resulting text. The inventory worker must
process a newly created file with its original PID and process start time.
[Shared recovery scenario](../../tools/rust-qa/graphics/scenarios.py).

After recovery the observer tabs to the language button and confirms its
accessible role and focus. After one second to settle, it counts nonempty
buffer commits on the titled application surface for 15 seconds. A native
close releases that window before a second 15-second interval. The bounds
are at most one visible commit and zero hidden commits. The observer also
records the GUI and worker's combined CPU ticks. Three independently
started sessions must pass using the same GUI and worker binaries.
[Resource budget](rw02-performance.md) · [Idle observer](../../tools/rust-qa/wayland-recovery/idle.py).

On a native Fedora x64 host with the already verified Intel render node,
stage a freshly built GUI and worker through the existing integrated
graphics procedure. Use three fresh output labels.
[Build and staging commands](rw02-graphics.md#canonical-gui-integration).

```sh
subject=artifacts/rust/graphics/graphics-current/subject
for trial in 1 2 3; do
  python3 tools/rust-qa/wayland-recovery/observe.py --name "wayland-recovery-$trial" --subject "$subject" || exit 1
done
python3 tools/rust-qa/wayland-recovery/verify.py artifacts/rust/graphics/wayland-recovery-{1,2,3}
```

## Executed comparison

The comparison used the native x86_64 Rust release builder with Ubuntu
24.04.5 build tools and the same audited 235-package graph. The two build
receipts differed only in the hash of `graphics.rs` and the resulting
executable. The initial GUI at `8a8adaa` produced SHA-256
`322b2f68aa6c706b493f5403b16d168332d0d1a3530b9231d29904ccffd131c2`.
The surface-capability change produced
`bf32b8928c9245c1b34df3eb00447f7000b9ddce8492b9f8c75d9a3cd2bafe0b`.
Both ran on Fedora x64 with Intel Iris Xe and llvmpipe. The private Vulkan
render node was `226:128`. Each client rendered into Mutter's 1280 × 900
virtual output with an active private PipeWire consumer.

The new baseline run produced 14 captured monitor frames, one native
window and one ready graphics generation. The focused editor failed to
accept the next key. The client trace contained 10 FIFO set-barrier and
19 wait-barrier requests. The capability-based candidate reported
`[Mailbox, Fifo]` on both Intel and llvmpipe and selected Mailbox on both
generations. Its traces contain zero FIFO barrier requests. The captures
do not establish a cause inside Mesa or Mutter.

| Independent session | Nonempty monitor frames | Frames during key input | Application buffer commits after the replacement editor received a key | Visible / hidden commits in 15 s each | Visible / hidden CPU, % of one core |
| --- | ---: | ---: | ---: | --- | --- |
| 1 | 49 | 41 | 2 | 0 / 0 | 0 / 0 |
| 2 | 51 | 43 | 1 | 0 / 0 | 0 / 0.067 |
| 3 | 47 | 39 | 3 | 0 / 0 | 0 / 0 |

All three sessions released the first logical device, mapped the second
renderer, restored the filename and focus, accepted `rw02x` and drained
on Quit. Each worker reconciled the new file and retained its original PID
and start time across recovery and both idle intervals. In three earlier
observer trials, Tab moved to the focused password field, whose blinking
caret generated exactly 30 application buffer commits per 15 seconds.
Reading the button's role independently provided a stationary control.

The same binary recovered on X11 without requesting a different mode on
either generation. A Wayland initialization failure successfully reached
the second-generation CPU renderer. A separate llvmpipe session retained
the default-policy Anthy commit and all four monitor transitions. Frozen
Clippy with warnings denied and rustfmt passed. The hardware observations
cover this Intel driver and virtual Mutter output. Physical monitors and
other hardware drivers require separate evidence.
[Local receipt and trace hashes](../../tools/rust-qa/wayland-recovery/evidence.sha256).

The central graphics observer reads the SHA-256 of `graphics.rs` from the
verified GUI build receipt. For the first integrated graphics source at
`8b071ab`, it checks the historical llvmpipe marker. The current observer
checks the mode list, selected driver, window system and event order
separately for every ready graphics generation. A missing capability log
therefore fails a current run. The older source check accepted 25 original
integrated observations in the local archive.
[Graphics observer](../../tools/rust-qa/graphics/probe.py) · [Policy regression tests](../../tools/rust-qa/wayland-recovery/test_surface_modes.py).
