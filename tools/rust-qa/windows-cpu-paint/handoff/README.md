# Visible CPU-to-DXGI texture handoff

Run the two commands below on the disposable Windows x64 worker after the native CPU build. The first command builds a separate Cargo example in that build's release directory. It checks the compiler stream against the original library artifacts, features and manifests. The private example copies the retained application, adds a small scene below the language button and accepts two input bytes in the existing isolated stdin reader. The renderer uses its ordinary adapter and draw-data selection.

```powershell
$cpu = "artifacts/rust/windows-warm-window/x86_64-pc-windows-msvc/cpu-paint"
python -B tools/rust-qa/windows-cpu-paint/handoff/run.py $cpu
python -B tools/rust-qa/windows-cpu-paint/handoff/readback.py $cpu
```

The original texture contains eight by eight red texels with linear filtering. Once the screen observer sees the first frame, the scene updates the center four by four texels to green. After the observer captures the updated patch, the scene draws that same managed texture and a separate blue texture with nearest filtering. The standard wgpu painter receives the unsupported sampler on the retained root. The first texture receives one full upload and one partial update over the entire scene.

For each phase the observer reads three five-by-five regions from the physical desktop. Each retained PPM contains the original corner, original center and sampler marker from left to right. The native observer checks window ownership at every pixel and records the client and screen coordinates. The reader requires a full native CPU blit for each of the first two phases, permanent retirement of the CPU presenter, and a successful DXGI present on the original GUI thread before the final green center and blue marker. The same held GUI process must complete normal Quit, destroy the original HWND and leave an empty job.

Keep the parent CPU build evidence and the complete `handoff/` output for offline replay. It contains the source archive, Cargo compiler stream, example and ETW executables, subject and observer logs, three PPM tiles and `result.json`. The detached command reconstructs the CPU build from its archived sources and checks the example's source changes, compiler outputs, process and pixel evidence. Run the portable negative controls with `python -B -m unittest discover -s tools/rust-qa/windows-cpu-paint/handoff`.
