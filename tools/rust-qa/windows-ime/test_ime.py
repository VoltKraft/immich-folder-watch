"""Check that installed-language hints or directly entered Unicode cannot pass the IME trial."""

import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from run import KEYBOARD_CATEGORY, QA, ROOT, accepted, checked_build, digest, eligibility


class ImeTests(unittest.TestCase):
    def test_inventory_requires_loaded_layout_and_usable_engine(self):
        row = {"language": 0x411, "immIme": False}
        profile = {"type": 1, "enabled": True, "category": KEYBOARD_CATEGORY}
        observation = {"layouts": [row], "profiles": [profile], "enumeratedTsf": True}
        self.assertIsNone(eligibility(observation))
        self.assertIsNone(eligibility({"layouts": [{"language": 0x411, "immIme": True}]}))
        for changes in ({"layouts": [{"language": 0x409, "immIme": False}]},
                        {"enumeratedTsf": False}, {"profiles": [{**profile, "enabled": False}]},
                        {"profiles": [{**profile, "type": 2}]}, {"profiles": [{**profile, "category": "other"}]},
                        {"profiles": [], "japaneseBasicCapability": ["Installed"]}):
            with self.subTest(changes=changes):
                self.assertIsNotNone(eligibility({**observation, **changes}))

    def test_requires_ordered_native_events_exact_field_and_restoration(self):
        positive = {"status": "passed", "subjectId": 23, "selectedLayout": 0xe0010411, "preeditBeforeEnter": True,
                    "commitAfterEnter": True, "normalFilenameConfirmed": True, "committedCodePoint": "U+3042",
                    "originalLayout": 0x04090409, "restoredLayout": 0x04090409}
        self.assertTrue(accepted(positive, 23))
        self.assertFalse(accepted(positive, 42))
        for k in positive:
            self.assertFalse(accepted({n: v for n, v in positive.items() if n != k}, 23), k)
        self.assertFalse(accepted({**positive, "restoredLayout": 0x411}, 23))
        self.assertFalse(accepted({**positive, "committedCodePoint": "U+0061"}, 23))

    def test_gui_receipt_binds_executable_native_machine_and_field_source(self):
        with tempfile.TemporaryDirectory() as d:
            binary, record = Path(d) / "app.exe", Path(d) / "receipt.json"
            pe = bytearray(150)
            pe[:2], pe[60:64], pe[100:106] = b"MZ", struct.pack("<I", 100), b"PE\0\0\x64\xaa"
            binary.write_bytes(pe)
            field = QA / "gui/src/main.rs"
            info = {"source": "revision", "binarySha256": digest(binary), "target": "aarch64-pc-windows-msvc",
                    "compilerSources": {field.relative_to(ROOT).as_posix(): digest(field)}}
            record.write_text(json.dumps(info))
            self.assertEqual(checked_build(binary, record, info["target"], 0xaa64, "revision")["source"], "revision")
            for machine, source in ((0x8664, "revision"), (0xaa64, "changed")):
                with self.assertRaises(ValueError):
                    checked_build(binary, record, info["target"], machine, source)
            bad = copy.deepcopy(info)
            bad["compilerSources"][field.relative_to(ROOT).as_posix()] = "changed"
            record.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                checked_build(binary, record, info["target"], 0xaa64, None)


if __name__ == "__main__":
    unittest.main()
