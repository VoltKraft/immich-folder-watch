# Dependabot PR #37 validation

## Scope and source review

PR [#37](https://github.com/VoltKraft/immich-folder-watch/pull/37) upgrades only the
production Pages upload action from v4 to v5.0.0. Original head `c8989d6` was
integrated with current remote main `1ab0748` without a force-push. No #32/#34
changes, release/version bump, merge, Pages deployment or signing secret access.

- Proposed [v5 action](https://github.com/actions/upload-pages-artifact/blob/fc324d3547104276b827a68afc52ff2a11cc49c9/action.yml)
  and [MIT license](https://github.com/actions/upload-pages-artifact/blob/fc324d3547104276b827a68afc52ff2a11cc49c9/LICENSE)
  are pinned to `fc324d3547104276b827a68afc52ff2a11cc49c9`.
- Embedded [upload-artifact v7 action](https://github.com/actions/upload-artifact/blob/bbbca2ddaa5d8feaa63e36b76fdaad77386f024f/action.yml)
  and [MIT license](https://github.com/actions/upload-artifact/blob/bbbca2ddaa5d8feaa63e36b76fdaad77386f024f/LICENSE)
  are pinned to `bbbca2ddaa5d8feaa63e36b76fdaad77386f024f`.
  Both are CI tooling, not bundled application dependencies; no license conflict
  with this AGPL-3.0-only distribution was identified.
- v5 retains `github-pages`, `artifact_id`, one-day retention and tar creation.
  The new hidden-file input defaults to false, matching the previous exclusion.
  `.git` and `.github` are excluded even when other hidden files are included.
  Production keeps its existing path-only inputs; behavior is not silently changed.
- Existing [deploy-pages v5 artifact lookup](https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/src/internal/api-client.js)
  uses current-run artifact names/IDs and accepts upload-artifact v4 or later.
  Upload-artifact v7 uses Node24; hosted runners are validated by the actual CI
  smoke, not inferred only from version labels. Deployment itself is out of scope.

## Validation contract

`pages-artifact-validation.yaml` runs through CI with `contents: read`, no secrets,
no Pages environment and no deploy action. Two jobs upload harmless synthetic
files with hidden-file selection false/true, then download by the action's returned
artifact ID. The verifier reads the resulting `artifact.tar` without extracting
it and checks exact paths/bytes, regular-file link dereferencing and repository
metadata exclusion. Tests enforce the same upload pin in production and smoke.
This proves artifact transport/layout, not a successful deployment to Pages.

Local execution of the exact upstream Linux tar script passed both fixture modes
(7/9 files); the wrong hidden-file policy was rejected. Workflow YAML parsing and
whitespace checks passed. Hosted exact-head CI and CodeQL results follow after
publication of this PR update; no success is claimed before those runs finish.
