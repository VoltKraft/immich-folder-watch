from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "prepare-flathub-release.py"
SPEC = importlib.util.spec_from_file_location("prepare_flathub_release", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def release_payload() -> dict[str, object]:
    return {
        "tag_name": "v2.11.0",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-09-09T12:00:00Z",
        "assets": [
            {"name": f"immich-folder-watch-2.11.0-{suffix}", "size": 123, "state": "uploaded"}
            for suffix in (
                "win-x64.msi", "win-arm64.msi", "linux-x64.flatpak", "linux-arm64.flatpak"
            )
        ],
    }


def nuget_source(package: str, sha: str = "a" * 128) -> dict[str, str]:
    filename = f"{package}.10.0.8.nupkg"
    return {
        "type": "file",
        "url": f"https://api.nuget.org/v3-flatcontainer/{package}/10.0.8/{filename}",
        "sha512": sha,
        "dest": "nuget-sources",
        "dest-filename": filename,
    }


def sources_for(runtime: str) -> list[dict[str, str]]:
    return [nuget_source("avalonia"), nuget_source(f"microsoft.netcore.app.runtime.{runtime}")]


MANIFEST = """app-id: io.github.voltkraft.immich-folder-watch
modules:
  - name: app
    sources:
      - type: git
        url: https://github.com/VoltKraft/immich-folder-watch.git
        tag: v2.5.3
        commit: REPLACE_ME
        x-checker-data:
          type: json
          url: https://api.github.com/repos/VoltKraft/immich-folder-watch/releases/latest
          tag-query: .tag_name
      # Keep the generated NuGet source list next to the manifest.
      - nuget-sources.json
    build-commands:
      - dotnet publish --source ./nuget-sources
"""


class ReleaseValidationTests(unittest.TestCase):
    def test_accepts_complete_published_stable_release(self) -> None:
        self.assertEqual("v2.11.0", MODULE.validate_release(release_payload()))

    def test_rejects_nonstable_or_malformed_tags(self) -> None:
        for tag in (None, 123, "2.11.0", "v2.11.0-beta", "v2.11.0+build", "v02.11.0", "v2.11", "v2.11.0\n"):
            with self.subTest(tag=tag), self.assertRaisesRegex(MODULE.ManifestError, "stable"):
                MODULE.validate_release({**release_payload(), "tag_name": tag})

    def test_rejects_draft_prerelease_and_missing_publication(self) -> None:
        for field, value in (
            ("draft", True), ("draft", None), ("draft", "false"),
            ("prerelease", True), ("published_at", None),
            ("published_at", "2026-09-09"), ("published_at", "not-a-date"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(MODULE.ManifestError):
                MODULE.validate_release({**release_payload(), field: value})

    def test_rejects_incomplete_extra_duplicate_or_wrong_assets(self) -> None:
        valid = release_payload()["assets"]
        invalid_lists = [
            None, valid[:-1], valid + [valid[0]], valid[:-1] + [valid[0]],
            valid[:-1] + [{**valid[-1], "name": "another.flatpak"}],
            valid[:-1] + [None],
        ]
        for assets in invalid_lists:
            with self.subTest(assets=assets), self.assertRaises(MODULE.ManifestError):
                MODULE.validate_release({**release_payload(), "assets": assets})

    def test_rejects_empty_unuploaded_or_invalid_asset_sizes(self) -> None:
        for update in ({"size": 0}, {"size": -1}, {"size": True}, {"size": "123"}, {"state": "new"}):
            release = release_payload()
            release["assets"][0].update(update)
            with self.subTest(update=update), self.assertRaisesRegex(MODULE.ManifestError, "nonempty and uploaded"):
                MODULE.validate_release(release)


class NugetValidationTests(unittest.TestCase):
    def test_deduplicates_packages_and_sorts_independently_of_input_order(self) -> None:
        x64, arm64 = sources_for("linux-x64"), sources_for("linux-arm64")
        arm64[0]["sha512"] = arm64[0]["sha512"].upper()
        expected = MODULE.merge_nuget_sources(x64, arm64)
        self.assertEqual(3, len(expected))
        self.assertEqual(sorted(source["dest-filename"] for source in expected), [source["dest-filename"] for source in expected])
        self.assertEqual(expected, MODULE.merge_nuget_sources(list(reversed(x64)), list(reversed(arm64))))

    def test_rejects_conflicting_shared_destination(self) -> None:
        arm64 = sources_for("linux-arm64")
        arm64[0]["sha512"] = "b" * 128
        with self.assertRaisesRegex(MODULE.ManifestError, "conflicting NuGet sources"):
            MODULE.merge_nuget_sources(sources_for("linux-x64"), arm64)

    def test_rejects_conflicts_within_one_input(self) -> None:
        x64 = sources_for("linux-x64") + [nuget_source("avalonia", "b" * 128)]
        with self.assertRaisesRegex(MODULE.ManifestError, "conflicting NuGet sources"):
            MODULE.merge_nuget_sources(x64, sources_for("linux-arm64"))

    def test_requires_both_nonempty_architecture_inputs_and_runtime_packs(self) -> None:
        for runtime in ("linux-x64", "linux-arm64"):
            for source_list in (None, [], {}, [nuget_source("avalonia")], sources_for("linux-riscv64")):
                with self.subTest(runtime=runtime, sources=source_list), self.assertRaises(MODULE.ManifestError):
                    MODULE.validate_nuget_sources(source_list, runtime)

    def test_rejects_unsafe_source_options_paths_urls_and_hashes(self) -> None:
        invalid_updates = [
            {"type": "shell"}, {"commands": ["echo unsafe"]}, {"dest": "../outside"},
            {"dest": "/tmp/outside"}, {"dest-filename": "../outside.nupkg"},
            {"dest-filename": "subdir/file.nupkg"}, {"dest-filename": "..\\outside.nupkg"},
            {"sha512": "a" * 127}, {"sha512": "g" * 128}, {"sha512": None},
            {"url": "http://api.nuget.org/v3-flatcontainer/avalonia/10.0.8/avalonia.10.0.8.nupkg"},
            {"url": "https://api.nuget.org.evil.example/v3-flatcontainer/avalonia/10.0.8/avalonia.10.0.8.nupkg"},
            {"url": "https://user@api.nuget.org/v3-flatcontainer/avalonia/10.0.8/avalonia.10.0.8.nupkg"},
            {"url": "https://api.nuget.org/v3-flatcontainer/avalonia/10.0.8/%2e%2e.nupkg"},
            {"url": "https://api.nuget.org/v3-flatcontainer/avalonia/10.0.8/other.nupkg"},
            {"url": "https://api.nuget.org/v3-flatcontainer/avalonia/10.0.8/avalonia.10.0.8.nupkg?token=x"},
        ]
        for update in invalid_updates:
            sources = sources_for("linux-x64")
            sources[0].update(update)
            with self.subTest(update=update), self.assertRaises(MODULE.ManifestError):
                MODULE.validate_nuget_sources(sources, "linux-x64")


@unittest.skipUnless(shutil.which("git"), "Git is required for checkout validation")
class PreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "source"
        self.checkout.mkdir()
        self.manifest_dir = self.checkout / "packaging" / "flatpak" / "flathub"
        self.manifest_dir.mkdir(parents=True)
        (self.checkout / "Directory.Build.props").write_text("<Project><PropertyGroup><Version>2.11.0</Version></PropertyGroup></Project>", encoding="utf-8")
        self.metainfo = self.manifest_dir.parent / f"{MODULE.APP_ID}.metainfo.xml"
        self.metainfo.write_text('<component><releases><release version="2.11.0" /></releases></component>', encoding="utf-8")
        (self.manifest_dir / f"{MODULE.APP_ID}.yml").write_text(MANIFEST, encoding="utf-8")
        self.config = {"only-arches": ["x86_64", "aarch64"], "skip-appstream-check": False}
        (self.manifest_dir / "flathub.json").write_text(json.dumps(self.config), encoding="utf-8")
        (self.checkout / ".gitignore").write_text("obj/\n", encoding="utf-8")
        self.git("init", "--quiet")
        self.commit_checkout()
        self.release_json = self.root / "release.json"
        self.release_json.write_text(json.dumps(release_payload()), encoding="utf-8")
        self.x64 = self.root / "x64.json"
        self.arm64 = self.root / "arm64.json"
        self.x64.write_text(json.dumps(sources_for("linux-x64")), encoding="utf-8")
        self.arm64.write_text(json.dumps(sources_for("linux-arm64")), encoding="utf-8")
        self.output = self.root / "output"

    def git(self, *arguments: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.checkout), *arguments], text=True, stderr=subprocess.PIPE).strip()

    def commit_checkout(self) -> None:
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test release")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("tag", "--force", "v2.11.0")

    def prepare(self) -> list[Path]:
        return MODULE.prepare_release(self.checkout, self.release_json, self.commit, self.x64, self.arm64, self.output)

    def test_cli_writes_only_three_deterministic_files_from_clean_release(self) -> None:
        (self.checkout / "obj").mkdir()
        (self.checkout / "obj" / "ignored-build-file").touch()
        result = subprocess.run([
            sys.executable, str(SCRIPT_PATH), "--source-root", str(self.checkout),
            "--release-json", str(self.release_json), "--commit", self.commit.upper(),
            "--nuget-x64", str(self.x64), "--nuget-arm64", str(self.arm64),
            "--output-dir", str(self.output),
        ], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({f"{MODULE.APP_ID}.yml", "nuget-sources.json", "flathub.json"}, {path.name for path in self.output.iterdir()})
        manifest = (self.output / f"{MODULE.APP_ID}.yml").read_text(encoding="utf-8")
        self.assertIn("tag: v2.11.0\n", manifest)
        self.assertIn(f"commit: {self.commit}\n", manifest)
        self.assertNotIn("x-checker-data", manifest)
        self.assertNotIn("tag-query", manifest)
        self.assertIn("# Keep the generated NuGet", manifest)
        self.assertIn("- dotnet publish", manifest)
        self.assertEqual({**self.config, "disable-external-data-checker": True}, json.loads((self.output / "flathub.json").read_text()))
        first_output = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.output = self.root / "second-output"
        self.x64.write_text(json.dumps(list(reversed(sources_for("linux-x64")))), encoding="utf-8")
        self.prepare()
        self.assertEqual(first_output, {path.name: path.read_bytes() for path in self.output.iterdir()})
        self.assertEqual("", self.git("status", "--porcelain"))

    def test_rejects_nonempty_output_without_changing_it(self) -> None:
        self.output.mkdir()
        existing = self.output / "keep-me"
        existing.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestError, "empty or new"):
            self.prepare()
        self.assertEqual("original", existing.read_text())

    def test_rejects_checkout_output_and_input_overlap(self) -> None:
        for output in (self.checkout, self.checkout / "generated", self.root, self.root / "inputs"):
            with self.subTest(output=output):
                self.output = output
                if output.name == "inputs":
                    output.mkdir()
                    self.x64 = output / "x64.json"
                    self.x64.write_text("[]", encoding="utf-8")
                with self.assertRaises(MODULE.ManifestError):
                    self.prepare()

    def test_rejects_symlinked_output_inside_source(self) -> None:
        self.output.symlink_to(self.checkout, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.ManifestError, "overlap"):
            self.prepare()

    def test_rejects_dirty_and_untracked_release_checkout(self) -> None:
        for path in (self.checkout / "Directory.Build.props", self.checkout / "untracked"):
            with self.subTest(path=path):
                original = path.read_bytes() if path.exists() else None
                path.write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(MODULE.ManifestError, "tracked or untracked"):
                    self.prepare()
                self.assertFalse(self.output.exists())
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)

    def test_rejects_invalid_commit_mismatched_head_and_missing_tag(self) -> None:
        original = self.commit
        for commit in ("abc123", "x" * 40, "0" * 40):
            self.commit = commit
            with self.subTest(commit=commit), self.assertRaises(MODULE.ManifestError):
                self.prepare()
        self.commit = original
        self.git("tag", "--delete", "v2.11.0")
        with self.assertRaises(MODULE.ManifestError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_rejects_tag_that_resolves_to_another_commit(self) -> None:
        (self.checkout / "extra").write_text("next release", encoding="utf-8")
        previous = self.commit
        self.commit_checkout()
        self.git("tag", "--force", "v2.11.0", previous)
        with self.assertRaisesRegex(MODULE.ManifestError, "tag does not resolve"):
            self.prepare()

    def test_rejects_version_and_top_appstream_mismatches(self) -> None:
        for path, content, error in (
            (self.checkout / "Directory.Build.props", "<Project><Version>2.10.0</Version></Project>", "Directory.Build.props"),
            (self.metainfo, '<component><releases><release version="2.10.0"/><release version="2.11.0"/></releases></component>', "top AppStream"),
        ):
            with self.subTest(path=path):
                original = path.read_text()
                path.write_text(content, encoding="utf-8")
                self.commit_checkout()
                with self.assertRaisesRegex(MODULE.ManifestError, error):
                    self.prepare()
                self.assertFalse(self.output.exists())
                path.write_text(original, encoding="utf-8")
                self.commit_checkout()

    def test_rejects_invalid_input_before_creating_output(self) -> None:
        self.arm64.write_text("not JSON", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestError, "JSON input"):
            self.prepare()
        self.assertFalse(self.output.exists())


@unittest.skipUnless(shutil.which("bash"), "Bash is required for generator argument tests")
class GeneratorArgumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "automation"
        (self.repo / "tools").mkdir(parents=True)
        self.script = self.repo / "tools" / "generate-nuget-sources.sh"
        shutil.copyfile(SCRIPT_PATH.with_name(self.script.name), self.script)
        self.project_suffix = Path("src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj")
        (self.repo / self.project_suffix).parent.mkdir(parents=True)
        (self.repo / self.project_suffix).touch()
        self.mock_bin = self.root / "bin"
        self.mock_bin.mkdir()
        for command in ("git", "flatpak", "dotnet"):
            path = self.mock_bin / command
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        cache = self.root / "cache"
        generator = cache / "immich-folder-watch/flatpak-builder-tools/dotnet/flatpak-dotnet-generator.py"
        generator.parent.mkdir(parents=True)
        generator.write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "Path(sys.argv[-2]).write_text(json.dumps([{'arguments': sys.argv[1:]}]))\n",
            encoding="utf-8",
        )
        self.environment = {**os.environ, "XDG_CACHE_HOME": str(cache), "PATH": str(self.mock_bin) + os.pathsep + os.environ["PATH"]}

    def run_generator(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(self.script), *arguments], capture_output=True, text=True, env=self.environment)

    def test_default_runtime_and_output_remain_compatible(self) -> None:
        result = self.run_generator()
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.repo / "packaging/flatpak/flathub/nuget-sources.json"
        arguments = json.loads(output.read_text())[0]["arguments"]
        self.assertIn("--runtime=linux-x64", arguments)
        self.assertEqual(str(self.repo / self.project_suffix), arguments[-1])

    def test_explicit_source_root_output_and_runtime_in_both_option_forms(self) -> None:
        source = self.root / "release checkout"
        (source / self.project_suffix).parent.mkdir(parents=True)
        (source / self.project_suffix).touch()
        for use_equals in (False, True):
            output = self.root / f"feed {use_equals}.json"
            options = {"--source-root": str(source), "--output": str(output), "--runtime": "linux-arm64"}
            args = [f"{key}={value}" for key, value in options.items()] if use_equals else [part for pair in options.items() for part in pair]
            with self.subTest(use_equals=use_equals):
                result = self.run_generator(*args)
                self.assertEqual(0, result.returncode, result.stderr)
                arguments = json.loads(output.read_text())[0]["arguments"]
                self.assertIn("--runtime=linux-arm64", arguments)
                self.assertEqual(str(source / self.project_suffix), arguments[-1])
        self.assertFalse((source / "packaging").exists())

    def test_rejects_missing_output_source_root_and_unsupported_runtime(self) -> None:
        for args in (("--output",), ("--output=",), ("--source-root",), ("--source-root=",), ("--runtime", "linux-riscv64")):
            with self.subTest(args=args):
                result = self.run_generator(*args)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("ERROR:", result.stderr)


if __name__ == "__main__":
    unittest.main()
