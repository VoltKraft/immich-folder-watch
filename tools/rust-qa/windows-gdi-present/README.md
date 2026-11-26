# Full egui view presented through GDI

This Windows x64 RW-02 comparison renders the retained application's actual
egui primitives, textures and callbacks on the DX12 Microsoft Basic Render
Driver. A private build transfers the rendered root texture to the window
with `SetDIBitsToDevice` and flushes GDI on the owning thread. The root keeps
its winit HWND, eframe event loop and AccessKit tree. The earlier two-color
[GDI control](../windows-gdi-control/README.md) has its own measurements.

Run on the disposable native x64 desktop after completing the ordinary
retained build, its editor observation, and the three-trial WPF and Rust
comparisons. Use the same checkout, pinned compiler and reviewed offline
Cargo cache throughout.

```powershell
python -B -m unittest discover -s tools/rust-qa/windows-gdi-present
python -B tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --gdi-present
python -B tools/rust-qa/windows-gdi-present/gdi_case.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/gdi-present
```

The launcher selects the GDI output only for the isolated diagnostic.
The renderer verifies the adapter name, backend, device type and opaque
root viewport before selecting it. The HWND's unconfigured wgpu surface
supplies format and adapter capabilities. The existing egui renderer paints
the offscreen frame. One readback at a time supplies a bounded, row-aligned
buffer. The presenter checks the visible client size immediately before the
blit. The native API returns a scanline count. A separate UI Automation test
edits the filename and captures its actual pixels on the reopened HWND.
[Win32 bitmap transfer](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-setdibitstodevice) ·
[GDI batch results](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-gdiflush).

The recorder pairs the single comparison trial with this desktop's original
WPF limits and ordinary retained results. It measures the complete GUI and
worker process tree at idle and across two 100,000-file inventory passes.
The GDI transfer records and the PID-filtered DXGI trace use the same
native clock as the independent window and file observations. Preserve
the calibration reopens, idle intervals, scan requests and successful
full-frame transfers with the edited screen images. Qualification of a
shipping renderer requires the three ordinary trials.

### Reusing the mapped readback buffer

In the `5efe1f1` scan the first complete GDI transfer began a median
50.92 ms after the observer saw the reopened HWND. The transfer and
flush took 0.14 ms. The ordinary one-frame Mailbox trial on that host
started its first observed DXGI present after 4.82 ms. At `f155b65` the
corresponding GDI start was 16.44 ms. These timings locate the delay
before the blit. The earlier presenter allocated a new 1,024,000-byte
staging buffer for each 640 × 400 frame. Its logs do not time that
allocation or the subsequent GPU readback.
[Earlier Windows measurements](../../../docs/rust/rw02-windows-window.md#native-results-at-5efe1f1).

The GDI root now retains one unmapped buffer on its device. Each frame
checks it out exclusively. A different width or height replaces it, even
when padding gives both frames the same byte count. After the submission
completes, the renderer presents the mapped pixels and fulfills any screen
capture using those same pixels. It returns the buffer after unmapping
and successful presentation handling. A root or device rebuild discards
the slot.

Each `STAGING_COPY` record includes the layout, allocation or reuse, and
QPC times. The first interval measures checkout or buffer creation. The
second begins before mapping and ends when the CPU can read the pixels.
The independent readback matches each full or partial transfer to that
mapping and reports the allocation count and p95 times for idle, inventory
and editor trials. A mapped frame that produces no visible transfer earns
no presentation credit. The scan still requires five complete transfers
during observed work, each entirely between the original HWND reopening
and the following close request. Replaying a historical archive requires
the observer and renderer sources from that run's revision.

Keep `gdi-build.json`, `source.zip`, `compiler.jsonl`, `gdi.exe`, the
original reports and logs, and `retained-edit/` together under
`gdi-present/`. Also retain the sibling ordinary build, compiler stream,
eframe source archive, measured result and editor result. The source
archive contains the published egui-wgpu crate, its upstream notices,
the first-party changes and their license, both Cargo manifests/locks via
the retained source archive, and the actual modified compiler files.
Offline replay reconstructs that archive and compares all native compiler
units and feature sets to the ordinary build.
