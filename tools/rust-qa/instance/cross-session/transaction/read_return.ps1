param([int]$ProcessId, [Int64]$Created, [Int64]$Hwnd, [string]$Work)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$area = Join-Path $Work 'rust-return'
$app = 'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe'
if ($env:COMPUTERNAME -cne 'IFW-QA25' -or $env:USERNAME -cne 'ifw-test' -or
    [IO.Path]::GetFullPath($Work) -ine 'C:\Users\ifw-test\AppData\Local\IFW-MsiSessions\trial-transaction-01' -or
    !(Test-Path "$area\prepared.json" -PathType Leaf) -or
    (Get-FileHash $app).Hash -ine 'b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675') {
    throw 'Expected the private profile and installed 3.0.4 application.'
}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ReturnWindow {
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int x, y; }
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point p);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hwnd, uint flag);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr dc, uint flags);
}
'@
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')
$strings = @{}
$xml = [Xml.XmlDocument]::new()
$xml.Load((Join-Path $repo 'src\ImmichFolderWatch.App.Shared\Resources\Strings.de.resx'))
foreach ($node in $xml.DocumentElement.data) { $strings[$node.name] = [string]$node.value }
function BoundRoot {
    $process = Get-Process -Id $ProcessId
    if ($process.Path -ine $app -or $process.StartTime.ToFileTimeUtc() -ne $Created -or
        $process.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) {throw 'Original WPF identity changed'}
    $root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
    if ($root.Current.NativeWindowHandle -ne $Hwnd -or $root.Current.ProcessId -ne $ProcessId -or
        $root.Current.Name -cne 'Immich Folder Watch' -or $root.Current.IsOffscreen) {throw 'Original WPF window changed'}
    return $root
}
function FindOwned($type, $label) {
    $end = [DateTime]::UtcNow.AddSeconds(6)
    do {
        $condition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,$type)
        $found = @((BoundRoot).FindAll([Windows.Automation.TreeScope]::Descendants,$condition) | Where-Object {
            $_.Current.ProcessId -eq $ProcessId -and $_.Current.Name -ceq $label -and $_.Current.IsEnabled -and !$_.Current.IsOffscreen
        })
        if ($found.Count -gt 1) {throw "Ambiguous owned control: $label"}
        if ($found.Count -eq 1) {return $found[0]}
        Start-Sleep -Milliseconds 120
    } while ([DateTime]::UtcNow -lt $end)
    throw "Missing visible owned control: $label"
}
function CaptureOwned {
    $bounds = (BoundRoot).Current.BoundingRectangle
    $image = [Drawing.Bitmap]::new([int]$bounds.Width, [int]$bounds.Height)
    $graphics = [Drawing.Graphics]::FromImage($image)
    try {
        $dc = $graphics.GetHdc()
        try { $ok = [ReturnWindow]::PrintWindow([IntPtr]$Hwnd, $dc, 2) }
        finally { $graphics.ReleaseHdc($dc) }
        if (!$ok) {throw 'The restored WPF window could not be captured'}
        $image.Save((Join-Path $area 'returned-window.png'), [Drawing.Imaging.ImageFormat]::Png)
        # The reference region was measured on two independent, native 1080x760
        # WPF captures. Preserve the complete screenshot for detached comparisons.
        if ($image.Width -eq 1080 -and $image.Height -eq 760) {
            $pixels = [Collections.Generic.List[byte]]::new()
            for ($y=394; $y -lt 431; $y++) {
                for ($x=454; $x -lt 690; $x++) {
                    $c = $image.GetPixel($x,$y)
                    $pixels.Add($c.R); $pixels.Add($c.G); $pixels.Add($c.B)
                }
            }
            $record.albumPixels = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($pixels.ToArray())).ToLowerInvariant()
        }
    } finally { $graphics.Dispose(); $image.Dispose() }
}
function ReadField($field, $method) {
    if (!$field -or $field.Current.ProcessId -ne $ProcessId -or
        $field.Current.ControlType -ne [Windows.Automation.ControlType]::Edit -or
        $field.Current.Name -cne $strings['UI_ImmichAlbumName']) {return $false}
    $pattern = $null
    if (!$field.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)) {return $false}
    $record.label = $field.Current.Name
    $record.fieldPid = $field.Current.ProcessId
    $record.runtimeId = @($field.GetRuntimeId())
    $record.album = $pattern.Current.Value
    $record.method = $method
    return $true
}
function ReadVisibleAlbum($tab) {
    # The shipping General content can be absent from the root's UIA descendants.
    # Hit-test the album textbox shown two rows below the selected General tab.
    $root = BoundRoot
    $r = $tab.Current.BoundingRectangle
    if ($r.IsEmpty -or !$tab.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected) {
        throw 'The original General tab was not selected'
    }
    $p = [ReturnWindow+Point]::new()
    $p.x = [int]($r.Left + $r.Width * 0.75)
    $p.y = [int]($r.Bottom + $r.Height * 4.0)
    $record.point = @($p.x, $p.y)
    if (!$root.Current.BoundingRectangle.Contains($p.x,$p.y) -or
        [ReturnWindow]::GetAncestor([ReturnWindow]::WindowFromPoint($p),2).ToInt64() -ne $Hwnd) {
        throw 'The album hit does not belong to the original WPF window'
    }
    $hit = [Windows.Automation.AutomationElement]::FromPoint([Windows.Point]::new($p.x,$p.y))
    $record.hit = @{name=$hit.Current.Name; type=$hit.Current.ControlType.ProgrammaticName; pid=$hit.Current.ProcessId}
    if (ReadField $hit 'UIA FromPoint') {return}
    if ($hit.Current.ProcessId -ne $ProcessId -or
        $record.albumPixels -cne '7181b9d5d68560c9e75f52c349f033a299c5f038aef23a89271adbb86bff6bb6') {
        throw 'The original WPF has no independently matched album field'
    }
    $record.method = 'Owned WPF field pixels'

}
function SelectOwned($item) {
    if ($item.Current.ProcessId -ne $ProcessId -or $item.Current.IsOffscreen) {throw 'Selection owner changed'}
    $item.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
}
$record = [ordered]@{pid=$ProcessId;created=$Created;hwnd=$Hwnd;session=[Diagnostics.Process]::GetCurrentProcess().SessionId
    image=$app;status='started';sourceSha256=(Get-FileHash $PSCommandPath).Hash.ToLowerInvariant()}
try {
    SelectOwned (FindOwned ([Windows.Automation.ControlType]::ListItem) $strings['UI_Folders'])
    $list = FindOwned ([Windows.Automation.ControlType]::List) $strings['UI_WatchSources']
    $condition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,[Windows.Automation.ControlType]::ListItem)
    $entries = @($list.FindAll([Windows.Automation.TreeScope]::Children,$condition))
    $record.sourceCount = $entries.Count
    if ($entries.Count -ne 1) {throw 'Expected one source in the returned configuration'}
    SelectOwned $entries[0]
    $tab = FindOwned ([Windows.Automation.ControlType]::TabItem) $strings['UI_General']
    SelectOwned $tab
    Start-Sleep -Milliseconds 200
    CaptureOwned
    ReadVisibleAlbum $tab
    $record.windowName = (BoundRoot).Current.Name
    if ($record.method -ne 'Owned WPF field pixels' -and $record.album -cne 'Rust – Grüße 日本語 😀: # null') {throw 'Installed WPF returned a different album'}
    $record.status = 'read'
} catch {
    $record.error = $_.Exception.Message
    throw
} finally {
    [IO.File]::WriteAllText((Join-Path $area 'uia.json'),($record | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
