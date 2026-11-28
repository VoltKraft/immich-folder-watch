"""Keep local and hosted physical notification receipts distinct during offline replay."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from activation import TARGET
from toast_console import CleanupUnconfirmed, armed_screen, check_venue, corroborates_labels


class PhysicalVenueTests(unittest.TestCase):
    def test_clean_observer_start_failure_preserves_original_sender_once(self):
        child = MagicMock()
        child.__enter__.side_effect = OSError("could not start observer")
        with TemporaryDirectory() as folder:
            receipt, sends = {}, []
            with armed_screen(child, Path(folder), receipt):
                sends.append("original")
            self.assertEqual(sends, ["original"])
            self.assertFalse(receipt["armedBeforeSender"])
            self.assertTrue((Path(folder) / "physical.json").is_file())
            with self.assertRaises(OSError), armed_screen(child, Path(folder), {"pid": 7}):
                self.fail("The child did not drain")
            child.__enter__.side_effect = CleanupUnconfirmed("cannot confirm cleanup")
            with self.assertRaises(CleanupUnconfirmed), armed_screen(child, Path(folder), {}):
                self.fail("Unconfirmed observer cleanup cannot start a sender")

    def test_original_local_observer_has_no_hosted_run(self):
        sender = {"host": "isolated-vm", "target": TARGET["X64"][0]}
        check_venue(sender, {})
        check_venue(sender, {"target": sender["target"]})
        for mismatch in ({"host": "github-hosted"}, {"target": TARGET["ARM64"][0]}):
            with self.subTest(mismatch=mismatch), self.assertRaises(ValueError):
                check_venue(sender, mismatch)

    def test_arm64_pairs_only_the_same_compiler_run_attempt_and_observer(self):
        identity = dict(target=TARGET["ARM64"][0], head="test-revision", run="test-run", attempt="test-attempt")
        sender = {**identity, "observerInputs": {"tools/rust-qa/windows-services/toast_console.ps1": "script-digest"}}
        screen = {**identity, "host": "github-hosted", "scriptSha256": "script-digest"}
        check_venue(sender, screen)
        for key in screen:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_venue(sender, {**screen, key: "different"})

    def test_capture_needs_visual_review_when_point_provider_did_not_identify_both_labels(self):
        host = dict(hwnd=2, pid=3, session=1)
        title, body = {"runtimeId": "title"}, {"runtimeId": "body"}
        crop = {**host, "labels": [title, body]}
        match = dict(host=host, title=title, body=body)
        self.assertTrue(corroborates_labels(dict(status="visible", presentation={"match": match}), crop))
        self.assertFalse(corroborates_labels(dict(status="unavailable"), crop))
        changed = {**match, "body": {"runtimeId": "covering-element"}}
        self.assertFalse(corroborates_labels(dict(status="visible", presentation={"match": changed}), crop))
