#!/usr/bin/env bash
# Regenerate packaging/flatpak/flathub/nuget-sources.json from the .NET projects.
#
# Flatpak release builds run without network access inside the build sandbox,
# so the manifest cannot run `dotnet restore` itself. Instead we pre-collect
# every NuGet package URL + sha512 into nuget-sources.json and reference
# it as a sibling source list next to the manifest. This script regenerates
# that file from the live solution. It is gitignored upstream, copied beside
# the temporary GitHub release manifest in CI, and would be committed only in
# a future per-app Flathub repository.
#
# Run from a Linux dev machine with .NET 10 SDK + python3 + git on PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${REPO_ROOT}/packaging/flatpak/flathub/nuget-sources.json"
PROJECT="${REPO_ROOT}/src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj"

CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/immich-folder-watch"
TOOLS_DIR="${CACHE_DIR}/flatpak-builder-tools"
GENERATOR="${TOOLS_DIR}/dotnet/flatpak-dotnet-generator.py"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: '$1' not found on PATH." >&2
    [[ -n "${2:-}" ]] && echo "       $2" >&2
    exit 1
  fi
}

# .NET SDK path resolution:
# - prefer dotnet on PATH
# - else fall back to the default dotnet-install.sh per-user location at $HOME/.dotnet
# - else honour an explicit DOTNET_ROOT
if ! command -v dotnet >/dev/null 2>&1; then
  for candidate in "${DOTNET_ROOT:-}" "${HOME}/.dotnet" "/usr/share/dotnet" "/opt/dotnet"; do
    if [[ -n "${candidate}" && -x "${candidate}/dotnet" ]]; then
      export DOTNET_ROOT="${candidate}"
      export PATH="${candidate}:${PATH}"
      echo "Using dotnet from ${candidate} (auto-detected)."
      break
    fi
  done
fi

require dotnet  "Install .NET 10 SDK (e.g. via https://dot.net/v1/dotnet-install.sh) or set DOTNET_ROOT to its install dir."
require flatpak "Install Flatpak and the org.freedesktop.Sdk.Extension.dotnet10//25.08 runtime extension."
require python3 "Install Python 3 (most distributions ship it as 'python3')."
require git     "Install git."

mkdir -p "${CACHE_DIR}"

if [[ ! -d "${TOOLS_DIR}" ]]; then
  echo "Cloning flatpak/flatpak-builder-tools into ${TOOLS_DIR}…"
  git clone --depth=1 https://github.com/flatpak/flatpak-builder-tools.git "${TOOLS_DIR}"
else
  git -C "${TOOLS_DIR}" pull --ff-only --quiet || true
fi

if [[ ! -f "${GENERATOR}" ]]; then
  echo "ERROR: flatpak-dotnet-generator.py not found at ${GENERATOR}" >&2
  echo "       The flatpak-builder-tools layout may have changed." >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT}")"

echo "Running flatpak-dotnet-generator.py against ${PROJECT}…"
python3 "${GENERATOR}" \
  --dotnet 10 \
  --freedesktop 25.08 \
  --runtime=linux-x64 \
  "${OUTPUT}" "${PROJECT}"

python3 - "${OUTPUT}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fp:
    sources = json.load(fp)

if not sources:
    raise SystemExit(
        "ERROR: generated nuget-sources.json is empty. "
        "Make sure flatpak, org.freedesktop.Sdk//25.08 and "
        "org.freedesktop.Sdk.Extension.dotnet10//25.08 are installed."
    )
PY

echo "Wrote ${OUTPUT}"
