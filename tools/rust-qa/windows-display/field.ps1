param([Parameter(Mandatory)][int]$SubjectId, [Parameter(Mandatory)][long]$WindowHandle,
      [Parameter(Mandatory)][ValidateSet('Read','Prime','Frame','SourceFrame')][string]$Phase,
      [Parameter(Mandatory)][string]$OutputFile)
$ErrorActionPreference='Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'Use the isolated Windows display observer.' }
$handle=[IntPtr]::new($WindowHandle)
$result=[ordered]@{status='failed'; pid=$SubjectId; hwnd=$WindowHandle; phase=$Phase}
$oldDpi=[IntPtr]::Zero
$initial='Gr' + [char]0x00fc + [char]0x00df + 'e ' + [char]0x2013 + ' Sommer.jpg'
$first='IFW MMMM 27.jpg'
$second='IFW IIII 27.jpg'

function Field-Focused {
    if (-not [IfwObservedWindow]::OnInputDesktop() -or [IfwObservedWindow]::GetForegroundWindow() -ne $handle) { return $false }
    $focused=[Windows.Automation.AutomationElement]::FocusedElement
    return $null -ne $focused -and $focused.Current.ProcessId -eq $SubjectId -and [Windows.Automation.Automation]::Compare($field,$focused)
}

function Field-Equals([string]$expected) {
    return $field.Current.ProcessId -eq $SubjectId -and -not $field.Current.IsPassword -and
        $text.DocumentRange.GetText(64) -ceq $expected -and $value.Current.Value -ceq $expected
}

function Prefix-Box {
    $doc=$text.DocumentRange
    $range=$doc.Clone()
    $range.MoveEndpointByRange('End',$doc,'Start')
    if ($range.MoveEndpointByUnit('End','Character',3) -ne 3 -or $range.GetText(8) -cne 'IFW') {
        return $null
    }
    $boxes=@($range.GetBoundingRectangles())
    if ($boxes.Count -ne 1 -or $boxes[0].IsEmpty -or -not $field.Current.BoundingRectangle.Contains($boxes[0])) {
        return $null
    }
    return @($boxes[0].Left,$boxes[0].Top,$boxes[0].Right,$boxes[0].Bottom)
}

function Capture-Field([string]$suffix) {
    if (-not (Field-Focused)) { throw 'The synthetic filename lost native focus before capture.' }
    $bounds=$field.Current.BoundingRectangle
    $x=[int][Math]::Ceiling($bounds.Left+2); $y=[int][Math]::Ceiling($bounds.Top+2)
    $width=[int][Math]::Floor($bounds.Right)-$x-2; $height=[int][Math]::Floor($bounds.Bottom)-$y-2
    [IfwQaText.Input]::RequireRegion($handle,$SubjectId,$x,$y,$width,$height)
    $capture=Capture-SubjectField $field $suffix
    [IfwQaText.Input]::RequireRegion($handle,$SubjectId,$x,$y,$width,$height)
    if (-not $bounds.Equals($field.Current.BoundingRectangle)) { throw 'Filename moved during its physical pixel readback.' }
    return $capture
}

