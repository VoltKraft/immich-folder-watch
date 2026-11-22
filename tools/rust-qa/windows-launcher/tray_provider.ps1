# Observe one integrated icon and invoke only its uniquely identified, already visible Explorer item.
param([Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{32}$')][string]$Token,
      [Parameter(Mandatory)][uint32]$PrimaryId, [Parameter(Mandatory)][int64]$Receiver,
      [Parameter(Mandatory)][int64]$Creation)
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
# The observer never changes a desktop, a cursor, a taskbar item, or the overflow surface.
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public sealed class IfwIconSurface : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct Identifier { public uint Size; public IntPtr Owner; public uint Id; public Guid Guid; }
    [DllImport("shell32")] static extern int Shell_NotifyIconGetRect(ref Identifier id, out Rect bounds);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder name, int max);
    [DllImport("user32")] static extern IntPtr GetShellWindow();
    [DllImport("user32")] static extern IntPtr WindowFromPoint(Point p);
    [DllImport("user32")] static extern IntPtr GetAncestor(IntPtr hwnd, uint kind);
    [DllImport("user32")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
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
        public long hwnd, creation, hit, bar, shellCreation;
        public int[] rect, point;
        public string rgb, desktop = "Default";
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
    public IfwIconSurface(uint processId, long ownerHwnd, long expectedCreation, string expectedImage) {
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
            Require(creation == expectedCreation && WindowOwner(GetShellWindow()) == shellPid && Marshal.SizeOf(typeof(Identifier)) == 40,
                    "Expected the original primary and native Explorer of the disposable console");
        } catch { Dispose(); throw; }
    }
    public Sample Read() {
        DefaultInput();
        uint status;
        Require(GetExitCodeProcess(primaryHandle, out status) && status == 259 && GetExitCodeProcess(shellHandle, out status) && status == 259,
                "One of the retained process identities exited");
        var cls = new StringBuilder(128);
        Require(WindowOwner(receiver) == pid && GetClassName(receiver, cls, cls.Capacity) > 0 && cls.ToString() == "IFW RW02 synthetic tray receiver",
                "The integrated callback window changed");
        Require(FindWindow("Shell_TrayWnd", null) == bar && IsWindowVisible(bar) && WindowOwner(bar) == shellPid && WindowOwner(GetShellWindow()) == shellPid,
                "The original visible Explorer taskbar changed");
        var identifier = new Identifier { Size = (uint)Marshal.SizeOf(typeof(Identifier)), Owner = receiver, Id = 23 };
        Rect r; int hr = Shell_NotifyIconGetRect(ref identifier, out r);
        Require(hr == 0, "Independent Shell_NotifyIconGetRect returned " + hr.ToString("x8"));
        Require(r.Right-r.Left >= 2 && r.Right-r.Left <= 256 && r.Bottom-r.Top >= 2 && r.Bottom-r.Top <= 256, "Invalid native notification icon rectangle");
        var pt = new Point { X = r.Left + (r.Right-r.Left)/2, Y = r.Top + (r.Bottom-r.Top)/2 };
        IntPtr hit = WindowFromPoint(pt);
        Require(GetAncestor(hit, 2) == bar && IsWindowVisible(hit) && WindowOwner(hit) == shellPid, "Icon center did not hit the original visible Explorer taskbar");
        IntPtr dc = GetDC(IntPtr.Zero);
        Require(dc != IntPtr.Zero, "Could not read the visible icon pixel");
        uint pixel;
        try { pixel = GetPixel(dc, pt.X, pt.Y); }
        finally { if (ReleaseDC(IntPtr.Zero, dc) == 0) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        Require(pixel != 0xffffffff, "The compositor returned an invalid marker pixel");
        return new Sample { pid=pid, hwnd=receiver.ToInt64(), creation=creation, rect=new int[]{r.Left,r.Top,r.Right,r.Bottom}, point=new int[]{pt.X,pt.Y},
            hit=hit.ToInt64(), bar=bar.ToInt64(), shellPid=shellPid, shellCreation=shellCreation,
            rgb=String.Format("{0:x2}{1:x2}{2:x2}",pixel & 255,(pixel >> 8) & 255,(pixel >> 16) & 255) };
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

function Get-Marker($Guard, [int[]]$Expected, $First) {
    $until = [Diagnostics.Stopwatch]::StartNew()
    do {
        try {
            $live = $Guard.Read()
            $script:lastSurface = $live
            if ($null -ne $First -and ($live.hit -ne $First.hit -or ($live.rect -join ',') -ne ($First.rect -join ','))) {
                throw [InvalidOperationException]::new('The original physical marker point or hit window changed')
            }
            $ok = $true
            for ($i = 0; $i -lt 3; $i++) {
                $channel = [Convert]::ToInt32($live.rgb.Substring(2 * $i, 2), 16)
                if ([Math]::Abs($channel - $Expected[$i]) -gt 8) { $ok = $false }
            }
            if ($ok) { return $live }
            $reason = "Marker pixel on the original taskbar is $($live.rgb)"
        } catch {
            $underlying = $_.Exception.GetBaseException()
            if ($underlying -isnot [InvalidOperationException]) { throw }
            $reason = $underlying.Message
        }
        Start-Sleep -Milliseconds 80
    } while ($until.Elapsed.TotalSeconds -lt 4)
    throw [InvalidOperationException]::new($reason)
}

function Get-ExactProvider($Surface, [string]$Label) {
    $root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Surface.bar)
    $byName = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty, $Label)
    $byHelp = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::HelpTextProperty, $Label)
    $condition = [Windows.Automation.OrCondition]::new($byName, $byHelp)
    $found = $root.FindAll([Windows.Automation.TreeScope]::Descendants, $condition)
    if ($found.Count -ne 1) { throw [InvalidOperationException]::new("Expected one exact visible tray provider, found $($found.Count)") }
    $item = $found.Item(0)
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
        runtimeId = $runtime; pid = $current.ProcessId; matchCount = $found.Count; matchedLabel = $Label
        nameMatches = $nameMatches; helpMatches = $helpMatches
        enabled = $current.IsEnabled; offscreen = $current.IsOffscreen; hitDepth = $depth
        bounds = @($bounds.Left, $bounds.Top, $bounds.Right, $bounds.Bottom)
    } }
}

