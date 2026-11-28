# Read window identities on the current desktop. Only verified Shell elements may be searched.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class IfwToastRoots {
    [DllImport("user32")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder name, int size);
    [DllImport("user32")] static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32")] static extern IntPtr GetAncestor(IntPtr h, uint kind);
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    public static IntPtr At(int x, int y) { return GetAncestor(WindowFromPoint(new Point {X=x,Y=y}), 2); }
    public sealed class Window { public long hwnd; public uint pid; public bool core, visible; }
    public static Window Describe(IntPtr h) {
        uint pid;
        if (h == IntPtr.Zero || GetWindowThreadProcessId(h, out pid) == 0) return new Window();
        var name = new StringBuilder(256);
        GetClassName(h, name, name.Capacity);
        return new Window {hwnd=h.ToInt64(), pid=pid, core=name.ToString()=="Windows.UI.Core.CoreWindow", visible=IsWindowVisible(h)};
    }
}
'@

function Get-ToastShellImages {
    Join-Path $env:SystemRoot 'System32\ShellHost.exe'
    Join-Path $env:SystemRoot 'SystemApps\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\ShellHost.exe'
    foreach ($package in @('ShellExperienceHost_cw5n1h2txyewy','Microsoft.Windows.ShellExperienceHost_cw5n1h2txyewy')) {
        Join-Path $env:SystemRoot "SystemApps\$package\ShellExperienceHost.exe"
    }
}

function Get-ToastViewFilter {
    $element = [Windows.Automation.AutomationElement]
    $window = [Windows.Automation.PropertyCondition]::new($element::ControlTypeProperty,[Windows.Automation.ControlType]::Window)
    $ids = @('NormalToastView','Normal Toast View' | ForEach-Object {
        [Windows.Automation.PropertyCondition]::new($element::AutomationIdProperty,$_)
    })
    return [Windows.Automation.AndCondition]::new($window,[Windows.Automation.OrCondition]::new($ids[0],$ids[1]))
}

function Get-ToastModernRoots($shellImages, $viewFilter, $session) {
    $result = @{foreground=[IfwToastRoots]::Describe([IfwToastRoots]::GetForegroundWindow())
        visited=0; handled=0; handlelessShell=0; unresolvedShell=0; errors=0; queried=$false
        nodes=[Collections.Generic.List[object]]::new()}
    try {
        $children = [Windows.Automation.AutomationElement]::RootElement.FindAll(
            [Windows.Automation.TreeScope]::Children,[Windows.Automation.Condition]::TrueCondition)
        $result.queried = $true
        foreach ($node in $children) {
            $result.visited++
            try {
                $ownerId = $node.Current.ProcessId
                $handle = [IntPtr]$node.Current.NativeWindowHandle
                $surface = $node
                if ($handle -eq [IntPtr]::Zero) {
                    $owner = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
                    if (!$owner -or $owner.SessionId -ne $session -or $shellImages -inotcontains $owner.Path) { continue }
                    $result.handlelessShell++
                    $views = $node.FindAll([Windows.Automation.TreeScope]::Subtree,$viewFilter)
                    if ($views.Count -ne 1) { $result.unresolvedShell++; continue }
                    $surface = $views.Item(0)
                    $bounds = $surface.Current.BoundingRectangle
                    if ($surface.Current.ProcessId -ne $ownerId -or $surface.Current.IsOffscreen -or $bounds.IsEmpty) {
                        $result.unresolvedShell++; continue
                    }
                    $handle = [IfwToastRoots]::At([int]($bounds.X+$bounds.Width/2),[int]($bounds.Y+$bounds.Height/2))
                }
                $actual = [IfwToastRoots]::Describe($handle)
                if ($actual.pid -eq $ownerId -and $actual.core -and $actual.visible) {
                    $result.nodes.Add(@{hwnd=$actual.hwnd; node=$surface; pid=$ownerId})
                    $result.handled++
                }
            } catch [Windows.Automation.ElementNotAvailableException] { $result.errors++ }
              catch [Runtime.InteropServices.COMException] { $result.errors++ }
        }
    } catch [Windows.Automation.ElementNotAvailableException] { $result.errors++ }
      catch [Runtime.InteropServices.COMException] { $result.errors++ }
    return $result
}

function Get-ToastCandidates($physical, $classic, $modern) {
    # Preserve the original physical path and retain UIA roots with a different provider for the same HWND.
    $handles = [Collections.Generic.HashSet[long]]::new()
    foreach ($handle in @($physical) + @($classic)) {
        $hwnd = ([IntPtr]$handle).ToInt64()
        if ($hwnd -ne 0 -and $handles.Add($hwnd)) { @{hwnd=$hwnd; node=$null} }
    }
    $fg = $modern.foreground
    if ($fg.core -and $fg.visible -and $handles.Add($fg.hwnd)) { @{hwnd=$fg.hwnd; node=$null} }
    foreach ($item in $modern.nodes) { $item }
}
