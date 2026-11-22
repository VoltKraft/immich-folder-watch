# Observe only the fresh synthetic title and body on the disposable runner's original desktop.
param([Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{32}$')][string]$Token,
      [Parameter(Mandatory)][string]$Fixture)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:RUNNER_OS -cne 'Windows' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or
    $env:IFW_QA_LATE_NOTIFICATION -cne '1' -or [IO.Path]::GetFullPath($Fixture) -ine (Join-Path $env:RUNNER_TEMP "ifw-shell-$Token") -or
    [IO.File]::ReadAllText((Join-Path $Fixture 'synthetic.fixture')) -cne $Token) { throw 'Expected the disposable notification fixture' }
function Emit([hashtable]$Record) {
    [Console]::Out.WriteLine('NOTICE_OBSERVER ' + ($Record | ConvertTo-Json -Depth 8 -Compress))
    [Console]::Out.Flush()
}
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;

public static class IfwNoticeDesktop {
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    delegate bool Visitor(IntPtr hwnd, IntPtr arg);
    [DllImport("user32",SetLastError=true)] static extern bool EnumDesktopWindows(IntPtr desktop, Visitor cb, IntPtr arg);
    [DllImport("kernel32")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32")] static extern uint GetCurrentProcessId();
    [DllImport("kernel32")] static extern uint WTSGetActiveConsoleSessionId();
    [DllImport("kernel32")] static extern bool ProcessIdToSessionId(uint pid, out uint id);
    [DllImport("kernel32")] public static extern ulong GetTickCount64();
    [DllImport("kernel32")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32")] static extern bool GetExitCodeProcess(IntPtr h, out uint exit);
    [DllImport("kernel32")] static extern bool GetProcessTimes(IntPtr h, out long created, out long ended, out long kernel, out long user);
    [DllImport("kernel32",CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr h, uint flags, StringBuilder path, ref int size);
    [DllImport("advapi32")] static extern bool OpenProcessToken(IntPtr h, uint access, out IntPtr token);
    [DllImport("user32")] static extern IntPtr GetThreadDesktop(uint tid);
    [DllImport("user32")] static extern IntPtr GetProcessWindowStation();
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern bool GetUserObjectInformation(IntPtr h, int kind, StringBuilder value, uint length, out uint used);
    [DllImport("user32",EntryPoint="GetUserObjectInformationW")] static extern bool InputFlag(IntPtr h, int kind, out int value, uint length, out uint used);
    [DllImport("user32")] static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32",SetLastError=true)] static extern bool CloseDesktop(IntPtr h);
    [DllImport("user32")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder cls, int count);
    [DllImport("user32")] static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32")] static extern IntPtr GetAncestor(IntPtr hwnd, uint kind);
    [DllImport("user32")] static extern IntPtr MonitorFromPoint(Point point, uint flags);
    [DllImport("dwmapi")] static extern int DwmGetWindowAttribute(IntPtr hwnd, uint attr, out uint value, int size);
    [DllImport("user32")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);

    public class Root { public long hwnd, creation; public uint pid, session; public string image, windowClass; public bool sameUser; }
    static string ObjName(IntPtr h) {
        var s = new StringBuilder(256); uint used;
        return h != IntPtr.Zero && GetUserObjectInformation(h,2,s,512,out used) ? s.ToString() : "";
    }
    static bool OnDefault(IntPtr h) {
        int flag; uint ignored;
        return ObjName(h) == "Default" && InputFlag(h,6,out flag,4,out ignored) && flag != 0;
    }
    public static bool Active() {
        uint id;
        if (!ProcessIdToSessionId(GetCurrentProcessId(),out id) || id == 0 || id != WTSGetActiveConsoleSessionId() ||
            ObjName(GetProcessWindowStation()) != "WinSta0" || !OnDefault(GetThreadDesktop(GetCurrentThreadId()))) return false;
        IntPtr h = OpenInputDesktop(0,false,1);
        if (h == IntPtr.Zero) return false;
        try { return OnDefault(h); }
        finally { if (!CloseDesktop(h)) throw new Win32Exception(Marshal.GetLastWin32Error()); }
    }
    static readonly string windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
    static readonly HashSet<string> images = new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
        Path.Combine(windows,"explorer.exe"), Path.Combine(windows,@"System32\ShellHost.exe"),
        Path.Combine(windows,@"SystemApps\ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe"),
        Path.Combine(windows,@"SystemApps\Microsoft.Windows.ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe"),
        Path.Combine(windows,@"SystemApps\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\ShellHost.exe")
    };
    static void Close(IntPtr h) { if (!CloseHandle(h)) throw new Win32Exception(Marshal.GetLastWin32Error()); }
    static Root Describe(IntPtr hwnd) {
        uint pid, session, cloaked;
        uint tid = GetWindowThreadProcessId(hwnd,out pid);
        if (tid == 0 || !OnDefault(GetThreadDesktop(tid)) || !IsWindowVisible(hwnd) || IsIconic(hwnd) ||
            !ProcessIdToSessionId(pid,out session) || session != WTSGetActiveConsoleSessionId() ||
            DwmGetWindowAttribute(hwnd,14,out cloaked,4) != 0 || cloaked != 0) return null;
        var handle = OpenProcess(0x1000,false,pid);
        if (handle == IntPtr.Zero) return null;
        try {
            var image = new StringBuilder(32768); int size = image.Capacity;
            uint state; long created, ended, system, user;
            if (!QueryFullProcessImageName(handle,0,image,ref size) || !images.Contains(image.ToString()) ||
                !GetExitCodeProcess(handle,out state) || state != 259 ||
                !GetProcessTimes(handle,out created,out ended,out system,out user)) return null;
            IntPtr token;
            if (!OpenProcessToken(handle,8,out token)) return null;
            try {
                using (var their = new WindowsIdentity(token))
                using (var ours = WindowsIdentity.GetCurrent()) {
                    if (their.User == null || !their.User.Equals(ours.User)) return null;
                }
            } finally { Close(token); }
            var cls = new StringBuilder(256);
            if (GetClassName(hwnd,cls,cls.Capacity) == 0) return null;
            if (Path.GetFileName(image.ToString()).Equals("explorer.exe",StringComparison.OrdinalIgnoreCase) &&
                (cls.ToString() == "CabinetWClass" || cls.ToString() == "ExploreWClass" || cls.ToString() == "Progman" ||
                 cls.ToString() == "WorkerW")) return null;
            return new Root{hwnd=hwnd.ToInt64(),pid=pid,creation=created,session=session,image=image.ToString(),
                            windowClass=cls.ToString(),sameUser=true};
        } finally { Close(handle); }
    }
    public static Root[] Roots() {
        if (!Active()) throw new InvalidOperationException("The original input desktop or console changed");
        var result = new List<Root>();
        Exception error = null;
        if (!EnumDesktopWindows(GetThreadDesktop(GetCurrentThreadId()),delegate(IntPtr hwnd,IntPtr arg) {
            try { var root = Describe(hwnd); if (root != null) result.Add(root); return result.Count <= 128; }
            catch (Exception e) { error = e; return false; }
        },IntPtr.Zero)) {
            if (error != null) throw error;
            throw new InvalidOperationException("Could not enumerate visible notification hosts on the original desktop");
        }
        return result.ToArray();
    }
    public static bool Covers(Root root, int x, int y) {
        if (!Active()) return false;
        var hwnd = new IntPtr(root.hwnd);
        var now = Describe(hwnd);
        var point = new Point{X=x,Y=y};
        var hit = WindowFromPoint(point); uint pid;
        return now != null && now.pid == root.pid && now.creation == root.creation && now.image == root.image &&
               MonitorFromPoint(point,0) != IntPtr.Zero && GetWindowThreadProcessId(hit,out pid) != 0 &&
               pid == root.pid && GetAncestor(hit,2) == hwnd;
    }
}
'@

function Read-Label($Node, $Root, [string]$Expected, $Container, [bool]$AllowParentHit) {
    $c = $Node.Current
    $r = $c.BoundingRectangle
    if ($c.ProcessId -ne $Root.pid -or $c.IsOffscreen -or $c.Name -cne $Expected -or $r.IsEmpty -or
        $r.Width -lt 1 -or $r.Height -lt 1) { return }
    $x = [Math]::Floor($r.Left + $r.Width / 2)
    $y = [Math]::Floor($r.Top + $r.Height / 2)
    if (-not [IfwNoticeDesktop]::Covers($Root,$x,$y)) { return }
    $hit = [Windows.Automation.AutomationElement]::FromPoint([Windows.Point]::new($x,$y))
    # Text often delegates hit testing to its immediate container. Require the actual
    # label or that exact shared container, never another notification in the same flyout.
    $buttonHit = $AllowParentHit -and $null -ne $hit -and [Windows.Automation.Automation]::Compare($hit,$Container) -and
        [Windows.Automation.Automation]::Compare([Windows.Automation.TreeWalker]::RawViewWalker.GetParent($Node),$Container)
    for ($depth = 0; -not $buttonHit -and $null -ne $hit -and $depth -lt 8; $depth++) {
        if ($hit.Current.ProcessId -ne $Root.pid) { return }
        if ([Windows.Automation.Automation]::Compare($hit,$Node)) { $buttonHit = $true; break }
        if ([Windows.Automation.Automation]::Compare($hit,$Container)) { break }
        $hit = [Windows.Automation.TreeWalker]::RawViewWalker.GetParent($hit)
    }
    if ($buttonHit) {
        return @{text=$Expected; pid=$c.ProcessId; bounds=@($r.Left,$r.Top,$r.Right,$r.Bottom); point=@($x,$y)
                 offscreen=$c.IsOffscreen; nativeHit=$true; providerHit=$true; runtimeId=($Node.GetRuntimeId() -join ',')}
    }
}

function Match-Notice($HostWindow, $TitleCondition, $BodyCondition) {
    $uia = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$HostWindow.hwnd)
    if ($uia.Current.ProcessId -ne $HostWindow.pid) { return }
    $scope = [Windows.Automation.TreeScope]::Descendants
    $titles = $uia.FindAll($scope,$TitleCondition)
    if ($titles.Count -ne 1) { return }
    $bodies = $uia.FindAll($scope,$BodyCondition)
    if ($bodies.Count -ne 1) { return }
    $titleNode = $titles.Item(0); $bodyNode = $bodies.Item(0)
    $walker = [Windows.Automation.TreeWalker]::RawViewWalker
    $container = $walker.GetParent($titleNode)
    for ($level = 0; $null -ne $container -and $level -lt 5; $level++) {
        if ($container.Current.ProcessId -ne $HostWindow.pid) { return }
        $parent = $walker.GetParent($bodyNode)
        for ($i = 0; $null -ne $parent -and $i -lt 5; $i++) {
            if ($parent.Current.ProcessId -ne $HostWindow.pid) { break }
            if ([Windows.Automation.Automation]::Compare($parent,$container)) {
                $allowParentHit = -not [Windows.Automation.Automation]::Compare($uia,$container)
                $a = Read-Label $titleNode $HostWindow $title $container $allowParentHit
                $b = Read-Label $bodyNode $HostWindow $body $container $allowParentHit
                if ($null -ne $a -and $null -ne $b -and [IfwNoticeDesktop]::Covers($HostWindow,$a.point[0],$a.point[1]) -and
                    [IfwNoticeDesktop]::Covers($HostWindow,$b.point[0],$b.point[1])) {
                    return @{title=$a; body=$b; host=$HostWindow; container=($container.GetRuntimeId() -join ',')
                             tick=[IfwNoticeDesktop]::GetTickCount64(); desktop='Default'}
                }
                return
            }
            if ([Windows.Automation.Automation]::Compare($uia,$parent)) { break }
            $parent = $walker.GetParent($parent)
        }
        if ([Windows.Automation.Automation]::Compare($container,$uia)) { return }
        $container = $walker.GetParent($container)
    }
}

$title = "IFW notice $Token"; $body = "Synthetic IFW notification $Token"
$name = [Windows.Automation.AutomationElement]::NameProperty
$titleCondition = [Windows.Automation.PropertyCondition]::new($name,$title)
$bodyCondition = [Windows.Automation.PropertyCondition]::new($name,$body)
$oldDpi = [IfwNoticeDesktop]::SetThreadDpiAwarenessContext([IntPtr](-4))
if ($oldDpi -eq [IntPtr]::Zero) { Emit @{stage='unavailable'; reason='Physical coordinate context unavailable'}; exit 2 }
try {
    $roots = [IfwNoticeDesktop]::Roots()
    foreach ($candidate in $roots) {
        try { $existing = Match-Notice $candidate $titleCondition $bodyCondition }
        catch [System.Windows.Automation.ElementNotAvailableException] { continue }
        catch [Runtime.InteropServices.COMException] { continue }
        if ($null -ne $existing) { throw 'The fresh notification was visible before the sender started' }
    }
    Emit @{stage='armed'; tick=[IfwNoticeDesktop]::GetTickCount64(); initialRoots=$roots.Count; preexistingMatch=$false}
    $wait = [Diagnostics.Stopwatch]::StartNew()
    while (-not [IO.File]::Exists((Join-Path $Fixture 'notice.sent'))) {
        if ([IO.File]::Exists((Join-Path $Fixture 'notice.finish'))) { return }
        if ($wait.Elapsed.TotalSeconds -ge 25) { throw 'The notification sender did not announce its single request' }
        Start-Sleep -Milliseconds 25
    }
    if ([IO.File]::ReadAllText((Join-Path $Fixture 'notice.sent')) -cne $Token) { throw 'Notification marker did not match' }
    $scan = [Diagnostics.Stopwatch]::StartNew()
    $samples = 0; $peak = 0; $providerErrors = 0; $lastHresult = $null
    do {
        $liveRoots = [IfwNoticeDesktop]::Roots()
        $samples++; $peak = [Math]::Max($peak,$liveRoots.Count)
        foreach ($candidate in $liveRoots) {
            try { $match = Match-Notice $candidate $titleCondition $bodyCondition }
            catch [System.Windows.Automation.ElementNotAvailableException] { $providerErrors++; $lastHresult=$_.Exception.HResult; continue }
            catch [Runtime.InteropServices.COMException] { $providerErrors++; $lastHresult=$_.Exception.HResult; continue }
            if ($null -ne $match) {
                Emit @{stage='visible'; match=$match; samples=$samples; peakKnownRoots=$peak; providerErrors=$providerErrors}
                return
            }
        }
        if ([IO.File]::Exists((Join-Path $Fixture 'notice.finish'))) { break }
        Start-Sleep -Milliseconds 100
    } while ($scan.Elapsed.TotalSeconds -lt 10)
    Emit @{stage='unavailable'; reason='No exact visible title and body on the observed native Shell hosts'; samples=$samples
           peakKnownRoots=$peak; providerErrors=$providerErrors; lastHresult=$lastHresult}
    exit 2
} catch {
    $cause = $_.Exception.GetBaseException()
    if ($cause -is [InvalidOperationException] -or $cause -is [Runtime.InteropServices.COMException]) {
        Emit @{stage='unavailable'; reason=$cause.Message; hresult=$cause.HResult}
        exit 2
    }
    throw
} finally {
    if ([IfwNoticeDesktop]::SetThreadDpiAwarenessContext($oldDpi) -eq [IntPtr]::Zero) { throw 'Could not restore the observer thread DPI context' }
}
