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

Keep `gdi-build.json`, `source.zip`, `compiler.jsonl`, `gdi.exe`, the
original reports and logs, and `retained-edit/` together under
`gdi-present/`. Also retain the sibling ordinary build, compiler stream,
eframe source archive, measured result and editor result. The source
archive contains the published egui-wgpu crate, its upstream notices,
the first-party changes and their license, both Cargo manifests/locks via
the retained source archive, and the actual modified compiler files.
Offline replay reconstructs that archive and compares all native compiler
units and feature sets to the ordinary build.
