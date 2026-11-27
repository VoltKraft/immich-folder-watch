# Use the observer's actual recovery code with a controlled, stateful accessibility provider.
$ErrorActionPreference = 'Stop'
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'tray_provider.ps1'),[ref]$null,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$source=$ast.Find({param($n) $n -is [Management.Automation.Language.StringConstantExpressionAst] -and
    $n.Value.Contains('public sealed class IfwIconSurface')},$true)
Add-Type -TypeDefinition $source.Value
$testRect=[int[]]@(790,720,822,768)
$grid=[IfwIconSurface]::CountMarker($testRect,{
    param($x,$y)
    if ($x -lt 790 -or $x -ge 822 -or $y -lt 720 -or $y -ge 768) { throw 'Read outside the original rectangle' }
    if ($x -le 793 -and $y -le 724) { return 1 }
    if ($x -eq 821) { return -1 }
    return 0
})
if ($grid.matches -ne 4 -or $grid.matchingSampleSquares -ne 1 -or $grid.unobserved -ne 16 -or
    $grid.sampled -ne 240 -or ($grid.step -join ',') -ne '2,3' -or
    ($grid.matchingBounds -join ',') -ne '791,721,794,725') {
    throw 'The offset marker or the unobserved part of the Shell rectangle was misreported'
}
$sparse=[IfwIconSurface]::CountMarker([int[]]@(-12,-4,4,12),{
    param($x,$y)
    if ($x -eq -12 -or $y -eq 11) {return 1}; return 0
})
if ($sparse.matches -ne 31 -or $sparse.matchingSampleSquares -ne 0 -or
    ($sparse.matchingBounds -join ',') -ne '-12,-4,4,12') { throw 'Isolated rows were credited as a marker area' }
$empty=[IfwIconSurface]::CountMarker([int[]]@(0,0,256,2),{
    param($x,$y)
    if ($x -lt 0 -or $x -ge 256 -or $y -lt 0 -or $y -ge 2) { throw 'Unbounded grid' }
    return 0
})
if ($empty.columns -ne 16 -or $empty.rows -ne 2 -or $empty.sampled -ne 32 -or $null -ne $empty.matchingBounds) {
    throw 'An empty maximally wide rectangle recorded a hit or lost its sample geometry'
}
try {
    [void][IfwIconSurface]::CountMarker([int[]]@(0,0,257,2),{ throw 'Oversized rectangle read' })
    throw 'Oversized rectangle accepted'
} catch {
    if ($_.Exception.GetBaseException().Message -ne 'Invalid marker grid rectangle') { throw }
}
$bar=[IfwIconSurface+BarComparison]::new([int[]]@(-16,4,16,12),[int[]]@(0,4,12,12))
for ($pass=0; $pass -lt 4; $pass++) {
    $bar.AddPass($pass,{
        param($x,$y)
        if ($x -lt -16 -or $x -ge 16 -or $y -lt 4 -or $y -ge 12) { throw 'Sample left the taskbar' }
        if ($y -ne 6) { return -91L }
        switch ($x) {
            -14 { return 91L }  # Stable change outside the returned rectangle.
              2 { return 91L }  # Stable change inside it.
            -10 { if ($pass -lt 2) { return 91L }; return 81L }  # Replaced hit window.
             -6 { if ($pass -eq 2) { return 0L }; return 91L }    # Temporarily covered.
             -2 { if ($pass -eq 1) { return -91L }; return 91L }  # Transient color.
              6 { if ($pass -lt 2) { return 91L }; return -91L }  # Different locations.
             10 { if ($pass -ge 2) { return 91L }; return -91L }
            default { return -91L }
        }
    })
}
if ($bar.rows -ne 2 -or $bar.columns -ne 8 -or $bar.stable -ne 14 -or $bar.firstColor -ne 3 -or
    $bar.secondColor -ne 4 -or $bar.inside -ne 1 -or $bar.outside -ne 1 -or
    ($bar.transitionBounds -join ',') -ne '-14,6,3,7' -or ($bar | ConvertTo-Json) -match '"(hits|center)"') {
    throw 'The taskbar comparison misattributed a pixel, lost coverage counts or exposed its internal samples'
}
foreach ($bounds in @(@(0,0,4097,20),@(0,0,1000,162),@(2,0,800,52))) {
    try {
        [void][IfwIconSurface+BarComparison]::new([int[]]$bounds,[int[]]@(0,2,18,18))
        throw 'Unexpected taskbar dimensions were accepted'
    } catch {
        if ($_.Exception.GetBaseException().Message -ne 'Unexpected original taskbar or icon dimensions') { throw }
    }
}
$vertical=[IfwIconSurface+BarComparison]::new([int[]]@(0,0,160,4096),[int[]]@(10,70,25,100))
if ($vertical.columns*$vertical.rows -gt 1536) { throw 'The taskbar sampling budget was exceeded' }
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
Write-Output 'Icon and taskbar color sampling, flyout recovery and native identity controls passed.'
