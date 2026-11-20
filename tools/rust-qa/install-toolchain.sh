#!/usr/bin/env bash
# Install the verified native distribution in this checkout (also works in Git Bash).
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
target=${1:?expected a native target from rust/toolchain-inputs.json}
inputs="$root/artifacts/rust/toolchain-inputs"
prefix="$root/artifacts/rust/toolchain"
read -r url checksum < <(python3 - "$root/rust/toolchain-inputs.json" "$target" <<'PY'
import json
import sys
from pathlib import Path

archive = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["targets"][sys.argv[2]]["rust"]
# Git Bash reads these bytes even when the runner's Python uses CRLF on stdout.
sys.stdout.buffer.write(f"{archive['url']} {archive['sha256']}\n".encode("ascii"))
PY
)
archive=${url##*/}
distribution=${archive%.tar.xz}
mkdir -p "$inputs/unpacked"
if [[ ! -f "$inputs/$archive" ]]; then
    curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 \
        --output "$inputs/$archive.download" "$url"
    (cd "$inputs" && printf '%s  %s\n' "$checksum" "$archive.download" | sha256sum --check)
    mv "$inputs/$archive.download" "$inputs/$archive"
else
    (cd "$inputs" && printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check)
fi

components=(rustc cargo "rust-std-$target" rustfmt-preview clippy-preview)
entries=("$distribution/install.sh" "$distribution/components" "$distribution/rust-installer-version")
for component in "${components[@]}"; do entries+=("$distribution/$component"); done
tar -xJf "$inputs/$archive" -C "$inputs/unpacked" "${entries[@]}"
selected=$(IFS=,; echo "${components[*]}")
bash "$inputs/unpacked/$distribution/install.sh" --prefix="$prefix" \
    --components="$selected" --disable-ldconfig
"$prefix/bin/rustc" -vV
