#!/usr/bin/env bash
# Run the same paired release and native measurements in either Ubuntu workflow.
set -euo pipefail
qa=tools/rust-qa/performance
area=artifacts/rust/performance
case ${1:?reference or candidate} in
  reference)
    reference=19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc
    git diff --exit-code "$reference" HEAD -- src ':!src/ImmichFolderWatch.Tests.*' Directory.Build.props Directory.Build.targets global.json NuGet.Config assets/branding tools/BrandAssetGen packaging/avalonia-reduced
    python3 tools/prepare_reduced_avalonia.py
    dotnet build src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj -c Release --artifacts-path artifacts/rust/linux-reference
    python3 "$qa/linux.py" measure --name "hosted-dotnet-$NATIVE_TARGET" \
      --entry artifacts/rust/linux-reference/bin/ImmichFolderWatch.App.Linux/release/immich-folder-watch.dll \
      --runtime-root "$DOTNET_ROOT" --revision "$reference" --input-interval-ms 25
    ;;
  candidate)
    subject=${2:?native subject directory}
    revision=${3:?native source revision}
    python3 "$qa/linux.py" measure --name "hosted-rust-$NATIVE_TARGET" --entry "$subject/native-gui-assessment" \
      --revision "$revision" --desktop-spike --frame-counter --input-interval-ms 25 \
      --start-marker INVENTORY_STARTED --finish-marker INVENTORY_COMPLETE
    python3 "$qa/linux.py" compare "$area/hosted-dotnet-$NATIVE_TARGET.json" "$area/hosted-rust-$NATIVE_TARGET.json"
    ;;
  *) exit 2 ;;
esac
