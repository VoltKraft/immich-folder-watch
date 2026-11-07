# GitHub Pages Flatpak repository

The prepared repository URL is <https://voltkraft.github.io/immich-folder-watch/>.
Activation is pending explicit approval for uploading the signing key; see
[project status](../../docs/status.md).
It supplements GitHub Release bundles and is independent of Flathub acceptance.
See [Linux installation](../../docs/installation-linux.md) for user commands.

## Publication contract

`.github/workflows/flatpak-pages.yaml` imports both existing Linux bundles from
GitHub's latest published stable `vMAJOR.MINOR.PATCH` release. It does not rebuild
application sources or change release assets. The existing `master` Flatpak
branch is preserved for x86_64 and aarch64. CI's `test` branch is rejected.

The workflow runs for published releases and manual dispatch. The release
workflow explicitly dispatches it because events created by `GITHUB_TOKEN`
do not trigger other workflows. Manual runs must use the default branch; the
optional `release_tag` must equal the latest release. One concurrency group
serializes complete deployments, and a second latest-release check runs just
before deployment. A stale run fails without replacing the current site.

`tools/build-flatpak-repo.py` creates a fresh archive-mode OSTree snapshot, signs
both application commits and the repository summary, and regenerates AppStream.
It publishes these paths in one Pages artifact:

- `repo/`: OSTree objects, refs, summary and signatures.
- `immich-folder-watch.flatpakrepo`: repository descriptor and public key.
- `io.github.voltkraft.immich-folder-watch.flatpakref`: native-architecture installer,
  suggested remote name `immich-folder-watch`, and Flathub runtime source.
- `public-key.gpg`, `index.html`, `.nojekyll`.

Only the latest release snapshot is retained. Ordinary Flatpak updates work
without server-side historical commits; historical rollback comes from release
bundles. Objects shared by both architectures are deduplicated. Static deltas
are not generated. Clients request individual objects over HTTPS.
The generator rejects sites above 950 MB, leaving headroom below Pages' 1 GB
limit. Pages also has a soft 100 GB/month bandwidth limit; move to suitable
hosting if distribution exceeds it. Generated repositories are not stored in Git.
A failed build/deployment leaves the previous published site available.

## Signing identity and initial setup

Public fingerprint:

```text
4ED65AC1C14D559C721C7A8B44B33451708EAD7D
```

The corresponding public key is tracked in
[`repository-signing-key.asc`](repository-signing-key.asc). The private key must
never be committed, logged, or uploaded as a workflow artifact. GitHub requires:

| Setting | Value / purpose |
| --- | --- |
| Settings → Pages → Source | GitHub Actions (`build_type: workflow`) |
| Actions secret `FLATPAK_GPG_PRIVATE_KEY` | ASCII-armored private signing key; noninteractive, without a passphrase |
| Actions variable `FLATPAK_GPG_KEY_ID` | Full fingerprint above |
| Environment `github-pages` | Permit default-branch deployments and release tags if using the `release: published` trigger |

The initial setup stores a private recovery copy locally in ignored
`artifacts/flatpak-signing/private-key.asc` (directory mode 0700, file mode 0600).
Keep a secure backup outside disposable build artifacts before cleaning that
directory. GitHub Secrets cannot be downloaded to reconstruct a lost key.
An existing key must be reused: replacing it silently breaks installed clients'
trust. Plan a signed trust transition or explicit client re-enrollment for
rotation; update the public key and fingerprint in the same reviewed change.

For a repository administrator restoring the existing setup:

```bash
gh secret set FLATPAK_GPG_PRIVATE_KEY --repo VoltKraft/immich-folder-watch \
  < /secure/backup/private-key.asc
gh variable set FLATPAK_GPG_KEY_ID --repo VoltKraft/immich-folder-watch \
  --body 4ED65AC1C14D559C721C7A8B44B33451708EAD7D
# Only when Pages is absent; update an existing site instead of replacing it.
gh api --method POST repos/VoltKraft/immich-folder-watch/pages -f build_type=workflow
gh workflow run flatpak-pages.yaml --repo VoltKraft/immich-folder-watch --ref main
```

The build job has only contents/pages read access. The separate deployment job
has `pages: write` and `id-token: write`, uses the `github-pages` environment,
and does not receive the signing secret. The key is imported into a temporary
GNUPGHOME and removed on exit. Fork/PR runs cannot deploy this workflow.

## Recovery and validation

Re-run **Flatpak repository** on `main` after fixing a failure. An empty tag input
selects the latest release, including the first publication of an already-existing
release. A partial or failed import never becomes a site. Do not overwrite an
existing release or publish an older release to repair deployment; use a new
product release when an application rollback is required.

For a local staging build, import the existing private key into a temporary,
mode-0700 `GNUPGHOME`, export that variable, download both matching release
bundles to an ignored directory, and run:

```bash
python3 tools/build-flatpak-repo.py \
  --bundles-dir artifacts/flatpak-pages-input \
  --output-dir artifacts/flatpak-pages-preview \
  --base-url https://voltkraft.github.io/immich-folder-watch \
  --gpg-key-id 4ED65AC1C14D559C721C7A8B44B33451708EAD7D
python3 -m unittest discover -s tools/tests -p 'test_build_flatpak_repo.py' -v
```

The output directory must not already exist. `GNUPGHOME` must contain an unlocked
signing key. Required tools: Python 3.11+, Flatpak, OSTree, GnuPG. `TMPDIR` can
select a writable temporary location. Tests generate an ephemeral key and tiny
synthetic bundles, verify signed updates after complete repository replacement,
reject unsigned summaries and invalid input, and consume the `.flatpakref` in an
isolated Flatpak user directory without installing into the real user profile.
CI runs them in the existing packaging lint job. Native app rebuilds and live
Immich connections are not needed to verify this distribution layer.

## Sources and build-tool licenses

- [Flatpak repository hosting and descriptors](https://docs.flatpak.org/en/latest/hosting-a-repository.html).
- [GitHub Pages workflow permissions and artifacts](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
- New CI-only actions: [configure-pages v5](https://github.com/actions/configure-pages/blob/v5/LICENSE),
  [upload-pages-artifact v4](https://github.com/actions/upload-pages-artifact/blob/v4/LICENSE),
  [deploy-pages v4](https://github.com/actions/deploy-pages/blob/v4/LICENSE).
  Their upstream MIT licenses were verified on 2026-11-07. They are compatible
  build tooling for this AGPL-3.0-only project and are not shipped in the app.
  No application dependencies are added or updated.
