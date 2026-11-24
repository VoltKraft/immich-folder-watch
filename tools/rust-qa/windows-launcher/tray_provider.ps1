# Observe one integrated icon on the pinned Explorer taskbar or its temporary hidden-icons flyout.
param([Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{32}$')][string]$Token,
      [Parameter(Mandatory)][uint32]$PrimaryId, [Parameter(Mandatory)][int64]$Receiver,
      [Parameter(Mandatory)][int64]$Creation, [Parameter(Mandatory)][uint32]$ShellPid,
      [Parameter(Mandatory)][int64]$Bar)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or
    $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or $env:IFW_QA_WINDOWS_TRAY -cne '1' -or
    $env:IFW_QA_ISOLATED -cne '1' -or $env:IFW_QA_WINDOWS_LAUNCHER -cne '1' -or
    $env:IFW_QA_BENCHMARK -cne '1' -or $env:IFW_QA_INVENTORY_TOKEN -cne $Token) {
    throw 'The provider observer requires the isolated hosted launcher trial'
}
$area = Join-Path $env:RUNNER_TEMP "ifw-rw02-$Token"
if ([IO.Path]::GetFullPath($env:IFW_QA_INVENTORY_ROOT) -ine $area -or
    [IO.File]::ReadAllText((Join-Path $area 'inventory.owner')) -cne $Token) { throw 'Unexpected isolated profile' }

