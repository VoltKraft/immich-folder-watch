# RW-02 font rendering and bidirectional filename editing

On 2026-11-20 a private native Linux x64 run found that the frozen egui 0.37
supervisor can render Japanese and Arabic with the reviewed fallback fonts.
Dragging across the leftmost Arabic glyph in a mixed filename can delete a
different character. An isolated port of the upstream caret patch fixes both
tested failures on that host. Windows x64, Windows ARM64 and Linux ARM64
candidate evidence and adoption in the maintained GUI profile remain open.

## Native observations

The experiment instruments the filename TextEdit from
`6c953e32c0b2710bfe06b19805214946653480af`. It records its actual glyph advances,
positions and logical selection, plus the full viewport returned by wgpu.
The two font profiles use the same executable within each comparison arm. The stock profile installs the two
baseline Noto fonts. The candidate appends Symbols 2, Arabic and CJK JP to both
font families. Eight 30-point samples share the field's font configuration.
A hit in the font mapping, visible raster ink, comparison with an explicitly
unmapped character, and distinct shapes are checked separately.

| Native Xvnc and Vulkan llvmpipe result | Observation |
| --- | --- |
| Latin-only control | Japanese あ and 界, pentagon ⬟, and Arabic ب, ت and ث all matched the unmapped U+10FFFD glyph's same 100-pixel mask. |
| Expanded font coverage | The six corresponding glyphs had distinct normalized masks with 274, 307, 390, 127, 134 and 141 ink pixels. Latin A and U+10FFFD retained their original masks. |
| Japanese editing | In `あ界⬟.jpg`, a click before the first glyph followed by Right moved the logical caret from 0 to 1. A native pointer drag across 界 selected indices 1–2. Delete left `あ⬟.jpg`. |
| Three connected Arabic letters in an LTR filename | For the logical sequence BEH, TEH, THEH, the leftmost painted glyph in the field's galley is THEH. A private pointer drag across that glyph selected logical indices 2–3, so Delete removed BEH. The galley contained two surplus zero-width entries. |
| Arabic surrounding European digits | The input sequence BEH, 1, 2, TEH between Latin prefixes and suffixes should appear as TEH, 1, 2, BEH when read from the left of this row. The native field instead showed BEH, 1, 2, TEH. Comparing its real pixels with the individually rendered references recognized BEH on the left (0.815 mask overlap, versus 0.130 for TEH) and TEH on the right (0.792, versus 0.157 for BEH). Drag and Delete removed BEH. |

The two expected visual index maps were checked independently with GNU
FriBidi 1.0.18, Unicode 18.0.0. The input reaches the isolated X server through
XTEST. The observed Xvnc screen was 1280 × 900 and the window readback was
640 × 400. Only the synthetic window and temporary bus were mounted. The
fixture also supports native Windows HWND-targeted input and DX12 readback.
Linux ARM64, Windows x64 and Windows ARM64 runs are pending for this experiment.

## Font origins and notices

The [input manifest](../../tools/rust-qa/font-coverage/inputs.json) pins the
unmodified binaries, complete matching license texts, upstream revisions and
original GUI source hashes. The [auditor](../../tools/rust-qa/font-coverage/inputs.py)
reads the actual OpenType copyright, family, version, trademark and license
records. The verified private build carries both complete license files and
the font-specific copyright and trademark records in its source receipt.

