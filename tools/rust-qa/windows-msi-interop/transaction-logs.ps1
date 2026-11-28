# Replay the original Windows Installer logs without reading host registration or running msiexec.
param([Parameter(Mandatory)][string]$Directory, [switch]$InstallOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../../RustCompatibilityOracle/installed/windows.ps1')

$request = [Console]::In.ReadToEnd() | ConvertFrom-Json -AsHashtable
$identity = $request.identity
$expected = Get-ReleasePayload $request.arch
if ($identity.packageCode -ine $expected.packageCode -or $identity.productCode -ine $expected.productCode -or
    $identity.template -ine "$($request.arch);1033" -or $identity.upgradeCode -ine '{F82E51D6-6D61-4A5D-B8AA-9D84A5D0D57D}' -or
    $identity.version -cne '3.0.4' -or $identity.productName -cne 'Immich Folder Watch' -or
    $identity.manufacturer -cne 'VoltKraft' -or $identity.allUsers -cne '1') {
    throw 'The archived identity differs from the original 3.0.4 MSI for this architecture.'
}
$checks = [ordered]@{}
foreach ($entry in @(@('install.log', '/i'), @('uninstall.log', '/x'))) {
    $name, $switch = $entry
    if ($InstallOnly -and $switch -eq '/x') { continue }
    $text = [IO.File]::ReadAllText((Join-Path $Directory $name))
    $checks[$name] = Read-MsiOperationLog $text $request.logs[$name].nativePath $switch $identity
}
$checks | ConvertTo-Json -Depth 4 -Compress
