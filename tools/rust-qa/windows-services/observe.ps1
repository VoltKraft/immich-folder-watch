param(
    [Parameter(Mandatory)][ValidateSet("private", "startup", "tray")][string]$Stage,
    [Parameter(Mandatory)][string]$Fixture,
    [Parameter(Mandatory)][ValidatePattern("^[0-9a-f]{32}$")][string]$Token,
    [Parameter(Mandatory)][string]$Executable
)

$ErrorActionPreference = "Stop"
$result = [ordered]@{ stage = $Stage }
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
    $shell = New-Object -ComObject WScript.Shell
    try {
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
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class IfwSyntheticShellObserver {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindow(string className, string title);
}
"@
    $result.taskbarRoots = 0
    $result.trayElementFound = $false
    $result.trayElementEnabled = $false
    $result.trayElementOffscreen = $null
    $result.invokeSupported = $false
    $result.invokeSent = $false
    $result.notificationElementFound = $false
    $result.providerError = $null
    $trayName = [System.Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::NameProperty, "IFW tray $Token")
    $noticeName = [System.Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::NameProperty, "IFW notice $Token")
    $scope = [Windows.Automation.TreeScope]::Descendants
    $until = [DateTime]::UtcNow.AddSeconds(4)
    do {
        $rootsThisPoll = 0
        foreach ($class in @("Shell_TrayWnd", "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland")) {
            $handle = [IfwSyntheticShellObserver]::FindWindow($class, $null)
            if ($handle -eq [IntPtr]::Zero) { continue }
            try {
                $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
                $rootsThisPoll++
                $item = $root.FindFirst($scope, $trayName)
                if ($null -ne $item) {
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
        if ($result.trayElementFound -and $result.notificationElementFound) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $until)
}
$result | ConvertTo-Json -Compress
