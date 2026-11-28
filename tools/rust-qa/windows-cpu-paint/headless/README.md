# Headless comparison with the ordinary editor

## Original editor

On Fedora Linux x64, the direct and cached CPU painters reproduced six BGRA frames from the real editor within **two channel values out of 255**. Of 4,992,000 pixel comparisons, 4,986,360 matched exactly. A single pixel reached a difference of two, in direct mode on the 640 × 400 edited frame. Each scale's initial and restored frames matched byte for byte within each renderer.

| Physical pixels | Frame | Triangles | Exact pixels, cached | Exact pixels, direct | Largest channel difference, cached / direct |
| --- | --- | ---: | ---: | ---: | ---: |
| 640 × 400 | German | 426 | 255,629 | 255,629 | 1 / 1 |
| 640 × 400 | English | 414 | 255,660 | 255,660 | 1 / 2 |
| 640 × 400 | Restored | 426 | 255,629 | 255,629 | 1 / 1 |
| 960 × 600 | German | 426 | 575,398 | 575,398 | 1 / 1 |
| 960 × 600 | English | 414 | 575,466 | 575,466 | 1 / 1 |
| 960 × 600 | Restored | 426 | 575,398 | 575,398 | 1 / 1 |

The test stages the ordinary GUI with its pinned lockfile and calls the unchanged `Window::ui`. A synthetic model supplies German and English labels, the filenames `Grüße – Sommer.jpg` and `東京 – صورة.png`, and an example password. The test-only patch permits a framework creation context without a window surface. Every renderer receives the same five clipped meshes and the same texture updates. The 2048 × 32 atlas uses Linear minification and magnification, ClampToEdge and no mipmaps. Editing uploads a 183 × 14 patch at scale 1 and a 249 × 19 patch at scale 1.5. The reference uses egui-wgpu on Mesa's Vulkan CPU adapter with a BGRA8Unorm texture and waits for readback. This measures offscreen pixels. It establishes no window lifecycle, display, presentation or latency result.

## Reproduce the comparison

