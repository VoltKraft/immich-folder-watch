# Supplemental NuGet license notices

These are unmodified upstream license and notice texts for existing dependencies
whose NuGet archives omit some required attribution files. The application
dependencies and their licenses are unchanged. Each retained upstream file keeps
its original license terms; the application's `AGPL-3.0-only` license does not
replace those terms.

`sources.json` records each file's immutable upstream URL and SHA-256 digest.
`catalog.json` associates files with the exact package IDs and versions reviewed
for the offline feed. Do not edit the upstream texts or replace copyright holders
with a generic license template.

The build runs `tools/install-flatpak-license-notices.py` to copy original license
and third-party notice files from every `.nupkg`, add the relevant supplements,
and write `index.json` under the app's `share/licenses` directory. It runs offline,
uses only Python's standard library, rejects unsafe archive paths and symlinks,
and validates all inputs before creating output. The destination must be empty
or absent. A package without license text, a changed supplement checksum, or a
new version of a supplemented package fails the build instead of silently
dropping its attribution.

The inventory describes the entire build feed, including branding build tools,
other architectures, and other-platform assets. It is not a runtime SBOM. For
example, `Svg.Custom` carries MS-PL terms but is used by the separate branding
build tool and is absent from the Linux application's published dependency list.
Preserving these notices does not assert that every bundled transitive component
has received a legal review or that a package's top-level SPDX expression covers
every embedded component.

## Updating dependencies

1. Inspect the exact new NuGet archives and their `.nuspec` metadata. Preserve
   every supplied license, copyright, and third-party notice file.
2. For missing texts, obtain the upstream file at the package's recorded source
   revision or its verified release revision. Record the URL and file digest in
   `sources.json`, and update the exact package version in `catalog.json`.
3. Verify the new dependency terms against the application's license and actual
   distribution before changing its version. A license expression or the generated
   inventory is not a substitute for the original license and copyright notices.
4. Run the helper against both architectures' combined feed and inspect the
   resulting notices in the Flatpak export.

For the current `Avalonia.Fonts.Inter` 12.0.3 package, the font in
[the recorded Avalonia revision](https://github.com/AvaloniaUI/Avalonia/blob/21e816874efa142bf9903b51fd323d1f35e56ab3/src/Avalonia.Fonts.Inter/Assets/Inter-Regular.ttf)
identifies itself as Inter `3.019;git-0a5106e0b` and declares SIL OFL 1.1 in its
embedded name table. `Inter-OFL.txt` is from that exact Inter revision. The font's
OFL terms are retained separately from Avalonia's MIT license and upstream
third-party notice collection.

The authoritative [GNU license compatibility discussion](https://www.gnu.org/licenses/license-compatibility.en.html)
and [license list](https://www.gnu.org/licenses/license-list.html) explain the
distinction between preserving attribution, compatible software combinations,
and separately distributed font or build-tool components. This notice packaging
change adds no library or font dependency.
