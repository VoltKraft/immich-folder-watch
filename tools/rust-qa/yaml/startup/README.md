# Linux startup language

The Linux app reads `localization.language` before it creates its first editor
or tray menu. The [Rust reader](../src/startup_language.rs) opens
`$XDG_CONFIG_HOME/immich-folder-watch/config.yaml` or
`$HOME/.config/immich-folder-watch/config.yaml` read-only. It verifies the
held file is regular and uses the existing byte decoder, bounded YAML parser
and shipping configuration types. It accepts explicit `de` and `en`
case-insensitively with surrounding whitespace. Missing settings, `auto`,
other codes and read errors use the system UI language. The caller can
distinguish a missing file from a parse or open error without logging any
configuration values. [Shipping startup](../../../../src/ImmichFolderWatch.App.Linux/App.axaml.cs)
· [Shipping culture resolution](../../../../src/ImmichFolderWatch.App.Shared/Services/LocalizationService.cs).

`ifw_yaml_assessment::startup_language::load()` returns the language and the
original system choice. Call `Preference::System.resolve(startup.system)` when
the user switches back to automatic selection. The Linux reader follows the
first present variable among `LC_ALL`, `LC_MESSAGES` and `LANG`. A present
empty variable selected the invariant culture in the .NET reference. German
locales resolve to German, and other supported system locales resolve to
English. A non-regular settings entry falls back without waiting for a FIFO
writer. The reader creates no profile and writes no settings.

## Native comparison

On Fedora x64, 22 fresh C# processes and 22 Rust processes read identical
synthetic profile states. Each pair agreed on the path, read outcome, saved
preference, initial display language and automatic selection after a manual
language change in the C# process. Cases covered German-speaking regions,
a French system, locale precedence, the invariant culture, both saved
overrides, blank and unknown settings, UTF-32BE, a recognized alias,
repeated sections and a malformed typed field elsewhere in the document.
Existing file contents stayed identical; looking up an absent file created
no directory. The separate Rust FIFO case completed with the German system
fallback. The original report is
`artifacts/rust/yaml-assessment/startup-language-20261128/final/result.json`,
SHA-256 `5bae02b555da6cb602a7b26b7ebc50ad6c9cda4e59bcdcd52284ac081e2bf03e`.
The native Rust executable has SHA-256
`bab69981e66ab1bb704d986d985db6cf39769cb7bdd5e9d9d1425570fc840241`.

The [comparison](compare.py) checks out the original Linux x64 3.0.4
Flatpak commit, verifies the Core, App.Shared and YamlDotNet assemblies and
compiles its [C# observer](Reference.cs) against them. Use the pinned SDK
and a new output directory under `artifacts/rust`. The Cargo build uses the
filtered YAML directory source from the [native YAML assessment](../README.md).
The example prints diagnostic results for a synthetic profile.

```sh
vendor="$PWD/artifacts/rust/yaml-assessment/canonical-tar-review-01/vendor"
export PATH="$PWD/artifacts/rust/toolchain/bin:$PATH"
export CARGO_TARGET_DIR="$PWD/artifacts/rust/yaml-startup-build"
cargo build --manifest-path tools/rust-qa/yaml/Cargo.toml --release --frozen \
  --config 'source.crates-io.replace-with="reviewed"' \
  --config "source.reviewed.directory=\"$vendor\"" --example linux_startup_language
python3 -B tools/rust-qa/yaml/startup/compare.py \
  --rust "$CARGO_TARGET_DIR/release/examples/linux_startup_language" \
  --sdk artifacts/flatpak-local-2.11.2/sdk \
  --signed-repo artifacts/rust/yaml-assessment/signed-flatpak-3.0.4-folders/ostree \
  --output artifacts/rust/yaml-startup-result
```

The ordinary RW-02 GUI still initializes its editor and tray in German. To
use the reader on that path, its compiler and offline reconstruction must
consume the same reviewed, filtered YAML sources. The four YAML dependency
graphs and all 1,601 files in the filtered source bundle were checked for
this library extraction. Native runtime evidence here covers Fedora x64.
