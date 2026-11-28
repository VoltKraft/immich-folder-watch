param(
    [Parameter(Mandatory)][int]$SubjectPid,
    [Parameter(Mandatory)][long]$Window,
    [Parameter(Mandatory)][string]$OutputPath,
    [switch]$Keyboard
)
$ErrorActionPreference = 'Stop'
$hosted = $env:GITHUB_ACTIONS -ceq 'true' -and $env:RUNNER_ENVIRONMENT -ceq 'github-hosted' -and
    $env:RUNNER_OS -ceq 'Windows' -and $env:RUNNER_ARCH -ceq 'ARM64' -and
    $env:GITHUB_REPOSITORY -ceq 'VoltKraft/immich-folder-watch' -and $env:GITHUB_REF -ceq 'refs/heads/rewrite/rust'
$localVm = $env:IFW_QA_LOCAL_WINDOWS -ceq '1' -and !$env:GITHUB_ACTIONS -and !$env:RUNNER_ENVIRONMENT -and
    [Environment]::MachineName -ieq 'IFW-QA25' -and $env:PROCESSOR_ARCHITECTURE -ceq 'AMD64' -and
    [Security.Principal.WindowsIdentity]::GetCurrent().Name -ieq 'IFW-QA25\ifw-test'
if ($localVm) {
    $account = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    $localVm = !$account.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and
        (Get-CimInstance Win32_ComputerSystem).HypervisorPresent -eq $true
}
if ((!$hosted -and !$localVm) -or $env:IFW_QA_WINDOWS_TRAY -cne '1' -or
    $env:IFW_QA_WINDOWS_LAUNCHER -cne '1' -or $env:IFW_QA_BENCHMARK -cne '1' -or
    $env:IFW_QA_ISOLATED -cne '1' -or $env:IFW_QA_INVENTORY_TOKEN -cnotmatch '^[0-9a-f]{32}$') {
    throw 'Select the isolated Windows tray fixture.'
}
$temp = if ($localVm) { $env:IFW_QA_LOCAL_TEMP } else { $env:RUNNER_TEMP }
$profileRoot = Join-Path $temp "ifw-rw02-$env:IFW_QA_INVENTORY_TOKEN"
if ([IO.Path]::GetFullPath($env:IFW_QA_INVENTORY_ROOT) -ine $profileRoot -or
    [IO.File]::ReadAllText((Join-Path $profileRoot 'inventory.owner')) -cne $env:IFW_QA_INVENTORY_TOKEN) {
    throw 'The original private inventory marker is missing.'
}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$subject = [Diagnostics.Process]::GetProcessById($SubjectPid)
$root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Window)
if ($root.Current.ProcessId -ne $subject.Id -or $root.Current.Name -cne 'Desktop input probe') {
    throw 'Expected the native GUI window owned by the observed child.'
}
$buttonType = [Windows.Automation.PropertyCondition]::new(
    [Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Button)
$name = [Windows.Automation.PropertyCondition]::new(
    [Windows.Automation.AutomationElement]::NameProperty, 'Beenden')
$selector = [Windows.Automation.AndCondition]::new($buttonType, $name)
$deadline = [DateTime]::UtcNow.AddSeconds(12)
do {
    if ($subject.HasExited) { throw 'The GUI exited before the user action.' }
    $matches = $root.FindAll([Windows.Automation.TreeScope]::Descendants, $selector)
    if ($matches.Count -eq 1) { break }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
if ($matches.Count -ne 1) { throw 'Expected one German Quit button in the observed window.' }
$button = $matches[0]
$state = $button.Current
if ($state.ProcessId -ne $SubjectPid -or -not $state.IsEnabled -or $state.IsOffscreen -or
    $state.BoundingRectangle.IsEmpty -or $state.BoundingRectangle.Width -le 0 -or $state.BoundingRectangle.Height -le 0) {
    throw 'The owned Quit button is not visible and enabled.'
}
$report = [ordered]@{
    pid=$state.ProcessId; hwnd=$Window; name=$state.Name; enabled=$state.IsEnabled
    offscreen=$state.IsOffscreen; width=$state.BoundingRectangle.Width
    height=$state.BoundingRectangle.Height; method='InvokePattern'
}
if ($Keyboard) {
    if (-not $hosted) { throw 'Select the native ARM64 keyboard fixture.' }
    $report.method = 'SendInput'
    try {
        . (Join-Path $PSScriptRoot 'window-quit-keys.ps1')
        Invoke-KeyboardQuit $root $button ([IntPtr]$Window) $SubjectPid $report
    } finally {
        [IO.File]::WriteAllText($OutputPath, ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    }
    return
}
$action = $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern)
$action.Invoke()
[IO.File]::WriteAllText($OutputPath, ($report | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
