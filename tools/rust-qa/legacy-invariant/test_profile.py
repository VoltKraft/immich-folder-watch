import unittest

from invariant_profile import DIFFERENTIAL, check_source, decode, differences, encode, sha, three_profiles
from store import expected_entries


class ManagedInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tables = three_profiles()
        self.maps = [decode(table) for table in self.tables.values()]

    def test_exact_tables_and_retained_two_profile_boundary(self):
        for mapping, table in zip(self.maps, self.tables.values(), strict=True):
            self.assertEqual(encode(mapping), table)
        self.assertEqual([len(mapping) for mapping in self.maps], [1449, 1475, 1504])
        for code, expected in (
            (0x0061, (0x0041, 0x0041, 0x0041)), (0x00B5, (0x039C, 0x039C, 0x039C)),
            (0x00DF, (0x00DF, 0x00DF, 0x00DF)), (0x0130, (0x0130, 0x0130, 0x0130)),
            (0x0131, (0x0131, 0x0131, 0x0131)), (0x017F, (0x0053, 0x017F, 0x0053)),
            (0x019B, (0x019B, 0xA7DC, 0xA7DC)), (0x03C2, (0x03A3, 0x03A3, 0x03A3)),
            (0x10428, (0x10400, 0x10400, 0x10400)), (0x10D70, (0x10D70, 0x10D50, 0x10D50)),
            (0x16EBB, (0x16EBB, 0x16EBB, 0x16EA0)),
        ):
            with self.subTest(code=code):
                self.assertEqual(tuple(mapping.get(code, code) for mapping in self.maps), expected)

    def test_all_three_profile_differences(self):
        rows = differences(self.maps)
        self.assertEqual(len(rows), 56)
        self.assertEqual([sum(row[a] != row[b] for row in rows) for a, b in ((1, 2), (2, 3), (1, 3))],
                         [28, 29, 55])
        data = "".join("\t".join(f"{code:06X}" for code in row) + "\n" for row in rows)
        self.assertEqual(sha(data.encode("ascii")), DIFFERENTIAL)

    def test_last_write_per_key(self):
        for mapping, count, long_s, stroke, garay, beria in zip(
                self.maps, (11, 10, 8), (True, False, True), (False, True, True),
                (False, True, True), (False, False, True), strict=True):
            rows, lookups, shared = expected_entries(mapping, False)
            self.assertEqual(len(rows), count)
            self.assertEqual(shared, {"long-s": long_s, "stroke": stroke, "dotless": False, "sharp-s": False,
                                      "garay": garay, "beria": beria})
            self.assertEqual(lookups["long-s-S.jpg"], "long-s-lower" if long_s else "long-s-upper")
            sensitive, _, sensitive_aliases = expected_entries(mapping, True)
            self.assertEqual(len(sensitive), 12)
            self.assertFalse(any(sensitive_aliases.values()))

    def test_reject_wrong_source_bytes_before_use(self):
        for name in ("UnicodeData.txt", "gen-CategoryCasingInfo.cs", "CharUnicodeInfoData.cs"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "published source"):
                check_source(name, b"wrong source")


if __name__ == "__main__":
    unittest.main()
