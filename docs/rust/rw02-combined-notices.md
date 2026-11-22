# Original notices for the combined development executable

The four archives below contain the license and attribution files for each
target's combined development build at
`7517e3b6be84645bc0d40603750b003dd5792104`. Their package lists come from
the compiled Cargo units in desktop assessment run `45047460092`. Each
archive identifies the measured executable by SHA-256. The native ZIPs,
build receipts and target-specific SPDX documents identify the same subjects.
[Native assessment and input digests](rw02-native-gui.md#native-follow-up-at-7517e3b)
and [SPDX inventories](rw02-combined-sbom.md).

| Target | Cargo packages (host-only) | Protocol XMLs | ZIP members | Notice ZIP SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Linux x64 | 337 (41) | 100 | 709 | `625d52c4c53e30e198e50d97ddf71a30337f10dcd5714d784c6aa1a3f3af775a` |
| Linux ARM64 | 336 (41) | 100 | 707 | `b79a51b09eaef4b444110e50cecfb8862e283fa56aab263fd0c208f53eadffdd` |
| Windows x64 | 250 (28) | 0 | 462 | `5120473df67865312496a16c20f82b2c3677ebcbf47c578eae9b2a74955edbec` |
| Windows ARM64 | 249 (28) | 0 | 460 | `b5c1553b3bd0f7b515bd739b323a93868dcb213e5f7dd21e85de865adee7924b` |

## Reading an archive

Open `NOTICE.txt` for the package names, compiler roles, file paths and
five individual Noto font attributions. In `manifest.json`, `compiledFor`
lists `host`, the native target triple or both. `files` gives the byte length
and SHA-256 of each payload, including `NOTICE.txt`. The manifest records
the native archive, receipt, source inventory, compiler units and executable
digests. Each registry package has its upstream archive URL and digest. The
three reconstructed packages also identify their reviewed source trees.

- `crates/NAME-VERSION/` preserves source paths and exact file bytes. For
  example, the four relative links in granit-parser's `LICENSE` resolve to
  the original inherited grants. The ring notices retain their nested paths.
  The base64 crate contributes its two license files.
- `repository/` preserves Git paths at the native revision. The six project
  packages point to the project AGPL-3.0-only license. Packages with
  supplemental or reconstructed notice inputs reference the reviewed originals
  here. Each font record identifies the original asset by URL and digest and
  retains its version, copyright, trademark and matching complete OFL text.
  [Reviewed fonts and additional rights holders](rw02-gui-dependencies.md).
- On Linux the individual copyright and SPDX statements in the 100 source
  protocol XMLs are available in the original XML bytes. Eighteen carry
  LGPL-2.1-or-later. The archive includes Plasma's complete `COPYING.LIB`
  and Weston's original grant for the historical fullscreen-shell XML.
  The libsqlite3-sys crate contributes the complete authenticated SQLite
  `sqlite3/sqlite3.h` with the upstream public-domain blessing on each target.
  [Reviewed combined source profile](rw02-combined-profile.md).

## Offline generation and checks

The generator requires Python 3.11 or later, Git, the native revision in
the local repository, the original desktop assessment ZIP and the existing
project-local Cargo acquisition caches. It verifies the published digest of
the ZIP, the native evidence and compiler units, the immutable source review,
the original crate digest before reading its members, and each selected
member's digest. It selects files by their reviewed paths. The resulting ZIP
uses stored members, a fixed timestamp, ordering and file modes. It is made
visible using a hard link to the fully checked file in the same directory.
Repeating a build at the same destination verifies any existing bytes.
[Generator](../../tools/rust-qa/combined-profile/notices.py).

For example, run the following in the repository root for Linux x64.

```sh
revision=7517e3b6be84645bc0d40603750b003dd5792104
target=x86_64-unknown-linux-gnu
native_zip=artifacts/rust/hosted-desktop-storage/45047460092/linux-x64.zip
native_sha=afd05f889c75c40f2a1f3cebc9f413c9fc48c488160f1fa1f0f45bd68e0f8b6c
output_dir=artifacts/rust/combined-profile/notices-7517e3b

for copy in first repeat
do
    python3 -B tools/rust-qa/combined-profile/notices.py "$target" \
        --revision "$revision" --input "$native_zip" --archive-sha256 "$native_sha" \
        --output "$output_dir/$copy/linux-x64.zip" || exit 1
done
cmp "$output_dir/first/linux-x64.zip" "$output_dir/repeat/linux-x64.zip"
python3 -B tools/rust-qa/combined-profile/test_notices.py --target "$target" \
    --revision "$revision" --input "$native_zip" --archive-sha256 "$native_sha" \
    --notices "$output_dir/first/linux-x64.zip"
```

On 2026-11-22 two separate local invocations produced identical bytes for
each of the four native input ZIPs. The readback compared every member and
its digest with the target's source inventory, Git originals or font input
records, checked compiler roles, archive metadata, SQLite's blessing and the
relative links in granit-parser. Controls rejected changed crate or notice
bytes, absent, duplicate and linked members, unsafe or case-ambiguous paths,
and a conflicting output file. Substituting the Windows ARM64 notice ZIP for
the Linux x64 input failed the target check. [Readback and controls](../../tools/rust-qa/combined-profile/test_notices.py).

RI-AC09 still requires the exact installed release candidate and its actual
runtime contents, bundled notices, package SBOM, corresponding source and
relink material. These archives cover the development Cargo graph and reviewed
embedded assets. [Acceptance record](acceptance.md).
