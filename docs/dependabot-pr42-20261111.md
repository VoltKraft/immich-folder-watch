# PR 42: Windows hosting dependency review

Reviewed on 2026-11-11 against main `a82216d4251e6517b71236602ab09abfdb13f3e1`.

## Compatibility

The only dependency change upgrades Microsoft.Extensions.Hosting from 10.0.0 to
11.0.0 in the WPF host. The other Microsoft.Extensions references and the Linux
host already use 11.0.0. The product remains on .NET 10; this package supplies a
`net10.0` assembly. A fresh WPF restore with SDK 10.0.203 and
`-p:EnableWindowsTargeting=true` selected that assembly for `net10.0-windows7.0`
and completed without warnings. No application code or configuration migration
is required. Linux cannot execute the Windows test suite; hosted CI owns that
validation.

## License evidence

The exact NuGet archive identifies the MIT license and source revision
[`dotnet/dotnet@297acf930fb0f5c07fd4e51d78e521b4ad2e5d1f`](https://github.com/dotnet/dotnet/tree/297acf930fb0f5c07fd4e51d78e521b4ad2e5d1f).
The upstream LICENSE.TXT matches the already retained `Dotnet-11.0.0-LICENSE.txt`
byte-for-byte (SHA-256
`ae48df11a335dc1a615f4f938b69cba73bcf4485c4f97af49b38efb0f216353b`).
Its packaged THIRD-PARTY-NOTICES.TXT has SHA-256
`e3a241a6cf35167d82bf7e081de9641c59d10d2dbd8824409817bed31980d407`.
The existing Microsoft 11.0.0 review and exact-version catalog already cover
this package and its permissive third-party notices; see
[retained license provenance](../packaging/flatpak/licenses/README.md).
No new license exception or supplement is needed for AGPL-3.0-only distribution.

## Validation boundary

The original dependency head passed CI run
[43010609667](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43010609667).
Its neutral CodeQL aggregate was not accepted as a completed analysis. The
review commit triggers fresh CI and all configured CodeQL languages; their
final exact-head results are recorded in the PR description and project status.
This PR remains open for explicit merge authorization. PR 32 is excluded and
automatic merging remains disabled.
