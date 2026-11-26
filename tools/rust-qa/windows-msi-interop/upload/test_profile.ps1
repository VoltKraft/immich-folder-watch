# Check only the dedicated PNG profile and the existing closed-proxy default.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../install.ps1')
. (Join-Path $PSScriptRoot '../reverse/profile.ps1')
$area = [IO.Directory]::CreateTempSubdirectory('ifw-msi-profile-').FullName
try {
    $dir = Join-Path $area 'profile'
    $media = Join-Path $area 'wpf-media'
    New-FixtureDirectory $dir
    New-FixtureDirectory $media
    $token = [Guid]::NewGuid().ToString('n')
    $marker = Join-Path $dir ('.rw02-owned-' + $token)
    [IO.File]::WriteAllText($marker, $token)
    $file = Join-Path $dir 'config.yaml'
    $config = @"
immich:
  serverApiUrl: "http://127.0.0.1:32023/api"
  apiKey: "synthetic-installed-upload"
  allowInsecureHttp: true
watch:
  sources:
    - path: '$($media.Replace("'", "''"))'
      syncMode: uploadAll
      includeSubdirectories: true
      deleteAfterUpload: false
      extensions: [".png"]
logging:
  target: file
  level: Information
  logDirectory: engine-logs
"@
    function Test-Expected([string]$Text, [bool]$Enable, [bool]$Pass) {
        [IO.File]::WriteAllText($file, $Text + "`n")
        try { Assert-InteropProfile $dir $dir $marker (Get-FileDigest $file) $area -Upload:$Enable }
        catch { if ($Pass) { throw }; return }
        if (-not $Pass) { throw 'Accepted an unexpected upload configuration.' }
    }
    Test-Expected $config $true $true
    Test-Expected $config $false $false
    Test-Expected ($config.Replace('127.0.0.1','192.0.2.9')) $true $false
    Test-Expected ($config.Replace('wpf-media','profile')) $true $false
    Test-Expected ($config.Replace('.png','.jpg')) $true $false
    Test-Expected ($config.Replace('synthetic-installed-upload','synthetic-benchmark')) $true $false
    $archive = Join-Path $area 'evidence'
    $retained = Join-Path $archive 'wpf-profile'
    New-FixtureDirectory $archive
    New-FixtureDirectory $retained
    [IO.File]::WriteAllText((Join-Path $dir 'sync-state.db'), 'owned fixture')
    Copy-Item -LiteralPath (Join-Path $dir 'sync-state.db') -Destination $retained
    $hash = Get-FileDigest (Join-Path $dir 'sync-state.db')
    Write-Record (Join-Path $archive 'upload-observation.json') @{
        status='observed';restored=@{quit=@{empty=$true}};profileFiles=@{'sync-state.db'=$hash}
    }
    $outputs = @(Get-ReverseProfileEntries $dir $archive -Upload)
    if ($outputs.Count -ne 1 -or $outputs[0] -cne 'sync-state.db') { throw 'Expected the final observed database.' }
    [IO.File]::WriteAllText((Join-Path $retained 'sync-state.db'), 'different')
    try { Get-ReverseProfileEntries $dir $archive -Upload; throw 'Accepted a changed final database.' }
    catch { if ($_.Exception.Message -notlike '*observer digest differ*') { throw } }
}
finally { [IO.Directory]::Delete($area, $true) }
Write-Output 'Dedicated installed PNG profile controls passed.'
