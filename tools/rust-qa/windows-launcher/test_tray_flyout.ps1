# Use the observer's actual recovery code with a controlled, stateful accessibility provider.
$ErrorActionPreference = 'Stop'
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'tray_provider.ps1'),[ref]$null,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$source=$ast.Find({param($n) $n -is [Management.Automation.Language.StringConstantExpressionAst] -and
    $n.Value.Contains('public sealed class IfwIconSurface')},$true)
Add-Type -TypeDefinition $source.Value
. (Join-Path $PSScriptRoot '../windows-services/tray-overflow.ps1')
foreach ($name in @('Wait-OpenedPane','Restore-OpenedPane')) {
    $fn=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name},$true)
    . ([scriptblock]::Create($fn.Extent.Text))
}
$script:Bar=51; $script:ShellPid=81
$script:original=@{hwnd=62;pid=81;tid=77;windowClass='NotifyIconOverflowWindow'}
$guard=[pscustomobject]@{}
$guard | Add-Member ScriptMethod CheckOriginal {}
$guard | Add-Member ScriptMethod Overflow { return $script:shown }
$button=[pscustomobject]@{Current=@{ProcessId=81}}
$button | Add-Member ScriptMethod GetRuntimeId { return @(4,11) }
$provider=[pscustomobject]@{}
$provider | Add-Member ScriptMethod Invoke {
    $script:calls++
    $script:shown=if ($null -eq $script:shown) { $script:original }
    if ($script:throwAfterEffect) { throw 'Controlled provider error after changing visible state' }
}
function Get-IfwShellOwner($Window) { return $script:ShellPid }
function Get-IfwOverflowWindow($ExplorerId) { if ($null -ne $script:shown) { return [IntPtr]$script:shown.hwnd }; return [IntPtr]::Zero }
function Get-OverflowButton($State) { return @{runtimeId='4,11'} }
$saved=@{button=$button;bar=[IntPtr]51;explorer=81;action=@{method='Invoke';provider=$provider}}
foreach ($case in @('open-threw','close-threw','already-dismissed','foreign-surface')) {
    $lease=@{state=$saved;button=@{runtimeId='4,11'};pane=$null}
    $record=@{}; $script:calls=0; $script:shown=$null; $script:throwAfterEffect=($case -eq 'open-threw')
    try { $provider.Invoke() } catch { if ($case -ne 'open-threw') { throw } }
    if ($case -ne 'open-threw') { $lease.pane=$script:shown }
    $script:throwAfterEffect=($case -eq 'close-threw')
    if ($case -eq 'already-dismissed') { $script:shown=$null }
    if ($case -eq 'foreign-surface') { $script:shown=@{hwnd=92;pid=81;tid=99;windowClass='NotifyIconOverflowWindow'} }
    $refused=$false
    try { Restore-OpenedPane $guard $lease $record } catch { $refused=$true }
    if ($case -eq 'foreign-surface') {
        if (-not $refused -or $script:calls -ne 1 -or $script:shown.hwnd -ne 92) { throw 'Touched a replaced overflow window' }
    } else {
        $expectedCalls=if ($case -eq 'already-dismissed') { 1 } else { 2 }
        if ($refused -or $record.restored -ne $true -or $null -ne $script:shown -or $script:calls -ne $expectedCalls) {
            throw "Unexpected flyout restoration outcome for $case"
        }
    }
}
Write-Output 'Four original flyout recovery controls passed.'
