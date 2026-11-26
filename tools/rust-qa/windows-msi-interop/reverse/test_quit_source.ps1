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
# Compile the exact delegate used by the native observer without invoking the native helper on this desktop.
$close = $type[0].GetMethod('Close', [type[]]@([int])).CreateDelegate([Func[int,string]])
if ($close.Method.DeclaringType -ne $type[0] -or $close.Method.Name -cne 'Close') { throw 'Incorrect Quit delegate.' }
$observer = [InstalledQuitReceiver]::new()
$rc = [InstalledQuitReceiver+Rect]@{ left=-1920; top=-100; right=-891; bottom=675 }
$point = [InstalledQuitReceiver]::Interior($rc)
if ($point.x -ne -1149 -or $point.y -ne 481) { throw 'Incorrect physical anchor on a monitor with negative coordinates.' }
$hit = [InstalledQuitReceiver+Window]@{ hwnd=101; root=100; pid=20; tid=21; rootPid=20; rootTid=21 }
$observer.anchor.clientRect = $rc
$observer.anchor.point = $point
$observer.anchor.before = $hit
$observer.anchor.probes.Add($hit)
$observer.anchor.after = $hit
$observer.anchor.cursor = $point
$observer.anchor.physicalCursor = $point
if (-not $observer.Confirmed($rc, 100, 20, 21)) { throw 'Refused the original root and its owned child.' }
$observer.anchor.dpiContext = 'per-monitor-v2'
$wire = ($observer.anchor | ConvertTo-Json -Depth 8) | ConvertFrom-Json -AsHashtable
if ($wire.point.x -isnot [long] -or $wire.after.rootTid -ne 21 -or $wire.clientRect.left -ne -1920 -or
    $wire.physicalCursor.y -ne 481 -or $wire.dpiContext -cne 'per-monitor-v2') { throw 'Lost the physical anchor in JSON.' }
foreach ($field in @('hwnd', 'root', 'pid', 'tid', 'rootPid', 'rootTid')) {
    $value = $hit.$field
    $hit.$field = 0
    if ($observer.Confirmed($rc, 100, 20, 21)) { throw "Accepted an unbound hit field: $field" }
    $hit.$field = $value
}
$foreign = [InstalledQuitReceiver+Window]@{ hwnd=102; root=99; pid=20; tid=21; rootPid=20; rootTid=21 }
foreach ($name in @('before','after')) {
    $observer.anchor.$name = $foreign
    if ($observer.Confirmed($rc, 100, 20, 21)) { throw "Accepted a different root at $name." }
    $observer.anchor.$name = $hit
}
$shifted = [InstalledQuitReceiver+Point]@{ x=$point.x+1; y=$point.y }
foreach ($name in @('cursor','physicalCursor','point')) {
    $observer.anchor.$name = $shifted
    if ($observer.Confirmed($rc, 100, 20, 21)) { throw "Accepted an altered $name." }
    $observer.anchor.$name = $point
}
$rc.right += 1
if ($observer.Confirmed($rc, 100, 20, 21)) { throw 'Accepted a changed client rectangle.' }
$rc.right -= 1
$observer.anchor.probes.Insert(0, $foreign)
$point = [InstalledQuitReceiver]::Interior($rc, 1)
$observer.anchor.point = $point
$observer.anchor.cursor = $point
$observer.anchor.physicalCursor = $point
if ($point.x -ne -1406 -or -not $observer.Confirmed($rc, 100, 20, 21)) { throw 'Failed to select an exposed client point.' }
$observer.anchor.probes[0] = $hit
if ($observer.Confirmed($rc, 100, 20, 21)) { throw 'Skipped the first original client hit.' }
try {
    $null = [InstalledQuitReceiver]::Interior([InstalledQuitReceiver+Rect]@{ left=10; top=10; right=11; bottom=11 })
    throw 'Accepted an empty interior.'
} catch [Management.Automation.MethodInvocationException] {
    if ($_.Exception.InnerException.Message -cne 'The original client rectangle has no interior menu anchor.') { throw }
}
$tokens = $null
$errors = $null
$null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'quit.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw $errors[0].Message }
Write-Output "Validated both checkout line endings, altered-source refusals, native C# compilation and owned physical anchor controls. SHA-256 $expectedHash"
