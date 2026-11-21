"""Checks for incomplete compiler evidence and collateral changes in the relink control."""
from pathlib import Path
import json
import tempfile
import unittest

import relink
from sources import HERE, write
from units import compiler_units


class ProfileControls(unittest.TestCase):
    def test_unrelated_lock_edge_aborts_relink(self):
        original = (HERE / "Cargo.lock").read_text(encoding="utf-8")
        source = ('name = "wayland-protocols-plasma"\nversion = "0.3.12"\n'
                  'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
                  'checksum = "2b6d8cf1eb2c1c31ed1f5643c88a6e53538129d4af80030c8cabd1f9fa884d91"\n')
        self.assertEqual(original.count(source), 1)
        edited = original.replace(source, 'name = "wayland-protocols-plasma"\nversion = "0.3.12"\n')
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "Cargo.lock"
            path.write_text(edited, encoding="utf-8")
            relink.verify_lock(path)
            changed = edited.replace(' "windows-sys 0.61.2",', ' "windows-sys 0.52.0",', 1)
            self.assertNotEqual(changed, edited)
            path.write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected relink source change"):
                relink.verify_lock(path)

    def test_compiler_success_cannot_replace_missing_units(self):
        target = "x86_64-unknown-linux-gnu"
        with tempfile.TemporaryDirectory() as raw:
            area = Path(raw)
            write(area / (target + ".json"), {"features": {"synthetic v1.0.0": [["checked"]]}})
            (area / "build.log").write_text(json.dumps({"reason": "build-finished", "success": True}) + "\n")
            with self.assertRaisesRegex(ValueError, "Actual native compiler"):
                compiler_units(area, target)


if __name__ == "__main__":
    unittest.main()
