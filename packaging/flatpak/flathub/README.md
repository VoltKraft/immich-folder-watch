# Flathub submission and release updates

Status: the upstream automation is prepared; the app has not been submitted by
this change. GitHub Releases remains the available Linux channel until Flathub
accepts and publishes the app. Initial submission and automerge activation have
external prerequisites below. No existing release is changed or backfilled.

## Release flow

`.github/workflows/release.yaml` first publishes the complete four-artifact
GitHub Release, then dispatches WinGet and Flathub independently. The explicit
dispatch is necessary because releases created with `GITHUB_TOKEN` do not start
other `release` workflows. `flathub.yaml` also handles human-published releases
and supports manual preparation of an existing stable release.

The Flathub workflow:

1. Reads the published release and checks out its exact tag. Tooling comes from
   `main`; application code, metadata and manifest come from the release commit.
2. Generates NuGet sources for `linux-x64` and `linux-arm64`, merges them
   deterministically, and pins the manifest to the release tag and full SHA.
   It rejects drafts, prereleases, version mismatches, dirty source checkouts,
   incomplete GitHub asset sets, invalid hashes and conflicting package sources.
3. Saves the three packaging files as the `flathub-v<version>` Actions artifact.
   Separate native x86_64 and aarch64 jobs build the same combined offline feed.
   They mirror screenshots and run Flathub's repository linter on each export.
   Download the packaging artifact only after both validation jobs succeed.
4. When enabled, opens an update PR in the **existing**
   `flathub/io.github.voltkraft.immich-folder-watch` repository. It updates only
   the manifest and NuGet feed, preserving Flathub's repository configuration.
   Retries reuse matching PRs; superseded releases are skipped, and conflicting
   branches or rejected PRs require maintainer attention.
5. When separately enabled after approval, requests GitHub automerge. Flathub
   checks still apply, and Flathub publishes its own successful build after merge.

A Flathub error does not remove an already published GitHub Release or block
WinGet. Inspect the failed Actions job and rerun the Flathub workflow for the
same tag. Preparation always works without a Flathub write token; submission is
opt-in. No code in this repository submits the initial app to `flathub/flathub`.

## Current requirements review

