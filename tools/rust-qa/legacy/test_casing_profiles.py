import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import casing_profiles


class CasingProfileTests(unittest.TestCase):
    def test_both_original_tables_match_and_only_the_observed_55_scalars_differ(self):
        mappings = []
        for profile in casing_profiles.PROFILES:
            raw = profile.table.read_bytes()
            self.assertEqual(casing_profiles.match_reference(raw), profile)
            pairs = dict(line.split("\t") for line in raw.decode("ascii").splitlines()[1:])
            self.assertEqual(len(pairs), profile.changed_scalars)
            self.assertNotIn("000131", pairs)
            mappings.append(pairs)
        older, newer = mappings
        self.assertLessEqual(older.items(), newer.items())
        self.assertEqual(len(newer.keys() - older.keys()), 55)
        self.assertEqual(newer["00019B"], "00A7DC")

    def test_unknown_map_and_wrong_data_release_are_distinguishable(self):
        older, newer = casing_profiles.PROFILES
        raw = older.table.read_bytes()
        self.assertIsNone(casing_profiles.match_reference(raw.replace(b"000041", b"000042", 1)))
        with self.assertRaisesRegex(ValueError, "Wrong UnicodeData"):
            casing_profiles.derive(newer, raw)

    def test_reference_cannot_substitute_for_changed_checked_in_table(self):
        profile, other = casing_profiles.PROFILES
        reference, wrong = profile.table.read_bytes(), other.table.read_bytes()
        with tempfile.TemporaryDirectory() as tmp, patch.object(casing_profiles, "HERE", Path(tmp)):
            profile.table.parent.mkdir()
            profile.table.write_bytes(wrong)
            with self.assertRaisesRegex(ValueError, "checked-in Unicode table differs"):
                casing_profiles.match_reference(reference)

    def test_source_column_is_simple_uppercase(self):
        raw = b"0061;LATIN SMALL LETTER A;Ll;0;L;;;;;N;;;0041;;0041\n"
        self.assertEqual(casing_profiles.simple_uppercase(raw), {0x61: 0x41})
        with self.assertRaisesRegex(ValueError, "Invalid UnicodeData"):
            casing_profiles.simple_uppercase(b"0061;0041\n")

    def test_original_notice_accompanies_profiles(self):
        self.assertEqual(hashlib.sha256(casing_profiles.LICENSE.read_bytes()).hexdigest(),
                         casing_profiles.LICENSE_SHA256)
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "notice"
            changed.write_text("other", encoding="utf-8")
            with patch.object(casing_profiles, "LICENSE", changed), self.assertRaisesRegex(ValueError, "license notice"):
                casing_profiles.match_reference(casing_profiles.PROFILES[0].table.read_bytes())


if __name__ == "__main__":
    unittest.main()
