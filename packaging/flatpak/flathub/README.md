# Flathub submission + maintenance

This directory holds the **Flathub-flavored** Flatpak manifest — the
one that lives in the per-app `flathub/io.github.voltkraft.ImmichFolderWatch`
repo Flathub creates on submission approval. It differs from
`../io.github.voltkraft.ImmichFolderWatch.yaml` (the internal manifest)
in two places:

1. The source is `type: git` pinned to a release tag + commit SHA,
   not `path: ../..`. Flathub builds offline from a stable ref.
2. `nuget-sources.json` is expected as a sibling file (regenerated
   per release from the matching tag and committed into the per-app
   Flathub repo). Locally gitignored to avoid two copies drifting.

## Pre-submission checklist (Phase 7.A)

- [x] `appstreamcli validate --pedantic ../io.github.voltkraft.ImmichFolderWatch.metainfo.xml` — only the `cid-contains-uppercase-letter` pedantic note remains; Flathub tolerates it.
- [x] `desktop-file-validate ../io.github.voltkraft.ImmichFolderWatch.desktop` — no warnings.
- [x] `flatpak-builder --show-manifest io.github.voltkraft.ImmichFolderWatch.yml` parses cleanly when a sibling `nuget-sources.json` is present.
- [x] Manifest `finish-args` reviewed against Flathub's "Permissions" guidance — every grant has a comment in the internal manifest explaining why we need it.
- [ ] Three screenshots in `../screenshots/` (see README there). User-action: capture from the live app on Fedora 44 + GNOME 46.
- [ ] `v2.5.0` tag pushed; `commit:` placeholder in the manifest replaced with the SHA `git rev-parse v2.5.0` reports.
- [ ] Fresh `nuget-sources.json` generated against the v2.5.0 tag (`tools/generate-nuget-sources.sh` from a clean checkout of the tag).

## Submission steps (Phase 7.B — user-action)

1. **Account.** Register at <https://flathub.org/login>. Sign in with
   GitHub. The first PR you open against `flathub/flathub` is gated
   on accepting the publisher agreement.
2. **Fork** <https://github.com/flathub/flathub>.
3. **Branch.** `git switch -c new-pr/io.github.voltkraft.ImmichFolderWatch`
4. **Add the manifest + nuget-sources.** Place both files at:
   - `apps/io.github.voltkraft.ImmichFolderWatch.yml` (or the
     directory form `apps/io.github.voltkraft.ImmichFolderWatch/`
     if Flathub's reviewer prefers — recent .NET app PRs use the
     directory form to keep `nuget-sources.json` out of the apps
     index root).
5. **Open the PR** against `flathub/flathub:new-pr`. Title format:
   `Add io.github.voltkraft.ImmichFolderWatch`.
6. **Review.** A Flathub maintainer (typically @razzeee, @bbhtt, or a
   bot) reviews within a few days. Common asks:
   - Tighten `finish-args` further (drop a permission, justify
     remaining ones in the PR body).
   - Re-spell metainfo categories or drop redundant keywords.
   - Move screenshots out of the upstream repo to a CDN they prefer.
7. **Merge.** After approval Flathub creates
   `flathub/io.github.voltkraft.ImmichFolderWatch` automatically and
   adds the submitter as a maintainer. Initial build runs immediately;
   the listing appears on flathub.org within an hour.

## Continuous publishing (Phase 7.C — to wire after 7.B)

The manifest already declares `x-checker-data` against the GitHub
Releases API. Once Flathub installs `flatpak-external-data-checker`
on the per-app repo (it ships with their stock CI), each new tag we
push to `VoltKraft/immich-folder-watch` will produce an auto-PR on
`flathub/io.github.voltkraft.ImmichFolderWatch` updating `tag` +
`commit`.

`nuget-sources.json` is not auto-updated by external-data-checker.
For each release, after the bot's PR appears we (the maintainer):

1. Check out the bot's branch in our flathub-app fork.
2. From a clean upstream checkout of the new tag, run
   `./tools/generate-nuget-sources.sh`.
3. Copy `packaging/flatpak/nuget-sources.json` into the bot's PR
   working tree, replacing the existing one.
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
2. Edit `io.github.voltkraft.ImmichFolderWatch.yml`:
   - `tag: v<NEW>`
   - `commit: <SHA from `git rev-parse v<NEW>`>`
3. Replace `nuget-sources.json` per the steps above.
4. Open a PR against the per-app repo's master.

## Files in this directory

- `io.github.voltkraft.ImmichFolderWatch.yml` — Flathub manifest
  (committed; this file is the source of truth that flows to the
  flathub-app repo at submission time).
- `nuget-sources.json` — gitignored; regenerated per release from
  the matching tag and only ever lives in the flathub-app repo
  long-term.
