# Dependabot PR #44 review — 2026-11-11

## Scope and failure

PR [#44](https://github.com/VoltKraft/immich-folder-watch/pull/44) updates the
build-only branding generator from Svg.Skia 3.6.0 to 5.2.3. Its original head
`945c4eaae02d73e2c3a223c06ad5a43654afa005` already includes current main
`a82216d4251e6517b71236602ab09abfdb13f3e1`; no refresh merge is necessary.
SkiaSharp and its Linux native branding dependency remain paired at 4.155.0.

CI run [43010830639](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43010830639)
failed both native Flatpak builds at the license installation gate. The first
reported missing version review was `ShimSkiaSharp/5.2.3`. All six updated
Svg-family archives omit embedded license texts, so adding only the first entry
would leave the next package blocked. The fix retains exact upstream texts and
adds all six version-specific catalog entries without relaxing the gate.

## Source and license evidence

All six Svg-family packages record source revision
[`7910666415a96a09643d1729eb5da5d115d75748`](https://github.com/wieslawsoltes/Svg.Skia/tree/7910666415a96a09643d1729eb5da5d115d75748).
`Svg.Skia`, `Svg.Model`, `Svg.SceneGraph`, `Svg.Animation`, and `ShimSkiaSharp`
use that revision's MIT license. `Svg.Custom` uses its MS-PL license, unchanged
from the previously reviewed build-only version. Neither this review nor the
notice inventory approves linking MS-PL into the AGPL application. The existing
separate tool boundary and absence from runtime output are required.

Retained upstream files and SHA-256:

- [Root MIT text](https://raw.githubusercontent.com/wieslawsoltes/Svg.Skia/7910666415a96a09643d1729eb5da5d115d75748/LICENSE.TXT):
  `31fdac60ff94d9cab3afef9794905df38c47e82b6879819c025d703d3aebd953`.
- [Svg.Custom MS-PL text](https://raw.githubusercontent.com/wieslawsoltes/Svg.Skia/7910666415a96a09643d1729eb5da5d115d75748/src/Svg.Custom/LICENSE.TXT):
  `d0ab1d6a97c328acf658b57141b6f2863d7eaf0066e42a9fd0792df0c4fd2521`.

The new build-only HarfBuzzSharp 14.2.0 family records source
[`4e4ce7af7ea8702593af5aeb25d05c65ffb74e90`](https://github.com/mono/SkiaSharp/tree/4e4ce7af7ea8702593af5aeb25d05c65ffb74e90).
Its archives embed the MIT license (SHA-256
`89101e35a8c66fd4d6dffc1763259161d35cb564c169714ec227a768c89f2938`).
Linux, macOS and Windows native notices have SHA-256
`21504c46c4c58aa64c1055bd2dcbc5f9a136b4b8c412ed3cc6740e22c5b127f5`,
identical to the existing reviewed SkiaSharp 4.155.0 native notices. The broad
collection includes permissive native terms and does not prove every named
component is linked. Unchanged ExCSS 4.3.1 retains its existing MIT supplement.

## Local validation

Using .NET SDK 10.0.203 selected under `global.json`:

- Branding restore and Release build succeeded with zero warnings/errors.
- The license installer succeeded against all 15 resolved branding package
  archives; all 15 license-helper unit tests passed.
- Linux x64 self-contained Release publish succeeded. Its `.deps.json` retains
  application SkiaSharp 3.119.4-preview.1.1 and HarfBuzzSharp 8.3.1.3. No Svg,
  ShimSkiaSharp or BrandAssetGen libraries or assemblies enter runtime output.
- Fresh branding output from current main was compared with the updated tool,
  using the same SVG source, SDK and SkiaSharp version. The copied SVG is
  byte-identical. The 160×160 header and all seven ICO frames (16, 24, 32, 48,
  64, 128 and 256 pixels) are pixel-identical.
- The 512×512 Flatpak PNG changes 46 of 262,144 pixels (0.01755%); maximum channel
  difference is 3/255, mean absolute RGBA channel difference is 0.0000811/255.
  Dimensions and nontransparent bounds remain `(0, 51, 512, 461)`. Both images
  were visually inspected; the folder/logo layout and colors remain consistent.

Commands were `dotnet build tools/BrandAssetGen/BrandAssetGen.csproj -c Release`,
`dotnet publish src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj
-c Release -r linux-x64 --self-contained true`, the notice helper against the
resolved scratch feed, and `python3 -m unittest discover -s tools/tests
-p test_install_flatpak_license_notices.py -v`. Generated files remain untracked.

## Remote validation and boundaries

The branch will be checked after this repair for Windows/Linux CI, both native
Flatpak builds, dependency review and CodeQL on its exact pushed revision.
The PR body records final run links and head to avoid a documentation-only commit
invalidating that evidence. No PR is merged, automatic merging remains disabled,
and PR #32 remains blocked. No release or stable Flatpak repository is published.
