# Observe an ordinary WinRT send through physical hit testing on the isolated x64 console.
param([Parameter(Mandatory)][string]$NativeDirectory, [Parameter(Mandatory)][string]$OutputDirectory,
      [Parameter(Mandatory)][switch]$IsolatedVm)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (!$IsolatedVm -or $env:GITHUB_ACTIONS -or ![Environment]::Is64BitProcess -or
    ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or
    (Split-Path -Leaf $NativeDirectory) -cne 'toast-history-x86_64-pc-windows-msvc' -or
    (Test-Path $OutputDirectory) -or (Test-Path "$NativeDirectory\result.json")) {
    throw 'Use a fresh native sender trial and a fresh output directory on the isolated standard-user console'
}
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$report = [ordered]@{status='unavailable'; frequency=[Diagnostics.Stopwatch]::Frequency}
try {
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing,System.Windows.Forms
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class IfwToastPoint {
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    [DllImport("user32")] static extern IntPtr WindowFromPoint(Point p);
    [DllImport("user32")] static extern IntPtr GetAncestor(IntPtr h, uint kind);
    [DllImport("user32")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int count);
    [DllImport("user32")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr v);
    public static IntPtr Root(int x, int y) { return GetAncestor(WindowFromPoint(new Point{X=x,Y=y}),2); }
    public static uint Pid(IntPtr h) { uint pid; GetWindowThreadProcessId(h,out pid); return pid; }
    public static string Class(IntPtr h) { var s=new StringBuilder(256); GetClassName(h,s,s.Capacity); return s.ToString(); }
}
'@
    [void][IfwToastPoint]::SetThreadDpiAwarenessContext([IntPtr](-4))
    $area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    $expectedImage = Join-Path $env:SystemRoot 'SystemApps\ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe'
    $conditionType = [Windows.Automation.AutomationElement]
    $scope = [Windows.Automation.TreeScope]::Descendants
    $start = [Diagnostics.Stopwatch]::StartNew()
    $token = $null
    while (!$token -and $start.Elapsed.TotalSeconds -lt 100) {
        $line = Get-Content -Raw "$NativeDirectory\000-prepare.txt" -ErrorAction SilentlyContinue
        if ($line -match '(?m)^aumid=IFW\.RustQA\.Toast\.([0-9a-f]{32})\r?$') { $token = $Matches[1] }
        if (!$token) { Start-Sleep -Milliseconds 100 }
    }
    if (!$token) { throw 'Missing the AUMID of the active native sender trial' }
    $report.token = $token
    $titles = @("IFW synthetic normal $token","Rust normal notification history $token")
    $conditions = @($titles | ForEach-Object {
        [Windows.Automation.PropertyCondition]::new($conditionType::NameProperty,$_)
    })
    function Read-PhysicalPopup([IntPtr]$root) {
        if ($root -eq [IntPtr]::Zero -or [IfwToastPoint]::Class($root) -cne 'Windows.UI.Core.CoreWindow') { return }
        $ownerId = [IfwToastPoint]::Pid($root)
        $owner = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
        if (!$owner -or $owner.Path -ine $expectedImage -or $owner.SessionId -ne $session) { return }
        $window = $conditionType::FromHandle($root)
        if ($window.Current.ProcessId -ne $ownerId) { return }
        $labels = @()
        foreach ($condition in $conditions) {
            $matches = $window.FindAll($scope,$condition)
            if ($matches.Count -ne 1) { return }
            $node = $matches.Item(0)
            $properties = $node.Current
            $b = $properties.BoundingRectangle
            if ($properties.ProcessId -ne $ownerId -or $properties.IsOffscreen -or $b.IsEmpty) { return }
            $x = [int]($b.X+$b.Width/2)
            $y = [int]($b.Y+$b.Height/2)
            if ([IfwToastPoint]::Root($x,$y) -ne $root) { return }
            $labels += [ordered]@{text=$properties.Name; runtimeId=($node.GetRuntimeId() -join ',');
                bounds=@($b.Left,$b.Top,$b.Right,$b.Bottom); point=@($x,$y); physicalHwnd=$root.ToInt64()}
        }
        # Crop from the original screen DC. Keep both complete label rectangles in the image.
        $left = [int]([Math]::Min($labels[0].bounds[0],$labels[1].bounds[0])-5)
        $top = [int]([Math]::Min($labels[0].bounds[1],$labels[1].bounds[1])-5)
        $width = [int]([Math]::Max($labels[0].bounds[2],$labels[1].bounds[2])-$left+5)
        $height = [int]([Math]::Max($labels[0].bounds[3],$labels[1].bounds[3])-$top+5)
        if ($width -lt 12 -or $width -gt 1200 -or $height -lt 12 -or $height -gt 480) { return }
        $bitmap = [Drawing.Bitmap]::new($width,$height)
        $graphics = [Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen($left,$top,0,0,$bitmap.Size)
            foreach ($label in $labels) {
                if ([IfwToastPoint]::Root($label.point[0],$label.point[1]) -ne $root) { return }
            }
            $bitmap.Save("$OutputDirectory\popup.png",[Drawing.Imaging.ImageFormat]::Png)
        } finally { $graphics.Dispose(); $bitmap.Dispose() }
        return [ordered]@{hwnd=$root.ToInt64(); windowClass=[IfwToastPoint]::Class($root); pid=$ownerId;
            image=$owner.Path; session=$session; createdUtc=$owner.StartTime.ToUniversalTime().ToString('o');
            labels=$labels; capture=@($left,$top,$width,$height); imageSha256=(Get-FileHash "$OutputDirectory\popup.png").Hash.ToLowerInvariant()}
    }
    $start.Restart()
    while ($start.Elapsed.TotalSeconds -lt 80 -and !(Test-Path "$NativeDirectory\result.json")) {
        $report.beginQpc = [Diagnostics.Stopwatch]::GetTimestamp()
        $root = [IfwToastPoint]::Root(($area.Right-260),($area.Bottom-97))
        try { $observed = Read-PhysicalPopup $root }
        catch [Windows.Automation.ElementNotAvailableException] { $observed = $null }
        if ($observed) {
            $report.endQpc = [Diagnostics.Stopwatch]::GetTimestamp()
            $report.popup = $observed
            $report.status = 'observed'
            break
        }
        Start-Sleep -Milliseconds 100
    }
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
} finally {
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$OutputDirectory\physical.json"
}
