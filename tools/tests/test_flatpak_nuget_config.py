"""Exercise offline restore-cache persistence across Flatpak build commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DOTNET = shutil.which("dotnet")


@unittest.skipUnless(DOTNET, "The pinned .NET SDK is required for the offline restore regression")
class FlatpakRestoreCacheTests(unittest.TestCase):
    def test_restored_package_survives_discarding_the_build_commands_home(self) -> None:
        version = json.loads((ROOT / "global.json").read_text())["sdk"]["version"]
        installed = subprocess.check_output([DOTNET, "--list-sdks"], text=True)
        if not any(line.startswith(version + " ") for line in installed.splitlines()):
            self.skipTest(f"The exact pinned SDK {version} is not installed")
        with tempfile.TemporaryDirectory(prefix="flatpak-restore-cache-") as temporary:
            root = Path(temporary)
            config = root / "packaging/flatpak/NuGet.Config"
            config.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "packaging/flatpak/NuGet.Config", config)
            shutil.copyfile(ROOT / "global.json", root / "global.json")
            feed = root / "artifacts/reduced-avalonia/feed"
            feed.mkdir(parents=True)
            (root / "nuget-sources").mkdir()
            archive = feed / "avalonia.0.0.0-flatpak-cache-test.nupkg"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("Avalonia.nuspec", '''<?xml version="1.0"?>
<package><metadata><id>Avalonia</id><version>0.0.0-flatpak-cache-test</version>
<authors>Test fixture</authors><description>Offline cache regression fixture</description>
</metadata></package>''')
                package.writestr("lib/net10.0/_._", "")
            project = root / "fixture.csproj"
            project.write_text('''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
<DisableImplicitFrameworkReferences>true</DisableImplicitFrameworkReferences></PropertyGroup>
<ItemGroup><PackageReference Include="Avalonia" Version="0.0.0-flatpak-cache-test" /></ItemGroup>
</Project>''')
            cache = root / "artifacts/nuget-packages"
            expected = cache / "avalonia/0.0.0-flatpak-cache-test" / archive.name
            for index in range(2):
                home = root / f"command-home-{index}"
                home.mkdir()
                env = dict(os.environ)
                for name in ("NUGET_PACKAGES", "NUGET_HTTP_CACHE_PATH", "NUGET_SCRATCH",
                             "NUGET_PLUGINS_CACHE_PATH", "MSBuildSDKsPath"):
                    env.pop(name, None)
                env.update(HOME=str(home), USERPROFILE=str(home), DOTNET_CLI_HOME=str(home),
                           DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
                           DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")
                result = subprocess.run([
                    DOTNET, "restore", str(project), "--configfile", str(config),
                    "--force", "--no-http-cache", "--disable-build-servers",
                ], cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                assets = json.loads((root / "obj/project.assets.json").read_text())
                self.assertEqual({cache.resolve()}, {Path(p).resolve() for p in assets["packageFolders"]})
                self.assertTrue(expected.is_file(), "The next build command needs the restored archive")
                shutil.rmtree(home)
                self.assertTrue(expected.is_file(), "Discarding HOME must not discard restored packages")
                archive.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
