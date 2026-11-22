param([Parameter(Mandatory)][int]$SubjectId, [Parameter(Mandatory)][long]$WindowHandle,
      [Parameter(Mandatory)][string]$OutputFile, [Parameter(Mandatory)][string]$PlanFile, [switch]$ReadOnly)
$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'Use the disposable Windows text launcher.' }
$handle = [IntPtr]::new($WindowHandle)
$plan = [IO.File]::ReadAllText($PlanFile) | ConvertFrom-Json
$result = [ordered]@{ status='failed'; pid=$SubjectId; hwnd=$WindowHandle; cases=@() }
function Save-Result {
    [IO.File]::WriteAllText($OutputFile, ($result | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
}

function Test-FieldFocus {
    if (-not [IfwObservedWindow]::OnInputDesktop() -or [IfwObservedWindow]::GetForegroundWindow() -ne $handle) { return $false }
    $active = [Windows.Automation.AutomationElement]::FocusedElement
    return $null -ne $active -and $active.Current.ProcessId -eq $SubjectId -and
        [Windows.Automation.Automation]::Compare($field,$active)
}
function Focus-Field {
    try { $field.SetFocus() } catch { $result.uiaFocusError=$_.Exception.GetBaseException().Message }
    if (-not (Test-FieldFocus)) {
        $r = $field.Current.BoundingRectangle
        if ($r.IsEmpty) { throw 'The filename field has no bounds.' }
        $x = [int]($r.Left + $r.Width/2)
        $y = [int]($r.Top + $r.Height/2)
        $result.focusClick = [IfwObservedWindow]::ClickOwnedControl($handle,$SubjectId,$x,$y)
    }
    [void](Wait-Observation { Test-FieldFocus } 'foreground and keyboard focus of the normal filename')
}
function Set-Sample([string]$Text) {
    Focus-Field
    $valuePattern.SetValue($Text)
    [void](Wait-Observation { $textPattern.DocumentRange.GetText(-1) -ceq $Text } 'the exact UIA text')
}
function Press-Key([string]$Key) {
    if (-not (Test-FieldFocus)) { throw 'The normal filename lost keyboard focus.' }
    [IfwQaText.Input]::Press($handle,$SubjectId,$Key)
}
function Get-Box([string]$Text, [int]$Index, [string]$Character) {
    $doc = $textPattern.DocumentRange
    if ($doc.GetText(-1) -cne $Text) { throw 'UIA text changed before the character measurement.' }
    $range = $doc.Clone()
    $range.MoveEndpointByRange('End',$doc,'Start')
    if ($range.MoveEndpointByUnit('Start','Character',$Index) -ne $Index -or
            $range.MoveEndpointByUnit('End','Character',1) -ne 1 -or $range.GetText(-1) -cne $Character) {
        throw "UIA did not resolve logical character $Index."
    }
    $boxes = @($range.GetBoundingRectangles() | Where-Object { -not $_.IsEmpty -and $_.Width -gt 0 -and $_.Height -gt 0 })
    if ($boxes.Count -ne 1 -or -not $field.Current.BoundingRectangle.Contains($boxes[0])) {
        throw "UIA character $Index has no unique rectangle inside the filename field."
    }
    return $boxes[0]
}
function Current-Selection {
    $selection = @($textPattern.GetSelection())
    if ($selection.Count -ne 1) { throw 'Expected one actual UIA selection or caret.' }
    $prefix = $textPattern.DocumentRange.Clone()
    $prefix.MoveEndpointByRange('End',$selection[0],'Start')
    # All caret test strings are BMP. Only the raster specimen has a supplementary scalar.
    return [ordered]@{ start=$prefix.GetText(-1).Length; value=$selection[0].GetText(-1) }
}
function Wait-Caret([int]$Expected, $Case) {
    [void](Wait-Observation {
        $Case.lastSelection = Current-Selection
        $Case.lastSelection.start -eq $Expected -and $Case.lastSelection.value -ceq ''
    } "collapsed UIA caret $Expected")
    $Case.arrowIndices += $Case.lastSelection.start
}
function Record-Editing($Spec, $Case) {
    Set-Sample $Spec.text
    $anchor = Get-Box $Spec.text $Spec.text.IndexOf([string]$Spec.anchor) $Spec.anchor
    if (-not (Test-FieldFocus) -or -not [IfwObservedWindow]::ClickOwnedControl($handle,$SubjectId,
            [int]($anchor.Left + $anchor.Width*$Spec.fraction), [int]($anchor.Top + $anchor.Height*.5))) {
        throw 'The native click at the owned character was unavailable.'
    }
    Wait-Caret $Spec.arrows[0] $Case
    Press-Key Right
    Wait-Caret $Spec.arrows[1] $Case
    Press-Key Left
    Wait-Caret $Spec.arrows[2] $Case
    # Avoid treating the later press as a second click in the same word.
    Start-Sleep -Milliseconds ([Windows.Forms.SystemInformation]::DoubleClickTime + 60)
    $rect = Get-Box $Spec.text $Spec.text.IndexOf([string]$Spec.target) $Spec.target
    $x0=[int]($rect.Left + $rect.Width*.1); $x1=[int]($rect.Left + $rect.Width*.9); $y=[int]($rect.Top + $rect.Height*.5)
    if (-not (Test-FieldFocus)) { throw 'The filename lost focus before the drag.' }
    [IfwQaText.Input]::Drag($handle,$SubjectId,$x0,$x1,$y)
    [void](Wait-Observation { $Case.lastSelection = Current-Selection; $Case.lastSelection.value -ceq $Spec.target } 'native pointer selection')
    $Case.dragScreen = @($x0,$x1,$y)
    $Case.selected = $Case.lastSelection.value
    $Case.selectedAt = $Case.lastSelection.start
    if ($Spec.visualIndices.Count) {
        $Case.characters = @(foreach ($i in $Spec.visualIndices) {
            $r = Get-Box $Spec.text $i $Spec.text.Substring($i,1)
            [ordered]@{ index=$i; left=$r.Left; right=$r.Right }
        })
    }
    $Case.deleteStage = 'keyboard'
    Press-Key Delete
    $Case.deleteSubmitted = $true
    $Case.deleteStage = 'readback'
    [void](Wait-Observation {
        try {
            $current = Get-Field 'Dateiname' ([Windows.Automation.ControlType]::Edit)
            if ($null -eq $current) { return $false }
            $focused = [Windows.Automation.AutomationElement]::FocusedElement
            if ($current.Current.ProcessId -ne $SubjectId -or $current.Current.IsPassword -or
                    -not [Windows.Automation.Automation]::Compare($current, $focused) -or
                    [IfwObservedWindow]::GetForegroundWindow() -ne $handle) {
                throw 'The owned normal filename lost foreground or keyboard focus after Delete.'
            }
            $valuePatternNow = $current.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
            $range = $current.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern).DocumentRange
            if ($null -eq $valuePatternNow -or $null -eq $range) {
                $Case.lastReadFailure = [ordered]@{ type='missingPatternOrRange'; hresult=$null }
                return $false
            }
            $value = $valuePatternNow.Current.Value
            $document = $range.GetText(-1)
            $Case.afterValue = if ($value -cin @($Spec.text,$Spec.after)) { $value } else { '<unexpected>' }
            $Case.after = if ($document -cin @($Spec.text,$Spec.after)) { $document } else { '<unexpected>' }
            return $Case.after -ceq $Spec.after -and $Case.afterValue -ceq $Spec.after
        } catch {
            $failure = Get-UiaReadFailure $_
            if ($null -eq $failure) { throw }
            $Case.lastReadFailure = $failure
            return $false
        }
    } 'native Delete result in both text patterns')
    $Case.deleteStage = 'verified'
}

function Record-Pixels($Sample) {
    Set-Sample $plan.sample
    $before = $field.Current.BoundingRectangle
    $cells = foreach ($cp in $plan.glyphs) {
        $s = [char]::ConvertFromUtf32($cp)
        $r = Get-Box $plan.sample $plan.sample.IndexOf($s) $s
        [pscustomobject]@{ scalar=$cp; rect=$r }
    }
    Press-Key Tab
    [void](Wait-Observation { (Get-SubjectFocus) -ceq 'Kennwort' } 'caret-free filename')
    Start-Sleep -Milliseconds 180
    $r = $field.Current.BoundingRectangle
    if (-not $r.Equals($before) -or $textPattern.DocumentRange.GetText(-1) -cne $plan.sample) {
        throw 'The filename moved or changed before capture.'
    }
    # Use the maintained field-only DX12 capture and its exact physical crop origin.
    $x = [int][Math]::Ceiling($r.Left+2); $y = [int][Math]::Ceiling($r.Top+2)
    $w = [int][Math]::Floor($r.Right)-$x-2; $h = [int][Math]::Floor($r.Bottom)-$y-2
    [IfwQaText.Input]::RequireRegion($handle,$SubjectId,$x,$y,$w,$h)
    $Sample.capture = Capture-SubjectField $field 'glyphs'
    [IfwQaText.Input]::RequireRegion($handle,$SubjectId,$x,$y,$w,$h)
    $bitmap = [Drawing.Bitmap]::new("$OutputFile.glyphs.png")
    try {
        if ($bitmap.Width -ne $w -or $bitmap.Height -ne $h) { throw 'Inconsistent physical field crop.' }
        # The existing platform-independent font observer reads lossless P6 frames.
        $frame = "$OutputFile.glyphs.ppm"
        $stream = [IO.File]::Open($frame,'CreateNew','Write','None')
        try {
            $header = [Text.Encoding]::ASCII.GetBytes("P6" + [char]10 + "$w $h" + [char]10 + "255" + [char]10)
            $stream.Write($header,0,$header.Length)
            for ($j=0; $j -lt $h; ++$j) { for ($i=0; $i -lt $w; ++$i) {
                $p = $bitmap.GetPixel($i,$j)
                $stream.WriteByte($p.R); $stream.WriteByte($p.G); $stream.WriteByte($p.B)
            } }
        } finally { $stream.Dispose() }
        $Sample.frameSha256 = (Get-FileHash $frame).Hash.ToLowerInvariant()
        foreach ($cell in $cells) {
            $r = $cell.rect
            $left = [int][Math]::Floor($r.Left)-$x; $top = [int][Math]::Floor($r.Top)-$y
            $cw = [int][Math]::Ceiling($r.Right)-$x-$left; $ch = [int][Math]::Ceiling($r.Bottom)-$y-$top
            if ($left -lt 0 -or $top -lt 0 -or $cw -le 0 -or $ch -le 0 -or $left+$cw -gt $w -or $top+$ch -gt $h) {
                throw 'A UIA glyph rectangle is clipped in the filename capture.'
            }
            $Sample.cells += [ordered]@{ scalar=$cell.scalar; crop=@($left,$top,$cw,$ch) }
        }
    } finally { $bitmap.Dispose() }
}

$previousDpi = [IntPtr]::Zero
try {
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms,System.Drawing
    $shared = Join-Path (Split-Path $PSScriptRoot) 'observe-windows-input.ps1'
    $errors=$null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($shared,[ref]$null,[ref]$errors)
    $bridge = @($ast.FindAll({ param($a) $a -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
        $a.StringConstantType -eq 'SingleQuotedHereString' -and $a.Value.Contains('public static class IfwObservedWindow {') },$true))
    if ($errors -or $bridge.Count -ne 1) { throw 'Could not locate the shared HWND and hit-test bridge.' }
    Add-Type -TypeDefinition ($bridge[0].Value + [Environment]::NewLine + [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Pointer.cs')))
    foreach ($name in @('Get-AccessibleName','Get-Field','Get-SubjectFocus','Get-UiaReadFailure','Wait-Observation','Capture-SubjectField')) {
        $definitions = @($ast.FindAll({ param($a) $a -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -ceq $name },$true))
        if ($definitions.Count -ne 1) { throw "Missing shared observer function $name." }
        . ([scriptblock]::Create($definitions[0].Extent.Text))
    }
    $previousDpi = [IfwQaText.Input]::SetThreadDpiAwarenessContext([IntPtr]::new(-4))
    if ($previousDpi -eq [IntPtr]::Zero) { throw 'Physical per-monitor DPI coordinates are unavailable.' }
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    [uint32]$owner = 0
    if (-not [IfwObservedWindow]::GetWindowThreadProcessId($handle,[ref]$owner) -or $owner -ne $SubjectId -or $root.Current.ProcessId -ne $SubjectId) {
        throw 'The Win32 or UIA root differs from the synthetic child.'
    }
    $result.status='unavailable'
    $scope = [Windows.Automation.TreeScope]::Descendants
    $field = Wait-Observation { Get-Field 'Dateiname' ([Windows.Automation.ControlType]::Edit) } 'normal German filename'
    if ($field.Current.ProcessId -ne $SubjectId -or $field.Current.IsPassword) { throw 'Unexpected UIA editor identity.' }
    $valuePattern = $field.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
    $textPattern = $field.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern)
    if ($textPattern.DocumentRange.GetText(-1) -cne $plan.initial -or $valuePattern.Current.Value -cne $plan.initial) {
        throw 'The initial filename differs from the synthetic fixture.'
    }
    $result.field='Dateiname'
    $result.dpi=[IfwObservedWindow]::GetDpiForWindow($handle)
    $result.inputDesktop=[IfwObservedWindow]::OnInputDesktop()
    if ($ReadOnly -or -not $result.inputDesktop) { throw 'The disposable subject is outside the active unlocked console.' }
    $result.setForeground=[IfwObservedWindow]::SetForegroundWindow($handle)
    Focus-Field
    $result.foreground=$true
    $result.status='failed'
    $result.sample=[ordered]@{ status='failed'; cells=@() }
    try { Record-Pixels $result.sample; $result.sample.status='observed' }
    catch { $result.sample.error=$_.Exception.GetBaseException().Message }
    Save-Result
    foreach ($spec in $plan.cases) {
        $case=[ordered]@{ text=$spec.text; status='failed'; arrowIndices=@() }
        $result.cases += $case
        try { Record-Editing $spec $case; $case.status='observed' }
        catch {
            $cause=$_.Exception.GetBaseException()
            $case.error=$cause.Message
            $case.errorType=$cause.GetType().FullName
            $case.errorHresult=('0x{0:X8}' -f $cause.HResult)
        }
        Save-Result
    }
    if ($result.sample.status -ne 'observed' -or @($result.cases | Where-Object status -ne 'observed').Count) {
        throw 'One or more native text observations failed.'
    }
    $result.status='observed'
} catch { $result.error=$_.Exception.GetBaseException().Message; throw }
finally {
    if ($previousDpi -ne [IntPtr]::Zero) { [void][IfwQaText.Input]::SetThreadDpiAwarenessContext($previousDpi) }
    Save-Result
}
