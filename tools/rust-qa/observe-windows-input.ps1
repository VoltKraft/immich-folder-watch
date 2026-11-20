param(
    [Parameter(Mandatory)][int]$SubjectId,
    [Parameter(Mandatory)][long]$WindowHandle,
    [Parameter(Mandatory)][string]$SubjectLog,
    [Parameter(Mandatory)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'Use the disposable native GUI launcher.' }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class IfwObservedWindow {
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint id);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber();
}
'@

$handle = [IntPtr]::new($WindowHandle)
$result = [ordered]@{ processId = $SubjectId; status = 'failed'; focus = @() }
$scope = [Windows.Automation.TreeScope]::Descendants
$root = $null

function Wait-Observation([scriptblock]$Read, [string]$Label) {
    $until = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $value = & $Read
        if ($value) { return $value }
        Start-Sleep -Milliseconds 70
    } while ([DateTime]::UtcNow -lt $until)
    throw "Timed out observing $Label."
}

function Get-AccessibleName($Element) {
    $name = $Element.Current.Name
    if ($name) { return $name }
    $label = $Element.Current.LabeledBy
    if ($null -ne $label) { return $label.Current.Name }
    return ''
}

function Get-Field([string]$Name, $Role) {
    $condition = [Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::ControlTypeProperty, $Role)
    foreach ($element in $root.FindAll($scope, $condition)) {
        if ((Get-AccessibleName $element) -ceq $Name) { return $element }
    }
    return $null
}

function Get-SubjectFocus {
    $element = [Windows.Automation.AutomationElement]::FocusedElement
    if ($null -ne $element -and $element.Current.ProcessId -eq $SubjectId) {
        return (Get-AccessibleName $element)
    }
    return ''
}

function Send-SubjectKeys([string]$Keys) {
    [uint32]$owner = 0
    [void][IfwObservedWindow]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -ne $SubjectId -or [IfwObservedWindow]::GetForegroundWindow() -ne $handle) {
        throw 'The synthetic window does not own foreground input.'
    }
    [Windows.Forms.SendKeys]::SendWait($Keys)
}

