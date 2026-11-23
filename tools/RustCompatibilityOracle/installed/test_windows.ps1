# Portable checks for the release reader and its refusal to remove unowned files.
# The Windows Installer and system-integration calls only run in windows.ps1 on a fresh hosted VM.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'windows.ps1')

function Assert-Refused([scriptblock]$Check, [string]$Message) {
    try { & $Check | Out-Null }
    catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
        return
    }
    throw "Expected refusal containing '$Message'."
}

$area = (New-TemporaryFile).FullName
[IO.File]::Delete($area)
New-FixtureDirectory $area
try {
    if (-not $IsWindows -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted') {
        Assert-Refused { Invoke-InstalledBaseline $area $area $area } 'disposable GitHub-hosted'
    }
    Assert-Refused { New-FixtureDirectory $area } 'existing path'
    $bin = Join-Path $area 'bin'
    $locale = Join-Path $bin 'en-US'
    [void][IO.Directory]::CreateDirectory($locale)
    $dirs = @(
        @{ Directory = 'INSTALLFOLDER'; Parent = 'ProgramFiles64Folder'; Name = 'IFW|Immich Folder Watch' }
        @{ Directory = 'BINDIR'; Parent = 'INSTALLFOLDER'; Name = 'bin' }
        @{ Directory = 'locale'; Parent = 'BINDIR'; Name = 'en-US:source' }
    )
    $components = @(@{ Component = 'root'; Directory = 'BINDIR' }, @{ Component = 'sub'; Directory = 'locale' })
    $files = @(
        @{ File = 'aUpperId'; Component = 'root'; Name = 'short|RootLibrary.dll'; Bytes = 4 }
        @{ File = 'ZLowerId'; Component = 'sub'; Name = 'Nested.dll'; Bytes = 3 }
    )
    $layout = Get-FileLayout $dirs $components $files
    if ($layout.ZLowerId.path -cne [IO.Path]::Combine('en-US', 'Nested.dll')) { throw 'Directory table resolution failed.' }
    $rootFile = Join-Path $bin 'RootLibrary.dll'
    $nestedFile = Join-Path $locale 'Nested.dll'
    [IO.File]::WriteAllText($rootFile, 'ABCD')
    [IO.File]::WriteAllText($nestedFile, 'EFG')
    $expected = @{ files = 2; bytes = 7; digest = '803703f772cd49259ab6920ed57d87cfb494f349c704b6d173aba3acf869c6bd' }
    $receipt = Get-VerifiedPayload $bin $layout $expected
    if ($receipt.entries['aUpperId'].sha256 -cne 'e12e115acf4552b2568b55e93cbd39394c4ef81c82447fafc997882a02d23677') {
        throw 'Payload evidence omitted original bytes.'
    }
    $recordPath = Join-Path $area 'result.json'
    Write-Record $recordPath $receipt
    Assert-Refused { Write-Record $recordPath @{} } 'exist'
    if ((Get-Content -Raw -LiteralPath $recordPath | ConvertFrom-Json).files -ne 2) { throw 'Receipt was overwritten.' }
    [IO.File]::WriteAllText($rootFile, 'ABCE')
    Assert-Refused { Get-VerifiedPayload $bin $layout $expected } 'differ from the original'
    [IO.File]::WriteAllText($rootFile, 'ABCD')
    [IO.File]::Delete($nestedFile)
    Assert-Refused { Get-VerifiedPayload $bin $layout $expected } 'file count'
    [IO.File]::WriteAllText($nestedFile, 'EFG')
    [IO.File]::WriteAllText((Join-Path $bin 'additional'), 'extra')
    Assert-Refused { Get-VerifiedPayload $bin $layout $expected } 'file count'
    $dirs[-1].Parent = 'locale'
    Assert-Refused { Get-FileLayout $dirs $components $files } 'no destination under'
    Assert-Refused { Get-TargetName '..\outside' } 'Unsafe MSI destination'

    $identity = @{ productCode = (Get-ReleasePayload 'x64').productCode; version = '3.0.4'
        manufacturer = 'VoltKraft'; productName = 'Immich Folder Watch' }
    $paths = @{ exe = 'synthetic-executable' }
    $arp = @{ root = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'; productCode = $identity.productCode
        version = $identity.version; displayName = $identity.productName; publisher = $identity.manufacturer; windowsInstaller = 1 }
    $state = [ordered]@{ legacyProgramData = $false; legacyService = $false; staleApplicationSource = $false
        appProcesses = 0; pendingAppOperations = @(); registered = @($arp); relatedProducts = @($identity.productCode)
        installDirectory = $true; userProfile = $true; userMarker = @{ values = @{ DesktopShortcutInstalled = 1 } }
        eventLog = @{ values = @{ MaxSize = 1048576; Retention = 0 } }
        eventSource = @{ values = @{ TypesSupported = 7; EventMessageFile = '%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\EventLogMessages.dll' } }
        desktop = @(@{ exists = $true; target = $paths.exe; arguments = '' }, @{ exists = $false })
        startup = @{ exists = $true; target = $paths.exe; arguments = '--autostart' } }
    Assert-InstalledState $state $paths $identity
    $arp.productCode = (Get-ReleasePayload 'arm64').productCode
    Assert-Refused { Assert-OwnedRegistration $state $identity } 'per-machine ARP'
    $state.pendingAppOperations = @('deferred')
    Assert-Refused { Assert-NoInterference $state } 'pending product operation'
    $log = Join-Path $area 'test-msi.log'
    [IO.File]::WriteAllText($log, "Action start 14:03:15: MigrateLegacyUserConfig.`r`nMSI (s) : Skipping action: RelaunchAppAfterUpgrade (condition is false)")
    $actions = Get-MsiActionStarts $log
    if (-not $actions.migrationActionStarted -or $actions.guiRelaunchActionStarted) { throw 'A skipped relaunch produced an action-start observation.' }
    [IO.File]::AppendAllText($log, "`r`nAction start 14:03:18: RelaunchAppAfterUpgrade.")
    if (-not (Get-MsiActionStarts $log).guiRelaunchActionStarted) { throw 'The GUI relaunch action-start line was missed.' }

    $seed = Join-Path $area 'source'
    $owned = Join-Path $area 'owned'
    New-FixtureDirectory $seed
    New-FixtureDirectory $owned
    [IO.File]::WriteAllText((Join-Path $seed 'config.yaml'), 'synthetic yaml')
    [IO.File]::WriteAllText((Join-Path $seed 'sync-state.db'), 'synthetic data')
    $hashes = Get-ProfileHashes $seed
    Copy-Profile $seed $owned $hashes
    Assert-Refused { Copy-Profile $seed $owned $hashes } 'exist'
    $foreign = Join-Path $owned 'unrecognized'
    [IO.File]::WriteAllText($foreign, 'foreign')
    Assert-Refused { Remove-OwnedProfile $owned $hashes } 'left untouched'
    if ((Get-ChildItem -LiteralPath $owned).Count -ne 3 -or [IO.File]::ReadAllText($foreign) -cne 'foreign') {
        throw 'Unexpected profile contents were modified.'
    }
    [IO.File]::Delete($foreign)
    $db = Join-Path $owned 'sync-state.db'
    [IO.File]::WriteAllText($db, 'modified bytes')
    Assert-Refused { Assert-Profile $owned $hashes } 'original profile bytes changed'
    Assert-Refused { Remove-OwnedProfile $owned $hashes } 'left untouched'
    [IO.File]::Delete($db)
    Remove-OwnedProfile $owned $hashes
    [void](Assert-Profile $seed $hashes)
    if (-not $IsWindows) {
        [void][IO.Directory]::CreateSymbolicLink($owned, $seed)
        Assert-Refused { Remove-OwnedProfile $owned $hashes } 'reparse point'
        [void](Assert-Profile $seed $hashes)
    }
    Write-Host 'MSI payload, profile and cleanup fixtures passed.'
}
finally { [IO.Directory]::Delete($area, $true) }
