"""Exercise the same action-order checks used on compiled release MSIs."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging/windows/Test-InstallerUpgradeContract.ps1"
PWSH = os.environ.get("IFW_TEST_PWSH") or shutil.which("pwsh")

FIXTURE = r'''
$actions = @{
    Wix4CloseApplications_X64 = @{ Sequence = 1398; Condition = 'VersionNT > 400' }
    EnsureAppClosed = @{ Sequence = 1399; Condition = 'IFW_APP_RUNNING' }
    InstallValidate = @{ Sequence = 1400 }
    InstallInitialize = @{ Sequence = 1500 }
    RemoveExistingProducts = @{ Sequence = 1501 }
    RemoveFiles = @{ Sequence = 3500 }
}
$custom = @{
    Wix4CloseApplications_X64 = @{ Type = 1 }
    EnsureAppClosed = @{ Type = 19 }
}
$close = @{
    Target = 'ImmichFolderWatch.exe'
    Property = 'IFW_APP_RUNNING'
    Condition = ''
    Attributes = 9
    Timeout = 15000
}
'''


@unittest.skipUnless(PWSH, "PowerShell is required to execute the MSI contract validator")
class MsiUpgradeContractTests(unittest.TestCase):
    def check(self, mutation: str = "", *, succeeds: bool) -> None:
        source = ". '" + str(SCRIPT).replace("'", "''") + "'\n" + FIXTURE
        source += mutation + "\n" + r'''
try {
    Test-UpgradeSequence -Actions $actions -CustomActions $custom -CloseApplication $close
    Write-Output 'CONTRACT_ACCEPTED'
}
catch {
    Write-Output ('CONTRACT_REJECTED: ' + $_.Exception.Message)
    exit 23
}
'''
        result = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-Command", source],
            capture_output=True, text=True, check=False,
        )
        if succeeds:
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("CONTRACT_ACCEPTED", result.stdout)
        else:
            self.assertEqual(23, result.returncode, result.stdout + result.stderr)
            self.assertIn("CONTRACT_REJECTED:", result.stdout)

    def test_accepts_transactional_upgrade_after_process_check(self):
        self.check(succeeds=True)

    def test_accepts_native_arm64_action(self):
        self.check(
            "$actions.Wix4CloseApplications_A64 = $actions.Wix4CloseApplications_X64; "
            "$actions.Remove('Wix4CloseApplications_X64'); "
            "$custom.Wix4CloseApplications_A64 = $custom.Wix4CloseApplications_X64; "
            "$custom.Remove('Wix4CloseApplications_X64')",
            succeeds=True,
        )

    def test_rejects_released_303_order(self):
        self.check(
            "$actions.Wix4CloseApplications_X64.Sequence = 3999; "
            "$actions.RemoveExistingProducts.Sequence = 1401",
            succeeds=False,
        )

    def test_rejects_missing_unlinked_guard(self):
        self.check("$actions.Remove('EnsureAppClosed')", succeeds=False)

    def test_rejects_guard_with_wrong_property_or_type(self):
        for mutation in (
            "$actions.EnsureAppClosed.Condition = 'OTHER_PROPERTY'",
            "$custom.EnsureAppClosed.Type = 1",
            "$custom.Remove('EnsureAppClosed')",
        ):
            with self.subTest(mutation=mutation):
                self.check(mutation, succeeds=False)

    def test_rejects_nontransactional_or_late_removal(self):
        for sequence in (1401, 3501):
            with self.subTest(sequence=sequence):
                self.check(f"$actions.RemoveExistingProducts.Sequence = {sequence}", succeeds=False)

    def test_rejects_unsafe_close_configuration(self):
        for mutation in (
            "$close.Attributes = 41",  # Termination runs in a deferred action.
            "$close.Attributes = 13",  # Elevated close is also deferred.
            "$close.Property = ''",
            "$close.Target = 'AnotherApp.exe'",
            "$close.Condition = 'NOT Installed'",
            "$actions.Wix4CloseApplications_X64.Condition = 'NOT Installed'",
            "$custom.Wix4CloseApplications_X64.Type = 1025",
            "$custom.Wix4CloseApplications_X64.Type = 129",
            "$close.Timeout = 1000",
        ):
            with self.subTest(mutation=mutation):
                self.check(mutation, succeeds=False)


@unittest.skipUnless(PWSH, "PowerShell is required to execute the MSI identity validator")
class MsiIdentityTests(unittest.TestCase):
    def check(self, platform="x64", version="3.0.4", template="x64;1033",
              actual_version="3.0.4", action_suffix="X64", *, succeeds=True):
        source = ". '" + str(SCRIPT).replace("'", "''") + "'\n"
        source += f"$actions = @{{ Wix4CloseApplications_{action_suffix} = @{{ Sequence = 1398 }} }}\n"
        source += f"""
try {{
    Test-InstallerIdentity -Template '{template}' -ProductVersion '{actual_version}' -Actions $actions `
        -ExpectedPlatform '{platform}' -ExpectedVersion '{version}'
    Write-Output 'IDENTITY_ACCEPTED'
}}
catch {{
    Write-Output ('IDENTITY_REJECTED: ' + $_.Exception.Message)
    exit 23
}}
"""
        result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", source],
                                capture_output=True, text=True, check=False)
        self.assertEqual(0 if succeeds else 23, result.returncode, result.stdout + result.stderr)
        self.assertIn("IDENTITY_ACCEPTED" if succeeds else "IDENTITY_REJECTED:", result.stdout)

    def test_accepts_expected_x64_identity(self):
        self.check()

    def test_accepts_expected_arm64_identity(self):
        self.check(platform="arm64", template="Arm64;1033", action_suffix="A64")

    def test_rejects_x64_msi_mislabeled_as_arm64(self):
        self.check(platform="arm64", succeeds=False)

    def test_rejects_previous_product_version(self):
        self.check(actual_version="3.0.3", succeeds=False)

    def test_rejects_wrong_native_action_architecture(self):
        self.check(action_suffix="A64", succeeds=False)

    def test_rejects_itanium_template_for_x64(self):
        self.check(template="Intel64;1033", succeeds=False)


if __name__ == "__main__":
    unittest.main()
