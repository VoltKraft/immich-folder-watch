# PR 45: YAML configuration compatibility and notices

Reviewed on 2026-11-11 against main `a82216d4251e6517b71236602ab09abfdb13f3e1`.

## Changes and compatibility

YamlDotNet 18.1.0 supplies a `net10.0` assembly and has no transitive package
dependencies. The application uses the standard camel-case serializer and
deserializer; it does not implement the custom inspectors/type converters whose
interfaces changed in versions 16 and 18. Its shallow configuration does not
approach the new default recursion limit of 130. Existing configuration loader,
normalization and writer tests remain applicable; no migration is required.

New round-trip tests cover null-like and boolean-like strings, numbers, dates,
colons, hashes, Unicode and Windows/UNC paths in configuration values. They
exposed a pre-existing defect: the literal string `null` became an empty value
after writing and loading, reproduced with both 15.1.2 and 18.1.0. Enable
`WithQuotingNecessaryStrings()` before other serializer options so ambiguous
strings retain their meaning. Actual boolean and numeric fields remain typed.

## Packaging and license evidence

Both native Flatpak jobs in original CI
[43010860973](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43010860973)
failed because the NuGet archive omitted license text. Preserve both MIT texts
from the exact package source
[`aaubry/YamlDotNet@748334a8fa7c227740018b284b71ad95cc6b7fc7`](https://github.com/aaubry/YamlDotNet/tree/748334a8fa7c227740018b284b71ad95cc6b7fc7):

- Project LICENSE.txt: SHA-256 `daea8b7f1b2bab48ea12ad50b0ce91634669d99d7dd0cb64aed8dffeeef69ed3`.
- Retained libyaml LICENSE-libyaml: SHA-256 `cb65f46df0d9125ba60862117200ec6631fef3a8169cd0b4513ffcad4ef5cb9b`.

The original bytes, including libyaml CRLF line endings, are retained; existing
Git binary-text attributes preserve the checksum contract. MIT permits this
AGPL-3.0-only distribution with these notices. The exact-version catalog is
extended without weakening its missing-license or checksum checks.

## Validation

The notice installer succeeds against the actual 18.1.0 archive, installing
both source texts. All 15 notice-helper tests and all 498 portable Core tests
pass with SDK 10.0.203. Final exact-head CI/CodeQL evidence is recorded in the
PR description and project status. Hosted CI covers Windows and both native Flatpak architectures;
local tests do not claim a live Immich integration test.

The PR stays open for an explicit merge decision; #32 remains excluded and
automatic merging disabled. No release or deployment is performed.
