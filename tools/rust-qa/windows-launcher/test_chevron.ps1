# Exercise the actual selector and passive point readback against controlled Win32/UIA boundaries.
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
namespace IfwChevronTest {
    public static class Shell {
        public static IntPtr FindWindow(string cls, string title) { return new IntPtr(51); }
        public static bool IsWindowVisible(IntPtr hwnd) { return true; }
    }
    public sealed class Point { public double X,Y; public Point(double x,double y) { X=x; Y=y; } }
    public sealed class Bounds { public bool Contains(Point p) { return p.X==806 && p.Y==744; } }
    public sealed class ControlType {
        public int Id; public static readonly ControlType Button=new ControlType{Id=50000}, Pane=new ControlType{Id=50033};
    }
    public enum TreeScope { Element, Descendants }
    public enum ExpandCollapseState { Collapsed, Expanded }
    public enum ToggleState { Off, On }
    public static class ExpandCollapsePattern { public const string Pattern="expand"; }
    public static class TogglePattern { public const string Pattern="toggle"; }
    public static class InvokePattern { public const string Pattern="invoke"; }
    public sealed class PropertyCondition {
        public string Property,Value; public PropertyCondition(string p,string v) { Property=p; Value=v; }
    }
    public sealed class Info {
        public int ProcessId=81; public bool IsEnabled=true, IsOffscreen;
        public ControlType ControlType=ControlType.Button; public Bounds BoundingRectangle=new Bounds();
        public ExpandCollapseState ExpandCollapseState; public ToggleState ToggleState;
    }
    public sealed class AutomationElement {
        public const string NameProperty="name", HelpTextProperty="help";
        public static AutomationElement Root, Hit;
        public static AutomationElement FromHandle(IntPtr hwnd) { return hwnd.ToInt64()==51 ? Root : null; }
        public static AutomationElement FromPoint(Point p) { return Hit; }
        public Info Current=new Info();
        public AutomationElement Parent;
        public AutomationElement[] Children=new AutomationElement[0];
        public string Label,Help; public string[] Patterns=new string[0];
        public int Actions,CapabilityReads;
        public AutomationElement[] FindAll(TreeScope scope,PropertyCondition f) {
            if (scope!=TreeScope.Descendants || f.Property!=NameProperty) throw new Exception("Unbounded lookup");
            return Array.FindAll(Children,e=>e.Label==f.Value);
        }
        public AutomationElement FindFirst(TreeScope scope,PropertyCondition f) {
            if (scope!=TreeScope.Element) throw new Exception("Unbounded observation");
            return (f.Property==NameProperty ? Label : Help)==f.Value ? this : null;
        }
        public bool TryGetCurrentPattern(string p,out AutomationElement provider) {
            CapabilityReads++; provider=this; return Array.IndexOf(Patterns,p)>=0;
        }
        public void Invoke() { Actions++; } public void Toggle() { Actions++; } public void Expand() { Actions++; }
    }
    public static class Automation {
        public static bool ReplaceAfterBinding;
        public static bool Compare(object a,object b) {
            bool same=Object.ReferenceEquals(a,b);
            if (same && ReplaceAfterBinding && Object.ReferenceEquals(a,AutomationElement.Root)) AutomationElement.Hit.Current.ProcessId=17;
            return same;
        }
    }
    public sealed class TreeWalker {
        public static readonly TreeWalker RawViewWalker=new TreeWalker();
        public AutomationElement GetParent(AutomationElement e) { return e.Parent; }
    }
}
'@
function Import-ControlledFunction($File,$Name) {
    $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($File,[ref]$null,[ref]$errors)
    if ($errors.Count) { throw $errors[0] }
    $fn=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $Name},$true)
    $text=$fn.Extent.Text.Replace('[IfwSyntheticShellObserver]', '[IfwChevronTest.Shell]').Replace(
        '[Windows.Automation.', '[IfwChevronTest.').Replace('[Windows.Point]', '[IfwChevronTest.Point]')
    return [scriptblock]::Create($text)
}
. (Import-ControlledFunction (Join-Path $PSScriptRoot '../windows-services/tray-overflow.ps1') 'Open-IfwTrayOverflow')
. (Import-ControlledFunction (Join-Path $PSScriptRoot 'tray_provider.ps1') 'Get-ChevronHintReadback')
$script:Bar=51; $script:ShellPid=81
function Get-IfwShellOwner($Window) { return 81 }
function Get-IfwOverflowWindow($ExplorerId) { return [IntPtr]::Zero }
$root=[IfwChevronTest.AutomationElement]::new()
[IfwChevronTest.AutomationElement]::Root=$root
$wrong=@{expectedBar=52;expectedPid=81}
$state=Open-IfwTrayOverflow @{} $null $null $wrong
if ($state -or $wrong.names.Count -or $wrong.gate -cne 'different-original-taskbar' -or $wrong.bar -ne 51 -or $wrong.pid -ne 81) {
    throw 'A different original taskbar was inspected'
}
foreach ($case in @('missing','duplicate','foreign-process','offscreen','disabled','not-button','no-supported-pattern',
                    'expand-state','toggle-state','before-change','before-action','selected','standalone')) {
    $button=[IfwChevronTest.AutomationElement]::new()
    $button.Label='Show hidden icons'; $button.Patterns=@('invoke'); $root.Children=@($button)
    switch ($case) {
        'missing' { $button.Label='A private unrelated title' }
        'duplicate' { $root.Children=@($button,$button) }
        'foreign-process' { $button.Current.ProcessId=17 }
        'offscreen' { $button.Current.IsOffscreen=$true }
        'disabled' { $button.Current.IsEnabled=$false }
        'not-button' { $button.Current.ControlType=[IfwChevronTest.ControlType]::Pane }
        'no-supported-pattern' { $button.Patterns=@() }
        'expand-state' { $button.Patterns=@('expand'); $button.Current.ExpandCollapseState='Expanded' }
        'toggle-state' { $button.Patterns=@('toggle'); $button.Current.ToggleState='On' }
    }
    $record=@{}; $selection=@{}
    if ($case -eq 'standalone') { $state=Open-IfwTrayOverflow $record }
    else { $state=Open-IfwTrayOverflow $record { $case -ne 'before-change' } { $case -ne 'before-action' } $selection }
    if ($case -in @('selected','standalone')) {
        if ($button.Actions -ne 1 -or $state.action.method -cne 'Invoke' -or $record.Count -ne 2) { throw "Changed the normal $case action" }
        continue
    }
    if ($button.Actions -or $null -ne $state -or $record.Count) { throw "An ineligible control was acted on for $case" }
    if ($case -like 'before-*') {
        if ($selection.gate -cne $case) { throw "Missing actual guard for $case" }
    } else {
        $first=$selection.names[0]
        if ($selection.gate -cne 'known-name-selection' -or $first.name -cne 'Show hidden icons') { throw "Incorrect selector scope for $case" }
        if ($case -eq 'missing' -and ($first.count -ne 0 -or $selection.names.Count -ne 4)) { throw 'Missing exact-name counts' }
        if ($case -eq 'duplicate' -and $first.count -ne 2) { throw 'Duplicate accepted as unique' }
        if ($case -notin @('missing','duplicate') -and $first.rejected -cne $case) { throw "Lost actual rejection for $case" }
        if (($case -eq 'expand-state' -and $first.state -cne 'Expanded') -or
            ($case -eq 'toggle-state' -and $first.state -cne 'On') -or
            ($case -eq 'not-button' -and $first.controlType -ne 50033)) { throw "Lost native capability for $case" }
    }
}
$original=$button
foreach ($case in @('offscreen-and-pane','multiple-visible','unbound')) {
    $button=[IfwChevronTest.AutomationElement]::new()
    $button.Label='Show hidden icons'; $button.Patterns=@('invoke')
    $other=[IfwChevronTest.AutomationElement]::new(); $other.Label=$button.Label
    $other.Current.IsOffscreen=$case -ne 'multiple-visible'
    $pane=[IfwChevronTest.AutomationElement]::new(); $pane.Label=$button.Label; $pane.Current.ControlType=[IfwChevronTest.ControlType]::Pane
    $root.Children=@($other,$button,$pane)
    $selection=@{}; $record=@{}
    $state=Open-IfwTrayOverflow $record { $true } { $case -ne 'unbound' } $selection -SelectVisibleButton
    $expected=if ($case -eq 'offscreen-and-pane') { 1 } else { 0 }
    if ($button.Actions -ne $expected -or $other.Actions -or $pane.Actions -or
        $selection.names[0].count -ne 3 -or $selection.names[0].visibleButtons -ne (1 + [int]($case -eq 'multiple-visible')) -or
        (($null -ne $state) -ne [bool]$expected)) { throw "Incorrect menu selection for $case" }
}
$button=$original
$guard=[pscustomobject]@{}
$guard | Add-Member ScriptMethod ButtonHit { $script:reads++; if ($script:changed -and $script:reads -gt 1) { return 63 }; return 62 }
$surface=@{root=51; shellPid=81; hit=62; point=@(806,744)}
$leaf=[IfwChevronTest.AutomationElement]::new()
$leaf.Label='A private unrelated title'; $leaf.Help='Private tooltip'; $leaf.Parent=$button
$button.Label='Hidden icon menu'; $button.Help='Show hidden icons'; $button.Parent=$root
[IfwChevronTest.AutomationElement]::Hit=$leaf; $script:changed=$false; $script:reads=0
$snapshot=Get-ChevronHintReadback $guard $surface @('Show hidden icons')
$json=$snapshot | ConvertTo-Json -Depth 5 -Compress
if ($snapshot.status -cne 'bound-taskbar-point' -or $snapshot.elements.Count -ne 2 -or $snapshot.nativeHit -ne 62 -or
    $snapshot.elements[1].Name -cne 'Hidden icon menu' -or $snapshot.elements[1].HelpText -cne 'Show hidden icons' -or
    -not $snapshot.elements[1].invoke -or $snapshot.elements[1].toggle -or -not $snapshot.elements[1].containsPoint -or
    $json -match 'Private' -or $button.Actions -ne 1) { throw 'The read-only observations lost their scope or disclosed unrelated text' }
foreach ($case in @('other-root','foreign-uia','changed-uia','changed-native')) {
    $script:reads=0; $script:changed=($case -eq 'changed-native'); $leaf.Parent=$button
    $leaf.Current.ProcessId=if ($case -eq 'foreign-uia') { 17 } else { 81 }
    [IfwChevronTest.Automation]::ReplaceAfterBinding=($case -eq 'changed-uia')
    if ($case -eq 'other-root') { $leaf.Parent=$null }
    $previous=$leaf.CapabilityReads
    $snapshot=Get-ChevronHintReadback $guard $surface @('Show hidden icons')
    $expected=if ($case -eq 'changed-uia') { 'changed-uia-hit' } elseif ($case -eq 'changed-native') { 'changed-hit' } else { 'unbound-uia-hit' }
    if ($snapshot.elements -or $snapshot.status -cne $expected -or
        ($case -ne 'changed-native' -and $leaf.CapabilityReads -ne $previous) -or $button.Actions -ne 1) {
        throw "Reported unbound system control capabilities for $case"
    }
}
Write-Output 'Seventeen selection controls and five passive taskbar hit controls passed.'