$guard = $null
$invoking = $false
$script:lastSurface = $null
try {
    try { Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase }
    catch { throw [InvalidOperationException]::new('The native UI Automation client assemblies are unavailable') }
    $guard = [IfwIconSurface]::new($PrimaryId, $Receiver, $Creation, (Join-Path $area 'subject\native-gui-assessment.exe'))
    $orig = @(24 + ([Convert]::ToInt32($Token.Substring(0, 2), 16) -band 63)
              164 + ([Convert]::ToInt32($Token.Substring(2, 2), 16) -band 63)
              48 + ([Convert]::ToInt32($Token.Substring(4, 2), 16) -band 63))
    $contrast = @($orig | ForEach-Object { 255 - $_ })
    $first = Get-Marker $guard $orig $null
    Write-Event 'first' @{surface = $first}
    if ([Console]::In.ReadLine() -cne 'second') { exit 0 }
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
    if ([Console]::In.ReadLine() -cne 'invoke') { exit 0 }
    $fresh = Get-Marker $guard $contrast $first
    $current = Get-ExactProvider $fresh $label
    if (($current.descriptor | ConvertTo-Json -Compress) -cne ($provider.descriptor | ConvertTo-Json -Compress)) {
        throw [InvalidOperationException]::new('The resolved accessibility provider changed')
    }
    $script:lastSurface = $guard.Read()
    if (($fresh | ConvertTo-Json -Compress) -cne ($script:lastSurface | ConvertTo-Json -Compress)) {
        throw [InvalidOperationException]::new('The physical Shell hit or pixel changed before invocation')
    }
    $invoking = $true
    Write-Event 'attempt' @{surface = $fresh; provider = $current.descriptor; tick = [IfwIconSurface]::GetTickCount64()}
    $startTick = [IfwIconSurface]::GetTickCount64()
    $current.pattern.Invoke()
    $returnedTick = [IfwIconSurface]::GetTickCount64()
    Write-Event 'invoked' @{startTick = $startTick; returnedTick = $returnedTick}
} catch {
    $cause = $_.Exception.GetBaseException()
    if (-not $invoking -and ($cause -is [InvalidOperationException] -or $cause -is [Runtime.InteropServices.COMException] -or
                              $cause.GetType().FullName -eq 'System.Windows.Automation.ElementNotAvailableException')) {
        Write-Event 'unavailable' @{reason = $cause.Message; lastSurface = $script:lastSurface}
        exit 2
    }
    Write-Event 'failed' @{reason = $cause.Message}
    exit 1
} finally {
    if ($null -ne $guard) { $guard.Dispose() }
}
