# Invoke the Quit item on the original 3.0.4 process's own popup menu.
param([int]$ProcessId, [long]$Created, [long]$Receiver, [int]$ThreadId, [string]$Evidence)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not [Environment]::Is64BitProcess -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -ine 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') {
    throw 'Expected the disposable native Windows runner.'
}
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Text;
using System.Runtime.InteropServices;
public static class ShippingQuit {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct Bar { public uint Size; public Rect Bounds; public IntPtr Menu, Sub; public uint Flags; }
    [StructLayout(LayoutKind.Sequential)] struct Gui { public int Size,Flags; public IntPtr Active,Focus,Capture,MenuOwner,Move,Caret; public Rect Bounds; }
    public delegate bool EnumWindow(IntPtr hwnd, IntPtr data);
    [DllImport("user32")] static extern bool EnumThreadWindows(int tid, EnumWindow visit, IntPtr data);
    [DllImport("user32")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder name, int size);
    [DllImport("user32")] static extern int GetWindowThreadProcessId(IntPtr hwnd, out int pid);
    [DllImport("user32")] static extern bool GetGUIThreadInfo(int tid, ref Gui info);
    [DllImport("user32")] static extern bool GetMenuBarInfo(IntPtr hwnd, int which, int item, ref Bar bar);
    [DllImport("user32")] static extern int GetMenuItemCount(IntPtr menu);
    [DllImport("user32")] static extern int GetMenuItemID(IntPtr menu, int n);
    [DllImport("user32")] static extern bool GetMenuItemRect(IntPtr hwnd, IntPtr menu, uint n, out Rect rect);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern int GetMenuString(IntPtr menu, uint id, StringBuilder label, int size, uint flags);
    public static bool Owns(IntPtr hwnd,int pid,int tid) { int actual; return hwnd!=IntPtr.Zero && GetWindowThreadProcessId(hwnd,out actual)==tid && actual==pid; }
    public class Selection { public IntPtr Window, Menu; public int[] Commands; public string Label; public Rect Bounds; }
    public static Selection Inspect(int pid, int tid, IntPtr owner) {
        if (!Owns(owner,pid,tid)) throw new InvalidOperationException("Shipping tray receiver changed");
        var gui=new Gui(); gui.Size=Marshal.SizeOf(gui);
        if (!GetGUIThreadInfo(tid,ref gui) || gui.MenuOwner!=owner || (gui.Flags & 0x14)==0) return null;
        var popups=new List<IntPtr>();
        EnumThreadWindows(tid,delegate(IntPtr h, IntPtr unused){
            var n=new StringBuilder(128);
            if(Owns(h,pid,tid) && IsWindowVisible(h) && GetClassName(h,n,n.Capacity)>0 && n.ToString()=="#32768") popups.Add(h);
            return true;
        },IntPtr.Zero);
        if(popups.Count!=1) return null;
        IntPtr hwnd=popups[0]; var bar=new Bar(); bar.Size=(uint)Marshal.SizeOf(bar);
        if(!GetMenuBarInfo(hwnd,-4,0,ref bar) || bar.Menu==IntPtr.Zero || GetMenuItemCount(bar.Menu)!=5) return null;
        var ids=new int[5]; for (int i=0;i<5;i++) ids[i]=GetMenuItemID(bar.Menu,i);
        if(ids[0]!=1 || ids[2]!=2 || ids[4]!=3) return null;
        Rect rect; var label=new StringBuilder(256);
        if(!GetMenuItemRect(IntPtr.Zero,bar.Menu,4,out rect) || rect.Left>=rect.Right || rect.Top>=rect.Bottom ||
            GetMenuString(bar.Menu,3,label,label.Capacity,0)<=0) return null;
        return new Selection { Window=hwnd, Menu=bar.Menu, Commands=ids, Label=label.ToString(), Bounds=rect };
    }
}
'@
$record = [ordered]@{ pid = $ProcessId; created = $Created; receiver = $Receiver; tid = $ThreadId; status = 'incomplete' }
$process = [Diagnostics.Process]::GetProcessById($ProcessId)
try {
    if ($process.HasExited -or $process.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $Created) {
        throw 'The held shipping process changed.'
    }
    $until = [Diagnostics.Stopwatch]::StartNew()
    do {
        $menu = [ShippingQuit]::Inspect($ProcessId,$ThreadId,[IntPtr]$Receiver)
        if (-not $menu) { Start-Sleep -Milliseconds 30 }
    } while (-not $menu -and $until.Elapsed.TotalSeconds -lt 8 -and -not $process.HasExited)
    if (-not $menu) { throw 'The shipping process did not expose its original native Quit menu.' }
    $r = $menu.Bounds
    $point = [Windows.Point]::new(($r.Left + $r.Right) / 2, ($r.Top + $r.Bottom) / 2)
    $item = [Windows.Automation.AutomationElement]::FromPoint($point)
    $root = [Windows.Automation.AutomationElement]::FromHandle($menu.Window)
    $pattern = $null
    if (-not $item -or $item.Current.ProcessId -ne $ProcessId -or $item.Current.IsOffscreen -or
        -not $item.Current.IsEnabled -or $item.Current.ControlType -ne [Windows.Automation.ControlType]::MenuItem -or
        $item.Current.Name -cne $menu.Label -or
        -not $item.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)) {
        throw 'The native Quit item does not own the observed menu point.'
    }
    $node = $item
    for ($i=0; $i -lt 8 -and $node -and $node.Current.ProcessId -eq $ProcessId; $i++) {
        if ([Windows.Automation.Automation]::Compare($node,$root)) { break }
        $node = [Windows.Automation.TreeWalker]::RawViewWalker.GetParent($node)
    }
    $same = [ShippingQuit]::Inspect($ProcessId,$ThreadId,[IntPtr]$Receiver)
    if (-not $node -or -not [Windows.Automation.Automation]::Compare($node,$root) -or -not $same -or
        $same.Menu -ne $menu.Menu -or $same.Window -ne $menu.Window -or $process.HasExited -or
        -not [Windows.Automation.Automation]::Compare($item, [Windows.Automation.AutomationElement]::FromPoint($point))) {
        throw 'The original WPF popup menu or provider changed.'
    }
    $record.menuHwnd = $menu.Window.ToInt64()
    $record.menu = $menu.Menu.ToInt64()
    $record.commands = $menu.Commands
    $record.label = $item.Current.Name
    $record.runtimeId = $item.GetRuntimeId()
    $record.bounds = @($r.Left,$r.Top,$r.Right,$r.Bottom)
    $pattern.Invoke()
    $record.status = 'invoked'
}
catch { $record.error = $_.Exception.Message; throw }
finally {
    $process.Dispose()
    $json = $record | ConvertTo-Json -Depth 6
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $file = [IO.File]::Open($Evidence, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $file.Write($bytes,0,$bytes.Length) } finally { $file.Dispose() }
}
