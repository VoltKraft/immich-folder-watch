# Use the observer's actual recovery code with a controlled, stateful accessibility provider.
$ErrorActionPreference = 'Stop'
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'tray_provider.ps1'),[ref]$null,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$source=$ast.Find({param($n) $n -is [Management.Automation.Language.StringConstantExpressionAst] -and
    $n.Value.Contains('public sealed class IfwIconSurface')},$true)
Add-Type -TypeDefinition $source.Value
. (Join-Path $PSScriptRoot '../windows-services/tray-overflow.ps1')
foreach ($name in @('Wait-OpenedPane','Restore-OpenedPane','Invoke-OriginalIcon')) {
    $fn=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name},$true)
    . ([scriptblock]::Create($fn.Extent.Text))
}
$script:Bar=51; $script:ShellPid=81
$script:original=[IfwIconSurface+Pane]::new(62,81,77,'NotifyIconOverflowWindow')
$recycled=[IfwIconSurface+Pane]::new(62,81,92,'NotifyIconOverflowWindow')
if ([IfwIconSurface]::SamePane($script:original,$recycled) -or -not [IfwIconSurface]::SamePane($script:original,$script:original)) {
    throw 'A recycled HWND did not preserve its distinct native thread identity'
}
$json=$script:original | ConvertTo-Json -Compress | ConvertFrom-Json
if ($json.hwnd -ne 62 -or $json.pid -ne 81 -or $json.tid -ne 77 -or $json.windowClass -cne 'NotifyIconOverflowWindow') {
    throw 'The complete native pane identity was not exposed to the receipt encoder'
}
$guard=[pscustomobject]@{}
$guard | Add-Member ScriptMethod CheckOriginal {}
$guard | Add-Member ScriptMethod Overflow {
    $script:strongReads++
    if ($script:scenario -eq 'cloaked-at-close' -and $script:strongReads -ge 2) { $script:shown=$null }
    if ($script:scenario -eq 'icon-threw' -and $script:pendingDismiss -and $script:strongReads -ge 2) { $script:shown=$null }
    if ($script:scenario -eq 'reappeared' -and $script:strongReads -eq 4) { $script:shown=$script:original }
    return $script:shown
}
$button=[pscustomobject]@{Current=@{ProcessId=81}}
$button | Add-Member ScriptMethod GetRuntimeId { return @(4,11) }
$provider=[pscustomobject]@{}
$provider | Add-Member ScriptMethod Invoke {
    $script:calls++
    $script:shown=if ($null -eq $script:shown) { $script:original }
    if ($script:throwAfterEffect) { throw 'Controlled provider error after changing visible state' }
}
function Get-IfwShellOwner($Window) { return $script:ShellPid }
function Get-IfwOverflowWindow($ExplorerId) {
    if ($script:scenario -eq 'cloaked-at-close') { return [IntPtr]$script:original.hwnd }
    if ($null -ne $script:shown) { return [IntPtr]$script:shown.hwnd }
    return [IntPtr]::Zero
}
function Get-OverflowButton($State) { return @{runtimeId='4,11'} }
$saved=@{button=$button;bar=[IntPtr]51;explorer=81;action=@{method='Invoke';provider=$provider}}
foreach ($case in @('open-threw','close-threw','already-dismissed','foreign-surface','cloaked-at-close','icon-threw','reappeared')) {
    $lease=@{state=$saved;button=@{runtimeId='4,11'};pane=$null}
    $record=@{}; $script:calls=0; $script:strongReads=0; $script:pendingDismiss=$false; $script:scenario=$case
    $script:shown=$null; $script:throwAfterEffect=($case -eq 'open-threw')
    try { $provider.Invoke() } catch { if ($case -ne 'open-threw') { throw } }
    if ($case -ne 'open-threw') { $lease.pane=$script:shown }
    $script:throwAfterEffect=($case -eq 'close-threw')
    if ($case -in @('already-dismissed','reappeared')) { $script:shown=$null }
    if ($case -eq 'foreign-surface') { $script:shown=$recycled }
    if ($case -eq 'icon-threw') {
        $icon=[pscustomobject]@{}
        $icon | Add-Member ScriptMethod Invoke {
            if ($lease.iconAttempted -ne $true -or $lease.startTick -ne 84) { throw 'Missing pre-COM attempt record' }
            $script:pendingDismiss=$true
            throw 'Controlled native activation followed by a COM error'
        }
        try { Invoke-OriginalIcon $lease $icon { return 84 }; throw 'Expected invocation error' }
        catch { if ($_.Exception.GetBaseException().Message -cne 'Controlled native activation followed by a COM error') { throw } }
    }
    $refused=$false
    try { Restore-OpenedPane $guard $lease $record } catch { $refused=$true }
    if ($case -in @('foreign-surface','reappeared')) {
        if (-not $refused -or $script:calls -ne 1 -or $record.restored) { throw "Certified an unstable overflow surface for $case" }
    } else {
        $expectedCalls=if ($case -in @('already-dismissed','cloaked-at-close','icon-threw')) { 1 } else { 2 }
        if ($refused -or $record.restored -ne $true -or $record.absentMs -lt 750 -or $record.absentSamples -lt 2 -or
            $null -ne $script:shown -or $script:calls -ne $expectedCalls) {
            throw "Unexpected flyout restoration outcome for $case"
        }
    }
}
Write-Output 'Seven original flyout recovery controls and the native tuple comparison passed.'
