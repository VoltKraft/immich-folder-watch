#Requires -Version 7.0
# Compile the pinned helper on the current host without invoking its native menu interaction.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'quit-source.ps1')

function Assert-Refused([string]$Path, [string]$ExpectedError) {
    try { $null = Get-InstalledUpgradeQuitSource -Path $Path }
    catch {
        if ($_.Exception.Message -cne $ExpectedError) { throw }
        return
    }
    throw "Accepted an altered upgrade reference: $Path"
}

$original = Get-InstalledUpgradeQuitSource
$expectedHash = 'f50baad6accfd09afc3e86beb9908027b8498525f6a787f35d217841c86c9e5c'
$utf8 = [Text.UTF8Encoding]::new($false, $true)
if ($original.Sha256 -cne $expectedHash -or $utf8.GetByteCount($original.Code) -ne 9270) {
    throw 'Missing the original 3.0.4 native Quit helper.'
}
$reference = Join-Path $PSScriptRoot '../../../../packaging/windows/Test-InstalledUpgrade.ps1'
$lf = [IO.File]::ReadAllText($reference, $utf8).Replace("`r`n", "`n")
$temp = [IO.Directory]::CreateDirectory((Join-Path ([IO.Path]::GetTempPath()) ('ifw-quit-source-' + [Guid]::NewGuid().ToString('N'))))
try {
    foreach ($checkout in @(@{ name = 'lf'; text = $lf }, @{ name = 'crlf'; text = $lf.Replace("`n", "`r`n") })) {
        $path = Join-Path $temp.FullName ($checkout.name + '.ps1')
        [IO.File]::WriteAllText($path, $checkout.text, $utf8)
        $observed = Get-InstalledUpgradeQuitSource -Path $path
        if ($observed.Code -cne $original.Code -or $observed.Sha256 -cne $expectedHash) {
            throw "The $($checkout.name) checkout changed the original native source."
        }
    }
    $changed = Join-Path $temp.FullName 'changed.ps1'
    [IO.File]::WriteAllText($changed, $lf.Replace('verifiedHighlightedCommandId=3', 'verifiedHighlightedCommandId=2'), $utf8)
    Assert-Refused $changed 'The installed 3.0.4 native Quit source digest differs.'
    [IO.File]::WriteAllText($changed, $lf.Replace('public static class UpgradeTestTrayQuit', 'public static class DifferentQuit'), $utf8)
    Assert-Refused $changed 'The installed 3.0.4 native Quit source digest differs.'
    [IO.File]::WriteAllText($changed, $lf + "`nfunction Close-TestApplicationGracefully {}", $utf8)
    Assert-Refused $changed 'Expected the unique installed upgrade Quit function.'
} finally { [IO.Directory]::Delete($temp.FullName, $true) }

$compiled = @(Add-Type -TypeDefinition $original.Code -PassThru)
$type = @($compiled | Where-Object { $_.FullName -ceq 'UpgradeTestTrayQuit' })
if ($type.Count -ne 1 -or -not $type[0].IsPublic -or -not $type[0].IsAbstract -or -not $type[0].IsSealed) {
    throw 'Expected the public static UpgradeTestTrayQuit class.'
}
foreach ($name in @('Close', 'Describe')) {
    $method = $type[0].GetMethod($name, [type[]]@([int]))
    if ($null -eq $method -or -not $method.IsPublic -or -not $method.IsStatic -or $method.ReturnType -ne [string]) {
        throw "Missing compiled original method $name(int)."
    }
}
Add-InstalledQuitReceiverCheck
$check = [InstalledQuitReceiver].GetMethod('Matches', [type[]]@([IntPtr], [uint32], [uint32]))
if ($null -eq $check -or -not $check.IsStatic -or $check.ReturnType -ne [bool]) {
    throw 'Missing compiled receiver identity check.'
}
$tokens = $null
$errors = $null
$null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'quit.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw $errors[0].Message }
Write-Output "Validated both checkout line endings, altered-source refusals and native C# compilation. SHA-256 $expectedHash"
