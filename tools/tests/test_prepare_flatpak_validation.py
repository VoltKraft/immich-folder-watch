from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "prepare-flatpak-validation.py"
SPEC = importlib.util.spec_from_file_location("prepare_flatpak_validation", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sources_for(runtime: str) -> list[dict[str, str]]:
    return [
        {
            "type": "file",
            "url": f"https://api.nuget.org/v3-flatcontainer/{package}/10.0.8/{package}.10.0.8.nupkg",
            "sha512": "a" * 128,
            "dest": "nuget-sources",
            "dest-filename": f"{package}.10.0.8.nupkg",
        }
        for package in ("avalonia", f"microsoft.netcore.app.runtime.{runtime}")
    ]


MANIFEST = """app-id: io.github.voltkraft.immich-folder-watch
modules:
  - name: app
    sources:
      - type: git
        url: https://github.com/VoltKraft/immich-folder-watch.git
        tag: v2.11.0
        commit: REPLACE_ME
      - nuget-sources.json
    build-commands:
      - dotnet publish --source ./nuget-sources
"""


@unittest.skipUnless(shutil.which("git"), "Git is required for checkout validation")
class CandidatePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "source"
        self.manifest_dir = self.checkout / "packaging/flatpak/flathub"
        self.manifest_dir.mkdir(parents=True)
        self.manifest_path = self.manifest_dir / f"{MODULE.APP_ID}.yml"
        self.manifest_path.write_text(MANIFEST, encoding="utf-8")
        self.config_path = self.manifest_dir / "flathub.json"
        self.config_path.write_text(json.dumps({
            "only-arches": ["x86_64", "aarch64"],
            "disable-external-data-checker": False,
        }), encoding="utf-8")
        (self.checkout / ".gitignore").write_text("artifacts/\nobj/\n", encoding="utf-8")
        self.git("init", "--quiet")
        self.commit_checkout()
        feed_directory = self.checkout / "artifacts/flatpak-validation"
        feed_directory.mkdir(parents=True)
        self.x64 = feed_directory / "x64.json"
        self.arm64 = feed_directory / "arm64.json"
        self.x64.write_text(json.dumps(sources_for("linux-x64")), encoding="utf-8")
        self.arm64.write_text(json.dumps(sources_for("linux-arm64")), encoding="utf-8")
        self.output = self.root / "candidate"

    def git(self, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(self.checkout), *arguments], text=True, stderr=subprocess.PIPE
        ).strip()

    def commit_checkout(self) -> None:
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "test candidate")
        self.commit = self.git("rev-parse", "HEAD")

    def prepare(self) -> list[Path]:
        return MODULE.prepare_validation(
            self.checkout, self.commit, self.x64, self.arm64, self.output
        )

    def test_cli_prepares_both_architectures_without_tags_or_release_metadata(self) -> None:
        result = subprocess.run([
            sys.executable, str(SCRIPT_PATH), "--source-root", str(self.checkout),
            "--commit", self.commit.upper(), "--nuget-x64", str(self.x64),
            "--nuget-arm64", str(self.arm64), "--output-dir", str(self.output),
        ], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", self.git("tag", "--list"))
        self.assertEqual({f"{MODULE.APP_ID}.yml", "nuget-sources.json", "flathub.json"},
                         {path.name for path in self.output.iterdir()})
        manifest = (self.output / f"{MODULE.APP_ID}.yml").read_text()
        self.assertIn(f"commit: {self.commit}\n", manifest)
        self.assertNotIn("tag:", manifest)
        self.assertNotIn("type: dir", manifest)
        self.assertIn("url: https://github.com/VoltKraft/immich-folder-watch.git", manifest)
        self.assertEqual(3, len(json.loads((self.output / "nuget-sources.json").read_text())))
        self.assertEqual({"only-arches": ["x86_64", "aarch64"], "disable-external-data-checker": True},
                         json.loads((self.output / "flathub.json").read_text()))
        self.assertEqual("", self.git("status", "--porcelain"))
        first_output = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.x64.write_text(json.dumps(list(reversed(sources_for("linux-x64")))), encoding="utf-8")
        self.output = self.root / "second-candidate"
        self.prepare()
        self.assertEqual(first_output, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_rejects_invalid_sha_or_head_mismatch_before_writing(self) -> None:
        for commit in ("main", "abc123", "x" * 40, "0" * 40, self.commit + "\n"):
            self.commit = commit
            with self.subTest(commit=commit), self.assertRaises(MODULE.ManifestError):
                self.prepare()
            self.assertFalse(self.output.exists())

    def test_rejects_tracked_and_untracked_source_changes(self) -> None:
        for path in (self.manifest_path, self.checkout / "untracked"):
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

    def test_rejects_source_subdirectory(self) -> None:
        self.checkout = self.manifest_dir
        with self.assertRaisesRegex(MODULE.ManifestError, "root of the validation checkout"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_rejects_missing_architecture_or_conflicting_download_before_writing(self) -> None:
        conflicting = sources_for("linux-arm64")
        conflicting[0]["sha512"] = "b" * 128
        for feed in ([], sources_for("linux-x64"), conflicting):
            self.arm64.write_text(json.dumps(feed), encoding="utf-8")
            with self.subTest(feed=feed), self.assertRaises(MODULE.ManifestError):
                self.prepare()
            self.assertFalse(self.output.exists())

    def test_rejects_configuration_that_disables_an_architecture(self) -> None:
        self.config_path.write_text('{"only-arches": ["x86_64"]}', encoding="utf-8")
        self.commit_checkout()
        with self.assertRaisesRegex(MODULE.ManifestError, "exactly x86_64 and aarch64"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_rejects_unpinnable_manifest(self) -> None:
        self.manifest_path.write_text(MANIFEST.replace("        commit: REPLACE_ME\n", ""), encoding="utf-8")
        self.commit_checkout()
        with self.assertRaisesRegex(MODULE.ManifestError, "exactly one commit field"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_rejects_source_overlap_and_symlinked_output(self) -> None:
        for output in (self.checkout, self.checkout / "artifacts/candidate", self.root):
            self.output = output
            with self.subTest(output=output), self.assertRaisesRegex(MODULE.ManifestError, "overlap"):
                self.prepare()
        self.output = self.root / "symlink"
        self.output.symlink_to(self.checkout, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.ManifestError, "overlap"):
            self.prepare()

    def test_rejects_nonempty_output_without_changing_it(self) -> None:
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestError, "empty or new"):
            self.prepare()
        self.assertEqual("original", marker.read_text())

    def test_rejects_output_containing_an_input(self) -> None:
        self.output.mkdir()
        self.x64 = self.output / "x64.json"
        self.x64.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestError, "must not contain an input"):
            self.prepare()

    def test_cli_reports_invalid_inputs_without_traceback_or_output(self) -> None:
        self.arm64.write_text("invalid JSON", encoding="utf-8")
        result = subprocess.run([
            sys.executable, str(SCRIPT_PATH), "--source-root", str(self.checkout),
            "--commit", self.commit, "--nuget-x64", str(self.x64),
            "--nuget-arm64", str(self.arm64), "--output-dir", str(self.output),
        ], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
