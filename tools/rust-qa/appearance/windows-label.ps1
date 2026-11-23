param(
    [Parameter(Mandatory)][int]$SubjectId,
    [Parameter(Mandatory)][long]$WindowHandle,
    [Parameter(Mandatory)][ValidateSet('original','changed','restored')][string]$Phase,
    [Parameter(Mandatory)][string]$OutputFile
)
$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'A synthetic Windows profile is required.' }
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Drawing
$qa = Split-Path $PSScriptRoot
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $qa 'observe-windows-input.ps1'),[ref]$null,[ref]$errors)
$bridge = @($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
    $n.StringConstantType -eq 'SingleQuotedHereString' -and $n.Value.Contains('public static class IfwObservedWindow {')},$true))
if ($errors -or $bridge.Count -ne 1) { throw 'Could not locate the shared native window observer.' }
Add-Type -TypeDefinition ($bridge[0].Value + [Environment]::NewLine + [IO.File]::ReadAllText((Join-Path $qa 'windows-text/Pointer.cs')))
$handle = [IntPtr]::new($WindowHandle)
$report = [ordered]@{phase=$Phase; pid=$SubjectId; hwnd=$WindowHandle; status='failed'; samples=@()}
$oldDpi = [IfwQaText.Input]::SetThreadDpiAwarenessContext([IntPtr]::new(-4))
try {
    if ($oldDpi -eq [IntPtr]::Zero) { throw 'Cannot determine physical label coordinates.' }
    [uint32]$owner = 0
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    if (-not [IfwObservedWindow]::GetWindowThreadProcessId($handle,[ref]$owner) -or $owner -ne $SubjectId -or
        $root.Current.ProcessId -ne $SubjectId -or -not [IfwObservedWindow]::OnInputDesktop()) {
        throw 'The window and input desktop do not belong to this test.'
    }
    if ($Phase -ceq 'original' -and [IfwObservedWindow]::GetForegroundWindow() -ne $handle) {
        $report.foregroundRequest = [IfwObservedWindow]::SetForegroundWindow($handle)
    }
    $text = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,
                                                        [Windows.Automation.ControlType]::Text)
    $name = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty, 'Dateiname')
    $condition = [Windows.Automation.AndCondition]::new($text, $name)
    $until = [DateTime]::UtcNow.AddSeconds(7)
    do {
        $labels = $root.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)
        if ($labels.Count -eq 1 -and [IfwObservedWindow]::GetForegroundWindow() -eq $handle) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $until)
    if ($labels.Count -ne 1) { throw 'The owned GUI has no unique Dateiname static label.' }
    $label = $labels.Item(0)
    $bounds = $label.Current.BoundingRectangle
    $x = [int][Math]::Ceiling($bounds.Left)
    $y = [int][Math]::Ceiling($bounds.Top)
    $width = [int][Math]::Floor($bounds.Right) - $x
    $height = [int][Math]::Floor($bounds.Bottom) - $y
    if ($label.Current.ProcessId -ne $SubjectId -or $label.Current.IsOffscreen -or $width -lt 4 -or $width -gt 512 -or
        $height -lt 4 -or $height -gt 96) { throw 'The static label has no usable owned capture rectangle.' }
    $report.label = 'Dateiname'
    $report.rect = @($x,$y,$width,$height)
    $report.runtimeId = $label.GetRuntimeId()
    foreach ($index in 1..2) {
        [IfwQaText.Input]::RequireRegion($handle,$SubjectId,$x,$y,$width,$height)
        $bitmap = [Drawing.Bitmap]::new($width,$height,[Drawing.Imaging.PixelFormat]::Format24bppRgb)
        try {
            $graphics = [Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.CopyFromScreen($x,$y,0,0,$bitmap.Size,[Drawing.CopyPixelOperation]::SourceCopy)
            } finally { $graphics.Dispose() }
            [IfwQaText.Input]::RequireRegion($handle,$SubjectId,$x,$y,$width,$height)
            if ($label.Current.ProcessId -ne $SubjectId -or $label.Current.Name -cne 'Dateiname' -or
                -not $bounds.Equals($label.Current.BoundingRectangle)) { throw 'The owned label changed during capture.' }
            $image = "$OutputFile.$index.bmp"
            $bitmap.Save($image,[Drawing.Imaging.ImageFormat]::Bmp)
            $report.samples += @{file=[IO.Path]::GetFileName($image); sha256=(Get-FileHash -Algorithm SHA256 $image).Hash.ToLowerInvariant()}
        } finally { $bitmap.Dispose() }
        if ($index -eq 1) { Start-Sleep -Milliseconds 130 }
    }
    $report.status = 'observed'
} catch { $report.error = $_.Exception.GetBaseException().Message; throw }
finally {
    if ($oldDpi -ne [IntPtr]::Zero) { [void][IfwQaText.Input]::SetThreadDpiAwarenessContext($oldDpi) }
    [IO.File]::WriteAllText($OutputFile,($report | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
