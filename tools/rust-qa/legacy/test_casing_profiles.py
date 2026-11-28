import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import casing_profiles
import oracle_runtime
import verify


class CasingProfileTests(unittest.TestCase):
    def test_runtime_selection_requires_the_exact_installed_patch(self):
        pin = "Microsoft.NETCore.App 10.0.12 [/sdk/shared/Microsoft.NETCore.App]"
        newer = "Microsoft.NETCore.App 10.0.15 [/sdk/shared/Microsoft.NETCore.App]"
        path, versions = oracle_runtime.installed_corelib("\r\n".join([newer, pin]))
        self.assertEqual(path, Path("/sdk/shared/Microsoft.NETCore.App/10.0.12/System.Private.CoreLib.dll"))
        self.assertEqual(versions, ["10.0.15", "10.0.12"])
        with self.assertRaisesRegex(ValueError, "found 0"):
            oracle_runtime.installed_corelib(newer)

    def test_managed_mode_requires_its_own_runtime_and_complete_table(self):
        table = Path(__file__).resolve().parents[1] / "legacy-invariant/managed-invariant-10.0.12.tsv"
        manifest = {"GlobalizationInvariantRequested": True, "Runtime": "10.0.12", "CoreLibSha256": "e" * 64,
                    "CoreLibBuild": "10.0.12+95017c711e6afc1085133d440e42b4bd78155701"}
        self.assertTrue(verify.independent_casing(table, manifest, True)[1]["qualified"])
        self.assertFalse(verify.independent_casing(table, manifest, False)[1]["qualified"])
        for key, value in (("GlobalizationInvariantRequested", False), ("Runtime", "10.0.11"), ("Runtime", "10.0.15"),
                           ("CoreLibBuild", "10.0.12+different-source"), ("CoreLibSha256", None)):
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, "reviewed .NET runtime"):
                verify.independent_casing(table, {**manifest, key: value}, True)
        with self.assertRaisesRegex(ValueError, "complete managed invariant table"):
            verify.independent_casing(casing_profiles.PROFILES[1].table, manifest, True)

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
