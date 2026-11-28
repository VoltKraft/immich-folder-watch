"""Check the private post-commit inventory and its detached interpretation."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import replay


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODERN = (HERE / 'admin.ps1').read_bytes()


class InventoryTests(unittest.TestCase):
    def test_success_requires_distinct_path_and_complete_process_observations(self):
        class Archive:
            def read(self, key):
                return json.dumps(self.files[key]).encode()

        z = Archive()
        z.files = {'committed.json': {'phase': 'committed', 'product': replay.SUCCESSOR, 'shortcuts': [], 'runningWpf': 0}}
        snapshot = {'oldLaunchWin32Error': 2, 'preflight': 21}
        self.assertEqual(replay.post_commit(z, snapshot, b'')['processObserver'], 'Get-Process and Toolhelp')
        with self.assertRaises(ValueError):
            replay.post_commit(z, snapshot, MODERN)
        clear = dict(image=replay.STOCK_EXE, pathStatus='absent', pathError=None,
                     processStatus='enumerated', processError=None, processes=[])
        z.files[replay.INVENTORY] = clear
        self.assertEqual(replay.post_commit(z, snapshot, MODERN)['processObserver'], 'Win32_Process and Toolhelp')
        for changed in (dict(pathStatus='indeterminate'), dict(pathStatus='present'), dict(processStatus='indeterminate'),
                        dict(processes=None), dict(processes=[dict(pid=61, session=2, image='installed-path')])):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                z.files[replay.INVENTORY] = {**clear, **changed}
                replay.post_commit(z, snapshot, MODERN)

    def test_powershell_distinguishes_missing_files_and_failed_or_occupied_snapshots(self):
        pwsh = shutil.which('pwsh') or ROOT / 'artifacts/rust/qa-powershell/7.7.0/pwsh'
        if not Path(pwsh).is_file():
            self.skipTest('PowerShell is required for the filesystem and simulated CIM checks')
        program = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$tree = [Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path './admin.ps1'), [ref]$null, [ref]$null)
$function = $tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
                                       $node.Name -ceq 'Read-StockInventory'}, $true)
. ([scriptblock]::Create($function.Extent.Text))
function Get-CimInstance($ClassName, $Filter, $Property, $ErrorAction) {
    if ($ClassName -cne 'Win32_Process' -or $Filter -cne "Name = 'ImmichFolderWatch.exe'" -or
        $ErrorAction -ne 'Stop' -or ($Property -join ',') -cne 'Name,ProcessId,SessionId,ExecutablePath') {
        throw 'Unexpected CIM query'
    }
    if ($script:sample -eq 'failed') { throw 'Simulated provider failure' }
    if ($script:sample -eq 'occupied') {
        $pidValue = 60
        foreach ($image in @($script:original, $null, 'other.exe')) {
            [pscustomobject]@{Name='ImmichFolderWatch.exe'; ProcessId=++$pidValue; SessionId=2; ExecutablePath=$image}
        }
    }
}
$original = (Resolve-Path './admin.ps1').Path
$missing = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
$sample = 'empty'
$empty = Read-StockInventory $missing
$sample = 'occupied'
$occupied = Read-StockInventory $original
$sample = 'failed'
$failed = Read-StockInventory $missing
$sample = 'empty'
$badPath = Read-StockInventory ("invalid" + [char]0)
@($empty, $occupied, $failed, $badPath) | ConvertTo-Json -Depth 5
"""
        empty, occupied, failed, bad_path = json.loads(subprocess.check_output(
            [pwsh, '-NoProfile', '-NonInteractive', '-Command', program], cwd=HERE))
        self.assertEqual((empty['pathStatus'], empty['processStatus'], empty['processes']), ('absent', 'enumerated', []))
        self.assertEqual(occupied['pathStatus'], 'present')
        self.assertEqual(occupied['processes'], [dict(pid=i, session=2, image=v) for i, v in
                                                 enumerate(['installed-path', 'unavailable', 'other-path'], 61)])
        self.assertEqual((failed['pathStatus'], failed['processStatus'], failed['processes']),
                         ('absent', 'indeterminate', None))
        self.assertTrue(failed['processError'])
        self.assertEqual((bad_path['pathStatus'], bad_path['processStatus'], bad_path['processes']),
                         ('indeterminate', 'enumerated', []))
        self.assertTrue(bad_path['pathError'])


if __name__ == '__main__':
    unittest.main()
