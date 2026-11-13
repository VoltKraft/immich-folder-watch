"""Check the source contract for safe, synchronous MSI upgrade preparation."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


INSTALLER = Path(__file__).parents[2] / "packaging/windows/Installer.wxs"
NS = {"w": "http://wixtoolset.org/schemas/v4/wxs", "u": "http://wixtoolset.org/schemas/v4/wxs/util"}


class WindowsInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ET.parse(INSTALLER).getroot()
        self.package = self.root.find("w:Package", NS)
        self.assertIsNotNone(self.package)

    def test_running_process_guard_is_linked_before_any_product_removal(self) -> None:
        # Keeping these in an unreferenced Fragment silently drops them from MSI.
        actions = self.package.findall("w:InstallExecuteSequence/w:Custom", NS)
        by_action = {action.attrib["Action"]: action for action in actions}
        close = by_action["override Wix4CloseApplications_$(sys.BUILDARCHSHORT)"]
        guard = by_action[close.attrib["Before"]]
        self.assertEqual("EnsureAppClosed", guard.attrib["Action"])
        self.assertEqual("InstallValidate", guard.attrib["Before"])
        self.assertEqual("IFW_APP_RUNNING", guard.attrib["Condition"])
        self.assertEqual("VersionNT > 400", close.attrib["Condition"])
        error = self.package.find("w:CustomAction[@Id='EnsureAppClosed']", NS)
        self.assertIsNotNone(error)
        self.assertTrue(error.attrib["Error"])
        self.assertNotIn("Return", error.attrib)

    def test_early_close_never_requests_deferred_work(self) -> None:
        close = self.package.find("u:CloseApplication", NS)
        self.assertIsNotNone(close)
        self.assertEqual("ImmichFolderWatch.exe", close.attrib["Target"])
        self.assertEqual("IFW_APP_RUNNING", close.attrib["Property"])
        self.assertEqual("yes", close.attrib["CloseMessage"])
        self.assertEqual("yes", close.attrib["EndSessionMessage"])
        self.assertGreaterEqual(int(close.attrib["Timeout"]), 5)
        self.assertEqual("no", close.attrib["PromptToContinue"])
        self.assertEqual("no", close.attrib["RebootPrompt"])
        self.assertNotIn("TerminateProcess", close.attrib)
        for flag in ("ElevatedCloseMessage", "ElevatedEndSessionMessage"):
            self.assertNotEqual("yes", close.attrib.get(flag, "no"))
        # No other CloseApplication row may cause this early util action to
        # schedule a deferred operation before InstallInitialize.
        self.assertEqual(1, len(self.root.findall(".//u:CloseApplication", NS)))

    def test_old_product_removal_is_inside_rollback_transaction(self) -> None:
        upgrade = self.package.find("w:MajorUpgrade", NS)
        self.assertIsNotNone(upgrade)
        self.assertEqual("afterInstallInitialize", upgrade.attrib["Schedule"])
        self.assertNotEqual("yes", upgrade.attrib.get("IgnoreRemoveFailure", "no"))
        self.assertNotEqual("yes", upgrade.attrib.get("AllowDowngrades", "no"))


if __name__ == "__main__":
    unittest.main()