try {
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms,System.Drawing
    $qa=Split-Path $PSScriptRoot
    $errors=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $qa 'observe-windows-input.ps1'),[ref]$null,[ref]$errors)
    $bridge=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
        $n.StringConstantType -eq 'SingleQuotedHereString' -and $n.Value.Contains('public static class IfwObservedWindow {')},$true))
    if ($errors -or $bridge.Count -ne 1) { throw 'Missing shared native window observer.' }
    Add-Type -TypeDefinition ($bridge[0].Value + [Environment]::NewLine + [IO.File]::ReadAllText((Join-Path $qa 'windows-text/Pointer.cs')))
    foreach ($name in @('Wait-Observation','Get-AccessibleName','Get-Field','Capture-SubjectField','Get-FieldPixelDifference')) {
        $definitions=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true))
        if ($definitions.Count -ne 1) { throw "Missing shared observer function $name." }
        . ([scriptblock]::Create($definitions[0].Extent.Text))
    }
    $oldDpi=[IfwQaText.Input]::SetThreadDpiAwarenessContext([IntPtr]::new(-4))
    if ($oldDpi -eq [IntPtr]::Zero) { throw 'Per-monitor physical coordinates are required.' }
    [uint32]$owner=0
    $root=[Windows.Automation.AutomationElement]::FromHandle($handle)
    if (-not [IfwObservedWindow]::GetWindowThreadProcessId($handle,[ref]$owner) -or $owner -ne $SubjectId -or $root.Current.ProcessId -ne $SubjectId) {
        throw 'The HWND and UIA root must belong to the identified Rust child.'
    }
    $scope=[Windows.Automation.TreeScope]::Descendants
    $field=Wait-Observation {Get-Field 'Dateiname' ([Windows.Automation.ControlType]::Edit)} 'owned filename'
    if ($field.Current.ProcessId -ne $SubjectId -or $field.Current.IsPassword) { throw 'Unexpected editor identity.' }
    $text=$field.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern)
    $value=$field.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
    $framePhase=$Phase -in @('Frame','SourceFrame')
    $expected=if ($framePhase) {$first} else {$initial}
    if (-not (Field-Equals $expected)) { throw 'The normal filename differs from the expected synthetic state.' }
    $r=$field.Current.BoundingRectangle
    if ($r.IsEmpty -or $r.Width -le 0 -or $r.Height -le 0) { throw 'The filename has no physical UIA geometry.' }
    $result.field='Dateiname'; $result.rect=@($r.Left,$r.Top,$r.Right,$r.Bottom)
    $result.dpi=[IfwObservedWindow]::GetDpiForWindow($handle)
    $result.expectedText=$expected; $result.focusAtEntry=Field-Focused
    if ($Phase -ne 'Read') {
        if (-not [IfwObservedWindow]::OnInputDesktop()) { throw 'The observer is outside the current input desktop.' }
        if ($Phase -eq 'Prime') {
            $result.foregroundRequest = [IfwObservedWindow]::SetForegroundWindow($handle)
            try { $field.SetFocus() } catch { $result.setFocusUnavailable=$true }
            if (-not (Field-Focused)) {
                $x=[int]($r.Left+$r.Width/2); $y=[int]($r.Top+$r.Height/2)
                $result.pointOwnedBeforeClick=[IfwObservedWindow]::SubjectAt($handle,$SubjectId,$x,$y)
                $result.ownedClick=$result.pointOwnedBeforeClick -and [IfwObservedWindow]::ClickOwnedControl($handle,$SubjectId,$x,$y)
                if (-not $result.ownedClick) {
                    throw 'The owned foreground field could not acquire focus.'
                }
            }
            [void](Wait-Observation { Field-Focused } 'initial filename focus')
            $next=$first
        } else {
            if (-not $result.focusAtEntry) { throw 'The actual filename lost foreground or keyboard focus.' }
            $result.prefixRect=@(Wait-Observation { Prefix-Box } 'the three fixed glyph bounds')
            $result.before=Capture-Field 'before'
            $next=$second
        }
        if (-not (Field-Focused) -or -not (Field-Equals $expected)) { throw 'Focus or synthetic text changed before the edit.' }
        $value.SetValue($next)
        [void](Wait-Observation { (Field-Focused) -and (Field-Equals $next) } 'owned UIA text readback')
        $result.textAfter=$next
        if ($Phase -eq 'Prime') { $result.prefixRect=@(Wait-Observation { Prefix-Box } 'the three fixed glyph bounds') }
        if ($framePhase) {
            [void](Wait-Observation {
                $result.after=Capture-Field 'after'
                $result.difference=Get-FieldPixelDifference "$OutputFile.before.png" "$OutputFile.after.png" $result.before $result.after $result.dpi
                $result.difference.textChanged
            } 'a changed stationary filename frame')
            if (-not $r.Equals($field.Current.BoundingRectangle) -or -not (Field-Equals $next)) { throw 'The stationary frame geometry or text changed.' }
            if ($Phase -eq 'SourceFrame') {
                if (-not (Field-Focused)) { throw 'The subject lost focus before restoring the fixed text.' }
                $value.SetValue($first)
                [void](Wait-Observation { (Field-Focused) -and (Field-Equals $first) } 'restored source-monitor control')
                $result.textRestored=$first
            }
        }
    }
    $result.focusAtExit=Field-Focused
    $result.status='observed'
} catch { $result.error=$_.Exception.GetBaseException().Message; throw }
finally {
    if ($oldDpi -ne [IntPtr]::Zero) { [void][IfwQaText.Input]::SetThreadDpiAwarenessContext($oldDpi) }
    [IO.File]::WriteAllText($OutputFile,($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
