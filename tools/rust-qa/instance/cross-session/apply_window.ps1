param(
    [ValidateSet('held','released')][string]$Phase,
    [int]$ProcessId,
    [Int64]$Created,
    [Int64]$Hwnd,
    [string]$Work
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -AssemblyName WindowsBase,System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ApplyWindowNative {
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int x, y; }
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr dc, uint flags);
}
'@
$workPath = [IO.Path]::GetFullPath($Work)
$fixtureParent = Join-Path $env:LOCALAPPDATA 'IFW-MsiSessions'
if ((Split-Path $workPath -Parent) -ne $fixtureParent -or (Split-Path $workPath -Leaf) -notlike 'trial-*' -or
    $env:COMPUTERNAME -ne 'IFW-QA25' -or $env:USERNAME -ne 'ifw-test') { throw 'Expected a disposable apply fixture' }
$area = Join-Path $workPath 'apply'
$draft = Get-Content (Join-Path $area 'launch.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$uri = [uri]$draft.url
if ($uri.Scheme -ne 'https' -or $uri.Host -cne '127.0.0.1' -or $uri.AbsolutePath -cne '/api' -or
    $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $draft.key -cne 'synthetic-installed-upload' -or
    $draft.media -ine (Join-Path $area 'media')) { throw 'Invalid synthetic form values' }
$app = 'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe'
if ((Get-FileHash $app).Hash -ine 'b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675') { throw 'Unexpected installed image' }
$strings = @{}
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')
foreach ($file in @('Strings.resx','Strings.de.resx')) {
    $path = Join-Path $repo "src\ImmichFolderWatch.App.Shared\Resources\$file"
    $xml = New-Object Xml.XmlDocument
    $xml.Load($path)
    foreach ($node in $xml.DocumentElement.data) {
        $strings[$node.name] = @($strings[$node.name] | Where-Object { $_ }) + @([string]$node.value)
    }
}
function BoundRoot {
    $proc = Get-Process -Id $ProcessId -ErrorAction Stop
    if ($proc.Path -ine $app -or $proc.StartTime.ToFileTimeUtc() -ne $Created -or
        $proc.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) { throw 'WPF process identity changed' }
    $r = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
    if (!$r -or $r.Current.NativeWindowHandle -ne $Hwnd -or $r.Current.ProcessId -ne $ProcessId -or
        $r.Current.Name -cne 'Immich Folder Watch' -or $r.Current.IsOffscreen) { throw 'WPF root identity changed' }
    return $r
}
function Elements($type) {
    $r = BoundRoot
    $condition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,$type)
    return $r.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)
}
function FindControl($type,$labels) {
    $until = [DateTime]::UtcNow.AddSeconds(8)
    do {
        $matches = @(Elements $type | Where-Object {
            $_.Current.ProcessId -eq $ProcessId -and !$_.Current.IsOffscreen -and $_.Current.IsEnabled -and $labels -ccontains $_.Current.Name
        })
        if ($matches.Count -gt 1) { throw "Ambiguous WPF control $labels" }
        if ($matches.Count -eq 1) {return $matches[0]}
        Start-Sleep -Milliseconds 120
    } while ([DateTime]::UtcNow -lt $until)
    $visible = @(Elements $type | Where-Object { $_.Current.ProcessId -eq $ProcessId } | ForEach-Object { "$($_.Current.AutomationId) $($_.Current.Name) offscreen=$($_.Current.IsOffscreen)" })
    throw "Missing WPF control $labels. Controls of this type: $($visible -join ', ')"
}
function SelectPage($key) {
    $item = FindControl ([Windows.Automation.ControlType]::ListItem) $strings[$key]
    $item.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
}
function SetField($key,$value) {
    if ($key -eq 'UI_FolderPath') {
        $r = BoundRoot
        $rect = $r.Current.BoundingRectangle
        $item = $null
        for ($y = [int]$rect.Top + 8; $y -lt $rect.Bottom -and !$item; $y += 12) {
            for ($x = [int]$rect.Left + 8; $x -lt $rect.Right -and !$item; $x += 48) {
                $point = [ApplyWindowNative+Point]::new()
                $point.x=$x; $point.y=$y
                $native = [ApplyWindowNative]::WindowFromPoint($point)
                if ([ApplyWindowNative]::GetAncestor($native,2).ToInt64() -ne $Hwnd) { continue }
                $hit = [Windows.Automation.AutomationElement]::FromPoint([Windows.Point]::new($x,$y))
                if ($hit -and $hit.Current.ProcessId -eq $ProcessId -and $hit.Current.ControlType -eq [Windows.Automation.ControlType]::Edit -and
                    !$hit.Current.IsOffscreen -and $hit.Current.IsEnabled -and $strings[$key] -ccontains $hit.Current.Name) {
                    $item=$hit
                    $record.folderPoint=@($x,$y)
                }
            }
        }
        if (!$item) { $item = FindControl ([Windows.Automation.ControlType]::Edit) $strings[$key] }
    } else { $item = FindControl ([Windows.Automation.ControlType]::Edit) $strings[$key] }
    $item.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).SetValue($value)
}
$record = [ordered]@{phase=$Phase;pid=$ProcessId;hwnd=$Hwnd;created=$Created;issued=$false;outcome=$null}
try {
    if ($Phase -eq 'held') {
        SelectPage 'UI_Connection'
        SetField 'UI_ServerApiUrl' $draft.url
        SetField 'UI_ApiKey' $draft.key
        SelectPage 'UI_Folders'
        $list = FindControl ([Windows.Automation.ControlType]::List) $strings['UI_WatchSources']
        $entryType = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,[Windows.Automation.ControlType]::ListItem)
        $entries = @($list.FindAll([Windows.Automation.TreeScope]::Children,$entryType))
        if ($entries.Count -ne 1 -or $entries[0].Current.ProcessId -ne $ProcessId) { throw 'Expected the single default watch source' }
        $entries[0].GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
        $tab = FindControl ([Windows.Automation.ControlType]::TabItem) $strings['UI_General']
        $tab.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
        SetField 'UI_FolderPath' $draft.media
    }
    $button = FindControl ([Windows.Automation.ControlType]::Button) $strings['App_SaveAndApply']
    $record.buttonName=$button.Current.Name
    $record.buttonRuntimeId=@($button.GetRuntimeId())
    $record.startQpc=[Diagnostics.Stopwatch]::GetTimestamp()
    $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
    $record.issued=$true
    $end = [DateTime]::UtcNow.AddSeconds(35)
    do {
        $texts = @(Elements ([Windows.Automation.ControlType]::Text) | Where-Object { $_.Current.ProcessId -eq $ProcessId -and !$_.Current.IsOffscreen } | ForEach-Object { $_.Current.Name })
        $prefixes = @($strings['Op_SaveFailedFormat'] | ForEach-Object { $_.Split('{')[0] })
        foreach ($value in $texts) {
            if ($Phase -eq 'held' -and ($prefixes | Where-Object { $value.StartsWith($_) }) -and $value -match 'config\.yaml') { $record.outcome='save-failed';$record.message=$value;break }
            if ($Phase -eq 'released' -and ($strings['Op_SavedApplied'] | Where-Object { $value.StartsWith($_) })) { $record.outcome='saved-applied';$record.message=$value;break }
        }
        if (!$record.outcome) { Start-Sleep -Milliseconds 140 }
    } while (!$record.outcome -and [DateTime]::UtcNow -lt $end)
    if (!$record.outcome) { $record.visibleText=$texts;throw 'No matching shipping Apply outcome on the original WPF window' }
    $record.observedQpc=[Diagnostics.Stopwatch]::GetTimestamp()
} catch {
    $record.error=$_.Exception.Message
    $r = BoundRoot
    $record.controls=@($r.FindAll([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.Condition]::TrueCondition) | Select-Object -First 180 | ForEach-Object {
        "$($_.Current.ControlType.ProgrammaticName) $($_.Current.AutomationId) $($_.Current.Name)"
    })
    $rect=$r.Current.BoundingRectangle
    $image=[Drawing.Bitmap]::new([int]$rect.Width,[int]$rect.Height)
    $graphics=[Drawing.Graphics]::FromImage($image)
    $dc=$graphics.GetHdc()
    try {
        if ([ApplyWindowNative]::PrintWindow([IntPtr]$Hwnd,$dc,2)) { $record.captured=$true }
    } finally { $graphics.ReleaseHdc($dc); $graphics.Dispose() }
    try { if($record.captured){$image.Save((Join-Path $area "$Phase-window.png"),[Drawing.Imaging.ImageFormat]::Png)} } finally {$image.Dispose()}
    throw
} finally {
    [IO.File]::WriteAllText((Join-Path $area "$Phase-window.json"),($record|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
}