function Get-FieldText($Element) {
    $pattern = $null
    if ($Element.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        return $pattern.Current.Value
    }
    if ($Element.TryGetCurrentPattern([Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
        return $pattern.DocumentRange.GetText(64)
    }
    throw 'The filename editor provides neither ValuePattern nor TextPattern.'
}

try {
    [uint32]$owner = 0
    [void][IfwObservedWindow]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -ne $SubjectId) { throw 'The HWND does not belong to the observed child.' }
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    if ($root.Current.ProcessId -ne $SubjectId) { throw 'UI Automation returned a different process.' }
    $result.dpi = [IfwObservedWindow]::GetDpiForWindow($handle)
    $result.monitorCount = [Windows.Forms.Screen]::AllScreens.Length
    $bounds = [Windows.Forms.Screen]::FromHandle($handle).Bounds
    $result.monitorPixels = @($bounds.Width, $bounds.Height)
    if ($result.dpi -eq 0) { throw 'Could not observe the native window DPI.' }
    $edit = [Windows.Automation.ControlType]::Edit
    $button = [Windows.Automation.ControlType]::Button
    $file = Wait-Observation { Get-Field 'Dateiname' $edit } 'German filename label'
    $password = Wait-Observation { Get-Field 'Kennwort' $edit } 'German password label'
    $english = Wait-Observation { Get-Field 'English' $button } 'language button'
    $result.germanLabels = @((Get-AccessibleName $file), (Get-AccessibleName $password), (Get-AccessibleName $english))
    $result.passwordProperty = $password.Current.IsPassword
    foreach ($element in @($file, $password, $english)) {
        if (-not $element.Current.IsKeyboardFocusable) { throw 'A named control is not keyboard focusable.' }
    }
    if (-not $result.passwordProperty) { throw 'Password editor lacks its UI Automation protected property.' }
    [void][IfwObservedWindow]::SetForegroundWindow($handle)
    $result.foreground = Wait-Observation { [IfwObservedWindow]::GetForegroundWindow() -eq $handle } 'owned foreground'
    for ($i = 0; $i -lt 7; $i++) {
        $name = Get-SubjectFocus
        if ($name -cin @('Dateiname','Kennwort','English')) { $result.focus += $name }
        if ($name -ceq 'Kennwort') { break }
        Send-SubjectKeys '{TAB}'
        Start-Sleep -Milliseconds 125
    }
    if ((Get-SubjectFocus) -cne 'Kennwort') { throw 'Tab did not reach the password editor.' }
    $length = 0
    foreach ($key in @('x','y','z')) {
        Send-SubjectKeys $key
        $length++
        [void](Wait-Observation {
            [IO.File]::ReadAllText($SubjectLog).Contains("EDIT masked chars=$length")
        } 'password edit length')
    }
    $result.passwordCharactersTyped = $length
    # A protected provider may reject access, omit a pattern, or return masks.
    # Record only the behavior, never the provider's returned password string.
    $result.passwordPatterns = [ordered]@{}
    foreach ($kind in @('Value','Text')) {
        $pattern = $null
        $id = if ($kind -eq 'Value') { [Windows.Automation.ValuePattern]::Pattern }
              else { [Windows.Automation.TextPattern]::Pattern }
        if (-not $password.TryGetCurrentPattern($id, [ref]$pattern)) {
            $result.passwordPatterns[$kind] = 'unavailable'
            continue
        }
        try {
            $value = if ($kind -eq 'Value') { $pattern.Current.Value }
                     else { $pattern.DocumentRange.GetText(8) }
        } catch {
            $result.passwordPatterns[$kind] = 'access-refused'
            continue
        }
        if ($value -and $value -cne ([string][char]0x2022 * 3)) {
            throw 'Protected text provider exposed an unexpected value.'
        }
        $result.passwordPatterns[$kind] = if ($value) { 'three-masks' } else { 'empty' }
    }
    Send-SubjectKeys '{TAB}'
    [void](Wait-Observation { (Get-SubjectFocus) -ceq 'English' } 'language button focus')
    $result.focus += 'English'
    Send-SubjectKeys ' '
    $file = Wait-Observation { Get-Field 'Filename' $edit } 'English filename label'
    $password = Wait-Observation { Get-Field 'Password' $edit } 'English password label'
    $result.englishLabels = @((Get-AccessibleName $file), (Get-AccessibleName $password))
    Send-SubjectKeys '{TAB}'
    [void](Wait-Observation { (Get-SubjectFocus) -ceq 'Filename' } 'translated filename focus')
    $result.focus += 'Filename'
    $expected = 'Gr' + [char]0xfc + [char]0xdf + 'e ' + [char]0x2013 + ' Sommer.jpg'
    if ((Get-FieldText $file) -cne $expected) { throw 'Synthetic Unicode filename differs before copy.' }
    $before = [IfwObservedWindow]::GetClipboardSequenceNumber()
    Send-SubjectKeys '^a'
    Send-SubjectKeys '^c'
    [void](Wait-Observation { [IfwObservedWindow]::GetClipboardSequenceNumber() -ne $before } 'clipboard change')
    [void](Wait-Observation { [Windows.Forms.Clipboard]::GetText() -ceq $expected } 'copied synthetic name')
    Send-SubjectKeys '{BACKSPACE}'
    [void](Wait-Observation { (Get-FieldText $file) -ceq '' } 'empty filename after clear')
    Send-SubjectKeys '^v'
    [void](Wait-Observation { (Get-FieldText $file) -ceq $expected } 'native Unicode paste')
    $result.unicodeClipboardRoundTrip = $true
    $result.status = 'passed'
} catch {
    $result.error = $_.Exception.Message
    throw
} finally {
    [IO.File]::WriteAllText($OutputFile, ($result | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
}
