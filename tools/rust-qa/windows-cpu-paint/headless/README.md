# Headless comparison with the ordinary editor

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
