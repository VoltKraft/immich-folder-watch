"""Keep local and hosted physical notification receipts distinct during offline replay."""

import unittest

from activation import TARGET
from toast_console import check_venue


class PhysicalVenueTests(unittest.TestCase):
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
