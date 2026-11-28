# Observe an ordinary WinRT send through physical hit testing on the original console.
[CmdletBinding(DefaultParameterSetName='Local')]
param([Parameter(Mandatory)][string]$NativeDirectory, [Parameter(Mandatory)][string]$OutputDirectory,
      [Parameter(Mandatory,ParameterSetName='Local')][switch]$IsolatedVm,
      [Parameter(Mandatory,ParameterSetName='Hosted')][switch]$HostedArm64)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($PSCmdlet.ParameterSetName -ceq 'Hosted') {
    $target = 'aarch64-pc-windows-msvc'
    $base = Join-Path $env:GITHUB_WORKSPACE 'artifacts\rust\windows-services'
    if (!$HostedArm64 -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
        $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ARCH -cne 'ARM64' -or
        $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or
        [IO.Path]::GetFullPath($NativeDirectory) -ine (Join-Path $base "toast-history-$target") -or
        [IO.Path]::GetFullPath($OutputDirectory) -ine (Join-Path $base "toast-physical-$target")) {
        throw 'Expected the native ARM64 rewrite job and its own observation directories'
    }
} else {
    $target = 'x86_64-pc-windows-msvc'
    if (!$IsolatedVm -or $env:GITHUB_ACTIONS -or
        ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Expected the isolated standard-user x64 console'
    }
}
if (![Environment]::Is64BitProcess -or (Split-Path -Leaf $NativeDirectory) -cne "toast-history-$target" -or
    (Test-Path $OutputDirectory) -or (Test-Path "$NativeDirectory\result.json")) {
    throw 'Use a fresh native sender trial and a fresh output directory'
}
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$report = [ordered]@{status='unavailable'; target=$target; frequency=[Diagnostics.Stopwatch]::Frequency}
# The native Windows PowerShell host may lack the Get-FileHash module.
function Get-ObserverDigest([string]$path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($path)
        try { $digest = $algorithm.ComputeHash($stream) } finally { $stream.Dispose() }
        return [BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()
    } finally { $algorithm.Dispose() }
}
if ($HostedArm64) {
    $profileToken = $env:IFW_QA_INVENTORY_TOKEN
    $scratch = Join-Path $env:RUNNER_TEMP ("ifw-shell-" + $profileToken)
    if ($profileToken -cnotmatch '^[a-f0-9]{32}$' -or $env:IFW_QA_ISOLATED -cne '1' -or
        $PWD.Path -ine $scratch -or $env:TEMP -ine $scratch -or $env:TMP -ine $scratch -or
        [IO.File]::ReadAllText((Join-Path $scratch 'synthetic.fixture')) -cne $profileToken) {
        throw 'The physical observer requires its original pinned profile.'
    }
    $report.profileToken = $profileToken
    $report.host = 'github-hosted'
    $report.head = $env:GITHUB_SHA
    $report.run = $env:GITHUB_RUN_ID
    $report.attempt = $env:GITHUB_RUN_ATTEMPT
    $report.job = $env:GITHUB_JOB
    $report.workflow = $env:GITHUB_WORKFLOW
    $report.scriptSha256 = Get-ObserverDigest $PSCommandPath
    $report.observerPid = $PID
}
try {
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing,System.Windows.Forms
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class IfwToastPoint {
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    [DllImport("user32")] static extern IntPtr WindowFromPoint(Point p);
    [DllImport("user32")] static extern IntPtr GetAncestor(IntPtr h, uint kind);
    delegate bool WindowVisitor(IntPtr h, IntPtr data);
    [DllImport("user32")] static extern bool EnumWindows(WindowVisitor visitor, IntPtr data);
    [DllImport("user32")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int count);
    [DllImport("user32")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr v);
    public static IntPtr Root(int x, int y) { return GetAncestor(WindowFromPoint(new Point{X=x,Y=y}),2); }
    public static bool Covers(IntPtr h, int x, int y, int width, int height) {
        for (int row=0; row<height; row++)
            for (int col=0; col<width; col++)
                if (Root(x+col,y+row)!=h) return false;
        return true;
    }
    public static uint Pid(IntPtr h) { uint pid; GetWindowThreadProcessId(h,out pid); return pid; }
    public static string Class(IntPtr h) { var s=new StringBuilder(256); GetClassName(h,s,s.Capacity); return s.ToString(); }
    public static IntPtr[] CoreWindows() {
        var windows = new List<IntPtr>();
        if (!EnumWindows(delegate(IntPtr h, IntPtr unused) {
            if (IsWindowVisible(h) && Class(h) == "Windows.UI.Core.CoreWindow") windows.Add(h);
            return windows.Count <= 128;
        }, IntPtr.Zero)) throw new InvalidOperationException("Could not enumerate Shell window candidates");
        return windows.ToArray();
    }
}
'@
    if ([IfwToastPoint]::SetThreadDpiAwarenessContext([IntPtr](-4)) -eq [IntPtr]::Zero) {
        throw 'Could not select physical monitor coordinates'
    }
    $area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    if ($HostedArm64) {
        $helper = Join-Path $PSScriptRoot 'toast_roots.ps1'
        . $helper
        $report.modernRootsSha256 = Get-ObserverDigest $helper
        $report.discovery = [Collections.Generic.List[object]]::new()
        $viewFilter = Get-ToastViewFilter
        $report.session = $session
        $report.diagnostics = [ordered]@{samples=0; firstQpc=$null; lastQpc=$null; visibleCoreWindowVisits=0
            shellWindowVisits=0; viewQueries=0; normalViewMatches=0; onscreenViewVisits=0; staleElements=0}
    }
    $shellImages = @(
        (Join-Path $env:SystemRoot 'SystemApps\ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe')
        (Join-Path $env:SystemRoot 'SystemApps\Microsoft.Windows.ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe')
    )
    if ($HostedArm64) { $shellImages = @(Get-ToastShellImages) }
    $conditionType = [Windows.Automation.AutomationElement]
    $scope = [Windows.Automation.TreeScope]::Descendants
    $start = [Diagnostics.Stopwatch]::StartNew()
    $token = $null
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'ready'),$target)
    while (!$token -and $start.Elapsed.TotalSeconds -lt 100 -and !(Test-Path "$NativeDirectory\result.json")) {
        $line = Get-Content -Raw "$NativeDirectory\000-prepare.txt" -ErrorAction SilentlyContinue
        if ($line -match '(?m)^aumid=IFW\.RustQA\.Toast\.([0-9a-f]{32})\r?$') { $token = $Matches[1] }
        if (!$token) { Start-Sleep -Milliseconds 100 }
    }
    if (!$token) { $report.reason = 'Sender did not reach notification identity preparation'; return }
    $report.token = $token
    $titles = @("IFW synthetic normal $token","Rust normal notification history $token")
    $conditions = @($titles | ForEach-Object {
        [Windows.Automation.PropertyCondition]::new($conditionType::NameProperty,$_)
    })
    function Read-PhysicalPopup([IntPtr]$root, $uiaRoot) {
        if ($root -eq [IntPtr]::Zero -or [IfwToastPoint]::Class($root) -cne 'Windows.UI.Core.CoreWindow') { return }
        $ownerId = [IfwToastPoint]::Pid($root)
        $owner = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
        if (!$owner -or $owner.SessionId -ne $session -or $shellImages -inotcontains $owner.Path) { return }
        if ($HostedArm64) { $report.diagnostics.shellWindowVisits++ }
        $window = if ($null -ne $uiaRoot) { $uiaRoot } else { $conditionType::FromHandle($root) }
        if ($window.Current.ProcessId -ne $ownerId) { return }
        $surface = $window
        $normalView = $null
        if ($HostedArm64) {
            $views = $window.FindAll([Windows.Automation.TreeScope]::Subtree,$viewFilter)
            $report.diagnostics.viewQueries++
            $report.diagnostics.normalViewMatches += $views.Count
            if ($views.Count -ne 1) { return }
            $surface = $views.Item(0)
            if ($surface.Current.ProcessId -ne $ownerId -or $surface.Current.IsOffscreen) { return }
            $report.diagnostics.onscreenViewVisits++
            $normalView = @{automationId=$surface.Current.AutomationId; runtimeId=($surface.GetRuntimeId() -join ',')}
        }
        $labels = @()
        foreach ($condition in $conditions) {
            $matches = $surface.FindAll($scope,$condition)
            if ($matches.Count -ne 1) { return }
            $node = $matches.Item(0)
            $properties = $node.Current
            $b = $properties.BoundingRectangle
            if ($properties.Name -cne $titles[$labels.Count] -or $properties.ProcessId -ne $ownerId -or $properties.IsOffscreen -or $b.IsEmpty) { return }
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
            if ($HostedArm64) {
                $viewBounds = $surface.Current.BoundingRectangle
                if ($left -lt $viewBounds.Left -or $top -lt $viewBounds.Top -or
                    $left+$width -gt $viewBounds.Right -or $top+$height -gt $viewBounds.Bottom -or
                    ![IfwToastPoint]::Covers($root,$left,$top,$width,$height)) { return }
            }
            $graphics.CopyFromScreen($left,$top,0,0,$bitmap.Size)
            foreach ($label in $labels) {
                if ([IfwToastPoint]::Root($label.point[0],$label.point[1]) -ne $root) { return }
            }
            if ($HostedArm64 -and (![IfwToastPoint]::Covers($root,$left,$top,$width,$height) -or
                [IfwToastPoint]::Pid($root) -ne $ownerId)) { return }
            if ($HostedArm64) {
                $normalView.bounds = @($viewBounds.Left,$viewBounds.Top,$viewBounds.Right,$viewBounds.Bottom)
                $normalView.coveredPixelsBefore = $width*$height
                $normalView.coveredPixelsAfter = $width*$height
            }
            $bitmap.Save("$OutputDirectory\popup.png",[Drawing.Imaging.ImageFormat]::Png)
        } finally { $graphics.Dispose(); $bitmap.Dispose() }
        return [ordered]@{hwnd=$root.ToInt64(); windowClass=[IfwToastPoint]::Class($root); pid=$ownerId;
            image=$owner.Path; session=$session; createdUtc=$owner.StartTime.ToUniversalTime().ToString('o');
            normalView=$normalView; labels=$labels; capture=@($left,$top,$width,$height); imageSha256=(Get-ObserverDigest "$OutputDirectory\popup.png")}
    }
    # A retained notifier can retry its Setting query before reaching the one
    # ordinary Show. Start the screen interval from that sender's own return.
    $start.Restart()
    $showEnd = $null
    while ($null -eq $showEnd -and $start.Elapsed.TotalMinutes -lt 5 -and !(Test-Path "$NativeDirectory\result.json")) {
        foreach ($sender in (Get-ChildItem -LiteralPath $NativeDirectory -Filter '???-post-normal.txt' -File)) {
            $sendLog = Get-Content -Raw -LiteralPath $sender.FullName -ErrorAction SilentlyContinue
            if ($sendLog -match "(?m)^aumid=IFW\.RustQA\.Toast\.$token\r?$" -and
                $sendLog -match '(?m)^suppressPopup=false\r?$' -and $sendLog -match '(?m)^showHresult=0\r?$' -and
                $sendLog -match '(?m)^showReturned=true\r?$' -and $sendLog -match '(?m)^showEndQpc=([1-9][0-9]*)\r?$') {
                $showEnd = [long]$Matches[1]
                break
            }
        }
        if ($null -eq $showEnd) { Start-Sleep -Milliseconds 50 }
    }
    if ($null -eq $showEnd) { $report.reason = 'No completed ordinary Show in the native sender logs'; return }
    while ([Diagnostics.Stopwatch]::GetTimestamp() -le $showEnd + 10L * $report.frequency -and !(Test-Path "$NativeDirectory\result.json")) {
        $report.beginQpc = [Diagnostics.Stopwatch]::GetTimestamp()
        $root = [IfwToastPoint]::Root(($area.Right-260),($area.Bottom-97))
        $candidates = @(@{hwnd=$root; node=$null})
        if ($HostedArm64) {
            $coreWindows = @([IfwToastPoint]::CoreWindows())
            $modern = Get-ToastModernRoots $shellImages $viewFilter $session
            $candidates = @(Get-ToastCandidates $root $coreWindows $modern)
            $visible = [Collections.Generic.HashSet[long]]::new()
            foreach ($h in $coreWindows) { [void]$visible.Add($h.ToInt64()) }
            if ($modern.foreground.core -and $modern.foreground.visible) { [void]$visible.Add($modern.foreground.hwnd) }
            foreach ($item in $modern.nodes) { [void]$visible.Add($item.hwnd) }
            $report.discovery.Add(@{qpc=$report.beginQpc; foreground=$modern.foreground; classic=$coreWindows.Count
                children=$modern.visited; uiaCore=$modern.handled; handlelessShell=$modern.handlelessShell
                unresolvedShell=$modern.unresolvedShell; errors=$modern.errors; uiaQueried=$modern.queried; uniqueCore=$visible.Count})
            $report.diagnostics.samples++
            if ($null -eq $report.diagnostics.firstQpc) { $report.diagnostics.firstQpc = $report.beginQpc }
            $report.diagnostics.lastQpc = $report.beginQpc
            $report.diagnostics.visibleCoreWindowVisits += $visible.Count
        }
        $observed = $null
        foreach ($candidate in $candidates) {
            try { $observed = Read-PhysicalPopup ([IntPtr]$candidate.hwnd) $candidate.node }
            catch [Windows.Automation.ElementNotAvailableException] {
                if ($HostedArm64) { $report.diagnostics.staleElements++ }
                continue
            }
            if ($observed) { break }
        }
        if ($observed) {
            $report.endQpc = [Diagnostics.Stopwatch]::GetTimestamp()
            $report.popup = $observed
            $report.status = 'observed'
            break
        }
        Start-Sleep -Milliseconds 100
    }
    if (!$report.popup) { $report.reason = 'No matching physical Shell banner was observed' }
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
} finally {
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$OutputDirectory\physical.json"
}
