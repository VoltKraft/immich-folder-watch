$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../install.ps1')
. (Join-Path $PSScriptRoot 'profile.ps1')
$root = [IO.Directory]::CreateTempSubdirectory('ifw-reverse-profile-').FullName
try {
    $profileRoot = Join-Path $root 'owned'
    $out = Join-Path $root 'out'
    $copy = Join-Path $out 'wpf-profile'
    foreach ($p in @($profileRoot, $out, $copy)) { New-FixtureDirectory $p }
    $files = @{}
    foreach ($p in @($profileRoot,$copy)) {
        $logs = Join-Path $p 'engine-logs'
        New-FixtureDirectory $logs
        [IO.File]::WriteAllText((Join-Path $logs 'immich-folder-watch-20261126.log'), 'synthetic log')
        [IO.File]::WriteAllText((Join-Path $p 'sync-state.db'), 'synthetic database')
    }
    foreach ($n in @('sync-state.db','engine-logs/immich-folder-watch-20261126.log')) {
        $files[$n] = Get-FileDigest (Join-Path $copy $n)
    }
    Write-Record (Join-Path $out 'reverse-activation.json') @{status='observed';quit=@{empty=$true};profileFiles=$files}
    $names = @(Get-ReverseProfileEntries $profileRoot $out)
    if ($names.Count -ne 2 -or $names -cnotcontains 'sync-state.db' -or $names -cnotcontains 'engine-logs') {
        throw 'Expected only the authored output entries.'
    }
    [IO.File]::WriteAllText((Join-Path $copy 'sync-state.db'), 'changed')
    try { Get-ReverseProfileEntries $profileRoot $out; throw 'Accepted different preserved data' }
    catch { if ($_.Exception.Message -notlike '*observer digest differ*') { throw } }
    $foreign = Join-Path $profileRoot 'unrecognized-directory'
    New-FixtureDirectory $foreign
    try { Get-ReverseProfileEntries $profileRoot $out; throw 'Accepted unrelated directory' }
    catch { if ($_.Exception.Message -notlike '*Unexpected WPF profile directory*') { throw } }
    if (-not [IO.Directory]::Exists($foreign)) { throw 'The profile guard changed unrelated input.' }
    Write-Host 'WPF primary profile capture and refusal controls passed.'
}
finally { [IO.Directory]::Delete($root,$true) }
