#!/usr/bin/env bash
# Reproduce the CI Flatpak build locally inside the same container the
# release workflow uses, so we can iterate on packaging/flatpak/...yaml
# (and the workflow itself) without a push-to-main round-trip.
#
# Requires: docker (or podman aliased to docker), the offline NuGet
# feed at packaging/flatpak/nuget-sources.json (run
# tools/generate-nuget-sources.sh once before this script).
#
# Usage:
#   tools/test-flatpak-build-in-container.sh
#
# Behavior:
#   - Pulls bilelmoussaoui/flatpak-github-actions:freedesktop-24.08
#   - Mounts the repo into /workspace
#   - Runs the same flatpak-builder + flatpak build-bundle commands
#     release.yaml runs, against the resolved JSON manifest
#   - Leaves the .flatpak bundle at ./immich-folder-watch-<VERSION>.flatpak
#
# Exit code matches the build's; useful for `git bisect` runs.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest_yaml="packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.yaml"
nuget_sources="packaging/flatpak/nuget-sources.json"

if [ ! -f "${repo_root}/${nuget_sources}" ]; then
    echo "ERROR: ${nuget_sources} is missing. Run tools/generate-nuget-sources.sh first." >&2
    exit 2
fi

# Read version straight from Directory.Build.props (same as release.yaml).
version=$(grep -oP '(?<=<Version>)[^<]+' "${repo_root}/Directory.Build.props" | head -1)
if [ -z "${version}" ]; then
    echo "ERROR: could not read <Version> from Directory.Build.props" >&2
    exit 2
fi

container="${IMMICH_FW_FLATPAK_TEST_IMAGE:-docker.io/bilelmoussaoui/flatpak-github-actions:freedesktop-24.08}"
runtime="${IMMICH_FW_CONTAINER_RUNTIME:-docker}"

echo "=== Local CI-equivalent flatpak build ==="
echo "Repo:       ${repo_root}"
echo "Version:    ${version}"
echo "Container:  ${container}"
echo "Runtime:    ${runtime}"
echo

# Pre-resolve the manifest on the host (uses the local flatpak-builder)
# so the container only consumes it. Side-steps the podman-userns
# write-permission dance for files generated inside the bind mount.
if [ ! -x "$(command -v flatpak-builder)" ]; then
    echo "ERROR: flatpak-builder not found on the host. Install it (Fedora: 'sudo dnf install flatpak-builder')." >&2
    exit 2
fi

# Manifest expects source.tar.gz next to itself (CI tarballs at release
# time; locally we do the same). Excludes mirror what release.yaml does.
echo "Creating source tarball..."
tar czf "${repo_root}/packaging/flatpak/source.tar.gz" \
    -C "${repo_root}" \
    --exclude=./.flatpak-builder \
    --exclude=./.git \
    --exclude=./flatpak_app \
    --exclude=./repo \
    --exclude=./artifacts \
    --exclude=./packaging/flatpak/source.tar.gz \
    --exclude=./packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json \
    .

flatpak-builder --show-manifest \
    "${repo_root}/${manifest_yaml}" \
    > "${repo_root}/packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json"

# Build runs as root inside the container — needed for flatpak --system
# ops. The bind-mounted workspace ends up with root-owned build
# artifacts which the host user can still read; cleanup with sudo if
# needed.
"${runtime}" run --rm --privileged \
    -v "${repo_root}:/workspace" \
    -w /workspace \
    -e VERSION="${version}" \
    "${container}" \
    bash -c '
        set -euo pipefail
        flatpak-builder \
            --repo=repo \
            --disable-rofiles-fuse \
            --install-deps-from=flathub \
            --force-clean \
            --default-branch=master \
            --arch=x86_64 \
            --ccache \
            --verbose \
            --state-dir .flatpak-builder \
            flatpak_app \
            packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json
        flatpak build-bundle \
            --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
            repo \
            "immich-folder-watch-${VERSION}.flatpak" \
            io.github.voltkraft.ImmichFolderWatch \
            master
    '

echo
echo "=== Done. Bundle: immich-folder-watch-${version}.flatpak ==="
