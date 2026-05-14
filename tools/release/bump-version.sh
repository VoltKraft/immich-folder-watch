#!/usr/bin/env bash
# Bump the unified semver across Directory.Build.props and CHANGELOG.md.
#
# Usage:
#   tools/release/bump-version.sh <new-version>     # e.g. 2.5.0
#
# After running, fill in release notes under the new CHANGELOG heading,
# review the diff, then commit on `main`. The release pipeline
# (.github/workflows/release.yaml) picks up the new version on push to
# main, builds the Windows MSI, and tags v<version>. Linux ships via
# Flathub (see packaging/flatpak/flathub/README.md), not this pipeline.
#
# This script does NOT touch packaging/flatpak/*.metainfo.xml. After
# filling in the CHANGELOG notes, run
#   python3 tools/update-appstream.py <new-version>
# to refresh the AppStream <release> block so the tagged release carries
# accurate Flathub "What's New" metadata.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <new-version>  (e.g. 2.5.0)" >&2
  exit 2
fi

NEW="$1"

if [[ ! "${NEW}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z\.\-]+)*$ ]]; then
  echo "ERROR: '${NEW}' is not a valid X.Y.Z[-tag] semver." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROPS="${REPO_ROOT}/Directory.Build.props"
CHANGELOG="${REPO_ROOT}/CHANGELOG.md"

[[ -f "${PROPS}" ]]     || { echo "ERROR: missing ${PROPS}"     >&2; exit 1; }
[[ -f "${CHANGELOG}" ]] || { echo "ERROR: missing ${CHANGELOG}" >&2; exit 1; }

# Assembly versions need four numeric parts (X.Y.Z.0); a pre-release
# suffix on the package version is dropped before assembly versioning.
BASE="${NEW%%-*}"
ASM="${BASE}.0"

TODAY="$(date -u +%Y-%m-%d)"

python3 - "${PROPS}" "${NEW}" "${ASM}" "${CHANGELOG}" "${TODAY}" <<'PY'
import re
import sys
from pathlib import Path

props_path, new, asm, changelog_path, today = sys.argv[1:6]

props = Path(props_path).read_text(encoding="utf-8")
for tag, value in (
    ("Version", new),
    ("AssemblyVersion", asm),
    ("FileVersion", asm),
):
    pattern = rf"<{tag}>[^<]*</{tag}>"
    if not re.search(pattern, props):
        sys.stderr.write(f"ERROR: <{tag}> not found in {props_path}\n")
        sys.exit(1)
    props = re.sub(pattern, f"<{tag}>{value}</{tag}>", props, count=1)
Path(props_path).write_text(props, encoding="utf-8")

changelog = Path(changelog_path).read_text(encoding="utf-8")
new_heading = f"## [Unreleased]\n\n## [{new}] - {today}"
updated, count = re.subn(
    r"^## \[Unreleased\][ \t]*$",
    lambda _: new_heading,
    changelog,
    count=1,
    flags=re.MULTILINE,
)
if count == 0:
    sys.stderr.write(f"ERROR: no '## [Unreleased]' heading in {changelog_path}\n")
    sys.exit(1)
Path(changelog_path).write_text(updated, encoding="utf-8")
PY

echo "Bumped Directory.Build.props to ${NEW} (assembly ${ASM})."
echo "Inserted '## [${NEW}] - ${TODAY}' below '## [Unreleased]' in CHANGELOG.md."
echo
echo "Next steps:"
echo "  1. Fill in release notes under the new CHANGELOG heading."
echo "  2. python3 tools/update-appstream.py ${NEW}   # refresh metainfo <release> block"
echo "  3. git diff Directory.Build.props CHANGELOG.md packaging/flatpak/*.metainfo.xml"
echo "  4. git commit -m \"release: v${NEW}\""
echo "  5. git push origin main                       # triggers release.yaml (Windows MSI)"
