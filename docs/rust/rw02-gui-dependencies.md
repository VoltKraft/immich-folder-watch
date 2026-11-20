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
