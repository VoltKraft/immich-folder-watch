from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "generate-flatpak-nuget-sources.py"
SPEC = importlib.util.spec_from_file_location("generate_flatpak_nuget_sources", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FeedValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.packages = self.root / "packages"
        self.artifacts = self.root / "artifacts"
        self.assets_file = self.artifacts / "obj/app/project.assets.json"
        self.assets_file.parent.mkdir(parents=True)
        self.package("example", "1.2.3")
        self.package("microsoft.netcore.app.runtime.linux-x64", "10.0.12")
        self.assets = {
            "libraries": {"Example/1.2.3": {"type": "package"}},
            "packageFolders": {str(self.packages): {}},
            "project": {"frameworks": {"net10.0": {"downloadDependencies": [{
                "name": "Microsoft.NETCore.App.Runtime.linux-x64", "version": "[10.0.12, 10.0.12]"
            }]}}},
        }
        self.write_assets()

    def write_assets(self) -> None:
        self.assets_file.write_text(json.dumps(self.assets), encoding="utf-8")

    def package(self, package: str, version: str) -> Path:
        directory = self.packages / package / version
        directory.mkdir(parents=True)
        archive = directory / f"{package}.{version}.nupkg"
        content = f"archive bytes for {package}/{version}".encode()
        archive.write_bytes(content)
        digest = base64.b64encode(hashlib.sha512(content).digest()).decode()
        archive.with_name(archive.name + ".sha512").write_text(digest, encoding="utf-8")
        (directory / ".nupkg.metadata").write_text(json.dumps({
            "source": MODULE.NUGET_INDEX, "contentHash": digest
        }), encoding="utf-8")
        return archive

    def collect(self) -> list[dict[str, str]]:
        return MODULE.collect_sources(self.packages, self.artifacts, "linux-x64")

    def test_emits_deterministic_five_field_sources_from_verified_bytes(self) -> None:
        result = self.collect()
        self.assertEqual(2, len(result))
        self.assertEqual(result, self.collect())
        for source in result:
            self.assertEqual({"type", "url", "sha512", "dest", "dest-filename"}, set(source))
            self.assertEqual("file", source["type"])
            self.assertEqual("nuget-sources", source["dest"])
            self.assertEqual(128, len(source["sha512"]))
        self.assertEqual("https://api.nuget.org/v3-flatcontainer/example/1.2.3/example.1.2.3.nupkg", result[0]["url"])

    def test_rejects_missing_archive_or_checksum_metadata(self) -> None:
        directory = self.packages / "example/1.2.3"
        for name in ("example.1.2.3.nupkg", "example.1.2.3.nupkg.sha512", ".nupkg.metadata"):
            path = directory / name
            data = path.read_bytes()
            path.unlink()
            with self.subTest(name=name), self.assertRaisesRegex(MODULE.GeneratorError, "is missing"):
                self.collect()
            path.write_bytes(data)

    def test_rejects_tampered_archives_and_hashes(self) -> None:
        path = self.packages / "example/1.2.3/example.1.2.3.nupkg"
        path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.GeneratorError, "checksum mismatch"):
            self.collect()

    def test_rejects_nonofficial_origin_even_when_checksum_matches(self) -> None:
        path = self.packages / "example/1.2.3/.nupkg.metadata"
        metadata = json.loads(path.read_text())
        metadata["source"] = "https://other.example/v3/index.json"
        path.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.GeneratorError, "official NuGet source"):
            self.collect()

    def test_signed_package_content_hash_is_not_used_as_archive_hash(self) -> None:
        path = self.packages / "example/1.2.3/.nupkg.metadata"
        metadata = json.loads(path.read_text())
        metadata["contentHash"] = base64.b64encode(hashlib.sha512(b"unsigned content").digest()).decode()
        path.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(2, len(self.collect()))

    def test_rejects_global_cache_assets(self) -> None:
        self.assets["packageFolders"][str(self.root / "global-packages")] = {}
        self.write_assets()
        with self.assertRaisesRegex(MODULE.GeneratorError, "outside the isolated cache"):
            self.collect()

    def test_requires_all_resolved_libraries_and_download_dependencies(self) -> None:
        for package in ("example/1.2.3", "microsoft.netcore.app.runtime.linux-x64/10.0.12"):
            directory = self.packages / package
            moved = self.root / "held"
            directory.rename(moved)
            with self.subTest(package=package), self.assertRaisesRegex(MODULE.GeneratorError, "absent from the fresh cache"):
                self.collect()
            moved.rename(directory)

    def test_requires_assets_and_matching_self_contained_runtime(self) -> None:
        with self.assertRaisesRegex(MODULE.GeneratorError, "runtime pack is missing"):
            MODULE.collect_sources(self.packages, self.artifacts, "linux-arm64")
        self.assets_file.unlink()
        with self.assertRaisesRegex(MODULE.GeneratorError, "no project.assets.json"):
            self.collect()

    def test_rejects_unpinned_download_dependency(self) -> None:
        self.assets["project"]["frameworks"]["net10.0"]["downloadDependencies"][0]["version"] = "[10.0.0, 11.0.0)"
        self.write_assets()
        with self.assertRaisesRegex(MODULE.GeneratorError, "one exact version"):
            self.collect()