Use Linux x64 with Bubblewrap, a Mesa lavapipe x64 ICD at `/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`, and the [pinned GUI toolchain, source cache and fonts](../../../../docs/development.md#rust-feasibility-workspace). From the repository root, seed the three reviewed private test archives once, then run the comparison offline.

```sh
python3 tools/rust-qa/windows-cpu-paint/upstream.py artifacts/rust/egui-cpu-assessment/cache --fetch
python3 tools/rust-qa/windows-cpu-paint/headless/run.py artifacts/rust/egui-cpu-assessment/cache
```

The runner verifies the native compiler, private GUI source trees and five font files. It compiles a frozen test copy with an isolated home, network namespace and read-only inputs. Each execution writes its 18 original BGRA files, compiler/test log and JSON report to a new directory under `artifacts/rust/egui-cpu-assessment/`. To repeat the channel comparisons without compiling, pass that directory's `pixels/` subdirectory to [pixels.py](pixels.py). Both commands return a failure on an incomplete frame, a failed edit/restore or a channel difference above two.

The original comparison used rustc 1.100.0 and llvmpipe with LLVM 23.1.5. Its `artifacts/rust/egui-cpu-view-local/pixel-comparison.json` has SHA-256 `1b9a7958707800295c5aabc4d7e5d5ac7eb3c214256da0ee6680e685bc578f01`, and `cpu-comparison.log` has SHA-256 `be7a48c5c2592dd8ed9b109c5d6a08d9797c7c9f655ec4f0c61a8600e4c9d4da`. Reconstructing the test from its staged GUI and the verified renderer archive reproduced all 18 original image files byte for byte. The ordinary application source SHA-256 was `a22d904d24eec3a7eabe543a176278ce46ed9f3ec2f90772d8137e5e03a201f9`.

With the Windows tray observer in the GUI, the source SHA-256 was
`d92c032a1c09bcf344d833f2accdbb4214496c717a4ae206520f39518b80ce18`.
All 18 BGRA files matched the originals byte for byte. Both CPU painters
passed the channel comparison against the six GPU reference frames. The
new comparison report has SHA-256
`085850f4926ac89be7de7fd12eb7d8026834fb9e1ade17e4ab6ffc8ad5937794`.

## Reconstructing the editor selection change

The canonical `main.rs` at `b71b573` has SHA-256
`650a20201c02196d9b483d880bd3abe9f80f974830bcebd0dd0c2fc51b8b5fc0`.
On window destruction the GUI reads both editor selections from its egui
context. The Windows retained patch keeps that context in the supervisor's
`Wake` struct until the window is dropped. The four patches and the original eframe
and winit archives produced the retained `main.rs` with SHA-256
`a7cc36d0b6f4663b601595a8e8b2b07518555f7579ad974912febf0ecfbc17de`.
The CPU paint variant kept those same application bytes. The separate
frame-ready variant inserted its session observer, producing
`e98a2b8585e57d2cfaa63aaa4624efe32145457a8cc516aedfea8b98f7e43a68`.
The texture-handoff example uses the existing byte reader for its two
scene commands and leaves the filename IME commands available during
IME observation. Its source reader also reconstructed the example's
`main.rs` in three earlier native handoff archives byte for byte.
[Retained builder](../../windows-warm-window/build.py) ·
[Frame-ready inputs](../../windows-frame-cost/frame-ready-pins.json) ·
[Texture-handoff example](../handoff/fixture_build.py).

On Linux x64 the headless test rendered all six frames of the updated
editor using at most two Cargo jobs. All 18 original BGRA files matched
the preceding run byte for byte. The largest CPU-to-GPU channel difference
was two. The new report is
`artifacts/rust/egui-cpu-assessment/headless-pl1afvg9/pixel-comparison.json`,
SHA-256 `707c9cb3d67558cb8cad03ea7263de1e57d1ab59351012f46febd58dcb42b424`.
The [ARM64 display workflow](../../../../.github/workflows/rust-windows-arm64-display.yaml)
owns native compilation and source-frame observation on that target.

## Editor with a window Quit button

The ordinary application at `c268a82` has SHA-256
`df337ee8c69b33490f08280e4aaac2a55e2e8c958edc64d97444d83c8dfae81f`.
The headless Linux model starts with tray registration pending. Both
language variants now draw the window Quit button. At 100% scaling the
changed reference pixels span rows 125–146 relative to the earlier view.
At 150% they span rows 188–220. The five meshes and initial 2048 × 32 atlas
were observed at both scales. Each German view used 546 triangles and 520
vertices. Each edited English view used 528 triangles and 484 vertices.
The edit uploaded a 203 × 14 atlas region at (391, 0) at 100%, and a
264 × 19 region at (490, 0) at 150%. Restoring the initial view required
no atlas upload.

The strict six-frame test reproduced all 18 images from a separate
measurement byte for byte. Across both CPU modes, 4,985,368 of 4,992,000
pixels matched the Vulkan reference exactly. The largest difference was
two channel values in the 100% direct-mode English frame. The report in
`artifacts/rust/egui-cpu-assessment/headless-kk5idh56/pixel-comparison.json`
has SHA-256 `5c5865daf2bec0d5e9a044eb753f72d2cd8b7e35ad8f947325a961abad74e1b7`.

The Windows source reconstruction in `50b1ace` produced identical retained
and CPU-paint application sources with SHA-256
`eb866736eeca6182a27052f032697053c4114db303f92475eeee5279b2470b5e`.
Adding the frame-ready observer produced
`fc734c1b518acb0e404e792dd3fd3192ab7566aeffb2d023ef4883e29d174ca9`.
Reversing the canonical Quit-button change in each reconstructed source
reproduced its earlier editor-selection hash.

## Editor with the staged Linux startup language

The optional replay reconstructs the editor at `c63d91c` using the
[startup qualification](../../gui/startup/README.md). It authenticates the
385 original registry archives and compiler trees, regenerates the combined
GUI/YAML lock and checks all four platform feature graphs before applying
the [headless test patch](../../gui/startup/headless-view.patch). The
instrumented manifest, lock and 28-file Rust source tree are checked against
the first measured headless build. Cargo then runs the original six-frame
test with one job in the isolated Linux x64 environment.

With the local reviewed archives and combined receipt already present, run
from the repository root.

```sh
area=artifacts/rust/combined-profile
python3 -B tools/rust-qa/windows-cpu-paint/headless/run.py \
  artifacts/rust/cpu-paint-cache \
  --build-cache artifacts/rust/egui-cpu-assessment/headless-build \
  --startup-vendor "$area/startup-vendor/registry/src/reviewed" \
  --combined-receipt "$area/runs/digest-native-2f63c15"
```

The two startup arguments select the staged editor. The ordinary invocation
above continues to reconstruct the original renderer control. In the local
Fedora replay, both preparations matched all 30 respective original files,
including the manifest and lock. The staged headless lock had SHA-256
`b5a1e53f83d3f17811fc88bd0bdfed3b304b3ae8be2c95d337d4662ef771b8ca`.

All 18 newly rendered BGRA files matched both the earlier staged run and
the original window-Quit editor byte-for-byte. Of 4,992,000 CPU-to-Vulkan
pixel comparisons, 4,985,368 matched exactly. The largest channel
difference was two. The source-bound Fedora report is
`artifacts/rust/egui-cpu-assessment/headless-ycr1rvcu/pixel-comparison.json`,
SHA-256 `5de2a39b5f3185b11ad0929e3bd3071bf2e7fa7ba353baef08a2d1c9567cea99`.
This offscreen comparison exercises the model's German and English views.
The separate [native editor and tray trial](../../gui/startup/README.md#fedora-desktop-readback)
covers reading the saved language and applying the system fallback at startup.
