# Remaining Dependabot PR review (2026-11-10)

## Follow-up integration validation

A later [configuration-check recovery attempt](dependabot-config-check-20261110.md)
advanced #34 to `f22797e` with an explanatory comment only. Its CI/CodeQL pass,
but the Dependabot service check remains queued; no recovery is claimed.

The subsequent authorized branch refresh incorporated main `13e93da` into all
five PRs. Every new head passed all six CI jobs, four CodeQL language analyses
and the aggregate CodeQL check. See [the current validation record](status.md#remaining-dependabot-refresh-completed-2026-11-10)
for exact heads, run links and the separately queued #34 Dependabot service check.
The initial review below remains evidence for unchanged proposed action/package
versions; its integration/CodeQL limitations describe the pre-refresh snapshot.
Publication-only paths remain unexecuted. No PR was merged.

## Scope and result

Reviewed the unchanged heads of #28, #29, #30, #31 and #34 for compatibility,
upstream license provenance and CI. No remote mutation, merge, rebase, workflow
rerun or publication was performed. Repository auto-merge remains disabled;
#32 remains open and blocked at `51898a8`.

No concrete compatibility or license blocker was identified in the five proposed
updates. This is not full integration acceptance: their successful CI predates
main `13e93da`, and CodeQL is neutral on every reviewed PR. Before a later merge,
validate the resulting integration with current main and obtain a complete
CodeQL assessment. Live publication paths were not exercised.

## Exact revisions and hosted validation

| PR | Update | Reviewed head | CI run |
| --- | --- | --- | --- |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | upload-artifact 6.0.0 → 7.0.2 | `339ee48a2d39eb2189e6cea54bfc65db3827a829` | [42874612332](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874612332) |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | deploy-pages 4.0.5 → 5.0.1 | `0c8975d528a0aa68a36bded68af8bf1dd71179f7` | [42874622935](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874622935) |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | configure-pages 5.0.0 → 6.0.0 | `383e1707e07253f07ee9da1c4a09eff50b8a26d7` | [42874636969](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874636969) |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | setup-node 6.5.0 → 7.1.0 | `9c6d43d74fae88b62cacc29ddf09b0caecbc2870` | [42874646182](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874646182) |
| [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34) | Branding SkiaSharp packages 3.119.1 → 4.155.0 | `a92df09f63b0ff2fe2e7749c06d8fe0b3d7e013c` | [42877735021](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42877735021) |

All five runs completed successfully with all six jobs passing: Windows/Linux
build and tests, packaging lint, candidate preparation, and native x86_64/ARM64
Flatpak builds. NuGet dependency submission also succeeded on each head. No CI
job is pending or failed on these five heads.

CodeQL is separately **neutral**, with the exact check title `4 configurations
not found` on all five PRs. Its summary cannot determine introduced alerts because
the main-branch configurations for Actions, C#, JavaScript/TypeScript and Python
were not found on these PR runs. Do not describe this as a successful security scan.

GitHub reports all five PRs open/unmerged and mergeable. Local `git merge-tree`
checks independently confirmed conflict-free integration of each unchanged head
with `origin/main` at `13e93da`; these only compute Git trees, do not merge branches,
and do not establish runtime compatibility. The old CI results are not evidence
of a new combined build after #27/#33/#35/#36 were merged.

## #28: upload-artifact

- Proposed pin: `cf430e030ddbb5b0abf93d22962f4752f3646cd9`, matching official v7.0.2.
- [MIT license at the exact commit](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/LICENSE).
  It remains a CI tool, with no new application-distribution dependency.
- [v7 release changes](https://github.com/actions/upload-artifact/releases/tag/v7.0.0)
  introduce ESM and optional unarchived single-file uploads. All three repository
  calls upload directories using the unchanged default `archive: true`; names and
  zipped contents retain their contract. See the [exact action definition](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/action.yml).
- Both old and new actions use Node 24. The successful candidate job used runner
  2.338.2 and explicitly executed the new SHA, successfully uploading the named
  candidate artifact. Both architecture jobs consumed it successfully.
- Release MSI upload and Flathub release-preparation upload were not executed by
  PR CI. That run used download-artifact v7; current main uses v8.0.2. Fresh
  integration CI is needed to confirm the combined repository configuration.

## #29 and #30: Pages actions

- deploy-pages pin: `368f82528645a54fb793d4d04e342629a3f51346` (v5.0.1).
  configure-pages pin: `45bfe0192ca1faeb007ade9deae92b16b8254a0d` (v6.0.0).
  Each PR changes only its SHA/version comment in `flatpak-pages.yaml`.
- Exact [deploy MIT license](https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/LICENSE)
  and [configure MIT license](https://github.com/actions/configure-pages/blob/45bfe0192ca1faeb007ade9deae92b16b8254a0d/LICENSE)
  have the same Git blob `8c9e791c9fb1f1433344d07ca0dd6a426c243c0a`.
- [Deploy v5](https://github.com/actions/deploy-pages/releases/tag/v5.0.0) and
  [configure v6](https://github.com/actions/configure-pages/releases/tag/v6.0.0)
  move Node 20 to Node 24. The hosted `ubuntu-24.04` runner is suitable; Node 24
  support starts at [runner 2.327.1](https://github.com/actions/runner/releases/tag/v2.327.1).
- The [deploy action contract](https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/action.yml)
  and [configure action contract](https://github.com/actions/configure-pages/blob/45bfe0192ca1faeb007ade9deae92b16b8254a0d/action.yml)
  retain used inputs/outputs, including `base_url`, `page_url` and `github-pages`.
  Existing `pages: read` configuration and `pages: write`/`id-token: write`
  deployment permissions and `github-pages` environment match these contracts.
  Automatic Pages enablement stays off by default.
- [Deploy 5.0.1](https://github.com/actions/deploy-pages/releases/tag/v5.0.1)
  adds polling backoff/jitter while keeping the ten-minute default timeout.
- PR CI does not run the publication/manual Pages workflow. Actual Pages API,
  OIDC and deployment behavior is therefore not verified by these passing jobs.
  No live deployment was triggered for this review.

## #31: setup-node

- Proposed pin: `949feb2413d6458794dcd2491c4babbbce0c15c1`, matching official v7.1.0.
  [Exact MIT license](https://github.com/actions/setup-node/blob/949feb2413d6458794dcd2491c4babbbce0c15c1/LICENSE).
- [v7](https://github.com/actions/setup-node/releases/tag/v7.0.0) migrates internals
  to ESM. The [current pinned contract](https://github.com/actions/setup-node/blob/949feb2413d6458794dcd2491c4babbbce0c15c1/README.md)
  also removes a dummy authentication-token fallback. The only repository call
  sets `node-version: '22'`, with no registry authentication or package caching;
  neither change affects its intended behavior. Both old/new actions use Node 24.
- CI logs confirm runner 2.338.2, execution of the exact new SHA, installation of
  Node 22.23.4, passing subsequent Flathub automation tests and successful post-action.

## #34: SkiaSharp branding tool

- Only `tools/BrandAssetGen/BrandAssetGen.csproj` changes. Both direct SkiaSharp
  packages move to 4.155.0; `Svg.Skia` remains 3.6.0.
- Official [managed package](https://api.nuget.org/v3-flatcontainer/skiasharp/4.155.0/skiasharp.4.155.0.nupkg),
  [Linux native package](https://api.nuget.org/v3-flatcontainer/skiasharp.nativeassets.linux.nodependencies/4.155.0/skiasharp.nativeassets.linux.nodependencies.4.155.0.nupkg),
  [Win32 package](https://api.nuget.org/v3-flatcontainer/skiasharp.nativeassets.win32/4.155.0/skiasharp.nativeassets.win32.4.155.0.nupkg)
  and [macOS package](https://api.nuget.org/v3-flatcontainer/skiasharp.nativeassets.macos/4.155.0/skiasharp.nativeassets.macos.4.155.0.nupkg)
  identify `mono/SkiaSharp` source `d25e7fa628a2576e50ecc42004cc4fd03c6657f5`.
  The native Skia gitlink is [c2d78902a56e24827a7273a4ed3461ce18780680](https://github.com/mono/skia/tree/c2d78902a56e24827a7273a4ed3461ce18780680).
- All four archives contain [MIT license text](https://github.com/mono/SkiaSharp/blob/d25e7fa628a2576e50ecc42004cc4fd03c6657f5/LICENSE.txt),
  SHA-256 `89101e35a8c66fd4d6dffc1763259161d35cb564c169714ec227a768c89f2938`.
  Native components have additional licenses; they are not collectively MIT.
- All three native archives contain identical 139,775-byte third-party notices,
  SHA-256 `21504c46c4c58aa64c1055bd2dcbc5f9a136b4b8c412ed3cc6740e22c5b127f5`.
  These match Linux.NoDependencies 3.119.1 byte-for-byte. The notices include BSD,
  Apache, Unicode, FreeType and alternative copyleft terms. No newly introduced
  notice terms were found; the broad notice inventory does not establish which
  components are linked or constitute an independent audit of every component.
  Existing packaging retains embedded notices automatically; no additional
  exact-version supplemental catalog entries are needed for these archives.
- Scratch restore confirms the application still resolves SkiaSharp
  3.119.4-preview.1.1. Version 4.155.0 is isolated to BrandAssetGen because the app
  project reference uses `ReferenceOutputAssembly="false"`. This PR introduces no
  Avalonia managed/native version mismatch and does not upgrade app rendering.
- The additional exact-head scratch build passed with zero warnings/errors and
  generated branding assets from the checked-in logo. SVG loading, surface/canvas
  rendering and PNG encoding therefore work for this use case. Evidence remains
  under `/tmp/ifw-pr34-review/`; no generated output was committed.
- [Upstream v4 migration notes](https://github.com/mono/SkiaSharp/blob/d25e7fa628a2576e50ecc42004cc4fd03c6657f5/documentation/docfx/releases/4.148.0.md)
  contain real breaking changes. Passing this generator is not a claim that all
  Svg.Skia 3.6.0 SVG/font/API features work with SkiaSharp 4. No visual comparison
  or live application test is claimed.

## License scope

The four reviewed GitHub Actions retain MIT licenses and are used as external CI
services/tools; their code is not introduced into shipped application binaries.
The permissive terms introduce no identified conflict with AGPL-3.0-only in this
usage. This source/provenance review is not an audit of every transitive npm module.
