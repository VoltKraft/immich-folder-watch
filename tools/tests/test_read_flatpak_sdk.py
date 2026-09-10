from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "read-flatpak-sdk.py"
SPEC = importlib.util.spec_from_file_location("read_flatpak_sdk", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def archive_source(arch: str, rid: str, version: str = "10.0.401") -> str:
    return f"""      - type: archive
        dest: dotnet-sdk
        strip-components: 0
        only-arches: [{arch}]
        url: https://builds.dotnet.microsoft.com/dotnet/Sdk/{version}/dotnet-sdk-{version}-{rid}.tar.gz
        sha512: {'a' * 128}
"""


def manifest() -> str:
    return 'runtime-version: "26.08"\nmodules:\n  - name: immich-folder-watch\n    sources:\n' + archive_source("x86_64", "linux-x64") + archive_source("aarch64", "linux-arm64")


class FlatpakSdkTests(unittest.TestCase):
    def read(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.yml"
            path.write_text(text)
            return MODULE.read_sdk_metadata(path)

    def test_extracts_exact_sdk_and_both_architecture_checksums(self) -> None:
        metadata = self.read(manifest())
        self.assertEqual("10.0.401", metadata["version"])
        self.assertEqual("26.08", metadata["runtime_version"])
        self.assertEqual({"linux-x64", "linux-arm64"}, set(metadata["sources"]))
        self.assertEqual("aarch64", metadata["sources"]["linux-arm64"]["flatpak_arch"])
        self.assertEqual("a" * 128, metadata["sources"]["linux-x64"]["sha512"])

    def test_rejects_different_sdk_versions_between_architectures(self) -> None:
        text = manifest().replace(archive_source("aarch64", "linux-arm64"), archive_source("aarch64", "linux-arm64", "10.0.400"))
        with self.assertRaisesRegex(MODULE.MetadataError, "same exact SDK"):
            self.read(text)

    def test_rejects_mismatched_architecture_filter(self) -> None:
        with self.assertRaisesRegex(MODULE.MetadataError, "architecture filters"):
            self.read(manifest().replace("only-arches: [aarch64]", "only-arches: [x86_64]"))

    def test_rejects_duplicate_architecture(self) -> None:
        text = manifest().replace(archive_source("aarch64", "linux-arm64"), archive_source("x86_64", "linux-x64"))
        with self.assertRaisesRegex(MODULE.MetadataError, "architecture filters"):
            self.read(text)

    def test_rejects_untrusted_url_and_mismatched_url_version(self) -> None:
        for text in (
            manifest().replace("builds.dotnet.microsoft.com", "example.com"),
            manifest().replace("dotnet-sdk-10.0.401-linux-x64", "dotnet-sdk-10.0.400-linux-x64"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(MODULE.MetadataError, "exact stable"):
                self.read(text)

    def test_rejects_incomplete_hash_or_unmanaged_extraction(self) -> None:
        for text in (
            manifest().replace("a" * 128, "a" * 64),
            manifest().replace("strip-components: 0", "strip-components: 1"),
            manifest().replace("dest: dotnet-sdk", "dest: /app/sdk"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(MODULE.MetadataError, "two pinned"):
                self.read(text)

    def test_rejects_extension_manifest_instead_of_guessing_sdk(self) -> None:
        with self.assertRaisesRegex(MODULE.MetadataError, "older SDK-extension manifests are unsupported"):
            self.read('runtime-version: "25.08"\nsdk-extensions:\n  - org.freedesktop.Sdk.Extension.dotnet10\n')

    def test_rejects_additional_sdk_archive(self) -> None:
        with self.assertRaisesRegex(MODULE.MetadataError, "two pinned"):
            self.read(manifest() + archive_source("x86_64", "linux-x64"))


if __name__ == "__main__":
    unittest.main()
