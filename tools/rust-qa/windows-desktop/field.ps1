param(
    [Parameter(Mandatory=$true)][int]$SubjectId,
    [Parameter(Mandatory=$true)][long]$WindowHandle,
    [Parameter(Mandatory=$true)][string]$OutputFile
)
$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'The private fixture launcher is required.' }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]::new($WindowHandle))
if ($root.Current.ProcessId -ne $SubjectId) { throw 'The UIA root belongs to a different process.' }
$condition = [Windows.Automation.PropertyCondition]::new(
    [Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Edit)
$until = [DateTime]::UtcNow.AddSeconds(12)
do {
    foreach ($field in $root.FindAll([Windows.Automation.TreeScope]::Descendants, $condition)) {
        if ($field.Current.ProcessId -ne $SubjectId) { continue }
        $label = $field.Current.LabeledBy
        if ($field.Current.Name -cne 'Dateiname' -and
            ($null -eq $label -or $label.Current.ProcessId -ne $SubjectId -or $label.Current.Name -cne 'Dateiname')) { continue }
        $r = $field.Current.BoundingRectangle
        if ($r.IsEmpty -or $r.Width -le 0 -or $r.Height -le 0) { continue }
        $record = [ordered]@{
            processId = $SubjectId
            hwnd = $WindowHandle
            name = 'Dateiname'
            rect = @($r.Left, $r.Top, $r.Right, $r.Bottom)
            center = @([int]($r.Left + $r.Width / 2), [int]($r.Top + $r.Height / 2))
        }
        [IO.File]::WriteAllText($OutputFile, ($record | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
        return
    }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $until)
throw 'Cannot resolve the owned German filename field geometry.'
