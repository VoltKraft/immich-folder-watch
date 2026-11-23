# Exercise the actual pixel selection used by the UIA observer without touching a desktop.
$ErrorActionPreference = 'Stop'
$errors = $null
$source = Join-Path $PSScriptRoot 'notification.ps1'
$ast = [Management.Automation.Language.Parser]::ParseFile($source,[ref]$null,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$definition = $ast.Find({param($node) $node -is [Management.Automation.Language.StringConstantExpressionAst] -and
    $node.Value.Contains('public static class IfwNoticeDesktop')},$true)
Add-Type -TypeDefinition $definition.Value
function Contains-Point($Rect,$Point) {
    return $Rect[0] -le $Point[0] -and $Point[0] -lt $Rect[2] -and $Rect[1] -le $Point[1] -and $Point[1] -lt $Rect[3]
}
foreach ($pair in @(
        @{a=@(-10.5,-4.5,1.2,-1.1); b=@(-2.2,-5.5,10,-1.1)},
        @{a=@(0,0,100,12); b=@(0,8,100,24)},
        @{a=@(0,0,10,10); b=@(10,0,20,10)})) {
    $a = [IfwNoticeDesktop]::LabelPoint($pair.a,$pair.b)
    $b = [IfwNoticeDesktop]::LabelPoint($pair.b,$pair.a)
    if (-not (Contains-Point $pair.a $a) -or (Contains-Point $pair.b $a) -or
        -not (Contains-Point $pair.b $b) -or (Contains-Point $pair.a $b)) {
        throw 'The two labels did not yield independently attributable physical pixels'
    }
}
$same = @(0,0,20,10)
$p = [IfwNoticeDesktop]::LabelPoint($same,$same)
if (-not (Contains-Point $same $p) -or $null -ne [IfwNoticeDesktop]::LabelPoint(@(0.1,0,0.9,4),$same)) {
    throw 'An inseparable or subpixel rectangle was not identified'
}
Write-Output 'Notification pixel selection passed.'
