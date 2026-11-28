# Observe Windows Settings and run a reversible Do not disturb comparison on a dedicated ARM64 console.
param([ValidateSet('Read','Permit','Restore')][string]$Action = 'Read')
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or
    $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or $env:RUNNER_ARCH -cne 'ARM64' -or
    $env:PROCESSOR_ARCHITECTURE -cne 'ARM64' -or $env:GITHUB_SHA -cnotmatch '^[a-f0-9]{40}$') {
    throw 'This readback requires the native ARM64 rewrite runner.'
}
if ($Action -ne 'Read' -and ($env:GITHUB_JOB -cne 'observe' -or
    $env:GITHUB_WORKFLOW -cne 'Rust Windows ARM64 notification on a fresh console' -or
    $env:IFW_QA_TOAST_POLICY -cne 'permitted')) {
    throw 'The temporary change requires the disposable ARM64 notification comparison.'
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
function Read-Switch($window, [string]$id, [ref]$patternOut = $null) {
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
    if ($null -ne $patternOut) { $patternOut.Value = $pattern }
    return @{ count = 1; state = $pattern.Current.ToggleState.ToString(); enabled = $node.Current.IsEnabled }
}
$folder = Join-Path $env:GITHUB_WORKSPACE 'artifacts/rust/windows-services'
$stem = 'toast-settings-aarch64-pc-windows-msvc'
$suffix = if ($Action -eq 'Read') { '' } else { '-' + $Action.ToLowerInvariant() }
$path = Join-Path $folder ($stem + $suffix + '.json')
$intentPath = Join-Path $folder ($stem + '-intent.json')
$masterId = 'SystemSettings_Notifications_ShowAppNotifications_ToggleSwitch'
$dndId = 'SystemSettings_Notifications_QuietHours_MuteNotification_Enabled_ToggleSwitch'
if (Test-Path -LiteralPath $path) { throw 'Expected a fresh notification settings result.' }
[int]$eligibility = 0
$hr = [IfwToastSettings]::SHQueryUserNotificationState([ref]$eligibility)
$report = [ordered]@{ head = $env:GITHUB_SHA; run = $env:GITHUB_RUN_ID; attempt = $env:GITHUB_RUN_ATTEMPT
    session = $session; action = $Action; afterSender = $Action -ne 'Permit'; eligibilityHresult = $hr; eligibilityValue = $eligibility
    scriptSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    status = 'unavailable'; opened = $false; closed = $false }
# Persist the intent before the native toggle. The restore step can recover
# it even if the setter or its subsequent readback fails.
function Save-Intent {
    $intent = [ordered]@{ run = $env:GITHUB_RUN_ID; attempt = $env:GITHUB_RUN_ATTEMPT
        head = $env:GITHUB_SHA; session = $session; scriptSha256 = $report.scriptSha256
        control = $dndId; original = 'On'; desired = 'Off' }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($intent | ConvertTo-Json -Compress))
    $file = [IO.File]::Open($intentPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $file.Write($bytes, 0, $bytes.Length); $file.Flush($true) } finally { $file.Dispose() }
}
function Confirm-Intent {
    $intent = Get-Content -Raw -LiteralPath $intentPath | ConvertFrom-Json
    if ($intent.head -cne $env:GITHUB_SHA -or $intent.run -cne $env:GITHUB_RUN_ID -or
        $intent.attempt -cne $env:GITHUB_RUN_ATTEMPT -or $intent.session -ne $session -or
        $intent.scriptSha256 -cne $report.scriptSha256 -or $intent.control -cne $dndId -or
        $intent.original -cne 'On' -or $intent.desired -cne 'Off') {
        throw 'The rollback intent does not belong to this console and run.'
    }
}
function Set-TestDnd($opened, $dndPattern) {
    if ($report.status -ne 'observed' -or !$dndPattern -or !$report.doNotDisturb.enabled -or
        $report.doNotDisturb.state -notin @('On','Off')) {
        throw 'The original Do not disturb control is unavailable.'
    }
    if ($Action -eq 'Restore') {
        Confirm-Intent
        $desired = 'On'
    } else {
        if ($report.notifications.state -cne 'On') { throw 'Notifications are disabled for this user.' }
        $desired = 'Off'
    }
    if ($report.doNotDisturb.state -cne $desired) {
        if ($dndPattern.Current.ToggleState.ToString() -cne $report.doNotDisturb.state) {
            throw 'The setting changed before the requested transition.'
        }
        if ($Action -eq 'Permit') { Save-Intent }
        $report.toggleRequested = $true
        $dndPattern.Toggle()
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $report.finalDoNotDisturb = Read-Switch $opened $dndId
        if ($report.finalDoNotDisturb.state -ceq $desired) { break }
        Start-Sleep -Milliseconds 120
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($report.finalDoNotDisturb.state -cne $desired) { throw 'The switch did not reach the required state.' }
    $report.status = if ($Action -eq 'Restore') { 'restored' } else { 'permitted' }
}
$opened = $null
try {
    if ($Action -eq 'Restore' -and !(Test-Path -LiteralPath $intentPath)) {
        $report.status = 'no-owned-change'
    } elseif (@(Get-SettingsWindow).Count -gt 0) {
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
                $dndPattern = $null
                $report.notifications = Read-Switch $opened $masterId
                $report.doNotDisturb = Read-Switch $opened $dndId ([ref]$dndPattern)
                if ($report.notifications.state -and $report.doNotDisturb.state) {
                    $report.status = 'observed'
                    break
                }
                Start-Sleep -Milliseconds 200
            } while ([DateTime]::UtcNow -lt $deadline)
            if ($Action -ne 'Read') { Set-TestDnd $opened $dndPattern }
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
if ($Action -eq 'Permit' -and $report.status -cne 'permitted') { throw 'The controlled trial has no verified starting setting.' }
if ($Action -eq 'Restore' -and $report.status -notin @('restored','no-owned-change')) { throw 'Restoration was not confirmed.' }
