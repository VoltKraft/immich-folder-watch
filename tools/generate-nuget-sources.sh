#!/usr/bin/env bash
# Regenerate packaging/flatpak/flathub/nuget-sources.json from the .NET projects.
#
# Flatpak release builds cannot download dependencies during their offline
# restore inside the build sandbox. Instead we pre-collect
# every NuGet package URL + sha512 into nuget-sources.json and reference
# it as a sibling source list next to the manifest. This script regenerates
# that file from the live solution. It is gitignored upstream, copied beside
# the temporary GitHub release manifest in CI, and would be committed only in
# the per-app Flathub repository.
#
# Run with Python 3 and the exact host .NET SDK pinned in the Flatpak manifest.
# Restore uses fresh temporary package/HTTP caches and an isolated artifacts path;
# no Flatpak runtime or SDK extension is needed to prepare the offline feed.
# Use --runtime linux-x64 or --runtime linux-arm64 to select the target
# architecture. The default remains linux-x64 for local compatibility.
# Use --source-root to target another checkout and --output to keep each
# architecture's generated sources outside that checkout.

set -euo pipefail

RUNTIME="linux-x64"
OUTPUT=""
SOURCE_ROOT=""

usage() {
  echo "Usage: $0 [--runtime linux-x64|linux-arm64] [--source-root DIR] [--output FILE]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --runtime requires a value." >&2
        usage
        exit 1
      fi
      RUNTIME="$2"
      shift 2
      ;;
    --runtime=*)
      RUNTIME="${1#*=}"
      shift
      ;;
    --output|--source-root)
      if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
        echo "ERROR: $1 requires a value." >&2
        usage
        exit 1
      fi
      if [[ "$1" == --output ]]; then
        OUTPUT="$2"
      else
        SOURCE_ROOT="$2"
      fi
      shift 2
      ;;
    --output=*|--source-root=*)
      if [[ -z "${1#*=}" ]]; then
        echo "ERROR: ${1%%=*} requires a value." >&2
        usage
        exit 1
      fi
      if [[ "$1" == --output=* ]]; then
        OUTPUT="${1#*=}"
      else
        SOURCE_ROOT="${1#*=}"
      fi
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument '$1'." >&2
      usage
      exit 1
      ;;
  esac
done

case "${RUNTIME}" in
  linux-x64|linux-arm64) ;;
  *)
    echo "ERROR: unsupported runtime '${RUNTIME}'. Expected linux-x64 or linux-arm64." >&2
    exit 1
    ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${SOURCE_ROOT:-${REPO_ROOT}}"
OUTPUT="${OUTPUT:-${SOURCE_ROOT}/packaging/flatpak/flathub/nuget-sources.json}"
PROJECT="${SOURCE_ROOT}/src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj"

if [[ ! -f "${PROJECT}" ]]; then
  echo "ERROR: Linux project not found at ${PROJECT}." >&2
  exit 1
fi

# Resolve the host SDK executable; its exact version is checked against the
# source manifest by the Python generator before any restore takes place.
if ! command -v dotnet >/dev/null 2>&1; then
  for candidate in "${DOTNET_ROOT:-}" "${HOME}/.dotnet" "/usr/share/dotnet" "/opt/dotnet"; do
    if [[ -n "${candidate}" && -x "${candidate}/dotnet" ]]; then
      export DOTNET_ROOT="${candidate}"
      export PATH="${candidate}:${PATH}"
      break
    fi
  done
fi

for dependency in dotnet python3; do
  if ! command -v "${dependency}" >/dev/null 2>&1; then
    echo "ERROR: '${dependency}' not found on PATH. Install the SDK pinned in the Flatpak manifest and Python 3." >&2
    exit 1
  fi
done

exec python3 "${REPO_ROOT}/tools/generate-flatpak-nuget-sources.py" \
  --source-root "${SOURCE_ROOT}" --runtime "${RUNTIME}" --output "${OUTPUT}"