function Write-Event([string]$Stage, [hashtable]$Values) {
    $Values.stage = $Stage
    [Console]::Out.WriteLine('IFW_PROVIDER ' + ($Values | ConvertTo-Json -Depth 6 -Compress))
    [Console]::Out.Flush()
}
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public abstract class IfwSyntheticShellObserver {
    [DllImport("user32", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32")] public static extern bool IsWindowVisible(IntPtr hwnd);
}

public sealed class IfwIconSurface : IfwSyntheticShellObserver, IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct Identifier { public uint Size; public IntPtr Owner; public uint Id; public Guid Guid; }
    [DllImport("shell32")] static extern int Shell_NotifyIconGetRect(ref Identifier id, out Rect bounds);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder name, int max);
    [DllImport("user32")] static extern IntPtr GetShellWindow();
    [DllImport("user32")] static extern IntPtr WindowFromPoint(Point p);
    [DllImport("user32")] static extern IntPtr GetAncestor(IntPtr hwnd, uint kind);
    [DllImport("user32")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32")] static extern IntPtr MonitorFromPoint(Point point, uint flags);
    [DllImport("user32")] static extern bool GetCursorPos(out Point point);
    [DllImport("dwmapi")] static extern int DwmGetWindowAttribute(IntPtr hwnd, uint attr, out uint value, int size);
    [DllImport("user32")] static extern IntPtr GetThreadDesktop(uint tid);
    [DllImport("user32")] static extern IntPtr GetProcessWindowStation();
    [DllImport("user32")] static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32", SetLastError=true)] static extern bool CloseDesktop(IntPtr handle);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern bool GetUserObjectInformation(IntPtr obj, int kind, StringBuilder value, uint bytes, out uint used);
    [DllImport("user32", EntryPoint="GetUserObjectInformationW")] static extern bool ReadInputFlag(IntPtr obj, int kind, out int receives, uint bytes, out uint used);
    [DllImport("user32")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32")] static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("user32", SetLastError=true)] static extern int ReleaseDC(IntPtr hwnd, IntPtr dc);
    [DllImport("gdi32")] static extern uint GetPixel(IntPtr dc, int x, int y);
    [DllImport("kernel32")] public static extern ulong GetTickCount64();
    [DllImport("kernel32")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32")] static extern uint WTSGetActiveConsoleSessionId();
    [DllImport("kernel32")] static extern bool ProcessIdToSessionId(uint pid, out uint session);
    [DllImport("kernel32")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32")] static extern bool GetExitCodeProcess(IntPtr handle, out uint status);
    [DllImport("kernel32")] static extern bool GetProcessTimes(IntPtr handle, out long created, out long exited, out long kernel, out long user);
    [DllImport("kernel32", CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr handle, uint flags, StringBuilder path, ref int size);
    [DllImport("kernel32", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    readonly uint pid, shellPid;
    readonly IntPtr receiver, bar;
    readonly long creation, shellCreation;
    IntPtr primaryHandle, shellHandle, originalDpi;

    public sealed class Sample {
        public uint pid, shellPid, id = 23;
        public long hwnd, creation, hit, bar, shellCreation, root, overflow, monitor;
        public int[] rect, point, cursor;
        public string rgb, rootClass, desktop = "Default";
        public Pane pane;
        public bool Matches(Sample b) {
            var arrays=System.Collections.StructuralComparisons.StructuralEqualityComparer;
            return b != null && pid==b.pid && hwnd==b.hwnd && id==b.id && creation==b.creation && shellPid==b.shellPid &&
                shellCreation==b.shellCreation && hit==b.hit && bar==b.bar && root==b.root && overflow==b.overflow &&
                monitor==b.monitor && rgb==b.rgb && rootClass==b.rootClass && desktop==b.desktop && SamePane(pane,b.pane) &&
                arrays.Equals(rect,b.rect) && arrays.Equals(point,b.point) && arrays.Equals(cursor,b.cursor);
        }
    }
    public sealed class Pane {
        public readonly long hwnd; public readonly uint pid, tid; public readonly string windowClass;
        public Pane(long h, uint process, uint thread, string cls) {
            Require(h > 0 && process != 0 && thread != 0 && (cls == "NotifyIconOverflowWindow" || cls == "TopLevelWindowForOverflowXamlIsland"),
                    "Invalid hidden-icons window identity");
            hwnd=h; pid=process; tid=thread; windowClass=cls;
        }
    }
    public sealed class PaneChanged : InvalidOperationException {
        public PaneChanged() : base("The original hidden-icons HWND, process, thread or class changed") {}
    }
    public static bool SamePane(Pane a, Pane b) {
        if (a == null || b == null) return a == b;
        return a.hwnd == b.hwnd && a.pid == b.pid && a.tid == b.tid && a.windowClass == b.windowClass;
    }

    static void Require(bool ok, string reason) { if (!ok) throw new InvalidOperationException(reason); }
    static string ObjectName(IntPtr handle) {
        uint needed;
        var name = new StringBuilder(256);
        return handle != IntPtr.Zero && GetUserObjectInformation(handle, 2, name, 512, out needed) ? name.ToString() : "";
    }
    static bool IsInput(IntPtr handle) {
        int receives; uint needed;
        return ObjectName(handle) == "Default" && ReadInputFlag(handle, 6, out receives, 4, out needed) && receives != 0;
    }
    static void DefaultInput() {
        Require(ObjectName(GetProcessWindowStation()) == "WinSta0" && IsInput(GetThreadDesktop(GetCurrentThreadId())), "Observer thread lost the original input desktop");
        IntPtr input = OpenInputDesktop(0, false, 1);
        Require(input != IntPtr.Zero, "The unlocked console input desktop could not be opened");
        try { Require(IsInput(input), "The active input desktop changed"); }
        finally { if (!CloseDesktop(input)) throw new Win32Exception(Marshal.GetLastWin32Error()); }
    }
    static uint WindowOwner(IntPtr hwnd) {
        uint owner; uint tid = GetWindowThreadProcessId(hwnd, out owner);
        Require(hwnd != IntPtr.Zero && tid != 0 && IsInput(GetThreadDesktop(tid)), "A required window is outside the runner's input desktop");
        return owner;
    }
    static long Identity(IntPtr handle, string path, uint owner) {
        uint status, session; long created, exited, kernel, user;
        var image = new StringBuilder(32768); int length = image.Capacity;
        Require(handle != IntPtr.Zero && GetExitCodeProcess(handle, out status) && status == 259 &&
                QueryFullProcessImageName(handle, 0, image, ref length) &&
                String.Equals(image.ToString(), path, StringComparison.OrdinalIgnoreCase) &&
                ProcessIdToSessionId(owner, out session) && session == WTSGetActiveConsoleSessionId(), "The pinned input-desktop executable or session changed");
        if (!GetProcessTimes(handle, out created, out exited, out kernel, out user)) throw new InvalidOperationException("Missing process creation time");
        return created;
    }
    public IfwIconSurface(uint processId, long ownerHwnd, long expectedCreation, string expectedImage, uint expectedShell, long expectedBar) {
        pid = processId; receiver = new IntPtr(ownerHwnd);
        try {
            DefaultInput();
            originalDpi = SetThreadDpiAwarenessContext(new IntPtr(-4));
            Require(originalDpi != IntPtr.Zero, "The observer could not select physical per-monitor coordinates");
            bar = FindWindow("Shell_TrayWnd", null);
            shellPid = WindowOwner(bar);
            primaryHandle = OpenProcess(0x1000, false, pid);
            shellHandle = OpenProcess(0x1000, false, shellPid);
            creation = Identity(primaryHandle, expectedImage, pid);
            shellCreation = Identity(shellHandle, Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"), shellPid);
            Require(creation == expectedCreation && bar.ToInt64() == expectedBar && shellPid == expectedShell &&
                    WindowOwner(GetShellWindow()) == shellPid && Marshal.SizeOf(typeof(Identifier)) == 40,
                    "Expected the original primary and native Explorer of the disposable console");
        } catch { Dispose(); throw; }
    }
    public void CheckOriginal() {
        DefaultInput();
        uint status;
        Require(GetExitCodeProcess(primaryHandle, out status) && status == 259 && GetExitCodeProcess(shellHandle, out status) && status == 259,
                "One of the retained process identities exited");
        var cls = new StringBuilder(128);
        Require(WindowOwner(receiver) == pid && GetClassName(receiver, cls, cls.Capacity) > 0 && cls.ToString() == "IFW RW02 synthetic tray receiver",
                "The integrated callback window changed");
        Require(FindWindow("Shell_TrayWnd", null) == bar && IsWindowVisible(bar) && WindowOwner(bar) == shellPid && WindowOwner(GetShellWindow()) == shellPid,
                "The original visible Explorer taskbar changed");
    }
    static bool Present(IntPtr hwnd) {
        uint cloaked;
        Require(DwmGetWindowAttribute(hwnd,14,out cloaked,4) == 0, "Could not read compositor visibility");
        return IsWindowVisible(hwnd) && !IsIconic(hwnd) && cloaked == 0;
    }
    public Pane Overflow() {
        CheckOriginal();
        Pane found = null;
        foreach (var cls in new string[]{"NotifyIconOverflowWindow","TopLevelWindowForOverflowXamlIsland"}) {
            IntPtr hwnd = IntPtr.Zero;
            for (int i=0; ; i++) {
                Require(i < 64, "Ambiguous hidden-icons surfaces");
                hwnd = FindWindowEx(IntPtr.Zero,hwnd,cls,null);
                if (hwnd == IntPtr.Zero) break;
                if (!IsWindowVisible(hwnd) || !Present(hwnd)) continue;
                uint owner, again; uint tid = GetWindowThreadProcessId(hwnd,out owner);
                var name = new StringBuilder(128);
                if (found != null || owner != shellPid || tid == 0 || !IsInput(GetThreadDesktop(tid)) || GetAncestor(hwnd,2) != hwnd ||
                    GetClassName(hwnd,name,name.Capacity) <= 0 || name.ToString() != cls ||
                    GetWindowThreadProcessId(hwnd,out again) != tid || again != owner) throw new PaneChanged();
                found = new Pane(hwnd.ToInt64(),owner,tid,cls);
            }
        }
        return found;
    }
    public int[] Cursor() {
        Point p; Require(GetCursorPos(out p), "Could not observe the original cursor position");
        return new int[]{p.X,p.Y};
    }
    public long ButtonHit(int x, int y) {
        CheckOriginal();
        var p = new Point{X=x,Y=y};
        var hit = WindowFromPoint(p);
        Require(MonitorFromPoint(p,0) != IntPtr.Zero && GetAncestor(hit,2) == bar && Present(bar) &&
                IsWindowVisible(hit) && WindowOwner(hit) == shellPid, "The hidden-icons button did not hit the original taskbar");
        return hit.ToInt64();
    }
    public Sample Read(Pane originalPane) {
        CheckOriginal();
        var identifier = new Identifier { Size = (uint)Marshal.SizeOf(typeof(Identifier)), Owner = receiver, Id = 23 };
        Rect r; int hr = Shell_NotifyIconGetRect(ref identifier, out r);
        Require(hr == 0, "Independent Shell_NotifyIconGetRect returned " + hr.ToString("x8"));
        Require(r.Right-r.Left >= 2 && r.Right-r.Left <= 256 && r.Bottom-r.Top >= 2 && r.Bottom-r.Top <= 256, "Invalid native notification icon rectangle");
        var pt = new Point { X = r.Left + (r.Right-r.Left)/2, Y = r.Top + (r.Bottom-r.Top)/2 };
        IntPtr hit = WindowFromPoint(pt);
        var root = GetAncestor(hit,2);
        var current = Overflow();
        long pane = current == null ? 0 : current.hwnd;
        if (!SamePane(originalPane,current)) throw new PaneChanged();
        Require(root == bar || (pane != 0 && root.ToInt64() == pane), "The icon center did not hit the original taskbar or its verified flyout");
        var monitor = MonitorFromPoint(pt,0);
        Require(monitor != IntPtr.Zero && Present(root) && IsWindowVisible(hit) && WindowOwner(hit) == shellPid,
                "The physical marker point did not hit a visible window of the original Explorer");
        IntPtr dc = GetDC(IntPtr.Zero);
        Require(dc != IntPtr.Zero, "Could not read the visible icon pixel");
        uint pixel;
        try { pixel = GetPixel(dc, pt.X, pt.Y); }
        finally { if (ReleaseDC(IntPtr.Zero, dc) == 0) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        Require(pixel != 0xffffffff, "The compositor returned an invalid marker pixel");
        if (!SamePane(originalPane,Overflow())) throw new PaneChanged();
        Require(WindowFromPoint(pt) == hit && GetAncestor(hit,2) == root && WindowOwner(hit) == shellPid,
                "The original hit window changed while the physical marker was sampled");
        return new Sample { pid=pid, hwnd=receiver.ToInt64(), creation=creation, rect=new int[]{r.Left,r.Top,r.Right,r.Bottom}, point=new int[]{pt.X,pt.Y},
            hit=hit.ToInt64(), bar=bar.ToInt64(), shellPid=shellPid, shellCreation=shellCreation, root=root.ToInt64(),
            rootClass=root == bar ? "Shell_TrayWnd" : current.windowClass, pane=current, overflow=pane, monitor=monitor.ToInt64(), cursor=Cursor(),
            rgb=String.Format("{0:x2}{1:x2}{2:x2}",pixel & 255,(pixel >> 8) & 255,(pixel >> 16) & 255) };
    }
    public sealed class MarkerGrid {
        public int columns, rows, sampled, unobserved, matches, matchingSampleSquares;
        public int[] step, matchingBounds;
    }
    // Only the coordinates and arrangement of challenge-color hits leave the scan.
    public static MarkerGrid CountMarker(int[] rect, Func<int,int,int> sample) {
        long w = (long)rect[2]-rect[0], h = (long)rect[3]-rect[1];
        Require(w >= 2 && w <= 256 && h >= 2 && h <= 256, "Invalid marker grid rectangle");
        int sx = ((int)w+15)/16, sy = ((int)h+15)/16;
        var grid = new MarkerGrid { step=new int[]{sx,sy}, columns=((int)w+sx-1)/sx, rows=((int)h+sy-1)/sy };
        var hit = new bool[grid.rows,grid.columns];
        for (int row=0; row<grid.rows; row++) {
            int y = rect[1] + Math.Min((int)h-1, row*sy+sy/2);
            for (int col=0; col<grid.columns; col++) {
                int x = rect[0] + Math.Min((int)w-1, col*sx+sx/2);
                int outcome = sample(x,y);
                if (outcome < 0) { grid.unobserved++; continue; }
                grid.sampled++;
                if (outcome == 0) continue;
                hit[row,col] = true;
                grid.matches++;
                if (grid.matchingBounds == null) grid.matchingBounds = new int[]{x,y,x+1,y+1};
                else {
                    grid.matchingBounds[0] = Math.Min(grid.matchingBounds[0],x);
                    grid.matchingBounds[1] = Math.Min(grid.matchingBounds[1],y);
                    grid.matchingBounds[2] = Math.Max(grid.matchingBounds[2],x+1);
                    grid.matchingBounds[3] = Math.Max(grid.matchingBounds[3],y+1);
                }
                if (row > 0 && col > 0 && hit[row-1,col] && hit[row,col-1] && hit[row-1,col-1])
                    grid.matchingSampleSquares++;
            }
        }
        return grid;
    }
    bool OnOriginalTaskbar(Point point, IntPtr hit, Sample center) {
        return hit != IntPtr.Zero && GetAncestor(hit,2) == bar && MonitorFromPoint(point,0).ToInt64() == center.monitor &&
            IsWindowVisible(hit) && WindowOwner(hit) == shellPid;
    }
    public MarkerGrid ReadMarkerGrid(Sample center, int[] expected) {
        Require(center != null && center.pane == null && center.root == bar.ToInt64() &&
                expected.Length == 3 && Array.TrueForAll(expected, v => v >= 0 && v <= 255) &&
                center.Matches(Read(null)), "The initial marker rectangle or its original Explorer changed before the scan");
        IntPtr dc=GetDC(IntPtr.Zero);
        Require(dc != IntPtr.Zero, "Could not read the bounded marker grid");
        MarkerGrid grid;
        try {
            grid = CountMarker(center.rect, delegate(int x, int y) {
                var point = new Point { X=x, Y=y };
                var hit = WindowFromPoint(point);
                if (!OnOriginalTaskbar(point,hit,center)) return -1;
                uint pixel = GetPixel(dc,x,y);
                if (pixel == 0xffffffff || WindowFromPoint(point) != hit || !OnOriginalTaskbar(point,hit,center)) return -1;
                return Math.Abs((int)(pixel & 255)-expected[0]) <= 8 && Math.Abs((int)((pixel>>8) & 255)-expected[1]) <= 8 &&
                    Math.Abs((int)((pixel>>16) & 255)-expected[2]) <= 8 ? 1 : 0;
            });
        } finally { if (ReleaseDC(IntPtr.Zero,dc) == 0) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        Require(center.Matches(Read(null)), "The original marker rectangle or Explorer changed during the scan");
        return grid;
    }
    public void Dispose() {
        int error = 0;
        if (primaryHandle != IntPtr.Zero && !CloseHandle(primaryHandle)) error = Marshal.GetLastWin32Error();
        if (shellHandle != IntPtr.Zero && !CloseHandle(shellHandle)) error = Marshal.GetLastWin32Error();
        if (originalDpi != IntPtr.Zero && SetThreadDpiAwarenessContext(originalDpi) == IntPtr.Zero) throw new InvalidOperationException("Could not restore the observer thread DPI context");
        primaryHandle = shellHandle = originalDpi = IntPtr.Zero;
        if (error != 0) throw new Win32Exception(error);
    }
}
'@
. (Join-Path $PSScriptRoot '../windows-services/tray-overflow.ps1')

function Get-Marker($Guard, [int[]]$Expected, $First) {
    $until = [Diagnostics.Stopwatch]::StartNew()
    do {
        try {
            $live = $Guard.Read($script:lease.pane)
            $script:lastSurface = $live
            if (($live.cursor -join ',') -ne ($script:originalCursor -join ',') -or ($null -ne $First -and
                ($live.hit -ne $First.hit -or $live.root -ne $First.root -or ($live.rect -join ',') -ne ($First.rect -join ',')))) {
                throw [InvalidOperationException]::new('The original physical marker point or hit window changed')
            }
            $ok = $true
            for ($i = 0; $i -lt 3; $i++) {
                $channel = [Convert]::ToInt32($live.rgb.Substring(2 * $i, 2), 16)
                if ([Math]::Abs($channel - $Expected[$i]) -gt 8) { $ok = $false }
            }
            if ($ok) { return $live }
            $reason = [InvalidOperationException]::new("The native icon rectangle yielded pixel $($live.rgb)")
            $reason.Data['markerColorMismatch'] = $true
        } catch {
            $underlying = $_.Exception.GetBaseException()
            if ($underlying -is [IfwIconSurface+PaneChanged] -or $underlying -isnot [InvalidOperationException]) { throw }
            $reason = $underlying
        }
        Start-Sleep -Milliseconds 80
    } while ($until.Elapsed.TotalSeconds -lt 4)
    throw $reason
}

function Get-ExactProvider($Surface, [string]$Label) {
    $byName = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty, $Label)
    $byHelp = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::HelpTextProperty, $Label)
    $condition = [Windows.Automation.OrCondition]::new($byName, $byHelp)
    $root = $null; $item = $null; $visible = 0
    foreach ($hwnd in @($Surface.bar, $Surface.overflow)) {
        if ($hwnd -eq 0) { continue }
        $candidateRoot = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$hwnd)
        if ($candidateRoot.Current.ProcessId -ne $Surface.shellPid) { throw [InvalidOperationException]::new('The provider root changed process') }
        $found = $candidateRoot.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)
        foreach ($candidate in $found) {
            if ($candidate.Current.IsOffscreen -or $candidate.Current.BoundingRectangle.IsEmpty) { continue }
            $visible++
            if ($hwnd -eq $Surface.root) { $item=$candidate; $root=$candidateRoot }
        }
    }
    if ($visible -ne 1 -or $null -eq $item) { throw [InvalidOperationException]::new("Expected one exact visible provider under the physical hit root, found $visible") }
    $current = $item.Current
    $point = [Windows.Point]::new($Surface.point[0], $Surface.point[1])
    $bounds = $current.BoundingRectangle
    $nameMatches = $current.Name -ceq $Label
    $helpMatches = $current.HelpText -ceq $Label
    if ((-not $nameMatches -and -not $helpMatches) -or $current.ProcessId -ne $Surface.shellPid -or
        $current.IsOffscreen -or -not $current.IsEnabled -or $bounds.IsEmpty -or -not $bounds.Contains($point) -or
        $point.X -ge $bounds.Right -or $point.Y -ge $bounds.Bottom -or
        $bounds.Left -lt $Surface.rect[0] -or $bounds.Top -lt $Surface.rect[1] -or
        $bounds.Right -gt $Surface.rect[2] -or $bounds.Bottom -gt $Surface.rect[3]) {
        throw [InvalidOperationException]::new('The exact provider failed the visible, enabled, process or native-bounds check')
    }
    $runtime = $item.GetRuntimeId() -join ','
    $hit = [Windows.Automation.AutomationElement]::FromPoint($point)
    $hitId = if ($null -ne $hit) { $hit.GetRuntimeId() -join ',' }
    $depth = 0
    while ($null -ne $hit -and $depth -lt 12 -and $hit.Current.ProcessId -eq $Surface.shellPid) {
        if ([Windows.Automation.Automation]::Compare($item, $hit)) { break }
        if ([Windows.Automation.Automation]::Compare($root, $hit)) { $hit = $null; break }
        $hit = [Windows.Automation.TreeWalker]::RawViewWalker.GetParent($hit)
        $depth++
    }
    $pattern = $null
    if (-not $runtime -or $null -eq $hit -or -not [Windows.Automation.Automation]::Compare($item, $hit) -or
        -not $item.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
        throw [InvalidOperationException]::new('The visible point did not belong to an exact invokable item')
    }
    return @{ pattern = $pattern; descriptor = [ordered]@{
        runtimeId = $runtime; hitRuntimeId = $hitId; root=$Surface.root; pid = $current.ProcessId; matchCount = $visible; matchedLabel = $Label
        nameMatches = $nameMatches; helpMatches = $helpMatches
        enabled = $current.IsEnabled; offscreen = $current.IsOffscreen; hitDepth = $depth
        bounds = @($bounds.Left, $bounds.Top, $bounds.Right, $bounds.Bottom)
    } }
}

function Test-ProviderPoint($Item,$Root,$Point,[uint32]$Owner) {
    $node = [Windows.Automation.AutomationElement]::FromPoint($Point)
    for ($i=0; $i -lt 12 -and $null -ne $node -and $node.Current.ProcessId -eq $Owner; $i++) {
        if ([Windows.Automation.Automation]::Compare($node,$Item)) { return $true }
        if ([Windows.Automation.Automation]::Compare($node,$Root)) { break }
        $node = [Windows.Automation.TreeWalker]::RawViewWalker.GetParent($node)
    }
    return $false
}

function Get-ChevronHintReadback($Guard,$Surface,$KnownNames) {
    if ($null -eq $Surface -or $Surface.root -ne $script:Bar -or $Surface.shellPid -ne $script:ShellPid) {
        return @{status='no-original-taskbar-hint'}
    }
    try {
        $point = [Windows.Point]::new($Surface.point[0],$Surface.point[1])
        if ($Guard.ButtonHit($point.X,$point.Y) -ne $Surface.hit) { return @{status='changed-native-hit'} }
        $root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$script:Bar)
        $hit = [Windows.Automation.AutomationElement]::FromPoint($point)
        $node = $hit; $path = @(); $bound = $false
        for ($i=0; $i -lt 12 -and $null -ne $node -and $node.Current.ProcessId -eq $script:ShellPid; $i++) {
            if ([Windows.Automation.Automation]::Compare($node,$root)) { $bound=$true; break }
            if ($path.Count -lt 3) { $path += $node }
            $node = [Windows.Automation.TreeWalker]::RawViewWalker.GetParent($node)
        }
        if (-not $bound) { return @{status='unbound-uia-hit'} }
        # Exact predicates disclose only these public system labels, including the Windows settings term.
        $terms = @($KnownNames) + 'Hidden icon menu'
        $items = @()
        foreach ($element in $path) {
            $current = $element.Current
            if ($current.ProcessId -ne $script:ShellPid) { return @{status='changed-uia-hit'} }
            $item = @{type=$current.ControlType.Id; enabled=$current.IsEnabled; offscreen=$current.IsOffscreen
                      containsPoint=$current.BoundingRectangle.Contains($point)}
            $pattern = $null
            $item.expand = $element.TryGetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$pattern)
            $item.toggle = $element.TryGetCurrentPattern([Windows.Automation.TogglePattern]::Pattern,[ref]$pattern)
            $item.invoke = $element.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)
            foreach ($field in @('Name','HelpText')) {
                $property = if ($field -eq 'Name') { [Windows.Automation.AutomationElement]::NameProperty }
                            else { [Windows.Automation.AutomationElement]::HelpTextProperty }
                foreach ($term in $terms) {
                    $filter = [Windows.Automation.PropertyCondition]::new($property,$term)
                    if ($null -ne $element.FindFirst([Windows.Automation.TreeScope]::Element,$filter)) { $item[$field]=$term; break }
                }
            }
            $items += $item
        }
        if ($Guard.ButtonHit($point.X,$point.Y) -ne $Surface.hit -or
            -not [Windows.Automation.Automation]::Compare($hit,[Windows.Automation.AutomationElement]::FromPoint($point))) {
            return @{status='changed-hit'}
        }
        return @{status='bound-taskbar-point'; nativeHit=$Surface.hit; point=$Surface.point; elements=$items}
    } catch { return @{status='readback-unavailable'} }
}

function Get-OverflowButton($State) {
    $guard.CheckOriginal()
    $button = $State.button; $current = $button.Current; $bounds = $current.BoundingRectangle
    $root = [Windows.Automation.AutomationElement]::FromHandle($State.bar)
    if ($State.bar.ToInt64() -ne $script:Bar -or $State.explorer -ne $script:ShellPid -or $root.Current.ProcessId -ne $script:ShellPid -or
        $current.ProcessId -ne $ShellPid -or -not $current.IsEnabled -or $current.IsOffscreen -or
        $current.ControlType -ne [Windows.Automation.ControlType]::Button -or $bounds.IsEmpty -or $bounds.Width -lt 2 -or $bounds.Height -lt 2) {
        throw [InvalidOperationException]::new('The original Show hidden icons button did not identify a visible Explorer provider')
    }
    $point = [Windows.Point]::new([Math]::Floor($bounds.Left+$bounds.Width/2), [Math]::Floor($bounds.Top+$bounds.Height/2))
    $hit = $guard.ButtonHit($point.X,$point.Y)
    if (-not (Test-ProviderPoint $button $root $point $ShellPid)) { throw [InvalidOperationException]::new('The physical chevron did not hit its provider') }
    $runtime = $button.GetRuntimeId() -join ','
    if (-not $runtime) { throw [InvalidOperationException]::new('The original chevron lacked a runtime identity') }
    return @{runtimeId=$runtime; nativeHit=$hit; bar=$script:Bar; pid=$script:ShellPid; bounds=@($bounds.Left,$bounds.Top,$bounds.Right,$bounds.Bottom)
             point=@([int]$point.X,[int]$point.Y)}
}

function Wait-OpenedPane($Guard) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        $pane = $Guard.Overflow()
        if ($null -ne $pane) { return $pane }
        Start-Sleep -Milliseconds 80
    } while ($timer.Elapsed.TotalSeconds -lt 3)
}

function Restore-OpenedPane($Guard,$Lease,$Record) {
    if ($null -eq $Lease.pane) {
        # COM may throw after Explorer accepted the change. Look for its actual resulting surface.
        $Lease.pane = Wait-OpenedPane $Guard
        if ($null -eq $Lease.pane) { throw 'The attempted flyout change never exposed an attributable native surface' }
    }
    $restoreGuard = {
        param($Candidate,$Owner)
        try {
            $Guard.CheckOriginal()
            $currentPane = $Guard.Overflow()
            $button = $Lease.state.button
            $signed = $Candidate.ToInt64() -eq $script:Bar -and $Owner -eq $script:ShellPid -and
                ($null -eq $currentPane -or [IfwIconSurface]::SamePane($currentPane,$Lease.pane)) -and
                $button.Current.ProcessId -eq $script:ShellPid -and ($button.GetRuntimeId() -join ',') -ceq $Lease.button.runtimeId
            if (-not $signed) { $Lease.identityLost=$true }
            return $signed
        } catch { $Lease.identityLost=$true; throw }
    }
    $authorizeClose = {
        param($Candidate,$Owner)
        if (-not (& $restoreGuard $Candidate $Owner)) { throw 'The original flyout provider changed before closure' }
        $action=$Lease.state.action
        if ($action.method -eq 'Expand' -and $action.provider.Current.ExpandCollapseState -ne [Windows.Automation.ExpandCollapseState]::Expanded) { return $false }
        if ($action.method -eq 'Toggle' -and $action.provider.Current.ToggleState -ne [Windows.Automation.ToggleState]::On) { return $false }
        try { $livePane=$Guard.Overflow() } catch { $Lease.identityLost=$true; throw }
        if ($null -eq $livePane) { return $false }
        if (-not [IfwIconSurface]::SamePane($livePane,$Lease.pane)) {
            $Lease.identityLost=$true; throw 'The visible native flyout was replaced before closure'
        }
        return $true
    }
    $Guard.CheckOriginal()
    $visible = $Guard.Overflow()
    if ($null -ne $visible -and $Lease.iconAttempted) {
        # Explorer may dismiss its flyout when the selected icon opens its GUI.
        $pause = [Diagnostics.Stopwatch]::StartNew()
        while ($null -ne $visible -and $pause.ElapsedMilliseconds -lt 750) {
            if (-not [IfwIconSurface]::SamePane($visible,$Lease.pane)) { throw 'The opened flyout was replaced' }
            Start-Sleep -Milliseconds 50
            $visible = $Guard.Overflow()
        }
    }
    if ($null -ne $visible) {
        $live = Get-OverflowButton $Lease.state
        if ($live.runtimeId -cne $Lease.button.runtimeId -or -not (& $restoreGuard $Lease.state.bar $Lease.state.explorer)) {
            throw 'The original flyout or its bound restoration provider changed'
        }
        try { Restore-IfwTrayOverflow $Lease.state $Record $restoreGuard $authorizeClose }
        catch {
            if ($Lease.identityLost) { throw }
            $Record.restoreProviderError=$_.Exception.GetBaseException().Message
        }
    }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $firstAbsent=$null; $Record.absentSamples=0
    do {
        $Guard.CheckOriginal()
        $pane = $Guard.Overflow()
        if ($null -eq $pane) {
            $action=$Lease.state.action
            $closed = switch ($action.method) {
                'Expand' { $action.provider.Current.ExpandCollapseState -eq [Windows.Automation.ExpandCollapseState]::Collapsed }
                'Toggle' { $action.provider.Current.ToggleState -eq [Windows.Automation.ToggleState]::Off }
                'Invoke' { $true }
            }
            if ($closed) {
                if ($null -eq $firstAbsent) { $firstAbsent=$timer.ElapsedMilliseconds }
                $Record.absentSamples++
                $Record.absentMs=$timer.ElapsedMilliseconds-$firstAbsent
                if ($Record.absentSamples -ge 2 -and $Record.absentMs -ge 750) { $Record.restored=$true; return }
            } else {
                $firstAbsent=$null; $Record.absentSamples=0
            }
        } elseif ($null -ne $firstAbsent -or -not [IfwIconSurface]::SamePane($pane,$Lease.pane)) {
            throw 'The original hidden-icons surface was replaced during restoration'
        }
        Start-Sleep -Milliseconds 80
    } while ($timer.Elapsed.TotalSeconds -lt 3)
    throw 'The original closed hidden-icons state was not observed after restoration'
}

function Invoke-OriginalIcon($Lease,$Pattern,[scriptblock]$Clock) {
    # A failing COM return can follow a successful native activation and automatic flyout dismissal.
    $Lease.iconAttempted=$true
    $Lease.startTick=& $Clock
    $Pattern.Invoke()
    return (& $Clock)
}

$guard = $null
$invoking = $false
$script:lastSurface = $null
$baselineRead = $false; $baseline = $null
$lease = @{state=$null; pane=$null; button=$null}
$flyout = @{overflow='untouched'; restored=$false}
$exitCode = 0
try {
    try { Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase }
    catch { throw [InvalidOperationException]::new('The native UI Automation client assemblies are unavailable') }
    $guard = [IfwIconSurface]::new($PrimaryId, $Receiver, $Creation, (Join-Path $area 'subject\native-gui-assessment.exe'),$ShellPid,$Bar)
    $script:originalCursor=$guard.Cursor()
    $baseline=$guard.Overflow(); $baselineRead=$true
    Write-Event 'baseline' @{pane=$baseline; bar=$Bar; pid=$ShellPid; cursor=$script:originalCursor}
    if ($null -ne $baseline) {
        throw [InvalidOperationException]::new('A hidden-icons flyout was already open; activating an icon could dismiss its original surface')
    }
    $orig = @(24 + ([Convert]::ToInt32($Token.Substring(0, 2), 16) -band 63)
              164 + ([Convert]::ToInt32($Token.Substring(2, 2), 16) -band 63)
              48 + ([Convert]::ToInt32($Token.Substring(4, 2), 16) -band 63))
    $contrast = @($orig | ForEach-Object { 255 - $_ })
    try { $first = Get-Marker $guard $orig $null }
    catch {
        $reason = $_.Exception.GetBaseException()
        if ($reason -is [IfwIconSurface+PaneChanged] -or $reason -isnot [InvalidOperationException]) { throw }
        $guard.CheckOriginal()
        $expectedRgb = ($orig | ForEach-Object {$_.ToString('x2')}) -join ''
        Write-Event 'hint' @{surface=$script:lastSurface; reason=$reason.Message; markerObserved=$false; expectedRgb=$expectedRgb}
        if ($reason.Data['markerColorMismatch'] -eq $true -and $script:lastSurface.root -eq $Bar) {
            $scan = @{status='unavailable'; rect=$script:lastSurface.rect; expectedRgb=$expectedRgb}
            try {
                $scan.grid = $guard.ReadMarkerGrid($script:lastSurface, $orig)
                $scan.status = 'sampled'
            } catch {
                $failure = $_.Exception.GetBaseException()
                if ($failure -is [IfwIconSurface+PaneChanged] -or $failure -isnot [InvalidOperationException]) { throw }
                $scan.reason = $failure.Message
            }
            Write-Event 'marker-grid' $scan
        }
        $selection = @{expectedBar=$script:Bar; expectedPid=$script:ShellPid}
        $beforeChange = {
            param($Candidate,$Owner)
            $guard.CheckOriginal()
            if ($Candidate.ToInt64() -ne $script:Bar -or $Owner -ne $script:ShellPid) { $selection.detail='different-taskbar'; return $false }
            if (($guard.Cursor() -join ',') -cne ($script:originalCursor -join ',')) { $selection.detail='cursor-changed'; return $false }
            if ($null -ne $guard.Overflow()) { $selection.detail='overflow-visible'; return $false }
            return $true
        }
        $beforeAction = {
            param($State)
            $button = Get-OverflowButton $State
            $root=[Windows.Automation.AutomationElement]::FromHandle($State.bar); $count=0
            foreach ($name in $State.names) {
                $named=[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty,$name)
                foreach ($item in $root.FindAll([Windows.Automation.TreeScope]::Descendants,$named)) {
                    if (-not $item.Current.IsOffscreen -and $item.Current.IsEnabled -and $item.Current.ControlType -eq [Windows.Automation.ControlType]::Button) { $count++ }
                }
            }
            if ($count -ne 1) { $selection.detail='visible-enabled-button-count'; $selection.count=$count; return $false }
            if (-not ($State.names -ccontains $State.button.Current.Name)) { $selection.detail='name-changed'; return $false }
            if (-not (& $beforeChange $State.bar $State.explorer)) { return $false }
            $hintHit=$false
            if ($null -ne $script:lastSurface) {
                $p=[Windows.Point]::new($script:lastSurface.point[0],$script:lastSurface.point[1])
                $hintHit=$State.button.Current.BoundingRectangle.Contains($p) -and (Test-ProviderPoint $State.button $root $p $ShellPid)
            }
            Write-Event 'opening' @{button=$button; name=$State.button.Current.Name; method=$State.action.method; hintHitButton=$hintHit}
            $lease.button=$button; $lease.state=$State
            return $true
        }
        try { $null=Open-IfwTrayOverflow $flyout $beforeChange $beforeAction $selection }
        finally {
            if ($null -eq $lease.state) {
                Write-Event 'chevron-diagnostic' @{selection=$selection; observerUICulture=[Globalization.CultureInfo]::CurrentUICulture.Name}
                $names = @($selection.names | ForEach-Object { $_.name })
                Write-Event 'chevron-hint' @{afterRejectionAtHint=(Get-ChevronHintReadback $guard $script:lastSurface $names)}
            }
        }
        if ($null -eq $lease.state) { throw [InvalidOperationException]::new("The pinned taskbar had no verified Show hidden icons provider ($($selection.gate))") }
        $lease.pane=Wait-OpenedPane $guard
        if ($null -eq $lease.pane) { throw [InvalidOperationException]::new('Explorer did not expose the requested native hidden-icons surface') }
        Write-Event 'opened' @{pane=$lease.pane}
        $first=Get-Marker $guard $orig $null
        if ($first.root -ne $lease.pane.hwnd) { throw [InvalidOperationException]::new('The first marker was outside the opened hidden-icons surface') }
    }
    Write-Event 'first' @{surface = $first}
    if ([Console]::In.ReadLine() -cne 'second') { return }
    $second = Get-Marker $guard $contrast $first
    $label = "IFW tray $Token"
    $arrival = [Diagnostics.Stopwatch]::StartNew()
    do {
        try {
            $provider = Get-ExactProvider $second $label
            break
        } catch {
            $cause = $_.Exception.GetBaseException()
            if ($arrival.Elapsed.TotalSeconds -ge 4 -or $cause -isnot [InvalidOperationException]) { throw }
            Start-Sleep -Milliseconds 120
            $second = Get-Marker $guard $contrast $first
        }
    } while ($true)
    Write-Event 'ready' @{surface = $second; provider = $provider.descriptor}
    if ([Console]::In.ReadLine() -cne 'invoke') { return }
    $fresh = Get-Marker $guard $contrast $first
    $current = Get-ExactProvider $fresh $label
    if (($current.descriptor | ConvertTo-Json -Compress) -cne ($provider.descriptor | ConvertTo-Json -Compress)) {
        throw [InvalidOperationException]::new('The resolved accessibility provider changed')
    }
    $script:lastSurface = $guard.Read($lease.pane)
    if (-not $fresh.Matches($script:lastSurface)) {
        throw [InvalidOperationException]::new('The physical Shell hit or pixel changed before invocation')
    }
    Write-Event 'attempt' @{surface = $fresh; provider = $current.descriptor; tick = [IfwIconSurface]::GetTickCount64()}
    $actual = Get-ExactProvider $fresh $label
    if (($actual.descriptor | ConvertTo-Json -Compress) -cne ($current.descriptor | ConvertTo-Json -Compress)) {
        throw [InvalidOperationException]::new('The exact accessibility provider changed after the attempt receipt')
    }
    $invocationSurface = $guard.Read($lease.pane)
    if (-not $fresh.Matches($invocationSurface)) {
        throw [InvalidOperationException]::new('The original Shell surface changed at invocation')
    }
    $invoking = $true
    $returnedTick=Invoke-OriginalIcon $lease $actual.pattern { [IfwIconSurface]::GetTickCount64() }
    Write-Event 'invoked' @{startTick=$lease.startTick; returnedTick=$returnedTick; surface=$invocationSurface; provider=$actual.descriptor}
} catch {
    $cause = $_.Exception.GetBaseException()
    if (-not $invoking -and ($cause -is [InvalidOperationException] -or $cause -is [Runtime.InteropServices.COMException] -or
                              $cause.GetType().FullName -eq 'System.Windows.Automation.ElementNotAvailableException')) {
        Write-Event 'unavailable' @{reason = $cause.Message; lastSurface = $script:lastSurface}
        $exitCode=2
    } else {
        Write-Event 'failed' @{reason=$cause.Message; iconAttempted=($lease.iconAttempted -eq $true); startTick=$lease.startTick; surface=$invocationSurface}
        $exitCode=1
    }
} finally {
    try {
        if ($null -ne $lease.state) { Restore-OpenedPane $guard $lease $flyout }
        $finalPane=if ($baselineRead) { $guard.Overflow() }
        $cursor=if ($baselineRead) { $guard.Cursor() }
        if ($baselineRead -and -not [IfwIconSurface]::SamePane($baseline,$finalPane)) { throw 'The original flyout state changed' }
        Write-Event 'cleanup' @{attempted=($null -ne $lease.state); baselineRead=$baselineRead; original=$baseline; final=$finalPane
                                observedOpen=$lease.pane; restored=$flyout.restored; cursor=$cursor; providerError=$flyout.restoreProviderError
                                iconAttempted=($lease.iconAttempted -eq $true); absentSamples=$flyout.absentSamples; absentMs=$flyout.absentMs}
        if ($baselineRead -and ($cursor -join ',') -cne ($script:originalCursor -join ',')) { throw 'The original cursor position changed' }
    } catch {
        Write-Event 'cleanup-failed' @{reason=$_.Exception.GetBaseException().Message; observedOpen=$lease.pane}
        throw
    } finally { if ($null -ne $guard) { $guard.Dispose() } }
}
exit $exitCode
