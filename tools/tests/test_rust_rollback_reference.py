"""Regression checks for the shipping worker's deletion ledger and repair timestamps."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "RustCompatibilityOracle"))
from verify_rollback import check_requests, journal_stamp


class RollbackReferenceTests(unittest.TestCase):
    def setUp(self):
        self.album = {"method": "GET", "path": "/api/albums", "body": None, "listedAsset": None}
        self.search = {"method": "POST", "path": "/api/search/metadata",
                       "body": {"albumIds": ["album-camera"], "page": 1, "size": 250}, "listedAsset": None}
        self.trash = {"method": "DELETE", "path": "/api/assets", "body": {"ids": ["test-asset"], "force": False},
                      "listedAsset": None}
        self.first = [self.album, {**self.search, "listedAsset": "test-asset"},
                      {"method": "GET", "path": "/api/assets/test-asset/original", "body": None, "listedAsset": None},
                      self.trash]

    def test_repeated_inventory_is_allowed_and_restart_requires_an_empty_album(self):
        check_requests(self.first, "test-asset", restart=False)
        check_requests([self.album, self.search, self.album, self.search], "test-asset", restart=True)
        for requests in ([self.album], [self.search, self.album], [self.album, self.first[1]],
                         [self.album, self.search, self.trash]):
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                check_requests(requests, "test-asset", restart=True)

    def test_trash_requires_one_exact_id_and_an_explicit_boolean_false(self):
        for body in ({"ids": ["test-asset"], "force": 0}, {"ids": ["test-asset"], "force": True},
                     {"ids": ["different"], "force": False}, {"ids": ["test-asset"]}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                check_requests([*self.first[:-1], {**self.trash, "body": body}], "test-asset", restart=False)
        with self.assertRaises(ValueError):
            check_requests([*self.first, self.trash], "test-asset", restart=False)

    def test_journal_conversion_preserves_the_seventh_fractional_digit(self):
        self.assertEqual(journal_stamp("2014-02-04T06:08:10.1234567+00:00"), "2014-02-04T06:08:10.1234567+00:00")
        self.assertEqual(journal_stamp("2014-02-04T06:08:10.12+00:00"), "2014-02-04T06:08:10.1200000+00:00")
        with self.assertRaises(ValueError):
            journal_stamp("2014-02-04T06:08:10.12345678+00:00")
