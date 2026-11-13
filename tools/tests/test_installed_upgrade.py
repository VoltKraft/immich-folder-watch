"""Exercise the strict evidence gate for a safely refused installed upgrade."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "packaging/windows/Test-InstalledUpgrade.ps1").read_text()
PWSH = os.environ.get("IFW_TEST_PWSH") or shutil.which("pwsh")
FUNCTION = SOURCE.split("function Assert-SafeRunningRefusal {", 1)[1].split(
    "function Close-TestApplicationGracefully", 1
)[0]
VALID_LOG = """Action start 18:39:48: EnsureAppClosed.
Action ended 18:39:48: EnsureAppClosed. Return value 3.
Property(S): IFW_APP_RUNNING = 1
"""


@unittest.skipUnless(PWSH, "PowerShell is required")
class InstalledUpgradeRefusalTests(unittest.TestCase):
    def check(self, log=VALID_LOG, mutation="", accepted=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "running-app-upgrade.log").write_text(log)
            (root / "config.yaml").write_text("synthetic config")
            (root / "sentinel.txt").write_text("synthetic sentinel")
            script = root / "test.ps1"
            script.write_text(
                "$ErrorActionPreference='Stop'\nSet-StrictMode -Version Latest\n"
                "function Assert-SafeRunningRefusal {" + FUNCTION + "\n"
                + r'''
$EvidenceDirectory=$PSScriptRoot
$configPath=Join-Path $PSScriptRoot 'config.yaml'
$sentinelPath=Join-Path $PSScriptRoot 'sentinel.txt'
$configHash=(Get-FileHash $configPath).Hash
$sentinelHash=(Get-FileHash $sentinelPath).Hash
$baseline=[ordered]@{'hostfxr.dll'='A';'coreclr.dll'='B'}
$script:after=[ordered]@{'hostfxr.dll'='A';'coreclr.dll'='B'}
$script:products=@([pscustomobject]@{ProductCode='{BASE}';Version='3.0.3'})
$script:pending=@()
function Get-InstalledSnapshot { return $script:after }
function Get-InstalledProducts { return $script:products }
function Get-PendingAppOperations { return $script:pending }
$process=Get-Process -Id $PID
'''
                + mutation + "\n"
                + r'''
try {
    Assert-SafeRunningRefusal $baseline '{BASE}' $configHash $sentinelHash $process
    Write-Output 'REFUSAL_VERIFIED'
}
catch {
    Write-Output ('REFUSAL_REJECTED: ' + $_.Exception.Message)
    exit 23
}
'''
            )
            result = subprocess.run(
                [PWSH, "-NoProfile", "-File", str(script)], text=True,
                capture_output=True, timeout=30,
            )
            self.assertEqual(0 if accepted else 23, result.returncode, result.stderr)
            self.assertIn("REFUSAL_VERIFIED" if accepted else "REFUSAL_REJECTED:", result.stdout)

    def test_accepts_guard_failure_only_when_baseline_is_unchanged(self):
        self.check(accepted=True)

    def test_rejects_generic_failure_or_missing_running_property(self):
        for log in ("MainEngineThread is returning 1603", VALID_LOG.replace("value 3", "value 2"),
                    VALID_LOG.replace("Property(S): IFW_APP_RUNNING = 1", "")):
            with self.subTest(log=log):
                self.check(log=log)

    def test_rejects_install_or_removal_that_started_before_failure(self):
        for action in ("InstallValidate", "InstallInitialize", "RemoveExistingProducts", "RemoveFiles", "InstallFiles"):
            for prefix in (f"MSI (s): Doing action: {action}\n", f"Action start 18:39:40: {action}.\n"):
                with self.subTest(action=action, prefix=prefix):
                    self.check(log=prefix + VALID_LOG)

    def test_rejects_changes_to_payload_registration_user_data_or_pending_operations(self):
        mutations = (
            "$script:after['hostfxr.dll']='CHANGED'",
            "$script:after.Remove('hostfxr.dll')",
            "$script:after['unexpected.dll']='NEW'",
            "$script:products[0].Version='3.0.4'",
            "$script:products[0].ProductCode='{NEW}'",
            "Set-Content $configPath 'changed config'",
            "Set-Content $sentinelPath 'changed sentinel'",
            "$script:pending=@('deferred deletion')",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.check(mutation=mutation)

    def test_native_tray_quit_helper_compiles(self):
        csharp = SOURCE.split("Add-Type -TypeDefinition @'", 1)[1].split("'@", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "compile.ps1"
            (Path(directory) / "harness.ps1").write_text(SOURCE)
            ui_script = SOURCE.split('$uiScript = Join-Path', 1)[1].split("    @'\n", 1)[1].split("'@ | Set-Content", 1)[0]
            (Path(directory) / "ui-helper.ps1").write_text(ui_script)
            script.write_text(
                "$ErrorActionPreference='Stop'\nAdd-Type -TypeDefinition @'" + csharp + "'@\n"
                + r'''
foreach ($name in @('harness.ps1', 'ui-helper.ps1')) {
    $tokens=$null
    $errors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw ($errors | Out-String) }
}
'COMPILED'
'''
            )
            result = subprocess.run([PWSH, "-NoProfile", "-File", str(script)], text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("COMPILED", result.stdout)


if __name__ == "__main__":
    unittest.main()
