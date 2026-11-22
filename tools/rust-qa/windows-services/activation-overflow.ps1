# Use only the pinned private Explorer's accessibility provider for the hidden-icons flyout.
param([Parameter(Mandatory)][string]$Desktop, [Parameter(Mandatory)][string]$Area,
      [Parameter(Mandatory)][int64]$Bar, [Parameter(Mandatory)][uint32]$ShellPid)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or
    $Desktop -cnotmatch '^IfwQa_[0-9a-f]{32}$') { throw 'Expected a disposable hosted private desktop' }
$token = $Desktop.Substring(6)
if ([IO.Path]::GetFullPath($Area) -ine (Join-Path $env:RUNNER_TEMP "ifw-shell-$token") -or
    [IO.File]::ReadAllText((Join-Path $Area 'synthetic.fixture')) -cne $token) { throw 'Unexpected fixture directory' }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class IfwSyntheticShellObserver {
    [DllImport("user32", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32")] public static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("kernel32")] static extern uint GetCurrentThreadId();
    [DllImport("user32")] static extern IntPtr GetThreadDesktop(uint tid);
    [DllImport("user32")] static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32")] static extern bool CloseDesktop(IntPtr handle);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern bool GetUserObjectInformation(IntPtr handle, int type, StringBuilder result, uint length, out uint needed);
    static string Name(IntPtr handle) {
        uint needed;
        var buffer = new StringBuilder(256);
        return handle != IntPtr.Zero && GetUserObjectInformation(handle, 2, buffer, 512, out needed) ? buffer.ToString() : "";
    }
    public static bool Matches(string name, IntPtr hwnd, uint expected) {
        uint pid;
        uint tid = GetWindowThreadProcessId(hwnd, out pid);
        if (tid == 0 || pid != expected || Name(GetThreadDesktop(tid)) != name || Name(GetThreadDesktop(GetCurrentThreadId())) != name) return false;
        IntPtr desktop = OpenInputDesktop(0, false, 1);
        if (desktop == IntPtr.Zero) return false;
        try { return Name(desktop) == name; } finally { CloseDesktop(desktop); }
    }
}
"@
. (Join-Path $PSScriptRoot 'tray-overflow.ps1')
$script:pinnedTaskbar = [IntPtr]$Bar
$script:pinnedOwner = $ShellPid
$script:privateDesktop = $Desktop
$guard = {
    param([IntPtr]$Candidate, [uint32]$Owner)
    return $Candidate -eq $script:pinnedTaskbar -and $Owner -eq $script:pinnedOwner -and
        [IfwSyntheticShellObserver]::FindWindow('Shell_TrayWnd', $null) -eq $Candidate -and
        [IfwSyntheticShellObserver]::Matches($script:privateDesktop, $Candidate, $Owner)
}
$record = @{ overflow = 'unchanged' }
$state = $null
try {
    if (-not (& $guard ([IntPtr]$Bar) $ShellPid)) { throw 'Private Explorer identity or input desktop changed' }
    $state = Open-IfwTrayOverflow $record $guard
    $record.providerReady = $true
    [IO.File]::WriteAllText((Join-Path $Area 'overflow.ready'), 'ready')
    $until = [DateTime]::UtcNow.AddSeconds(35)
    while ($null -ne $state -and -not [IO.File]::Exists((Join-Path $Area 'release-menu')) -and [DateTime]::UtcNow -lt $until) {
        Start-Sleep -Milliseconds 80
    }
} finally {
    try { Restore-IfwTrayOverflow $state $record $guard }
    finally { $record | ConvertTo-Json -Compress }
}
