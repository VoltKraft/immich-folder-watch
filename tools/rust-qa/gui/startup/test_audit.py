"""Check that unrelated package changes cannot pass as the composed GUI lock update."""
import unittest

from full_audit import verify_diff


def report(lock):
    return {"target": "aarch64-pc-windows-msvc", "lockSha256": lock,
            "packages": [{"name": "renderer", "version": "1", "features": [], "featureSets": [[]],
                          "notices": {"LICENSE": "original"}}], "excludedPackagesOrFeatures": []}


class StartupReportTests(unittest.TestCase):
    def test_ordinary_windows_lock_change_accepts_identical_complete_rows(self):
        self.assertEqual(verify_diff(report("original"), report("staged"))["changedFeatureRows"], [])

    def test_windows_rejects_a_different_feature_set_or_notice(self):
        for delta in ({"featureSets": [["default"]]}, {"notices": {"LICENSE": "changed"}}):
            with self.subTest(delta=delta):
                candidate = report("staged")
                candidate["packages"][0].update(delta)
                with self.assertRaises(ValueError):
                    verify_diff(report("original"), candidate)


if __name__ == "__main__":
    unittest.main()
