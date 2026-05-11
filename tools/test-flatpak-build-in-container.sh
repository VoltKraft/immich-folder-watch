#!/usr/bin/env bash
# Reproduce the CI Flatpak build locally inside the same base container
# the release workflow uses, so packaging/flatpak/...yaml and release
# workflow changes can be tested without a push-to-main round-trip.
#
# Requires: docker (or podman aliased to docker), the offline NuGet
# feed at packaging/flatpak/nuget-sources.json (run
# tools/generate-nuget-sources.sh once before this script).
#
# Usage:
#   tools/test-flatpak-build-in-container.sh
#
# Behavior:
#   - Pulls Fedora
#   - Mounts the repo into /workspace
#   - Installs flatpak-builder plus the freedesktop runtime/sdk/dotnet10
#   - Resolves the manifest's external nuget-sources fragment
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

container="${IMMICH_FW_FLATPAK_TEST_IMAGE:-docker.io/fedora:latest}"
runtime="${IMMICH_FW_CONTAINER_RUNTIME:-docker}"

echo "=== Local CI-equivalent flatpak build ==="
echo "Repo:       ${repo_root}"
echo "Version:    ${version}"
echo "Container:  ${container}"
echo "Runtime:    ${runtime}"
echo

# Manifest expects source.tar.gz next to itself (CI tarballs at release
# time; locally we do the same). Use tracked files so ignored build output
# never enters the app source.
echo "Creating source tarball..."
git -C "${repo_root}" ls-files -z \
    | tar --create --gzip --file "${repo_root}/packaging/flatpak/source.tar.gz" \
        --directory "${repo_root}" --null --files-from -

tar --list --gzip --file "${repo_root}/packaging/flatpak/source.tar.gz" \
    | grep -Fx 'src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj' >/dev/null

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
        dnf install -y --setopt=install_weak_deps=False \
            flatpak flatpak-builder ostree git tar gzip xz which \
            python3 python3-pyyaml
        flatpak-builder --version
        flatpak remote-add --system --if-not-exists \
            flathub https://flathub.org/repo/flathub.flatpakrepo
        flatpak install --system -y --noninteractive flathub \
            org.freedesktop.Platform//24.08 \
            org.freedesktop.Sdk//24.08 \
            org.freedesktop.Sdk.Extension.dotnet10//24.08

        python3 tools/resolve-flatpak-manifest.py \
            packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.yaml \
            packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json
        python3 tools/normalize-flatpak-manifest-paths.py \
            packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json \
            --manifest-dir packaging/flatpak

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
