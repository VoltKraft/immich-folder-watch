# Portable tests for the additional synthetic-profile and MSI removal boundaries.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'install.ps1')

function Assert-Refused([scriptblock]$Call, [string]$Reason) {
    try { & $Call }
    catch {
        if ($_.Exception.Message -notlike "*$Reason*") { throw }
        return
    }
    throw "Expected refusal containing '$Reason'."
}

if (-not $IsWindows -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted') {
    Assert-Refused { Invoke-MsiInterop '' '' '' '' '' '' '' '' } 'disposable GitHub-hosted'
}
$area = [IO.Directory]::CreateTempSubdirectory('ifw-msi-controls-').FullName
try {
    $work = Join-Path $area 'work'
    $profileDir = Join-Path $area 'synthetic profile'
    $media = Join-Path $work "photo's"
    foreach ($p in @($work, $profileDir, $media)) { New-FixtureDirectory $p }
    $token = '0123456789abcdef0123456789abcdef'
    $markerPath = Join-Path $profileDir ".rw02-owned-$token"
    $config = Join-Path $profileDir 'config.yaml'
    [IO.File]::WriteAllText($markerPath, $token)
    $valid = @"
immich:
  serverApiUrl: "http://127.0.0.1:32159/api"
  apiKey: "synthetic-benchmark"
  allowInsecureHttp: true
watch:
  sources:
    - path: '$($media.Replace("'", "''"))'
      syncMode: uploadNew
      includeSubdirectories: true
      deleteAfterUpload: false
      extensions: [".jpg"]
logging:
  target: file
  level: Information
  logDirectory: engine-logs
"@
    $valid = $valid.Replace("`r`n", "`n") + "`n"
    function Test-CurrentProfile {
        Assert-InteropProfile $profileDir $profileDir $markerPath (Get-FileDigest $config) $work
    }
    foreach ($content in @($valid, $valid.Replace("`n", "`r`n"))) {
        [IO.File]::WriteAllText($config, $content)
        Test-CurrentProfile
    }
    foreach ($content in @($valid.Replace('127.0.0.1', '192.0.2.5'), $valid.Replace('32159','65536'),
                           $valid.Replace('false','true'), ($valid + "unexpected: field`n"))) {
        [IO.File]::WriteAllText($config, $content)
        Assert-Refused { Test-CurrentProfile } 'loopback-only synthetic WPF config'
    }
    [IO.File]::WriteAllText($config, $valid.Replace($media.Replace("'", "''"), $profileDir))
    Assert-Refused { Test-CurrentProfile } 'strictly beneath'
    [IO.File]::WriteAllText($config, $valid)
    Assert-Refused { Assert-ChildDirectory $work ($work + [IO.Path]::DirectorySeparatorChar) } 'strictly beneath'
    Assert-Refused { Assert-InteropProfile $area $profileDir $markerPath (Get-FileDigest $config) $work } 'ownership marker'
    Assert-Refused { Assert-InteropProfile $profileDir $profileDir $markerPath ('0' * 64) $work } 'config digest'
    [IO.File]::WriteAllText($markerPath, ('f' * 32))
    Assert-Refused { Test-CurrentProfile } 'exact synthetic profile'
    [IO.File]::WriteAllText($markerPath, $token)
    $unknown = Join-Path $profileDir 'untouched'
    [IO.File]::WriteAllText($unknown, 'foreign')
    Assert-Refused { Test-CurrentProfile } 'exact synthetic profile'
    if ([IO.File]::ReadAllText($unknown) -cne 'foreign') { throw 'Refused profile was modified.' }
}
finally { [IO.Directory]::Delete($area, $true) }

function New-State {
    return @{
        registered = @(); relatedProducts = @(); installDirectory = $false; userProfile = $true
        legacyProgramData = $false; legacyService = $false; staleApplicationSource = $false
        appProcesses = 0; pendingAppOperations = @(); startup = @{ exists = $false }; desktop = @()
        eventLog = @{ exists = $false; values = @{} }; eventSource = @{ exists = $false; values = @{} }
        userMarker = @{ exists = $false; values = @{} }
    }
}