FAKE_DOTNET = '''#!/usr/bin/env python3
import base64, hashlib, json, os, sys
from pathlib import Path
arguments = sys.argv[1:]
pin = json.loads(Path('global.json').read_text())['sdk']
if arguments == ['--version']:
    print(os.environ.get('TEST_DOTNET_VERSION', pin['version']))
    raise SystemExit(0)
assert arguments[0] == 'restore'
assert pin['rollForward'] == 'disable'
runtime = arguments[arguments.index('--runtime') + 1]
packages = Path(arguments[arguments.index('--packages') + 1])
artifacts = Path(arguments[arguments.index('--artifacts-path') + 1])
assert not packages.exists()
assert os.environ['NUGET_PACKAGES'] == str(packages)
assert Path(arguments[1]).is_file()
record = {'arguments': arguments, 'cwd': str(Path.cwd()), 'pin': pin,
          'http_cache': os.environ['NUGET_HTTP_CACHE_PATH']}
Path(os.environ['TEST_DOTNET_RECORD']).write_text(json.dumps(record))
if os.environ.get('TEST_RESTORE_FAIL'):
    raise SystemExit(2)
libraries = {}
for package in ('example', 'microsoft.netcore.app.runtime.' + runtime):
    version = '10.0.12'
    directory = packages / package / version
    directory.mkdir(parents=True)
    content = (package + version).encode()
    digest = base64.b64encode(hashlib.sha512(content).digest()).decode()
    filename = package + '.' + version + '.nupkg'
    (directory / filename).write_bytes(content)
    (directory / (filename + '.sha512')).write_text(digest)
    (directory / '.nupkg.metadata').write_text(json.dumps({
        'source': 'https://api.nuget.org/v3/index.json', 'contentHash': digest}))
    libraries[package + '/' + version] = {'type': 'package'}
assets = artifacts / 'obj' / 'app' / 'project.assets.json'
assets.parent.mkdir(parents=True)
assets.write_text(json.dumps({'libraries': libraries, 'packageFolders': {str(packages): {}}}))
'''


class IsolatedRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        project = self.source / MODULE.PROJECT
        project.parent.mkdir(parents=True)
        project.write_text("<Project />", encoding="utf-8")
        (self.source / "global.json").write_text('{"sdk":{"version":"10.0.100"}}', encoding="utf-8")
        self.output = self.root / "feed.json"
        self.record = self.root / "record.json"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        dotnet = self.bin / "dotnet"
        dotnet.write_text(FAKE_DOTNET, encoding="utf-8")
        dotnet.chmod(0o755)
        environment = patch.dict(os.environ, {
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "TEST_DOTNET_RECORD": str(self.record),
            "NUGET_PACKAGES": str(self.root / "must-not-use-global-cache"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        metadata = patch.object(MODULE, "sdk_version", return_value="10.0.401")
        metadata.start()
        self.addCleanup(metadata.stop)

    def test_uses_pinned_sdk_and_fresh_cache_for_each_rid_without_source_changes(self) -> None:
        before = {path.relative_to(self.source): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        previous_cache = None
        for runtime in ("linux-x64", "linux-arm64"):
            with self.subTest(runtime=runtime):
                self.assertEqual(2, MODULE.generate_sources(self.source, runtime, self.output))
                record = json.loads(self.record.read_text())
                self.assertEqual("10.0.401", record["pin"]["version"])
                self.assertIn("-p:SelfContained=true", record["arguments"])
                self.assertIn("--no-http-cache", record["arguments"])
                self.assertIn("--force", record["arguments"])
                self.assertNotEqual(previous_cache, record["http_cache"])
                self.assertFalse(Path(record["cwd"]).exists())
                previous_cache = record["http_cache"]
                self.assertTrue(any(runtime in source["dest-filename"] for source in json.loads(self.output.read_text())))
        after = {path.relative_to(self.source): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_failed_restore_preserves_existing_output_and_cleans_cache(self) -> None:
        self.output.write_text("existing feed", encoding="utf-8")
        with patch.dict(os.environ, {"TEST_RESTORE_FAIL": "1"}):
            with self.assertRaisesRegex(MODULE.GeneratorError, "restore failed"):
                MODULE.generate_sources(self.source, "linux-x64", self.output)
        self.assertEqual("existing feed", self.output.read_text())
        self.assertFalse(Path(json.loads(self.record.read_text())["cwd"]).exists())

    def test_rejects_different_sdk_before_restore_or_output(self) -> None:
        with patch.dict(os.environ, {"TEST_DOTNET_VERSION": "10.0.203"}):
            with self.assertRaisesRegex(MODULE.GeneratorError, "exact Flatpak SDK 10.0.401"):
                MODULE.generate_sources(self.source, "linux-x64", self.output)
        self.assertFalse(self.record.exists())
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
