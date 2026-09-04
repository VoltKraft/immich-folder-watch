from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "prepare-flatpak-release-manifest.py"
SPEC = importlib.util.spec_from_file_location("prepare_flatpak_manifest", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PinGitSourceTests(unittest.TestCase):
    commit = "0123456789abcdef0123456789abcdef01234567"

    def test_pins_commit_and_preserves_other_manifest_content(self) -> None:
        manifest = """app-id: io.github.example.App
modules:
  - name: app
    sources:
      - type: git
        url: https://github.com/example/app.git
        tag: v1.2.3
        commit: REPLACE_ME
        x-checker-data:
          type: json
          tag-query: .tag_name
      - nuget-sources.json
"""

        result = MODULE.pin_git_source(manifest, self.commit.upper())

        self.assertNotIn("tag: v1.2.3", result)
        self.assertIn(f"commit: {self.commit}", result)
        self.assertIn("x-checker-data:", result)
        self.assertIn("- nuget-sources.json", result)

    def test_rejects_invalid_commit(self) -> None:
        with self.assertRaisesRegex(MODULE.ManifestError, "40-character"):
            MODULE.pin_git_source("", "abc123")

    def test_rejects_manifest_without_git_source(self) -> None:
        manifest = """modules:
  - name: app
    sources:
      - nuget-sources.json
"""

        with self.assertRaisesRegex(MODULE.ManifestError, "found 0"):
            MODULE.pin_git_source(manifest, self.commit)

    def test_rejects_multiple_git_sources(self) -> None:
        manifest = """modules:
  - name: app
    sources:
      - type: git
        commit: first
      - type: git
        commit: second
"""

        with self.assertRaisesRegex(MODULE.ManifestError, "found 2"):
            MODULE.pin_git_source(manifest, self.commit)

    def test_rejects_git_source_without_commit_field(self) -> None:
        manifest = """modules:
  - name: app
    sources:
      - type: git
        url: https://github.com/example/app.git
        tag: v1.2.3
"""

        with self.assertRaisesRegex(MODULE.ManifestError, "commit field"):
            MODULE.pin_git_source(manifest, self.commit)


if __name__ == "__main__":
    unittest.main()