$identity = @{ productCode = '{50554B02-DB63-4388-A959-8F0B25856F5A}'; version = '3.0.4'
    packageCode = '{19DC3747-2CBD-4D6A-9960-AB0AA4B65947}'; productName = 'Immich Folder Watch'; manufacturer = 'VoltKraft' }
$owned = New-State
$owned.registered = @(@{ productCode = $identity.productCode; displayName = $identity.productName; publisher = 'VoltKraft'
    version = '3.0.4'; windowsInstaller = 1; root = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' })
$owned.relatedProducts = @($identity.productCode)
$owned.installDirectory = $true
Assert-Refused { Assert-VacantHost $owned } 'unrelated product'
foreach ($name in @('legacyService', 'legacyProgramData', 'staleApplicationSource', 'appProcesses')) {
    $before = New-State
    $before[$name] = 1
    Assert-Refused { Assert-VacantHost $before } 'legacy directory/service/source'
}
foreach ($name in @('eventSource', 'userMarker', 'eventLog', 'startup')) {
    $before = New-State
    $before[$name].exists = $true
    Assert-Refused { Assert-VacantHost $before } 'unrelated product'
}

# Substitute the machine state and msiexec boundary only. Use the shipping ownership and teardown checks.
function Get-HostState($Paths, $Identity) { return $script:states.Dequeue() }
function Get-InstalledPackageCode($Identity) {
    if ($script:otherPackage) { throw 'The registered Windows Installer package code differs.' }
    return $Identity.packageCode
}
function Invoke-ReleaseMsi($Switch, $Subject, $LogPath, $Operations, $Identity) {
    if ($Switch -cne '/x' -or $Subject -cne $Identity.productCode -or [IO.Path]::GetFileName($LogPath) -cne 'uninstall.log') {
        throw 'Incorrect uninstall target.'
    }
    $script:uninstalls++
}
function New-Removal($Before, $After) {
    $script:states = [Collections.Generic.Queue[object]]::new()
    $script:states.Enqueue($Before)
    $script:states.Enqueue($After)
    $script:uninstalls = 0
    $script:otherPackage = $false
    return @{ operations = @(@{ timedOut = $false }); checkpoints = @{}; cleanup = @{} }
}
$clean = New-State
$record = New-Removal $owned $clean
Complete-InteropRemoval @{} $identity 'evidence' $record
if ($uninstalls -ne 1 -or -not $record.cleanup.msiRemoved -or $record.cleanup.packageCode -cne $identity.packageCode) {
    throw 'A verified installation must be removed exactly once.'
}
$record = New-Removal $clean $clean
Complete-InteropRemoval @{} $identity 'evidence' $record
if ($uninstalls -ne 0 -or -not $record.cleanup.msiRemoved) { throw 'Failed installation without registration attempted an uninstall.' }
$record = New-Removal $clean $clean
$record.checkpoints.installed = $owned
Assert-Refused { Complete-InteropRemoval @{} $identity 'evidence' $record } 'disappeared'
$record = New-Removal $owned $clean
$record.operations[0].timedOut = $true
Assert-Refused { Complete-InteropRemoval @{} $identity 'evidence' $record } 'timed out'
if ($uninstalls -or $states.Count -ne 2) { throw 'Timed-out transaction touched the machine.' }
$record = New-Removal $owned $clean
$script:otherPackage = $true
Assert-Refused { Complete-InteropRemoval @{} $identity 'evidence' $record } 'package code differs'
if ($uninstalls) { throw 'Unverified package was removed.' }
$foreign = New-State
$foreign.relatedProducts = @('{00000000-0000-0000-0000-000000000000}')
$record = New-Removal $foreign $clean
Assert-Refused { Complete-InteropRemoval @{} $identity 'evidence' $record } 'sole registered related product'
if ($uninstalls) { throw 'Unrelated registration was removed.' }
$foreign = New-State
$foreign.eventSource.exists = $true
$record = New-Removal $owned $foreign
Assert-Refused { Complete-InteropRemoval @{} $identity 'evidence' $record } 'unrelated product'
if ($record.cleanup.Contains('msiRemoved')) { throw 'Residual registration was accepted.' }
Write-Host 'Installed WPF observer profile, vacant machine and owned MSI teardown controls passed.'
