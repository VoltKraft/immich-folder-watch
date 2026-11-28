# Read two controls on the disposable ARM64 runner after the popup observation.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or
    $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or $env:RUNNER_ARCH -cne 'ARM64' -or
    $env:PROCESSOR_ARCHITECTURE -cne 'ARM64' -or $env:GITHUB_SHA -cnotmatch '^[a-f0-9]{40}$') {
    throw 'This readback requires the native ARM64 rewrite runner.'
}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class IfwToastSettings {
    [DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();
    [DllImport("shell32.dll")] public static extern int SHQueryUserNotificationState(out int state);
}
'@
$session = [Diagnostics.Process]::GetCurrentProcess().SessionId
if ($session -ne [IfwToastSettings]::WTSGetActiveConsoleSessionId()) {
    throw 'This readback requires the active console session.'
}
$element = [Windows.Automation.AutomationElement]
$scope = [Windows.Automation.TreeScope]
$root = $element::RootElement
$allowed = @((Join-Path $env:SystemRoot 'ImmersiveControlPanel/SystemSettings.exe'),
             (Join-Path $env:SystemRoot 'System32/ApplicationFrameHost.exe'))
function Get-SettingsWindow {
    $children = $root.FindAll($scope::Children, [Windows.Automation.Condition]::TrueCondition)
    foreach ($node in $children) {
        try {
            if ($node.Current.Name -notin @('Settings','Einstellungen')) { continue }
            $owner = Get-Process -Id $node.Current.ProcessId -ErrorAction SilentlyContinue
            if ($owner -and $owner.SessionId -eq $session -and $allowed -contains $owner.Path -and
                $node.Current.NativeWindowHandle -ne 0) { $node }
        } catch [Windows.Automation.ElementNotAvailableException] { continue }
    }
}
function Read-Switch($window, [string]$id) {
    $find = [Windows.Automation.PropertyCondition]::new($element::AutomationIdProperty, $id)
    $nodes = $window.FindAll($scope::Descendants, $find)
    if ($nodes.Count -ne 1) { return @{ count = $nodes.Count } }
    $node = $nodes[0]
    $owner = Get-Process -Id $node.Current.ProcessId -ErrorAction SilentlyContinue
    $pattern = $null
    if (!$owner -or $owner.SessionId -ne $session -or $allowed -notcontains $owner.Path -or
        !$node.TryGetCurrentPattern([Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) {
        return @{ count = 1; readable = $false }
    }
    return @{ count = 1; state = $pattern.Current.ToggleState.ToString(); enabled = $node.Current.IsEnabled }
}
$path = Join-Path $env:GITHUB_WORKSPACE 'artifacts/rust/windows-services/toast-settings-aarch64-pc-windows-msvc.json'
if (Test-Path -LiteralPath $path) { throw 'Expected a fresh notification settings result.' }
[int]$eligibility = 0
$hr = [IfwToastSettings]::SHQueryUserNotificationState([ref]$eligibility)
$report = [ordered]@{ head = $env:GITHUB_SHA; run = $env:GITHUB_RUN_ID; attempt = $env:GITHUB_RUN_ATTEMPT
    session = $session; afterSender = $true; eligibilityHresult = $hr; eligibilityValue = $eligibility
    scriptSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    status = 'unavailable'; opened = $false; closed = $false }
$opened = $null
try {
    if (@(Get-SettingsWindow).Count -gt 0) {
        $report.reason = 'A Settings window already existed on the console.'
    } else {
        Start-Process 'ms-settings:notifications'
        $report.requested = $true
        $deadline = [DateTime]::UtcNow.AddSeconds(12)
        do {
            $candidates = @(Get-SettingsWindow)
            if ($candidates.Count -eq 1) { $opened = $candidates[0]; break }
            if ($candidates.Count -gt 1) { throw 'Multiple newly visible Settings windows.' }
            Start-Sleep -Milliseconds 150
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($opened) {
            $report.opened = $true
            $report.hwnd = $opened.Current.NativeWindowHandle
            $report.pid = $opened.Current.ProcessId
            $deadline = [DateTime]::UtcNow.AddSeconds(8)
            do {
                $report.notifications = Read-Switch $opened 'SystemSettings_Notifications_ShowAppNotifications_ToggleSwitch'
                $report.doNotDisturb = Read-Switch $opened 'SystemSettings_Notifications_QuietHours_MuteNotification_Enabled_ToggleSwitch'
                if ($report.notifications.state -and $report.doNotDisturb.state) {
                    $report.status = 'observed'
                    break
                }
                Start-Sleep -Milliseconds 200
            } while ([DateTime]::UtcNow -lt $deadline)
        } else { $report.reason = 'The notification Settings window was unavailable.' }
    }
} finally {
    try {
        if ($opened) {
            $close = $null
            if (!$opened.TryGetCurrentPattern([Windows.Automation.WindowPattern]::Pattern, [ref]$close)) {
                throw 'The owned Settings window did not expose Close.'
            }
            $close.Close()
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            do {
                $same = @(Get-SettingsWindow | Where-Object {
                    $_.Current.NativeWindowHandle -eq $report.hwnd -and $_.Current.ProcessId -eq $report.pid
                })
                if ($same.Count -eq 0) { $report.closed = $true; break }
                Start-Sleep -Milliseconds 150
            } while ([DateTime]::UtcNow -lt $deadline)
            if (!$report.closed) { throw 'The owned Settings window was still open.' }
        }
    } finally {
        $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding UTF8
    }
}
