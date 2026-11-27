# CPU rendering of the retained Windows editor

This private Windows x64 trial measures how quickly the original egui
window hides and reopens while its worker inventories files. It rasterizes
the original meshes and font atlas on the CPU, presents the BGRA output
on the original HWND with GDI and compares the results against three
ordinary WPF and retained egui trials on the same runner.

This build selects CPU painting when wgpu reports the DX12 Microsoft Basic
Render Driver on an opaque, supported 8-bit root surface. Other adapters
use the ordinary wgpu renderer. A supported CPU frame also applies its
changed textures to the ordinary renderer. If a later valid draw needs
another sampler, a paint callback or an additional surface, the build
switches to wgpu for the remainder of the renderer's lifetime. The current
draw and its pending texture updates continue on that path.
The observer binds each
completed transfer to the HWND, UI thread and QPC clock, counts idle
frames and verifies that edits on both sides of a close and reopen
produced new visible pixels. The idle and scan processes must each keep
their first WARP device through Quit, with no active device loss or retry.
ETW observes the separate worker reading 100,000 synthetic inputs twice.
All eleven same-host budgets apply. The timing report also gives the
eligible reopen count, the number with a complete editor frame and the
p95 from request to completed transfer for those frames.
[Original offscreen pixel comparisons](headless/README.md) ·
[First native trial with explicit CPU selection](../../../docs/rust/rw02-windows-window.md#native-windows-x64-cpu-renderer-at-dddb21a).

## Native run and replay

Use the native MSVC environment on the disposable Windows x64 runner.
The workflow first builds the ordinary application and collects the WPF
budget. Run the remaining trial from the repository root.

```powershell
python -B tools/rust-qa/windows-cpu-paint/upstream.py artifacts/rust/cpu-paint-cache --fetch
python -B tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --cpu-paint
python -B tools/rust-qa/windows-cpu-paint/measure.py artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/cpu-paint
```

The separate texture example must show the partial update on the same
window after switching to wgpu. The native and detached commands both
use the staged CPU build. [Visible handoff and readback](handoff/README.md).

The device-recovery trial uses the same native GUI and inventory worker
as the timing run. It destroys the GUI's own WARP device after a visible
edit and checks the replacement window, preserved text and continued worker
activity. [Native recovery and readback](recovery/README.md).

The fetch verifies the sizes and hashes of three original crate archives.
Further source reconstruction and compilation use the offline cache.
The source bundle includes the original renderer, the patched renderer
manifest, the private Cargo lock, the three original archives and their
twelve attribution files. The new dependencies are hdrshot-egui-backend
0.2.0, constify 0.0.1 and strength_reduce 0.2.4. The existing syn 2.0.119
also provides its extra-traits feature for the private procedural macro.
The exact sources and original notices cover the rasterizer, pre-existing
SIMD and color code, division routines and macro sources. [Upstream source,
license selections and hashes](upstream.json).

Retain the original ZIP from the workflow and the native compiler stream,
source ZIP, CPU library ZIP and executable together. Replay at the
measured source revision with the pinned GUI cache and the original
Windows performance and ordinary build directories in their archived
layout. Read the individual comparison values in
`result.json` under `checks.resources` for the native verdict.
[Native workflow](https://github.com/VoltKraft/immich-folder-watch/blob/a051d46abf139c33bcd4e7c1f74f229b7fe5d6fe/.github/workflows/rust-windows-transitions.yaml).
