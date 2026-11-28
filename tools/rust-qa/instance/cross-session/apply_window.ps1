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
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd, uint msg, UIntPtr key, IntPtr data);
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
    $item = FindControl ([Windows.Automation.ControlType]::Edit) $strings[$key]
    $item.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).SetValue($value)
}
function SaveWindowImage([string]$name) {
    $r = BoundRoot
    $rect=$r.Current.BoundingRectangle
    $image=[Drawing.Bitmap]::new([int]$rect.Width,[int]$rect.Height)
    $graphics=[Drawing.Graphics]::FromImage($image)
    $dc=$graphics.GetHdc()
    try { $ok=[ApplyWindowNative]::PrintWindow([IntPtr]$Hwnd,$dc,2) } finally { $graphics.ReleaseHdc($dc); $graphics.Dispose() }
    try {
        if (!$ok) { throw 'The original WPF window did not supply a capture' }
        $image.Save((Join-Path $area $name),[Drawing.Imaging.ImageFormat]::Png)
    } finally { $image.Dispose() }
}
function EnterFolder($tab,$value) {
    # The shipping tab renders its first editor below General, outside the UIA tab content tree.
    $root=BoundRoot
    $r=$tab.Current.BoundingRectangle
    if (!$tab.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected -or $r.IsEmpty) {
        throw 'The source editor General tab is not selected'
    }
    $point=[ApplyWindowNative+Point]::new()
    $point.x=[int]($r.Left+$r.Width*.75)
    $point.y=[int]($r.Bottom+$r.Height*1.7)
    if (!$root.Current.BoundingRectangle.Contains($point.x,$point.y) -or
        [ApplyWindowNative]::GetAncestor([ApplyWindowNative]::WindowFromPoint($point),2).ToInt64() -ne $Hwnd) {
        throw 'The observed folder field is outside the original native WPF window'
    }
    SaveWindowImage 'folder-before.png'
    $original=[ApplyWindowNative+Point]::new()
    if (![ApplyWindowNative]::GetCursorPos([ref]$original)) {throw 'Could not read the original pointer'}
    try {
        if (![ApplyWindowNative]::SetCursorPos($point.x,$point.y)) {throw 'The pointer did not reach the observed folder field'}
        if ([ApplyWindowNative]::GetAncestor([ApplyWindowNative]::WindowFromPoint($point),2).ToInt64() -ne $Hwnd) {throw 'Changed native WPF hit'}
        [ApplyWindowNative]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
        [ApplyWindowNative]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
        Start-Sleep -Milliseconds 160
        $focus=[Windows.Automation.AutomationElement]::FocusedElement
        if (!$focus -or $focus.Current.ProcessId -ne $ProcessId -or [ApplyWindowNative]::GetForegroundWindow().ToInt64() -ne $Hwnd) {
            throw 'The original WPF process did not own foreground and keyboard focus'
        }
        $record.folderFocus=@{name=$focus.Current.Name;type=$focus.Current.ControlType.ProgrammaticName;point=@($point.x,$point.y);hwnd=$Hwnd}
        # Send WM_CHAR directly to this held, focused HWND. This cannot route text into another application.
        foreach ($c in $value.ToCharArray()) {
            if ([ApplyWindowNative]::GetForegroundWindow().ToInt64() -ne $Hwnd) {throw 'The original WPF window lost focus'}
            [void][ApplyWindowNative]::SendMessage([IntPtr]$Hwnd,0x0102,[UIntPtr][UInt32][int]$c,[IntPtr]1)
        }
        SaveWindowImage 'folder-entered.png'
    } finally { [void][ApplyWindowNative]::SetCursorPos($original.x,$original.y) }
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
        EnterFolder $tab $draft.media
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
    SaveWindowImage "$Phase-window.png"
    throw
} finally {
    [IO.File]::WriteAllText((Join-Path $area "$Phase-window.json"),($record|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
}
