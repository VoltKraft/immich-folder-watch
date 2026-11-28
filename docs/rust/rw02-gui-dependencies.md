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

The maintained GUI locks 372 registry archives and reconstructs three external
source trees. Each Linux normal/build graph selects 230 registry and three
reconstructed packages. Each Windows graph selects 130 registry and the same
three reconstructed packages. The graphs also contain the two repository
packages. Their union contains 253 external packages, including 52 packages
with a build script or procedural macro. The revised registry archive inventory
lists 456 notice files. It adds five original Plasma REUSE texts,
linebender_resource_handle's AUTHORS and winit's documentation artwork
attribution to the earlier 449 entries. All five font payloads enter through explicit build paths.
The four reports found no bundled font files in the selected crate sources and
no excluded egui font or inspection package or feature. The earlier prototype
at `6c953e3` used 374 registry archives and two explicit fonts.
The [graph auditor](../../tools/rust-qa/audit-graph.py) hashes each selected
original archive against the lock and records target feature sets, native
objects, shaders and individual notice hashes. The native build also checks
every unpacked source against the authenticated archive and the full inventory
against the [reviewed target digest](../../rust/audit/gui-profile.json).
The four reports also verify each reconstructed tree and the exact target
feature sets independently established by the isolated text-engine comparison.
All four target inventories were regenerated locally from verified unpacked
sources. On Linux, wayland-client 0.31.15 generates both its interfaces and
client code from its core `wayland.xml`, SHA-256
`cc860987e54f8d85c940e97fa1270c69b6e4ad31fbcf5a7f00107ce1157f5e07`.
Together with the 100 extension XMLs, the inventory covers 101 protocols.
The two upstream scanner test XMLs belong to its test suite. Plasma's
historical `fullscreen-shell.xml` lacks an inline notice.
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

Sixteen selected crates in the original graph omit standalone notices. The
[supplemental catalog](../../rust/audit/gui-inputs.json) pins their original
upstream bytes, Noto Sans and Mono, and the shared OFL notice. The
[text source inventory](../../rust/audit/gui-text-inputs.json) pins the other
three fonts, the text-engine sources and their full notices. The
following source obligations also apply to data embedded in nominally
permissive Rust packages.

