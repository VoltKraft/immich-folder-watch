# Deterministic controls for cleanup of the test's Explorer flyout.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tray-overflow.ps1')

$script:owner = 71
$script:visible = $false
$script:calls = 0
function Get-IfwShellOwner([IntPtr]$Window) { return $script:owner }
function Get-IfwOverflowWindow([uint32]$ExplorerId) {
    if ($script:visible) { return [IntPtr]91 }
    return [IntPtr]::Zero
}
$provider = [pscustomobject]@{}
$provider | Add-Member ScriptMethod Invoke { $script:calls++; $script:visible = -not $script:visible }
$state = @{ bar = [IntPtr]31; explorer = 71; button = @{ Current = @{ ProcessId = 71 } }
           action = @{ method = 'Invoke'; provider = $provider } }

$record = @{}
Restore-IfwTrayOverflow $null $record
if ($script:calls -or $record.Count) { throw 'A pre-existing tray flyout was changed' }
Restore-IfwTrayOverflow $state $record
if ($script:calls -or $record.overflowClosed -ne $true) { throw 'A closed flyout was opened by cleanup' }
$script:visible = $true
Restore-IfwTrayOverflow $state $record
if ($script:calls -ne 1 -or $script:visible -or $record.overflowClosed -ne $true) { throw 'The open flyout remained visible' }
$script:visible = $true
$script:owner = 72
$rejected = $false
try { Restore-IfwTrayOverflow $state $record }
catch { $rejected = $_.Exception.Message -eq 'Explorer changed while observing the temporary flyout' }
if (-not $rejected -or $script:calls -ne 1 -or -not $script:visible) { throw 'The observer acted on a different shell' }
$script:owner = 71
$rejected = $false
try { Restore-IfwTrayOverflow $state @{} { param($bar, $pidValue) return $false } }
catch { $rejected = $true }
if (-not $rejected -or $script:calls -ne 1 -or -not $script:visible) { throw 'A lost private desktop changed the flyout' }
$script:checks = 0
$rejected = $false
try {
    Restore-IfwTrayOverflow $state @{} {
        param($bar, $pidValue)
        $script:checks++
        return $script:checks -eq 1
    }
} catch { $rejected = $true }
if (-not $rejected -or $script:calls -ne 2) { throw 'A changed desktop certified a flyout closure' }
Write-Output 'Six tray cleanup controls passed'
