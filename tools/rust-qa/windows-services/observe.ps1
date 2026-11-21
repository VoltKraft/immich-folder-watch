param(
    [Parameter(Mandatory)][ValidateSet("private", "startup", "tray")][string]$Stage,
    [Parameter(Mandatory)][string]$Fixture,
    [Parameter(Mandatory)][ValidatePattern("^[0-9a-f]{32}$")][string]$Token,
    [Parameter(Mandatory)][string]$Executable
)

$ErrorActionPreference = "Stop"
$result = [ordered]@{ stage = $Stage }
$progress = Join-Path $Fixture "$Stage.observer-progress"
[IO.File]::WriteAllText($progress, "script-start")
if ($Stage -ne "tray") {
    $owned = [IO.File]::ReadAllText((Join-Path $Fixture "$Stage.owned"))
    $result.fileExists = [IO.File]::Exists($owned)
    $correctName = [IO.Path]::GetFileName($owned) -ceq "IFW-RW02-$Token.lnk"
    if (-not ($result.fileExists -and $correctName)) { throw "Expected the reserved synthetic shortcut" }
    $expectedParent = if ($Stage -eq "startup") {
        [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
    } else { Join-Path $Fixture "Synthetic Startup" }
    $result.directoryMatches = [IO.Path]::GetDirectoryName($owned) -ieq $expectedParent
    if (-not $result.directoryMatches) { throw "Shortcut directory did not match the fixture" }
    [IO.File]::WriteAllText($progress, "create-wscript-object")
    $shell = New-Object -ComObject WScript.Shell
    try {
        [IO.File]::WriteAllText($progress, "read-owned-shortcut")
        $shortcut = $shell.CreateShortcut($owned)
        try {
            $result.targetMatches = $shortcut.TargetPath -ieq $Executable
            $result.argumentsMatch = $shortcut.Arguments -ceq "--autostart"
            $result.workingDirectoryMatches = $shortcut.WorkingDirectory -ieq ([IO.Path]::GetDirectoryName($Executable))
            $result.descriptionMatches = $shortcut.Description -ceq "Immich Folder Watch synthetic startup"
            $icon = $shortcut.IconLocation -replace ",\s*0$", ""
            $result.iconMatches = $icon.Trim('"') -ieq $Executable
        } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) }
    } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
} else {
    [IO.File]::WriteAllText($progress, "load-uia")
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class IfwSyntheticShellObserver {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindow(string className, string title);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindowVisible(IntPtr window);
}
"@
    . (Join-Path $PSScriptRoot 'tray-overflow.ps1')
    [IO.File]::WriteAllText($progress, "observe-shell-tree")
    $result.taskbarRoots = 0
    $result.trayElementFound = $false
    $result.trayElementEnabled = $false
    $result.trayElementOffscreen = $null
    $result.invokeSupported = $false
    $result.invokeSent = $false
    $result.notificationElementFound = $false
    $result.providerError = $null
    $result.overflow = 'unchanged'
    $result.overflowVisibleAfterRequest = $false
    $result.overflowClosed = $null
    $named = [System.Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::NameProperty, "IFW tray $Token")
    $help = [System.Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::HelpTextProperty, "IFW tray $Token")
    $trayName = [Windows.Automation.OrCondition]::new($named, $help)
    $noticeName = [System.Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::NameProperty, "IFW notice $Token")
    $scope = [Windows.Automation.TreeScope]::Descendants
    $registered = [IO.File]::ReadAllText((Join-Path $Fixture 'tray.ready')) -ceq 'registered'
    $menu = $null
    $triedMenu = $false
    $until = [DateTime]::UtcNow.AddSeconds(8)
    try {
        do {
            if ($null -ne $menu -and (Get-IfwOverflowWindow $menu.explorer) -ne [IntPtr]::Zero) {
                $result.overflowVisibleAfterRequest = $true
            }
            $rootsThisPoll = 0
            foreach ($class in @("Shell_TrayWnd", "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland")) {
                $handle = [IfwSyntheticShellObserver]::FindWindow($class, $null)
                $explorer = Get-IfwShellOwner $handle
                if (-not $explorer) { continue }
                try {
                    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
                    $rootsThisPoll++
                    $item = $root.FindFirst($scope, $trayName)
                    if ($null -ne $item -and $item.Current.ProcessId -eq $explorer) {
                        $result.trayElementFound = $true
                        $result.trayElementEnabled = $item.Current.IsEnabled
                        $result.trayElementOffscreen = $item.Current.IsOffscreen
                        $pattern = $null
                        $result.invokeSupported = $item.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)
                        if ($result.invokeSupported -and $result.trayElementEnabled -and -not $result.trayElementOffscreen -and -not $result.invokeSent) {
                            # Address only the exact test token through its accessibility provider.
                            $pattern.Invoke()
                            $result.invokeSent = $true
                        }
                    }
                } catch { $result.providerError = $_.Exception.HResult }
            }
            $result.taskbarRoots = [Math]::Max($result.taskbarRoots, $rootsThisPoll)
            if ($rootsThisPoll -eq 0) { break }
            if ($registered -and -not $triedMenu -and -not $result.invokeSent -and
                (-not $result.trayElementFound -or $result.trayElementOffscreen)) {
                $triedMenu = $true
                $menu = Open-IfwTrayOverflow $result
            }
            # Only inspect UI hosted by the disposable session's known Shell processes.
            # Never retain unrelated names, window titles or tree snapshots.
            $shellPids = @(Get-Process -Name explorer, ShellExperienceHost, ShellHost -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty Id)
            $rootChildren = [Windows.Automation.AutomationElement]::RootElement.FindAll(
                [Windows.Automation.TreeScope]::Children, [Windows.Automation.Condition]::TrueCondition)
            foreach ($child in $rootChildren) {
                try {
                    if ($child.Current.ProcessId -in $shellPids -and $null -ne $child.FindFirst($scope, $noticeName)) {
                        $result.notificationElementFound = $true
                    }
                } catch { $result.providerError = $_.Exception.HResult }
            }
            if ($result.invokeSent -and $result.notificationElementFound) { break }
            Start-Sleep -Milliseconds 200
        } while ([DateTime]::UtcNow -lt $until)
    } finally {
        try { Restore-IfwTrayOverflow $menu $result }
        catch {
            $result.overflowClosed = $false
            $result.restoreHresult = $_.Exception.HResult
        }
    }
}
$result | ConvertTo-Json -Compress