Checked on 2026-09-10 against the official
[requirements](https://docs.flathub.org/docs/for-app-authors/requirements),
[submission procedure](https://docs.flathub.org/docs/for-app-authors/submission),
[runtime policy](https://docs.flathub.org/docs/for-app-authors/runtimes), and
[maintenance guide](https://docs.flathub.org/docs/for-app-authors/maintenance).
These policies can change; recheck them before submitting.
See [validation evidence](../../../docs/qa/flathub-preparation.md) for executed
checks and the native ARM64/remote publication boundaries.

| Area | Repository status and remaining action |
| --- | --- |
| Application identity | The reverse-domain ID maps to the GitHub project. Desktop entry, metadata and icon use the same ID. Verify GitHub ownership in Flathub's developer portal after acceptance. |
| License and sources | AGPL-3.0-only application, CC0 metadata, immutable Git source and hashed NuGet downloads. The build includes package license/notice texts and versioned upstream supplements. Submit packaging files only. The maintainer must confirm rights to the current name/logo before submission. |
| Runtime | **Open prerequisite:** 26.08 Platform/SDK is available for both architectures, while the .NET 10 SDK extension is currently available only through 25.08. New submissions require the latest runtime. Obtain a reviewer exception for supported 25.08 or wait for a compatible 26.08 extension and update/test all packaging tooling together. |
| Offline builds | The generator covers both architectures; native CI builds verify the combined feed. Flathub will also run its own build and repository linter. |
| Sandbox | No broad filesystem, session/system bus or host-spawn access. Folder selection and autostart use portals. X11/IPC matches the current Avalonia backend; do not replace it with Wayland permissions without testing backend support. |
| Notifications | `DBusNotifier` uses the Notification portal with no direct notification-daemon permission. Isolated bus tests verify the portal contract; desktop presentation still needs a smoke test. |
| Metadata | English description, setup requirements/help link, community-client identity, developer, release, OARS, categories, desktop entry and square 512px icon are present. Validate the exact released revision, including reachable screenshots. |
| Screenshots | The current images render actual Avalonia controls with sample data. Native Linux captures would better satisfy optional listing-quality guidance; see the [screenshot notes](../screenshots/README.md). |
| Automation | Custom update PRs are supported. Disable the global external-data checker to avoid tag-only updates with stale NuGet sources. Automerge requires Flathub approval. |
| Human submission | A maintainer must perform the initial submission and review interactions and disclose AI-generated material as required below. |

The manifest linter reports that 26.08 is available. Its warning is not approval
for a new submission on 25.08. A 25.08 SDK extension must not simply be combined
with a 26.08 base; see [extension compatibility](https://docs.flatpak.org/en/latest/extension.html#finding-base-runtime-version).
The official [.NET 10 extension](https://github.com/flathub/org.freedesktop.Sdk.Extension.dotnet10)
documents the self-contained build and offline NuGet approach used here.

## Prepare the packaging files

Before creating a release, run **CI** on the development branch. Its reusable
`flatpak-validation.yaml` workflow builds the exact public commit on both native
architectures, using the same combined feed and repository lint checks. The
`flatpak-validation-<commit>-<architecture>` artifacts contain installable
candidate bundles on the `test` branch; `flatpak-candidate-<commit>` contains
their packaging inputs. These artifacts are for validation, not initial
submission: final submission files must refer to a published stable release.

After this tooling is merged to `main`, run the **Flathub** workflow with the
published `release_tag` and leave `submit` false. This generates and builds a
reviewable artifact without creating a PR. The artifact contains only:

- `io.github.voltkraft.immich-folder-watch.yml`
- `nuget-sources.json`
- `flathub.json`

For local preparation, start in the upstream repository with the SDK and Flatpak
prerequisites from [the packaging guide](../README.md). Use a new output directory:

```bash
release_tag=v2.11.0
validation_dir="$PWD/artifacts/flathub-preparation"
mkdir -p "$validation_dir"
git clone --branch "$release_tag" https://github.com/VoltKraft/immich-folder-watch.git "$validation_dir/source"
gh api "repos/VoltKraft/immich-folder-watch/releases/tags/$release_tag" > "$validation_dir/release.json"
tools/generate-nuget-sources.sh --source-root "$validation_dir/source" \
  --runtime linux-x64 --output "$validation_dir/nuget-x64.json"
tools/generate-nuget-sources.sh --source-root "$validation_dir/source" \
  --runtime linux-arm64 --output "$validation_dir/nuget-arm64.json"
python3 tools/prepare-flathub-release.py \
  --source-root "$validation_dir/source" \
  --release-json "$validation_dir/release.json" \
  --commit "$(git -C "$validation_dir/source" rev-parse HEAD)" \
  --nuget-x64 "$validation_dir/nuget-x64.json" \
  --nuget-arm64 "$validation_dir/nuget-arm64.json" \
  --output-dir "$validation_dir/package"
```

The command uses the selected release's metadata. Fixes made after that tag,
including screenshot changes, need a new release; preparation does not inject
unreleased application or metadata changes into the source tree.

Validate with the official Builder, which includes Flathub's linter:

```bash
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
  manifest "$validation_dir/package/io.github.voltkraft.immich-folder-watch.yml"
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
  appstream "$validation_dir/source/packaging/flatpak/io.github.voltkraft.immich-folder-watch.metainfo.xml"
flatpak run org.flatpak.Builder --user --force-clean --sandbox \
  --default-branch=stable \
  --mirror-screenshots-url=https://dl.flathub.org/media \
  --compose-url-policy=full \
  --repo="$validation_dir/repo" "$validation_dir/build" \
  "$validation_dir/package/io.github.voltkraft.immich-folder-watch.yml"
flatpak run --command=flatpak-builder-lint org.flatpak.Builder repo "$validation_dir/repo"
```

Repeat build validation on native ARM64 or use the workflow's ARM64 job. Also
install and test Flathub's eventual PR build for folder access, upload/sync,
notifications, tray, autostart and restart persistence. Host unit tests and an
x86_64 build do not prove native ARM64 behavior or Flathub acceptance.

## Initial submission by the maintainer

Resolve the open requirements above first. Follow the official submission guide
to create the initial PR through GitHub's web interface against the `new-pr`
branch of `flathub/flathub`, using only the generated packaging files. Compose
its commit message, description, disclosure and review replies yourself.

Flathub's [generative AI policy](https://docs.flathub.org/docs/for-app-authors/requirements#generative-ai-policy)
requires disclosure of generated code, documentation and packaging, including
the affected parts and approximate extent. It prohibits AI agents from creating
or automating submission PRs or writing their submission/review interactions.
This preparation includes AI-generated automation and documentation; review it
and account for any earlier generated application content in your own disclosure.

After acceptance, enable GitHub 2FA and accept the per-app repository invitation
within the documented deadline. Complete
[verification](https://docs.flathub.org/docs/for-app-authors/verification) using
GitHub ownership. Mirror any reviewer-required manifest changes upstream before
enabling updates, so a later release does not undo them.

## Activate release updates

Configure these in the **upstream** repository's Actions settings only after the
Flathub application repository exists and its first build has been accepted:

| Setting | Purpose |
| --- | --- |
| Secret `FLATHUB_TOKEN` | Maintainer token with write access to the accepted Flathub app repository. Outside collaborators currently need a classic PAT with `public_repo`, subject to organization policy. Organization members eligible for fine-grained tokens can instead grant Contents and Pull requests read/write on this app repository, with organization approval where required. |
| Variable `FLATHUB_AUTOMATION_ENABLED=true` | Enables update PR submission after both native build jobs succeed. Leave unset until the first submission is accepted. |
| Variable `FLATHUB_AUTOMERGE_ENABLED=true` | Requests GitHub automerge on update PRs. Leave unset until Flathub has explicitly granted GitHub automerge for this app. |

The destination is fixed to the accepted app repository's `master` branch.
The upstream `GITHUB_TOKEN` cannot write there. See
[GitHub's token limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens-limitations)
before choosing a token; it also needs read access to the public upstream release.
Its `flathub.json` must contain `"disable-external-data-checker": true`, as the
initial generated file does. Do not also enable checker-driven update PRs.
The updater also requires both `x86_64` and `aarch64` in `only-arches` and rejects
any skipped architecture in the accepted repository; upstream build success
alone must not permit publishing an update for just one architecture.

Ask Flathub for GitHub automerge through its documented
[automerge request process](https://docs.flathub.org/docs/for-app-authors/maintenance#automerge-request).
Do not bypass branch protections or add `automerge-flathubbot-prs` for this
custom updater. Until approval, merge successful, tested update PRs manually.
Once approved, the intended flow is **GitHub Release → update PR → checks →
automerge → Flathub build/publication**. Permission or critical metadata changes
may still require moderation; publication has no fixed completion time.

For retries, manually run **Flathub** with the same `release_tag` and `submit`
true. It requires the enable variable and token. A release superseded by a newer
stable release cannot downgrade the listing. Investigate rejected PRs or branch
content conflicts instead of overwriting a reviewer's changes. Keep the token
valid and maintain runtime/security updates for the self-contained .NET package.

## User migration after publication

Announce Flathub availability only after its stable listing can actually be
installed. Link users to [Linux installation](../../../docs/installation-linux.md)
for migration from a GitHub bundle. That migration preserves the same app ID and
per-user configuration; do not delete Flatpak application data.
