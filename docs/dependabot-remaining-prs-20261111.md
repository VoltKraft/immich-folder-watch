# Remaining Dependabot PR preparation — 2026-11-11

## Scope

The user selected all remaining PRs except #32. The selected set is #38, #39,
#40, #42, #43, #44 and #45 against remote main
`a82216d4251e6517b71236602ab09abfdb13f3e1`. Each existing branch is updated through
ordinary commits/merges, with no force-push. No merge into main, main push,
release, deployment or live Immich access is authorized by this preparation.
The existing #32 license block and disabled automatic merging remain intact.

## Fixes and compatibility

| PR | Review result and changes |
| --- | --- |
| [38](https://github.com/VoltKraft/immich-folder-watch/pull/38) | Checkout 7.0.1, exact SHA/MIT/Node 24 review; existing trusted refs and disabled credential persistence preserved. |
| [39](https://github.com/VoltKraft/immich-folder-watch/pull/39) | GitHub Script 9.0.0, exact SHA/MIT/ESM compatibility review. New read-only CI smoke exercises actual action, CommonJS helper loading, REST lookup and outputs. |
| [40](https://github.com/VoltKraft/immich-folder-watch/pull/40) | Setup .NET 6.1.0, exact SHA/MIT review; current .NET 10 inputs and cache policy preserved. Publication-only WinGet path not executed. |
| [42](https://github.com/VoltKraft/immich-folder-watch/pull/42) | Windows Hosting 11.0.0 aligns with the existing Microsoft 11 graph. Fresh WPF restore selects net10 assembly without warnings; existing exact-source MIT and third-party notices cover it. |
| [43](https://github.com/VoltKraft/immich-folder-watch/pull/43) | SocketIOClient 4 removed the old transport interfaces. Port hardened adapters/DI/event handling, retain exact MIT notices, and fix the independently identified reconnect-after-stop lifetime gap. |
| [44](https://github.com/VoltKraft/immich-folder-watch/pull/44) | Svg.Skia 5.2.3 failed Flatpak's missing-license gate. Retain six exact-version source notices. MS-PL Svg.Custom stays in the separate branding tool; application runtime contains none of these tool assemblies. |
| [45](https://github.com/VoltKraft/immich-folder-watch/pull/45) | YamlDotNet 18.1.0 failed the same notice gate. Retain project and libyaml MIT texts; regression tests also exposed and fixed a pre-existing literal-string `null` round-trip defect. |

Detailed source revisions, hashes and local checks are retained in
`docs/dependabot-pr{38,39,40,42,43,44,45}-20261111.md` on the respective PR branches.
The branch reports are the authoritative per-dependency evidence; they need not
exist on local main before a merge.

## Local evidence and limits

- Actions: security/manifest/helper checks and exact source/license review.
  GitHub-hosted checks exercise current Node 24 runners; no publication is needed.
- Hosting: SDK 10.0.203 restores the WPF graph with `EnableWindowsTargeting=true`;
  hosted Windows CI supplies execution evidence unavailable on Linux.
- SocketIO's first fixed head passed Windows/Linux and CodeQL but exposed five
  additional Microsoft 10.0.3 notice gaps in the offline feed. The runtime graph
  remains on the existing 11.0.0 versions. The complete CI candidate feed was
  inventoried: all 89 archives passed SHA-512 verification, exact-source licenses
  were reviewed for the five additional versions, and the notice installer
  succeeded for 89/89. No unrelated legacy version was admitted.
- SocketIO: 18 focused synthetic transport/lifecycle cases, 486 portable Core
  tests, 53 Linux GUI/protocol tests and 15 license-helper tests pass. Independent
  security review found a P2 lifetime defect; the negative control reproduces it
  and the final fix passes. No remaining finding in the reviewed origin/TLS,
  redirects, credential use, per-response/message limits and lifecycle scope.
  Per-message limits do not constitute a total Socket.IO attachment memory budget.
- Svg: published app retains SkiaSharp 3.119.4-preview.1.1/HarfBuzz 8.3.1.3 and no
  Svg/Shim/BrandAssetGen runtime assembly. SVG bytes, header and all ICO frames
  match main; 46/262144 PNG pixels differ by at most 3/255. The branding result is
  visually unchanged. Fifteen license-helper tests pass.
- YAML: all 498 portable Core tests and 15 license-helper tests pass. New cases
  cover null-like/boolean-like/numeric strings, hashes, colons, dates, Unicode,
  Windows and UNC paths. The old serializer bug was reproduced on 15.1.2 before
  enabling necessary string quoting on 18.1.0. Original upstream notice bytes
  and CRLF line endings remain checksum-preserved.

## Hosted verification

| PR | Exact head | CI run | CodeQL run | NuGet submission | Result |
| --- | --- | --- | --- | --- | --- |
| #38 | `a1ebfc78bf7584c32fda6d5a0bd7e4912abfff52` | 43013956158 | 43013949077 | 43013947880 | 15/15 success, including separate Dependabot configuration check |
| #39 | `395225d662b52dbd1214c53d029be23476a65614` | 43015710092 | 43015701228 | 43015699961 | 14/14 success |
| #40 | `a758f1422e84c4a517504a768e74a8b7cdb7fd32` | 43013976112 | 43013969114 | 43013967089 | 15/15 success, including separate Dependabot configuration check |
| #42 | `2e36f9a851bfefeddde51660f7621ed7982bfb06` | 43014323712 | 43014318220 | 43014316031 | 14/14 success |
| #43 | `564269d33adffbbf7984f00d23eb54bd5e734a38` | 43017085757 | 43017077392 | 43017074878 | Final hosted checks pending |
| #44 | `19e72f6723ec7c4f0f5b15d9042c5decdf9d9a5e` | 43014159821 | 43014150502 | 43014148229 | 14/14 success |
| #45 | `9fe9d2790b3b837d7ff539c4b64bd90ca4ada07c` | 43015402572 | 43015397613 | 43015395383 | 14/14 success |

Every complete set includes eight CI jobs (Windows/Linux tests, packaging lint,
candidate preparation, native x86_64/aarch64 builds and two Pages artifact tests),
four actual CodeQL language analyses, the CodeQL aggregate and NuGet submission.
A neutral aggregate alone is not counted as successful analysis. Run links and
per-dependency detail are also preserved in each PR description.

## Separate queued Dependabot result

The initial refreshed #39 head `263b1ab` passed all 14 CI/CodeQL/submission checks,
but Dependabot app check `130500249152` stayed queued without output. The
signed-in GitHub check page exposed no restart control. Its service-side cause
cannot be inferred from the empty output. The final required changelog commit
`395225d` starts a new ordinary check cycle; no configuration requirement or
check gate is disabled. The old check is historical, not claimed successful. The final head has all
14 current checks successful and GitHub reports CLEAN; no separate configuration
check is attached to this documentation-only follow-up commit.

## Handoff

All selected PRs remain open for a separate merge decision. Root project
records are saved locally, preserving earlier unpublished documentation.
