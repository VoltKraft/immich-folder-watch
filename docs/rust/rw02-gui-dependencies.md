# RW-02 GUI input review

On 2026-11-20 the published crate contents and upstream release sources were
compared for the preferred egui/eframe prototype. The proposed native profile
uses eframe 0.37.0 with defaults disabled, `accesskit`, `clipboard` and
`wgpu_no_default_features`. Linux adds `x11` and `wayland`. The wgpu 30.0.0
profile selects `std`, `parking_lot` and `wgsl` with DX12 on Windows and Vulkan
on Linux. A renderer or software fallback becomes supported after a native
run records its adapter, startup, device-loss and error behavior.
[eframe features](https://github.com/emilk/egui/blob/841a328ba2dd8f6996beb7189ebb7fc00e668a2a/crates/eframe/Cargo.toml)

## Published code and notices

| Input | Published archive SHA-256 |
| --- | --- |
| eframe 0.37.0 | `9c5642501a65ca657d05f00c643a5c14ff2346cb3818032bfe23d58e1f8e5f84` |
| egui 0.37.0 | `bec9144f49b7a28b5f395d3147e325b4fe3e77ba686eac11d1bdf0a7da3f375f` |
| epaint 0.37.0 | `97bac86ae3dde93fc3951e790951caea739ff39a6c89d909cdaf1d9278dbb1bd` |
| egui-winit 0.37.0 | `e4e449f4c4a2a60c7ccb4ba7fa4078417bfe1f9ddc03b5e05ce75748e33a70de` |
| egui-wgpu 0.37.0 | `0309cbe1febed48af5b974e4bcc424b35e9664863a4d402697147b57a488c864` |
| wgpu 30.0.0 | `6d8f4bd44d92da5270f03409dba9f952dab24f128e05d6a554926101d1bf9114` |
| ashpd 0.14.0 (portal assessment) | `8ba377f1fb1e3972907220f1f8e7c0a45164580905c981d872c1fb90d921cbcc` |

All five egui-family archives omit their license files. The runtime sources and
assets match release commit `841a328ba2dd8f6996beb7189ebb7fc00e668a2a`.
Eframe records published revision `3c6eb8261c3293ad9c7ea1ed58487e038860ebef`.
The other four reference `7c0b40402271e8d40cda69f87cf3c2617c2e4382`, which
GitHub could not resolve during review. Comparing the archives against the
release identified README packaging changes in egui and a comment in epaint's
original manifest. Preserve the MIT file with SHA-256
`95ca92f5f8ea5231f1580b3a2a799e8260af3114b900e1def5355a7f44bcf60c`
and the Apache file with SHA-256
`8173d5c29b4f956d532781d2b86e4e30f83e6b7878dce18c919451d6ba707c90`.
Both upstream revisions have identical notice bytes.
[MIT](https://github.com/emilk/egui/blob/841a328ba2dd8f6996beb7189ebb7fc00e668a2a/LICENSE-MIT)
and [Apache](https://github.com/emilk/egui/blob/841a328ba2dd8f6996beb7189ebb7fc00e668a2a/LICENSE-APACHE).

## Locked assessment and additional rights holders

The maintained native GUI probe uses 374 external locked archives. The
normal/build tree actually selects 232 external packages on each Linux target
and 132 on each Windows target. Their union has 252 external packages, 52 with
a build script or procedural macro, and 449 in-archive notice files identified
by the inventory. None contains a font with a recognized native or web font
extension. The two explicit Noto font files are separate build inputs.
The four reports contain no excluded egui font or inspection package or feature.
The [graph auditor](../../tools/rust-qa/audit-graph.py) hashes each selected
original archive against the lock and records target feature sets, native
objects, shaders and individual notice hashes. The native build also checks
every unpacked source against the authenticated archive and the full inventory
against the [reviewed target digest](../../rust/audit/gui-profile.json).
All four target inventories were verified locally. The Linux graph records 100
Wayland protocol definitions with the SHA-256 and embedded attribution of
each XML. Plasma's historical `fullscreen-shell.xml` lacks an inline notice.
The original KDE import explicitly names Weston 1.5. Its 9,898 bytes match
the XML in the official release tarball, SHA-256
`2ccd919a865e8d5cc107842a387989746d78ec6c1ff07e163ffd6aa78e3807b5`.
Applying KDE's six subsequent spelling corrections reproduces the complete
9,902-byte packaged input, SHA-256
`ed7ded0629f9f05adb9326a378258255d623522b85ec4d47c787742da7fd5c7c`.
[Original KDE import](https://github.com/KDE/plasma-wayland-protocols/commit/03d462bbbac0c292beed03d3a5682bb90c893633),
[first correction](https://github.com/KDE/plasma-wayland-protocols/commit/f0238fc5bb038f0e15377c1ccd4a8863c1b3cf14),
[second correction](https://github.com/KDE/plasma-wayland-protocols/commit/588d62b4c60ff0599793c20a07be5142da3a04ee)
and [final correction](https://github.com/KDE/plasma-wayland-protocols/commit/ad543cf41905dcca8335a84d2770d76be8e0de5d).

Jason Ekstrand submitted the original protocol in April 2014 and acknowledged
the notice added to the evolved upstream protocol in 2018. For the historical
input, preserve the [complete Weston 1.5.0 grant](../../rust/audit/notices/weston-1.5.0-COPYING)
from the checksum-pinned release. Its main text matches HPND-sell-variant,
including the supporting-documentation notice and advertising-name restriction.
The separately identified libbacklight subsection applies to that component.
[Original submission](https://lists.freedesktop.org/archives/wayland-devel/2014-April/014027.html),
[author acknowledgement](https://lists.freedesktop.org/archives/wayland-devel/2018-June/038757.html)
and [SPDX license text](https://spdx.org/licenses/HPND-sell-variant.html).

Sixteen selected crates omit standalone notices. The [supplemental catalog](../../rust/audit/gui-inputs.json)
pins original upstream bytes and includes the fonts and their notice. The
following source obligations also apply to data embedded in nominally
permissive Rust packages.

| Component | Source findings and retained evidence |
| --- | --- |
| egui family 0.37.0 | Seven archives omit license files, including ecolor and emath. The retained release MIT and Apache files cover the matching sources. |
| AccessKit | The selected six archives omit standalone notices. Keep MIT and Apache files, the Apache-only grant for accesskit_winit, Chromium's BSD notice, and the per-file attributions in the corresponding sources. [Upstream notices](https://github.com/AccessKit/accesskit/tree/f3026222559c7f5f46d8f25cb7404de68eb149f0) |
| clipboard-win 5.4.3 and profiling 1.0.18 | The catalog supplies the original BSL-1.0 and MIT files for these two missing grants. |
| Vello 0.2.0 | Pixel encoding and blending include tiny-skia adaptations in vello_common and vello_cpu. Preserve tiny-skia's three-clause BSD notice, in addition to Vello's source notices. [tiny-skia](https://github.com/linebender/tiny-skia/blob/68b198a7210a6bbf752b43d6bc4db62445730313/LICENSE) |
| HarfRust 0.12.0 and unicode-general-category 1.1.0 | Preserve Unicode data headers and the [Unicode data license](../../tools/rust-qa/legacy/licenses/Unicode-LICENSE.txt), SHA-256 `e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96`. |
| spirv 0.4.0+sdk-1.4.341.0 | The archive omits the rspirv Apache notice. Its generated grammar also carries Khronos' MIT terms. Both upstream notices are retained. The reviewed grammar hash is `508e6677e27b0b58eac8395aa49a90ac1766a8d392c247a0aba7b03f4fdd85b9`. [Grammar](https://github.com/KhronosGroup/SPIRV-Headers/blob/04f10f650d514df88b76d25e83db360142c7b174/include/spirv/unified1/spirv.core.grammar.json) |
| Wayland protocol bindings | Seventeen protocol XML files in wayland-protocols-plasma 0.3.12 declare LGPL-2.1-or-later. This includes `blur.xml`, used by winit's KWin blur bindings. The misc 0.3.12 copy of `server-decoration.xml` carries the same terms. Plasma's `surface-extension.xml` declares BSD-3-Clause. Retain the complete XML with individual authors and matching license texts. The archive's `COPYING.LIB` is the LGPL text. |

For Linux static linking, distribute the corresponding application and library
sources, generator inputs, notices and reproducible relink instructions. Before
candidate acceptance, rebuild a modified library from that source and relink the
application using exactly the distributed inputs. The installed-package
inventory also needs the loaded system libraries, target-specific import objects
and shader compiler. The current reports cover development inputs.
[LGPL 2.1 section 6](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html#section6).

## Fonts

The following unmodified Noto assets were checked against their embedded
attributions and character maps. The first three come from
`notofonts/noto-fonts@ffebf8c1ee449e544955a7e813c54f9b73848eac` under
`hinted/ttf/<family>/<file>`. The CJK file comes from
`notofonts/noto-cjk@f8d157532fbfaeda587e826d4cd5b21a49186f7c` under
`Sans/OTF/Japanese/`. Preserve copyright records and OFL-1.1 with every
distributed font. [OFL bundling terms](https://openfontlicense.org/ofl-faq/).

| File | Font version | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| NotoSans-Regular.ttf | 2.008 | 569208 | `b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5` |
| NotoSansMono-Regular.ttf | 2.007 | 512836 | `d9e2b23d19f8230be7146f409a52b1d23117e635e28f2e2892cf91b7382f325b` |
| NotoSansSymbols2-Regular.ttf | 2.003 | 656852 | `630846d528dbe4c4981370a4d0a9475a1fd1491a129bb411f8e157cdb5de13c6` |
| NotoSansCJKjp-Regular.otf | 2.004 | 16467736 | `68a3fc98800b2a27b371f2fb79991daf3633bd89309d4ffaa6946fd587f375b5` |

The [Noto notice](https://github.com/notofonts/noto-fonts/blob/ffebf8c1ee449e544955a7e813c54f9b73848eac/LICENSE)
hash is `0dab92d0544f7b233403f14b84a663bdbfa746982eda629e7f4f9ffe1b036feb`.
The [CJK notice](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE)
hash is `6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2`.
Sans and Mono cover the German strings. CJK, Arabic, emoji and several symbols
require additional coverage. Epaint shapes runs with HarfRust and documents
unfinished bidi support. Check mixed-direction filenames, selection, caret
movement, composition and paste with the actual fonts and native input method.
[epaint text layout](https://github.com/emilk/egui/blob/841a328ba2dd8f6996beb7189ebb7fc00e668a2a/crates/epaint/src/text/text_layout.rs)

## Native interfaces and outstanding checks

- Hidden eframe windows can receive `App::logic` callbacks on a repaint wakeup.
  The app must drain bounded events there independently of visible frame input.
  Verify that hidden startup, tray failure and restoration work with the real
  window manager and that a dormant process sleeps.
  [Lifecycle API](https://github.com/emilk/egui/blob/841a328ba2dd8f6996beb7189ebb7fc00e668a2a/crates/eframe/src/epi.rs)
- ashpd 0.14.0 offers selective portal features. Its Wayland identifier export
  uses a thread performing blocking roundtrips and unwraps the channel send.
  A caller timeout alone cannot stop that thread. Test identifier lifetime,
  compositor stall and orderly shutdown before selecting the implementation.
  [Parent export](https://github.com/bilelmoussaoui/ashpd/blob/6dce3c409cfc60f7198ca4efae0002de38213c61/client/src/window_identifier/wayland.rs)
- Record actual X11/Wayland, Vulkan, accessibility and D-Bus libraries and the
  Windows SDK, D3D and shader compiler used. Pin or exclude extra DXC binaries.
  [DX12 compiler selection](https://github.com/gfx-rs/wgpu/blob/8bf3e5ff4ab45e2c150e0d6c70d01d25f5b126c1/wgpu-hal/src/dx12/instance.rs)
- Audit the locked transitive normal/build dependency and asset graph, sources
  and notices for each native target. Exclude the default font package,
  unreviewed system font lookup, emoji bundles and the inspection server.
  Retain the Rust distribution's `COPYRIGHT.html` and
  `COPYRIGHT-library.html` for component-level review.
  [Rust 1.100.0 copyright](https://github.com/rust-lang/rust/blob/1.100.0/COPYRIGHT)

The source review informs RW-02. The [acceptance record](acceptance.md) tracks
resolved build inputs, actual GUI tests and the stack decision.
