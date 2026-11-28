# Compile the actual capture guard and exercise it against synthetic window observations.
$ErrorActionPreference = 'Stop'
function SourceString($Path, $Declaration) {
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$null, [ref]$errors)
    if ($errors.Count) { throw $errors[0] }
    $sources = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.StringConstantExpressionAst] -and
        $n.Value.Contains($Declaration)}, $true))
    if ($sources.Count -ne 1) { throw "Missing source for $Declaration" }
    $sources[0].Value
}
$label = Join-Path $PSScriptRoot 'windows-label.ps1'
$inputDriver = Join-Path (Split-Path $PSScriptRoot) 'observe-windows-input.ps1'
$guard = SourceString $label 'public static class IfwPassiveLabel {'
$native = SourceString $label 'public static class IfwContrastWindows {'
$bridge = SourceString $inputDriver 'public static class IfwObservedWindow {'
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($label, [ref]$null, [ref]$errors)
$calls = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.InvokeMemberExpressionAst] -and
    $n.Member.Value -in 'RequireRegion','CopyFromScreen','GetForegroundWindow','SetForegroundWindow'}, $true))
if (($calls.Member.Value -join ',') -cne 'RequireRegion,CopyFromScreen,RequireRegion' -or
        $calls[0].Expression.Extent.Text -cne '[IfwPassiveLabel]' -or $calls[2].Expression.Extent.Text -cne '[IfwPassiveLabel]') {
    throw 'The passive observer must guard both sides of its screen read.'
}
Add-Type -TypeDefinition ($bridge + [Environment]::NewLine + $native + [Environment]::NewLine + $guard)

$testWindows = @'
using System;
namespace PassiveTest {
public static class IfwObservedWindow {
    public static string scenario;
    public static int pixels;
    public static bool OnInputDesktop() { return scenario != "inactive"; }
    public static uint GetWindowThreadProcessId(IntPtr window, out uint owner) { owner = scenario == "foreign" ? 2u : 1u; return 10; }
    public static bool SubjectAt(IntPtr window, uint pid, int x, int y) {
        ++pixels;
        return scenario != "wrong-pixel" || x != 1 || y != -2;
    }
}
public static class IfwContrastWindows {
    public struct Rect { public int left, top, right, bottom; }
    public static string ThreadDesktopName() { return IfwObservedWindow.scenario == "wrong-desktop" ? "Default" : "own"; }
    public static bool IsWindowVisible(IntPtr window) { return window != (IntPtr)12 || IfwObservedWindow.scenario != "hidden"; }
    public static bool IsIconic(IntPtr window) { return IfwObservedWindow.scenario == "minimized"; }
    public static IntPtr GetTopWindow(IntPtr parent) { return (IntPtr)11; } // Another window has foreground.
    public static IntPtr GetWindow(IntPtr current, uint command) {
        if (command != 2 || current != (IntPtr)11) throw new Exception("Unexpected Z-order traversal");
        if (IfwObservedWindow.scenario == "missing") return IntPtr.Zero;
        return (IntPtr)(IfwObservedWindow.scenario == "cycle" ? 11 : 12);
    }
    public static bool GetWindowRect(IntPtr window, out Rect rect) {
        rect = new Rect { left = -8, top = -9, right = -2, bottom = 2 }; // Ends where crop starts.
        if (IfwObservedWindow.scenario == "overlap") rect.right++;
        return IfwObservedWindow.scenario != "unknown-bounds";
    }
}
'@
Add-Type -TypeDefinition ($testWindows + [Environment]::NewLine + $guard + [Environment]::NewLine + '}')
function CheckRegion { [PassiveTest.IfwPassiveLabel]::RequireRegion('own', [IntPtr]::new(12), 1, -2, -3, 4, 4) }
[PassiveTest.IfwObservedWindow]::scenario = 'clear'
CheckRegion
if ([PassiveTest.IfwObservedWindow]::pixels -ne 16) { throw 'Expected every pixel in the unobstructed passive crop.' }
foreach ($case in 'inactive','foreign','wrong-desktop','hidden','minimized','missing','cycle','overlap','unknown-bounds','wrong-pixel') {
    [PassiveTest.IfwObservedWindow]::scenario = $case
    try { CheckRegion } catch [InvalidOperationException] { continue }
    throw "The inconclusive crop was accepted for $case"
}
Write-Output 'Passive contrast crop controls passed.'
