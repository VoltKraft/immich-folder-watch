# Release v3.0.2 verification

## Scope and preparation

Selected on 2026-11-11 by explicit user authorization to publish all new main
changes. Baseline: `8d7afba43d51d80021c28862a2ec94802eb83c17`. PR #32 remains
excluded and license-blocked; automatic merging remains disabled.

This compatible maintenance release includes the YAML string-preservation fix,
reviewed SocketIO transport/shutdown adaptation, build-tool and dependency
updates, Dependabot correction and all maintenance evidence since v3.0.1.
No configuration or persistent-data migration is introduced. Existing 3.0.0
HTTPS-by-default requirements remain unchanged.

Version preparation follows the repository bump script and AppStream generator.
[Semantic Versioning 2.0.0](https://semver.org/) and
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) were checked against
their official sites on 2026-11-11. Versions: 3.0.2 / 3.0.2.0.

## Validation and publication

Local checks pass: exact version/changelog/AppStream assertions, AppStream
validation without network, five manifest tests and six workflow-security tests.
Four PowerShell-specific tests are deferred to Windows CI. Independent review
confirms complete release notes, preserved historical entries and unchanged
product/workflow content; a Windows-only note was excluded from Linux metadata.
Hosted CI/CodeQL, four release builds and publication remain pending. The existing release workflow
creates the immutable tag only after all four artifacts build successfully.
Signed Pages deployment and downstream distribution outcomes will be recorded
separately. No live Immich connection or application installation is selected.
