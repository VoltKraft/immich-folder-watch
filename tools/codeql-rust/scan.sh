#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 4 ]]; then
    echo "Usage: bash tools/codeql-rust/scan.sh BUNDLE TARGET NEW_DIRECTORY PR_HEAD_SHA" >&2
    exit 2
fi
bundle=$(realpath "$1")
target=$2
work=$(realpath -m "$3")
revision=$4
case "$target" in
    x86_64-unknown-linux-gnu|x86_64-pc-windows-msvc) ;;
    *) echo "Unsupported analysis target $target" >&2; exit 2 ;;
esac
root=$(git rev-parse --show-toplevel)
if [[ ! $revision =~ ^[0-9a-f]{40}$ || $(git rev-parse HEAD) != "$revision" ]]; then
    echo "The checkout must match the requested PR head" >&2
    exit 1
fi
mkdir "$work"
mkdir "$work/source" "$work/results"
out="$work/results"
export RUSTUP_TOOLCHAIN=1.99.0 CARGO_NET_OFFLINE=true
digest=141e6eb4e99c8498a1258e282e6f7b59c747b4b1a7eabc7cbf7d1aa92792edf0
printf '%s  %s\n' "$digest" "$bundle" | sha256sum --check | tee "$out/bundle-check.txt"
tar --zstd -xf "$bundle" -C "$work"
cli="$work/codeql/codeql"
"$cli" version --format=json > "$out/codeql-version.json"
rustc -vV > "$out/analysis-rustc.txt"
grep -Fx 'commit-hash: b940084d7eb6a299eb4bfeb8e34901bc051e7ac4' "$out/analysis-rustc.txt"
git archive --format=tar "$revision:rust" | tar -x -C "$work/source"

cd "$work/source"
"$cli" database create "$work/db" --language=rust --build-mode=none --source-root="$work/source" \
    --extractor-option="cargo_target=$target" --threads=2 --common-caches="$work/cache" 2>&1 | tee "$out/extraction.log"
"$cli" database analyze "$work/db" codeql/rust-queries@0.1.47:codeql-suites/rust-security-extended.qls \
    --format=sarifv2.1.0 --output="$out/results.sarif" --sarif-add-baseline-file-info \
    --print-diagnostics-summary --no-download --threads=2 --ram=3000 --common-caches="$work/cache" 2>&1 | tee "$out/analysis.log"
"$cli" query run "$root/tools/codeql-rust/coverage.ql" --database="$work/db" --output="$work/coverage.bqrs" \
    --threads=2 --ram=3000 --common-caches="$work/cache" --no-default-compilation-cache
"$cli" bqrs decode "$work/coverage.bqrs" --format=csv --output="$out/coverage.csv"
python3 "$root/tools/codeql-rust/verify.py" "$work" "$revision" "$target" "$digest"
