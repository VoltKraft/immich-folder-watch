# Flathub submission + maintenance

> **Status:** Flathub publication is postponed. GitHub Releases is the active
> Linux distribution channel. Keep this material for a future submission, but
> do not advertise the app as currently available from Flathub.

This directory holds the shared Flatpak manifest intended for the future
`flathub/io.github.voltkraft.immich-folder-watch` repository. The upstream
release workflow also derives its commit-pinned GitHub bundle manifest from
this file, so packaging permissions and build commands remain in one place.

Key properties:

1. The source is `type: git` pinned to a release tag + commit SHA.
   Flathub builds offline from a stable ref.
2. `nuget-sources.json` is expected as a sibling file (regenerated
   per release from the matching tag and committed into the per-app
   Flathub repo). Locally gitignored to avoid two copies drifting.
3. The manifest maps Flatpak `x86_64` and `aarch64` to the self-contained .NET
   runtimes `linux-x64` and `linux-arm64`. A future Flathub submission must
   provide an offline source list covering both builds.

## Pre-submission checklist (Phase 7.A)

- [x] `appstreamcli validate --pedantic ../io.github.voltkraft.immich-folder-watch.metainfo.xml` — only the `cid-contains-uppercase-letter` pedantic note remains; Flathub tolerates it.
- [x] `desktop-file-validate ../io.github.voltkraft.immich-folder-watch.desktop` — no warnings.
- [x] `flatpak-builder --show-manifest io.github.voltkraft.immich-folder-watch.yml` parses cleanly when a sibling `nuget-sources.json` is present.
- [x] Manifest `finish-args` reviewed against Flathub's "Permissions" guidance.
- [x] StatusNotifierItem tray disabled for the Flathub build; the current
  Avalonia tray backend requires a broad KDE D-Bus own-name grant that Flathub
  no longer accepts for new apps.
- [ ] Three screenshots in `../screenshots/` (see README there). User-action: capture from the live app on Fedora + GNOME.
- [ ] Release tag pushed; `tag:` and `commit:` in the submission manifest match
  the version and SHA reported by `git rev-parse v<version>`.
- [ ] Fresh architecture-complete `nuget-sources.json` generated against that
  tag from a clean checkout. GitHub release jobs currently generate isolated
  source lists with `tools/generate-nuget-sources.sh --runtime <runtime>`.

## Submission steps (Phase 7.B — user-action)

1. **Account.** Register at <https://flathub.org/login>. Sign in with
   GitHub. The first PR you open against `flathub/flathub` is gated
   on accepting the publisher agreement.
2. **Fork** <https://github.com/flathub/flathub>.
3. **Branch.** `git switch -c add-io.github.voltkraft.immich-folder-watch`
4. **Add the manifest + nuget-sources.** Place both files at the root of
   the submission branch:
   - `io.github.voltkraft.immich-folder-watch.yml`
   - `nuget-sources.json`
5. **Open the PR** against `flathub/flathub:new-pr`. Title format:
   `Add io.github.voltkraft.immich-folder-watch`.
6. **Review.** A Flathub maintainer (typically @razzeee, @bbhtt, or a
   bot) reviews within a few days. Common asks:
   - Tighten `finish-args` further (drop a permission, justify
     remaining ones in the PR body).
   - Re-spell metainfo categories or drop redundant keywords.
   - Move screenshots out of the upstream repo to a CDN they prefer.
7. **Merge.** After approval Flathub creates
   `flathub/io.github.voltkraft.immich-folder-watch` automatically and
   adds the submitter as a maintainer. Initial build runs immediately;
   the listing appears on flathub.org within an hour.

## Continuous publishing (Phase 7.C — to wire after 7.B)

The manifest already declares `x-checker-data` against the GitHub
Releases API. Once Flathub installs `flatpak-external-data-checker`
on the per-app repo (it ships with their stock CI), each new tag we
push to `VoltKraft/immich-folder-watch` will produce an auto-PR on
`flathub/io.github.voltkraft.immich-folder-watch` updating `tag` +
`commit`.

`nuget-sources.json` is not auto-updated by external-data-checker.
For each release, after the bot's PR appears we (the maintainer):

1. Check out the bot's branch in our flathub-app fork.
2. From clean `x86_64` and `aarch64` upstream checkouts of the new tag,
   generate the corresponding source lists with
   `./tools/generate-nuget-sources.sh --runtime linux-x64` and
   `./tools/generate-nuget-sources.sh --runtime linux-arm64`.
3. Copy `packaging/flatpak/flathub/nuget-sources.json` into the bot's PR
   working tree after combining the two lists without duplicate sources.
4. Push to the bot's branch; the PR re-runs Flathub's CI, which
   builds offline against the new feed.
5. Merge after CI passes.

This is the standard cadence for .NET apps on Flathub. A future
optimization is a GitHub Action in our own repo that does steps 1-4
automatically; deferred until 7.B is done and we know the per-app
repo's exact PR conventions.

## Manual fallback

If the bot's PR breaks (e.g., GitHub Releases API schema change,
expired GitHub Action token):

1. Branch in the flathub-app repo.
2. Edit `io.github.voltkraft.immich-folder-watch.yml`:
   - `tag: v<NEW>`
   - `commit: <SHA from `git rev-parse v<NEW>`>`
3. Replace `nuget-sources.json` per the steps above.
4. Open a PR against the per-app repo's master.

## Files in this directory

- `io.github.voltkraft.immich-folder-watch.yml` — shared source manifest
  (committed; it feeds GitHub bundle builds now and the Flathub app repo after
  a future submission).
- `nuget-sources.json` — gitignored; regenerated per release from
  the matching tag and only ever lives in the flathub-app repo
  long-term.
