"""Check registration, ambiguous shapes and a rendered missing glyph independently of text layout."""
import unittest

from text_observations import identify_glyph


class GlyphPixelTests(unittest.TestCase):
    def setUp(self):
        self.samples = {
            "628": {(0, 1), (0, 2), (1, 2), (2, 2), (3, 2), (3, 1), (1, 5)},
            "62A": {(0, 3), (0, 4), (1, 4), (2, 4), (3, 4), (3, 3), (1, 0), (3, 0)},
            "62B": {(0, 0), (2, 0), (1, 1), (0, 4), (1, 5), (3, 4)},
            "10FFFD": {(x, y) for x in range(5) for y in range(5) if x in (0, 4) or y in (0, 4)},
        }

    def test_registration_is_limited_to_one_physical_pixel(self):
        glyph = self.samples["628"]
        measured = identify_glyph({(x + 1, y - 1) for x, y in glyph}, self.samples)
        self.assertEqual(measured["character"], "ب")
        self.assertEqual(measured["referenceOffsets"]["628"], (1, -1))
        self.assertIsNone(identify_glyph({(x + 5, y) for x, y in glyph}, self.samples)["character"])

    def test_missing_and_ambiguous_glyphs_are_unrecognized(self):
        self.assertIsNone(identify_glyph(self.samples["10FFFD"], self.samples)["character"])
        self.assertIsNone(identify_glyph(set(), self.samples)["character"])
        self.samples["62A"] = self.samples["628"]
        self.assertIsNone(identify_glyph(self.samples["628"], self.samples)["character"])