| Component | Source findings and retained evidence |
| --- | --- |
| egui family 0.37.0 | Seven archives omit license files, including ecolor and emath. The retained release MIT and Apache files cover the matching sources. |
| AccessKit | The selected six archives omit standalone notices. Keep MIT and Apache files, the Apache-only grant for accesskit_winit, Chromium's BSD notice, and the per-file attributions in the corresponding sources. [Upstream notices](https://github.com/AccessKit/accesskit/tree/f3026222559c7f5f46d8f25cb7404de68eb149f0) |
| clipboard-win 5.4.3 and profiling 1.0.18 | The catalog supplies the original BSL-1.0 and MIT files for these two missing grants. |
| Vello 0.2.0 | Pixel encoding and blending include tiny-skia adaptations in vello_common and vello_cpu. Preserve tiny-skia's three-clause BSD notice, in addition to Vello's source notices. [tiny-skia](https://github.com/linebender/tiny-skia/blob/68b198a7210a6bbf752b43d6bc4db62445730313/LICENSE) |
| HarfRust 0.12.0 and unicode-general-category 1.1.0 | Preserve Unicode data headers and the [Unicode data license](../../tools/rust-qa/legacy/licenses/Unicode-LICENSE.txt), SHA-256 `e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96`. |
| unicode-bidi 0.3.18 | Preserve the original source headers, AUTHORS, COPYRIGHT, both MIT and Apache grants, the Unicode 16 UCD readme and the Unicode data license. The original generator reproduces the compiled bidirectional class and paired-bracket table from the pinned UCD bytes. [Unicode 16.0 data](https://www.unicode.org/Public/16.0.0/ucd/) |
| spirv 0.4.0+sdk-1.4.341.0 | The archive omits the rspirv Apache notice. Its generated grammar also carries Khronos' MIT terms. Both upstream notices are retained. The reviewed grammar hash is `508e6677e27b0b58eac8395aa49a90ac1766a8d392c247a0aba7b03f4fdd85b9`. [Grammar](https://github.com/KhronosGroup/SPIRV-Headers/blob/04f10f650d514df88b76d25e83db360142c7b174/include/spirv/unified1/spirv.core.grammar.json) |
| Wayland protocol bindings | Seventeen Plasma XMLs and the misc copy of `server-decoration.xml` carry LGPL-2.1-or-later. The other tagged Plasma XMLs declare MIT-CMU, BSD-3-Clause or MIT. Preserve each assignment with the complete XML, its corresponding original REUSE text and the original `COPYING.LIB`. The REUSE directory also includes CC0-1.0. |
| Adobe Glyph List | read-fonts 0.41.0 cites Adobe's list for the nonbreaking space and soft hyphen glyph names in `src/ps/encoding.rs`. The packaged `data/glyphlist.txt` contains Adobe's copyright, binary redistribution condition, endorsement restriction and disclaimer. The notice archive retains the complete original header. [Upstream data cited in the source](https://github.com/adobe-type-tools/agl-aglfn/blob/4036a9ca80a62f64f9de4f7321a9a045ad0ecfd6/glyphlist.txt) |

For Linux static linking, distribute the corresponding application and library
sources, generator inputs, notices and reproducible relink instructions. Before
candidate acceptance, rebuild a modified library from that source and relink the
application using exactly the distributed inputs. The installed-package
inventory also needs the loaded system libraries, target-specific import objects
and shader compiler. The current reports cover development inputs.
[LGPL 2.1 section 6](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html#section6).

## Fonts

The following unmodified Noto assets were checked against their embedded
attributions and character maps. The TrueType files come from
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
| NotoSansArabic-Regular.ttf | 2.009 | 240456 | `ceea25b464a656dc3b26849bab9356740401af62aedf1bfa8b7f0d9b75925b1b` |
| NotoSansCJKjp-Regular.otf | 2.004 | 16467736 | `68a3fc98800b2a27b371f2fb79991daf3633bd89309d4ffaa6946fd587f375b5` |

The [Noto notice](https://github.com/notofonts/noto-fonts/blob/ffebf8c1ee449e544955a7e813c54f9b73848eac/LICENSE)
hash is `0dab92d0544f7b233403f14b84a663bdbfa746982eda629e7f4f9ffe1b036feb`.
The [CJK notice](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE)
hash is `6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2`.
Sans and Mono remain the first choices in their respective families. Both
families then use Symbols2, Arabic and CJK JP in that order. Retain the
per-file copyright and trademark records in the text source inventory with
the matching complete notices. The text builder reuses the original reviewed
font files without subsetting, converting or searching installed fonts.

## Bidirectional layout and native editor

Unmodified egui 0.37.0 drew the connected Arabic sample but selected the wrong
logical character after dragging over it. European digits exposed a second
failure in the visual order of a mixed-direction filename. The maintained GUI
uses the reviewed Rust changes from the upstream comparison between
`fc9d66dda742d722eedaa8684d23f86369cf8e5f` and
`e0bc7924dac211c5ff727d55922662ce371ec819`. The two original crate archives
still supply the base sources. The build applies the selected changes to 17
egui/epaint Rust files and provides the exact unicode-bidi 0.3.18 path input
with only `hardcoded-data` and `std`. The reviewed unicode-bidi source matches
its published archive at every retained source file. The compiler uses the
reviewed local manifest. Cargo verifies the normal/build graph on every
native host. [Upstream change](https://github.com/emilk/egui/pull/8828) and
[original visual and editing controls](rw02-font-coverage.md).

On a native Windows or Linux host, select the checked Rust toolchain and run
`python3 tools/rust-qa/build-gui-probe.py TARGET` from the repository root.
This fetches the pinned public originals and both locked Cargo graphs,
verifies fonts, notices, compiler inputs and graph, runs Clippy, and builds
the actual GUI. Run the same command with `--offline` to repeat using those
inputs. Reconstructing the three source directories from the cached originals
reproduced all 137 egui files, 59 epaint files and 17 unicode-bidi files,
including the generated Unicode table. Independent negative controls rejected
a changed Rust file, an added Rust file, an extra package root, a shortened
font and an empty source review. The original lock and feature comparison
for the independent service and portal fixtures use the verified manifests
from `6c953e3`. The first online setup requires that Git revision locally.
The sources and fonts go under ignored assessment directories. Windows needs
the native MSVC environment selected by the [native build guide](../development.md#rust-feasibility-workspace).

On Linux, `python3 tools/rust-qa/gui/profile_text.py` runs the maintained
executable in a private X11 desktop with Mesa. The fixture requires the GTK 3
and AT-SPI introspection libraries and XTEST. It pastes into the normal
filename editor through the native clipboard, clicks, presses left and right,
drags, presses Delete, and checks the resulting text and character extents
through AT-SPI. A separate window readback compares glyph pixel masks. On
Linux x64, Japanese, Arabic and mixed Arabic/European digits passed this
sequence. The window produced eight distinct masks for the Latin control,
two CJK characters, a symbol, three Arabic letters and the unmapped control.
The [four-host acceptance record](acceptance.md) tracks native evidence outside
this Linux x64 run, including IME and accessibility checks. The observed
binary has SHA-256 `80898c73bf97c9d6622ef837cd5361810b041e5d007a1fe742d32ad7921c1002`.
The [Linux x64 receipt](../../tools/rust-qa/gui/evidence/text-profile-linux-x64.sha256)
binds the native results, both build records, the source graph, observation
drivers and the application's orderly shutdown.

## Offline compiler inputs for the ordinary Linux GUI

The normal Linux [build entry point](../../tools/rust-qa/build-gui-probe.py)
prepares the pinned Cargo archives. Its [isolated compiler](../../tools/rust-qa/gui/build.py)
reconstructs the 372 registry packages in the ordinary GUI lock with
the same source filters as the standalone settings reader.
Their original archives and unpacked compiler sources have inventory
SHA-256 `0a4cc8dc3db5daee67b22898a0b4b3ca09a15fd157691e3d19eb72c134f885fe`.
The cache is under `artifacts/rust/gui-registry/<digest>/`. A new compiler
invocation authenticates the archives, file lists and individual source
bytes before mounting the directory at `/vendor`. Clippy, release builds
and native tests use this read-only mount in an offline namespace.
The separately reconstructed text crates and installed fonts keep their
existing inputs. [Directory reconstruction](../../tools/rust-qa/gui/startup/vendor.py).

For a release build, the [compiler check](../../tools/rust-qa/gui/compiler_inputs.py)
matches every compiled package and feature set to the native graph and
checks the manifest used by each build unit. The executable must come
from the ordinary GUI's `src/main.rs`. The per-target output under
`artifacts/rust/gui-native/` retains `compiler.jsonl`,
`registry-sources.json`, `graph.json` and their SHA-256 values in
`build.json`. The same check verifies the integrated settings reader's
[staged compiler output](../../tools/rust-qa/gui/startup/README.md).

The Fedora x64 offline build recorded 289 compiler units across 235
packages in graph `6c99492b82997e4e20b66e559a9de9bbea8c22d910bf00fe26484413f00df700`.
Clippy and all 40 native tests passed. The release executable had SHA-256
`a4e098475577ccc1244f441ea9b728a9afeb15f93f1d0e2acfe4854b55e645e1`.
On private X11 and Mutter Wayland desktops it passed the four lifecycle
cases on each display. The respective `results.json` digests were
`2997002748a926d60010001cdc19f0f17ca8a339a3bd035caa2fe11895af3108`
and `13a7b2321429ae7665f90fb0d3507a89b82ddaca568302af2be60b189ffebb8d`.

## Windows notification-area bindings

The ordinary GUI and the retained-window comparison now use the same
first-party receiver as the standalone Windows Shell assessment. The GUI
selects the already locked Microsoft `windows` 0.62.2 crate directly on
Windows. The only additional feature in either Windows GUI graph is
`Win32_UI_Shell`. Both retain 135 packages. The two Linux graphs retain
their 235 packages and their existing feature sets. The combined development
profile already selects these Shell APIs. [GUI manifest](../../tools/rust-qa/gui/Cargo.toml)
· [Standalone service review](rw02-windows-services.md#dependency-review-and-local-evidence).

The GUI also declares the existing `Win32_System_Threading` feature
directly to observe the registered Shell process through a synchronization
handle. AccessKit already selects it on both Windows targets. Reproducing
all four complete reports yielded the same four digests. The original
generated Threading module has SHA-256
`a4caf28ab454d5c886b02cb1caacec628f2d0ef55df507fca545145be2900893`.
The retained-window comparison reconstructed its eframe source archive
with SHA-256 `ce55769b1e721136161c6bf19fdd46665ccb6b00cca5f0b3290c23f1f8a06b7f`.
Its three tray source files and icon matched the canonical GUI byte-for-byte.
The retained and canonical normal/build features matched on all four targets.
Fifteen comparison tests passed, as did formatting and cross-Clippy for both
retained Windows targets.

The retained build also archives Cargo's complete release compiler message
stream in `compiler.jsonl`. Its build receipt records the digest and the
number of artifacts, distinct package feature sets and packages. The check
matches each package source to the retained lock, checks the six local
manifest locations and compares the compiled features with the native
normal/build dependency tree. The activation checks verify the log digest
before using the binary. [Retained build](../../tools/rust-qa/windows-warm-window/build.py)
· [Cargo compiler messages](https://doc.rust-lang.org/cargo/reference/external-tools.html#json-messages).

A native Fedora x64 release build of the retained source with the GUI and
tray from `93ecc35` produced 289 compiler artifacts, 240 distinct feature
sets and 235 packages. The compiler stream SHA-256 was
`1f48bfc05d2b18c40b7266895ffff8450bcf38396890f1c86e465c3e52ae9edb`.
The linked ELF SHA-256 was
`21b9bf68e78096b690e823e1176a7c1e0638416e6689299e069e2dc1b66c944c`.
The Windows builds capture their own compiler output on each architecture.

Independent review found that the GUI library and binary share package and
feature values. The verifier now requires a single Cargo binary target built
from the local `src/main.rs`. Its declared executable and output file must
identify the image passed to the observers. A replay of the full native
Fedora compiler stream at `8bb3248` bound the linked image with SHA-256
`865907276e5f9dcf15aa8f86269dca777ed7631cde2d4044d125b975a7f97d60`.
Removing just the binary message left the library and all package features
present and correctly failed the new check. Both canonical and retained GUI
sources also passed Clippy with the two Windows target libraries.

The original crate SHA-256 is
`527fadee13e0c05939a6a05d5bd6eec6cd2e3dbd648b9f8e447c6518133d8580`.
The generated Shell module is 3,585,884 bytes with SHA-256
`2f8f0191baf83d942c67090e12e34746c1dda8426f072f7f2ec498fe8ce25eb0`.
It declares the system Shell functions used for registration, modification,
rectangle lookup and removal. The GUI preserves Microsoft's original
MIT and Apache-2.0 license texts and selects the MIT option. All four
target reports were reproduced from the original archives and checked
against their unpacked sources. [Published source](https://static.crates.io/crates/windows/windows-0.62.2.crate)
· [Target digests](../../rust/audit/gui-profile.json).

## Windows x64 WARP renderer inputs at 3b488ca

The native Rust 1.100.0 MSVC build selected CPU painting on a supported
WARP surface. Its patched `egui-wgpu 0.37.0` retained the `capture` and
`winit` features. Cargo reported 156 compiler units and 138 package
identities. The measured `cpu.exe` had SHA-256
`6085e3f96e2e74cd890cbfdb5a9717aebb00b1353b41991f37eb36b92b71785f`.
[Original Windows x64 build and timings](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45908644127/artifacts/15161087080).

| Dependency change | Role in this build |
| --- | --- |
| `hdrshot-egui-backend 0.2.0` | Target rasterizer used by the patched presenter, compiled as `egui_software_backend` with `default` and `std`. |
| `strength_reduce 0.2.4` | Target arithmetic library used by the rasterizer, compiled with no Cargo features. |
| `constify 0.0.1` | Build-host procedural macro used to compile the rasterizer. Cargo produced a macro DLL. |
| `syn 2.0.119` | Existing build-host dependency of `constify`. The macro adds `extra-traits` to the selected features. |

The three added crates declare `MIT OR Apache-2.0`. The archived
`source.zip` contains their original crate bytes, twelve rasterizer and
inherited attribution files, the original egui-wgpu crate, the modified
sources and manifests, the lockfile and the project license. The WARP
patch has SHA-256 `2f70dad4bf081a6eaced6dc849f7ad23843db972f39964a596f8b11c9192dc12`.
[Original grants, provenance and individual hashes](../../tools/rust-qa/windows-cpu-paint/upstream.json)
· [Patched source hashes](../../tools/rust-qa/windows-cpu-paint/renderer-inputs.json).

The compiler stream and eight members of `cpu-libraries.zip` identify the
two target libraries and the host macro outputs. Together with the
executable and source archive they establish which private build ran.
A standalone relink and installed-package delivery remain unverified for
this executable. The combined development SPDX documents describe their own
executables. [Combined SPDX subjects](rw02-combined-sbom.md).

## Native interfaces and outstanding checks

At `8b071ab`, each native host rebuilt the integrated GUI. The archived
source and feature reports reproduced the four checked-in digests, covering
235 packages per Linux target and 135 per Windows target. The ordinary
Linux desktop window passed three editing cases and eight pixel controls on
each architecture. The integrated result hashes were
`6f1bb3eb38a3a6ddaeaf39257bdbc130e149258a280c58286cbacbe790957cff` on x64
and `7c53c16336c078873e4a57f9cd9f4d8543c11d6d942c954dc41970095138ac6f` on
ARM64. Each receipt includes the exact binary hash. Windows x64 passed the
CJK pointer selection, deletion and caret test in the comparative subject.
Both Windows hosts stopped before completing all mixed-direction cases.
[Native graph, build and editor evidence](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452).

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