| Font | Original bytes | Embedded copyright | Source |
| --- | ---: | --- | --- |
| Noto Sans Symbols2 2.003 | 656,852 | Copyright 2017 Google Inc. All Rights Reserved. | [Original TTF](https://github.com/notofonts/noto-fonts/blob/ffebf8c1ee449e544955a7e813c54f9b73848eac/hinted/ttf/NotoSansSymbols2/NotoSansSymbols2-Regular.ttf) |
| Noto Sans Arabic 2.009 | 240,456 | Copyright 2015–2021 Google LLC. All Rights Reserved. | [Original TTF](https://github.com/notofonts/noto-fonts/blob/ffebf8c1ee449e544955a7e813c54f9b73848eac/hinted/ttf/NotoSansArabic/NotoSansArabic-Regular.ttf) |
| Noto Sans CJK JP 2.004 | 16,467,736 | © 2014–2021 Adobe | [Original OTF](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf) |

All three embedded license records identify SIL OFL 1.1. The Arabic TTF also
matches upstream Git object `ce21d4f5ac8765b51b9eedb1bb5c0069ee8115a4`.
The OFL permits packaging unmodified fonts with application software. Retain
the fonts' own license, copyright and trademark records, the Noto Project
Authors' notice for Symbols 2 and Arabic, and the complete CJK notice in a
bundle and its asset inventory. The first-party application remains
AGPL-3.0-only. The glyph evidence covers the characters listed above. Production asset selection remains open. [Noto OFL](https://raw.githubusercontent.com/notofonts/noto-fonts/ffebf8c1ee449e544955a7e813c54f9b73848eac/LICENSE)
and [CJK OFL](https://raw.githubusercontent.com/notofonts/noto-cjk/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE).

## Reproduction

The upstream Unicode table generator writes using the operating system's
text-mode line endings. The four-host comparison converts only generated CRLF
to LF, then compares the generated bytes with the untouched published table.
The local replay produced SHA-256 `8cbe4b6a4fc690e76107d4654047d3f0d8988b870fc3234f76dc265ad2e2a9ca`.
Both a changed row and a lone carriage return failed the comparison.

On the matching native host, first prepare the existing audited GUI toolchain,
registry and fonts as described in the [development guide](../development.md).
Use the target triple of that host. The local registry, exact released GUI
sources and reviewed lockfile are checked before compilation. Use `--acquire`
once to retrieve the public font originals and notices. Build and observation
outputs stay under ignored `artifacts/rust/font-coverage/`.

```sh
python3 tools/rust-qa/font-coverage/build.py x86_64-unknown-linux-gnu --acquire
python3 tools/rust-qa/font-coverage/observe.py x86_64-unknown-linux-gnu --require-bidi
```

Linux needs the existing private X11 observation prerequisites, lavapipe and the
`fribidi` QA command. The acceptance switch exits unsuccessfully on incorrect
visual order or selection after retaining the entire native log, PPM and
JSON result. Without that switch the command checks the font controls and CJK
editing, and records the Bidi measurements. Both first-party fixtures passed Rust formatting, Clippy with warnings denied,
and the release build. The private source copy of egui emits an upstream
deprecation warning for `std::f32::EPSILON` in the unchanged scene widget.
The retained [native comparison](../../tools/rust-qa/font-coverage/native-linux-x64.json)
binds both final build receipts, executables and raw observations.

## Upstream cause and tested correction

In epaint 0.37.0, `segment_into_runs` splits by font face and `shape_text`
guesses a direction for each resulting run. The runs are then placed in
input order. `layout_shaped_run` assumes increasing cluster offsets when it
emits trailing continuation slots. HarfRust returns decreasing offsets for
the RTL run, so the last cluster acquires unrelated following characters.
`Row::char_at`, `x_offset` and the arrow routines connect visual columns
directly to logical indices. This explains the observed paint, hit-test and
deletion discrepancies. Upstream #8698 fixes the surplus slots and word-motion
bounds. #8577 adds run-aware shaping. The tested #8828 also includes paragraph
ordering, grapheme-aware movement and cursor affinity at directional boundaries.
[Released layout code](https://github.com/emilk/egui/blob/841a328ba2dd8f6996beb7189ebb7fc00e668a2a/crates/epaint/src/text/text_layout.rs),
[cluster fix](https://github.com/emilk/egui/pull/8698),
[run shaping](https://github.com/emilk/egui/pull/8577) and
[caret integration](https://github.com/emilk/egui/pull/8828).

| Isolated Linux x64 candidate | Native observation |
| --- | --- |
| Japanese | All six glyph samples and both controls kept their masks. Right moved from logical 0 to 1. Drag and Delete removed only 界. |
| Connected Arabic run | Dragging the leftmost glyph selected logical 4–5 (THEH) and Delete removed it alone. Starting at the boundary inside the RTL run, Right and Left gave logical indices 4 → 3 → 4 at screen x 74 → 85 → 74. |
| Arabic and European digits | The screenshot independently matched TEH on the left and BEH on the right. Drag and Delete removed TEH. Right and Left within the digits gave logical indices 3 → 4 → 3 at screen x 71 → 88 → 71. |

Each edit was delivered through XTEST key or button events. The observers read
the resulting field state and compared pointer-selected content, deletion and
visual caret movement. Pixel readbacks independently verified rasterization.
AccessKit ranges, IME composition, complex multi-line selection, arbitrary
Unicode repertoire and native Wayland integration are outside this comparison.
The four target dependency graphs were resolved on Linux.
Native editing evidence for this candidate currently exists on Linux x64.

## Candidate inputs and integration

The [private reconstruction](../../tools/rust-qa/font-coverage/bidi_candidate.py)
uses the original published egui and epaint 0.37.0 crate archives. It extracts
17 Rust-file changes from upstream comparison
`fc9d66dda742d722eedaa8684d23f86369cf8e5f...e0bc7924dac211c5ff727d55922662ce371ec819`.
The full patch digest is `6d849fed4a055ef4b9f7b198fb1d8f195d47f7c3e1ce2a1cc745953983ab569b`.
The applied Rust-file projection is `e88857f13581c6363781817cb7a3536fb1a089f1b11a6123479b08701cac3160`.
Existing egui MIT and Apache notices match the upstream head byte for byte.
The upstream proposal remained unmerged at review. [Exact comparison](https://github.com/ahmedhosnypro/egui/compare/fc9d66dda742d722eedaa8684d23f86369cf8e5f...e0bc7924dac211c5ff727d55922662ce371ec819).

1. Reconstruct the two private crates at the above hashes and apply Cargo
   overrides only for egui and epaint. Add `unicode-bidi = "=0.3.18"` to epaint
   with defaults disabled and `hardcoded-data,std`. The private normalized
   manifest selects original source bytes and excludes optional tracing, serde
   and small-vector integrations. The remaining registry package identities,
   checksums and native normal/build features match the frozen GUI graph on
   each target. The fixture lock is `19aa12ab5d107dbc4b6a7257b3f0e41aa36771da335feccb079d6bba0b4da173`.
   The reviewed feature trees contain 235 packages for each Linux target and
   135 for each Windows target, including first-party packages.
2. Include upstream `AUTHORS`, `COPYRIGHT`, `LICENSE-MIT`, `LICENSE-APACHE`
   and the Unicode data notice alongside the existing egui notices. The
   unicode-bidi 0.3.18 crate has SHA-256
   `5c1cb5db39152898a79168971543b1cb5020dff7fe43c8dc468b0885f5e29df5`.
   Every compiled Rust file, its original manifest and its notices match
   upstream revision `580b9c6c68fdb689916017e61d5052be3ed349b5`. The recipe
   independently reproduces the compiled Unicode 16 table from UnicodeData.txt
   and BidiBrackets.txt with the original generator. The resulting SHA-256 is
   `8cbe4b6a4fc690e76107d4654047d3f0d8988b870fc3234f76dc265ad2e2a9ca`.
   [Servo source and notices](https://github.com/servo/unicode-bidi/tree/580b9c6c68fdb689916017e61d5052be3ed349b5),
   [Unicode 16 data](https://www.unicode.org/Public/16.0.0/ucd/ReadMe.txt) and
   [Unicode license](https://www.unicode.org/license.txt).
3. Register the three exact original fonts after the existing faces in both
   font families. Include both complete OFL texts and all original per-font
   copyright and trademark records in the asset and release-notice inventory.
   Keep unreviewed system and default fonts disabled.
4. The maintained build needs a source-aware graph auditor for the two
   reconstructed crate trees and the explicit unicode-bidi input. Recompute
   its reviewed target reports and compiler receipts, then exercise the same
   input sequences on each native host. The historical comparison restores
   files from the pinned GUI commit when the checkout differs. Retain that Git
   object in shallow checkouts that change those files.

Use the following command pair for the private corrected GUI. On Linux the
`fribidi` executable is supplied by `libfribidi-bin` on Ubuntu. The Windows
observer uses messages addressed to the verified child PID and window title.
Each run writes a separate result directory.

```sh
python3 tools/rust-qa/font-coverage/build.py x86_64-unknown-linux-gnu --bidi-candidate --acquire
python3 tools/rust-qa/font-coverage/observe.py x86_64-unknown-linux-gnu --bidi-candidate --require-bidi
```

At `5895c0b` both Windows architectures compiled the corrected sources and
rendered the first native DX12 control. Python then encountered an unrepresentable
character while writing the progress line to a redirected Windows-1252
console. The observer now stores the UTF-8 result before emitting an
ASCII-safe progress message. The remaining Windows controls require a new
native run. The ordinary Linux x64 GUI independently passed the integrated
glyph and mixed-direction editing checks. [Native build and observer logs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264)
and [integrated text evidence](rw02-gui-dependencies.md).
