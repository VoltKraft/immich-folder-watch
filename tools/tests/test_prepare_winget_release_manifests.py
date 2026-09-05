from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "prepare-winget-release-manifests.py"
SPEC = importlib.util.spec_from_file_location("prepare_winget_manifests", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareWinGetReleaseManifestsTests(unittest.TestCase):
    version = "3.1.4"
    release_date = "2026-09-04"

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.metadata_path = self.root / "package.metadata.json"
        self.installers_path = self.root / "installers.json"
        self.output_dir = self.root / "output"
        self.metadata = {
            "packageIdentifier": "VoltKraft.ImmichFolderWatch",
            "packageName": "Immich Folder Watch",
            "packageLocale": "en-US",
            "publisher": "VoltKraft",
            "publisherUrl": "https://github.com/VoltKraft",
            "publisherSupportUrl": "https://github.com/VoltKraft/immich-folder-watch/issues",
            "packageUrl": "https://github.com/VoltKraft/immich-folder-watch",
            "repository": "VoltKraft/immich-folder-watch",
            "license": "AGPL-3.0",
            "moniker": "immich-folder-watch",
            "shortDescription": "Upload local media to Immich.",
            "tags": ["immich", "immich-api"],
            "installerLocale": "en-US",
            "installerType": "wix",
            "manifestVersion": "1.12.0",
            "releaseAssetNameTemplates": {
                "x64": "immich-folder-watch-{version}-win-x64.msi",
                "arm64": "immich-folder-watch-{version}-win-arm64.msi",
            },
        }
        self.installers = [
            self.installer(
                "arm64",
                "b" * 64,
                "{22222222-2222-2222-2222-222222222222}",
            ),
            self.installer(
                "x64",
                "a" * 64,
                "{11111111-1111-1111-1111-111111111111}",
            ),
        ]
        self.write_inputs()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def installer(
        self, architecture: str, sha256: str, product_code: str
    ) -> dict[str, str]:
        runtime = "win-arm64" if architecture == "arm64" else "win-x64"
        return {
            "architecture": architecture,
            "url": (
                "https://github.com/VoltKraft/immich-folder-watch/releases/"
                f"download/v{self.version}/"
                f"immich-folder-watch-{self.version}-{runtime}.msi"
            ),
            "sha256": sha256,
            "productCode": product_code,
        }

    def write_inputs(self) -> None:
        self.metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")
        self.installers_path.write_text(json.dumps(self.installers), encoding="utf-8")

    def prepare(self, version: str | None = None) -> list[Path]:
        self.write_inputs()
        return MODULE.prepare_manifests(
            self.metadata_path,
            self.installers_path,
            self.output_dir,
            version or self.version,
            self.release_date,
        )

    def test_creates_complete_two_architecture_manifest_set(self) -> None:
        outputs = self.prepare()

        self.assertEqual(3, len(outputs))
        self.assertTrue(all(path.is_file() for path in outputs))

        installer_manifest = (
            self.output_dir / "VoltKraft.ImmichFolderWatch.installer.yaml"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            installer_manifest.startswith(
                "# yaml-language-server: $schema=https://aka.ms/"
                "winget-manifest.installer.1.12.0.schema.json\n\n"
            )
        )
        self.assertEqual(1, installer_manifest.count('Architecture: "x64"'))
        self.assertEqual(1, installer_manifest.count('Architecture: "arm64"'))
        self.assertLess(
            installer_manifest.index('Architecture: "x64"'),
            installer_manifest.index('Architecture: "arm64"'),
        )
        self.assertIn(f'PackageVersion: "{self.version}"', installer_manifest)
        self.assertIn(f'ReleaseDate: "{self.release_date}"', installer_manifest)
        self.assertIn(f'InstallerSha256: "{"A" * 64}"', installer_manifest)
        self.assertIn(
            'ProductCode: "{11111111-1111-1111-1111-111111111111}"\n'
            "Installers:",
            installer_manifest,
        )
        self.assertIn(
            'ProductCode: "{22222222-2222-2222-2222-222222222222}"',
            installer_manifest,
        )
        self.assertEqual(2, installer_manifest.count("ProductCode:"))
        self.assertLess(
            installer_manifest.index(
                'ProductCode: "{11111111-1111-1111-1111-111111111111}"'
            ),
            installer_manifest.index("Installers:"),
        )
        self.assertGreater(
            installer_manifest.index(
                'ProductCode: "{22222222-2222-2222-2222-222222222222}"'
            ),
            installer_manifest.index('Architecture: "arm64"'),
        )

        locale_manifest = (
            self.output_dir
            / "VoltKraft.ImmichFolderWatch.locale.en-US.yaml"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            locale_manifest.startswith(
                "# yaml-language-server: $schema=https://aka.ms/"
                "winget-manifest.defaultLocale.1.12.0.schema.json\n\n"
            )
        )
        self.assertIn('Publisher: "VoltKraft"', locale_manifest)
        self.assertIn('Moniker: "immich-folder-watch"', locale_manifest)
        self.assertIn('  - "immich-api"', locale_manifest)
        self.assertIn(
            f'ReleaseNotesUrl: "https://github.com/VoltKraft/immich-folder-watch/releases/tag/v{self.version}"',
            locale_manifest,
        )

        version_manifest = (
            self.output_dir / "VoltKraft.ImmichFolderWatch.yaml"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            version_manifest.startswith(
                "# yaml-language-server: $schema=https://aka.ms/"
                "winget-manifest.version.1.12.0.schema.json\n\n"
            )
        )

    def test_rejects_missing_architecture(self) -> None:
        self.installers = self.installers[:1]

        with self.assertRaisesRegex(MODULE.ManifestError, "missing.*x64"):
            self.prepare()

    def test_rejects_duplicate_architecture(self) -> None:
        self.installers[1] = self.installer(
            "arm64",
            "c" * 64,
            "{33333333-3333-3333-3333-333333333333}",
        )

        with self.assertRaisesRegex(MODULE.ManifestError, "duplicate.*arm64"):
            self.prepare()

    def test_rejects_unknown_architecture(self) -> None:
        self.installers[0]["architecture"] = "x86"

        with self.assertRaisesRegex(MODULE.ManifestError, "unsupported.*x86"):
            self.prepare()

    def test_rejects_invalid_version(self) -> None:
        with self.assertRaisesRegex(MODULE.ManifestError, "MAJOR.MINOR.PATCH"):
            self.prepare("3.1.4-beta.1")

        with self.assertRaisesRegex(MODULE.ManifestError, "MAJOR.MINOR.PATCH"):
            self.prepare("03.1.4")

    def test_rejects_invalid_sha256(self) -> None:
        self.installers[0]["sha256"] = "not-a-sha"

        with self.assertRaisesRegex(MODULE.ManifestError, "invalid SHA-256"):
            self.prepare()

    def test_rejects_invalid_product_code(self) -> None:
        self.installers[0]["productCode"] = "not-a-guid"

        with self.assertRaisesRegex(MODULE.ManifestError, "invalid ProductCode"):
            self.prepare()

    def test_rejects_duplicate_product_code(self) -> None:
        self.installers[0]["productCode"] = self.installers[1]["productCode"]

        with self.assertRaisesRegex(MODULE.ManifestError, "duplicates.*ProductCode"):
            self.prepare()

    def test_rejects_url_that_does_not_match_release_asset_template(self) -> None:
        self.installers[0]["url"] = "https://example.com/arm64.msi"

        with self.assertRaisesRegex(MODULE.ManifestError, "URL must be"):
            self.prepare()

    def test_rejects_invalid_release_date(self) -> None:
        self.write_inputs()

        with self.assertRaisesRegex(MODULE.ManifestError, "YYYY-MM-DD"):
            MODULE.prepare_manifests(
                self.metadata_path,
                self.installers_path,
                self.output_dir,
                self.version,
                "04.09.2026",
            )


if __name__ == "__main__":
    unittest.main()
