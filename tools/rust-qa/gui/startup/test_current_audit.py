"""Verify the exact allowed comparison and canonical/staged source distinction."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from full_audit import BASE, LOCAL, UPDATED, UPDATED_YAML, verify_yaml_update
from gui.startup.audit_profile import StartupAudit


class CurrentSourceTests(unittest.TestCase):
    def test_linux_changes_only_the_reviewed_first_party_witness(self):
        _, manifest, sources = LOCAL["ifw-yaml-assessment"]
        old = {"target": "aarch64-unknown-linux-gnu", "packages": [{"name": "ifw-yaml-assessment",
               "firstPartyLibrary": {"entry": "src/lib.rs", "revision": BASE, "manifestSha256": manifest,
                                     "sourcesSha256": sources}}, {"name": "base64", "notices": {"LICENSE": "original"}}]}
        new = deepcopy(old)
        new["packages"][0]["firstPartyLibrary"].update(revision=UPDATED, sourcesSha256=UPDATED_YAML)
        self.assertTrue(verify_yaml_update(old, new)["updatedLinuxLibrary"])
        with self.assertRaises(ValueError):
            verify_yaml_update(old, old)
        new["packages"][1]["notices"].clear()
        with self.assertRaises(ValueError):
            verify_yaml_update(old, new)

    def test_windows_requires_identical_reports_and_no_linux_library(self):
        old = {"target": "x86_64-pc-windows-msvc", "packages": [{"name": "renderer"}]}
        self.assertFalse(verify_yaml_update(old, old)["updatedLinuxLibrary"])
        with self.assertRaises(ValueError):
            verify_yaml_update(old, {**old, "packages": []})
        old["packages"].append({"name": "ifw-yaml-assessment"})
        with self.assertRaises(ValueError):
            verify_yaml_update(old, old)

    def test_a_foreign_project_cannot_be_the_canonical_or_staged_audit_root(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "project/tools/rust-qa/gui/Cargo.toml"
            for loader in (StartupAudit, StartupAudit.for_canonical):
                with self.subTest(loader=loader.__name__), self.assertRaisesRegex(ValueError, "isolated staged project"):
                    loader(manifest, root, "x86_64-unknown-linux-gnu")


if __name__ == "__main__":
    unittest.main()
