# PR #34 refreshed validation (2026-11-11)

## Scope and revision

The user selected work on [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34),
without merging. Integrated remote main `2a9a96d18ead49682804cdbe61e444b8c5f99703`
into `f22797ed4d452e1940493bf09d44b25b931b2ee8` as `41d2ab1`, then pushed
`1a4722cc8ddf4d34ff0588627e804c7f9e3f8a59` with scoped maintenance documentation.
No history rewrite, protection bypass, release or deployment was used.

## Compatibility and licenses

- Both direct BrandAssetGen SkiaSharp dependencies remain the proposed 4.155.0;
  Svg.Skia remains 3.6.0. The app references the generator only for build ordering.
- Fresh main/PR generator builds using installed SDK 10.0.203 (allowed by global.json)
  passed with zero warnings/errors and generated the actual repository logo.
- Linux app restore resolves SkiaSharp and its native packages to
  3.119.4-preview.1.1; the app asset graph contains no SkiaSharp 4 package.
- All four downloaded 4.155.0 package archives again contain the exact MIT license
  hash and all three native archives contain the exact third-party-notice hash
  recorded in [the original source/license review](dependabot-review-20261110.md#34-skiasharp-branding-tool).
  Independent review rechecked the immutable upstream license and migration notes;
  no new license or source-level compatibility blocker was found.
- This is validation of the build-tool usage, not all Svg.Skia v3/v4 API combinations
  or an independent audit of every native component.

## Branding comparison

Compared decoded RGBA pixels and all seven embedded PNG ICO frames, using identical
source SVG and generator code from main and #34. Both PNGs and all ICO frames retain
identical dimensions and nontransparent bounds. SVG output is byte-identical.

- 512px Flatpak PNG: 19 of 262,144 pixels differ; maximum channel delta 1/255.
- 160px header PNG: 551 of 25,600 pixels differ; mean absolute channel delta
  0.068/255, maximum 51/255. Visual inspection preserves artwork and proportions.
- ICO sizes 16/24/32/48/64/128/256 decode successfully. Independent magnified
  inspection on white and dark backgrounds found no missing elements, crop or
  new halo; differences follow edge antialiasing. At 16px, raw channel deltas up
  to 255 occur in low-alpha pixels; composited maximum is 40/255, mean 1.78/255
  on white and 2.05/255 on dark. These raster changes are accepted for the update.
- Scratch evidence: `/tmp/ifw-pr34-branding-comparison.json` and
  `/tmp/ifw-pr34-visual-review/ico-comparison.png` / `composited-metrics.json`.
  Generated assets remain untracked and are not part of the change.

## Hosted validation

- [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43002535947): all eight jobs succeeded, including Windows/Linux tests,
  both native Flatpak candidates and both Pages artifact round trips.
- [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43002529061): all four language analyses succeeded; aggregate CodeQL also passed.
- [NuGet submission](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43002526226): success.

The final checked head has no Dependabot App check/suite. Parsed Dependabot YAML
is identical to current main; the existing explanatory comment is nonfunctional.
The old queued runs `130138962423` / `130148023423` were not completed or forged;
this refresh replaces the obsolete commit for PR acceptance. See the
[original diagnosis](dependabot-config-check-20261110.md) for the unresolved
internal service cause. Final readback reports 14 successful checks, no pending
checks, `MERGEABLE` / `CLEAN`, and zero open code-scanning alerts. The PR description
contains the exact-head evidence. No recreation or support contact was needed.

PR #32 stays blocked and unchanged; automatic merging remains disabled. No main
push, release, Pages deployment or live application/Immich test was performed.
