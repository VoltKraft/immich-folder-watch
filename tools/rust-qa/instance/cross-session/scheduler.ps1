param(
    [Parameter(Mandatory=$true)][string]$Area,
    [switch]$VerifyCleanup
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scheduler_cleanup.ps1')
if ($env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_ACTIONS -cne 'true' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') {
    throw 'This fixture requires the disposable Windows rewrite job.'
}
$areaPath = (Get-Item -LiteralPath $Area).FullName
$taskName = [IO.Path]::GetFileName($areaPath)
if ($taskName -cnotmatch '^IfwQaCross_[a-f0-9]{32}$' -or
    [IO.Path]::GetDirectoryName($areaPath) -ine (Get-Item -LiteralPath $env:RUNNER_TEMP).FullName -or
    [IO.File]::ReadAllText((Join-Path $areaPath 'profile\.ifw-instance-fixture')) -cne "synthetic-only`n") {
    throw 'Expected a new marked profile directly under the disposable runner temp directory.'
}
$config = [IO.File]::ReadAllText((Join-Path $areaPath 'controller.json')) | ConvertFrom-Json
if ($config.mode -cnotin @('hosted-S4U-ambient','hosted-S4U','hosted-temporary-standard')) { throw 'Expected a fixed hosted guard trial.' }
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $sidDigest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::ASCII.GetBytes($currentSid))).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
if ($sidDigest -cne $config.controller.sidSha256) { throw 'Controller account differs from the local registration principal.' }
# The executable is taken from the live parent, never from a command supplied in the manifest.
$python = [Diagnostics.Process]::GetProcessById([int]$config.controller.pid).MainModule.FileName
if ([IO.Path]::GetFileName($python) -notmatch '^python(?:3(?:\.\d+)?)?\.exe$') { throw 'Expected the Python controller.' }
$worker = (Get-Item -LiteralPath (Join-Path $PSScriptRoot 'worker.py')).FullName
$fixedArgs = '-I -B "' + $worker + '" "' + $areaPath + '"'
$source = 'ImmichFolderWatch rewrite fixture ' + $taskName
$report = [ordered]@{ registered = $false; cleanupVerified = $false; mode = 'on-demand S4U'; trial = $config.mode }
$task = $running = $registeredXml = $null
$owns = $false

function Assert-Definition($Registered) {
    $d = $Registered.Definition
    $principal = [string]$d.Principal.UserId
    if ($principal -notmatch '^S-1-') {
        $principal = ([Security.Principal.NTAccount]::new($principal)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    if ($Registered.Name -cne $taskName -or $d.RegistrationInfo.Source -cne $source -or
        $principal -cne $currentSid -or $d.Principal.LogonType -ne 2 -or $d.Principal.RunLevel -ne 0 -or
        $d.Triggers.Count -ne 0 -or $d.Actions.Count -ne 1 -or $d.Actions.Item(1).Type -ne 0 -or
        $d.Actions.Item(1).Path -ine $python -or $d.Actions.Item(1).Arguments -cne $fixedArgs -or
        $d.Actions.Item(1).WorkingDirectory -ine $areaPath) { throw 'Task definition ownership or fixed action differs.' }
}

function Find-ThisTask {
    try { return $folder.GetTask($taskName) }
    catch {
        if ($_.Exception.GetBaseException().HResult -eq -2147024894) { return $null }  # HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)
        throw
    }
}

function Save-Report($Name) {
    [IO.File]::WriteAllText((Join-Path $areaPath $Name), ($report | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
}

try {
    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()  # local Task Scheduler only
    $folder = $service.GetFolder('\')
    if ($VerifyCleanup) {
        $task = Find-ThisTask
        if ($null -ne $task) {
            Assert-Definition $task
            $owns = $true
            $report.recoveredRegistration = $true
        }
    } else {
        $definition = $service.NewTask(0)
        $definition.RegistrationInfo.Source = $source
        $definition.RegistrationInfo.Description = 'One-shot synthetic writer lock observation.'
        $definition.Principal.UserId = $currentSid
        $definition.Principal.LogonType = 2  # TASK_LOGON_S4U
        $definition.Principal.RunLevel = 0  # TASK_RUNLEVEL_LUA
        $definition.Settings.AllowDemandStart = $true
        $definition.Settings.DisallowStartIfOnBatteries = $false
        $definition.Settings.StopIfGoingOnBatteries = $false
        $definition.Settings.MultipleInstances = 2  # TASK_INSTANCES_IGNORE_NEW
        $definition.Settings.ExecutionTimeLimit = 'PT3M'
        $action = $definition.Actions.Create(0)  # TASK_ACTION_EXEC
        $action.Path = $python
        $action.Arguments = $fixedArgs
        $action.WorkingDirectory = $areaPath
        $task = $folder.RegisterTaskDefinition($taskName, $definition, 2, $currentSid, $null, 2, $null)  # TASK_CREATE
        $owns = $true
        $registeredXml = $task.Xml
        $report.registered = $true
        Assert-Definition $task
        $report.definition = [ordered]@{ currentSidMatched=$true; triggers=$task.Definition.Triggers.Count
            logonType=$task.Definition.Principal.LogonType; runLevel=$task.Definition.Principal.RunLevel
            actionCount=$task.Definition.Actions.Count; fixedActionMatched=$true
            executionTimeLimit=$task.Definition.Settings.ExecutionTimeLimit }
        $running = $task.Run($null)
        $report.instance = $running.InstanceGuid
        $start = [DateTime]::UtcNow
        do {
            if (Test-Path -LiteralPath (Join-Path $areaPath 'abort')) { break }
            if ($task.GetInstances(0).Count -eq 0 -and $task.State -ne 2) {
                $finished = Test-Path -LiteralPath (Join-Path $areaPath 'worker-done.json')
                if ($finished -or (([DateTime]::UtcNow - $start).TotalSeconds -gt 25 -and $task.LastTaskResult -ne 267011)) { break }
            }
            Start-Sleep -Milliseconds 150
        } while (([DateTime]::UtcNow - $start).TotalSeconds -lt 165)
        $report.lastTaskResult = $task.LastTaskResult
        $report.state = $task.State
    }
} catch {
    $report.error = $_.Exception.Message -replace '(?i)\bS-\d+-(?:\d+-)*\d+\b', '[account ID]'
    $report.hresult = ('0x{0:X8}' -f $_.Exception.GetBaseException().HResult)
    throw $report.error
} finally {
    try {
        if ($owns) {
            $current = Find-ThisTask
            if ($null -ne $current) {
                # The create-only return identifies our original definition even if a readback assertion failed.
                if ($null -eq $registeredXml -or $current.Xml -cne $registeredXml -or $current.Name -cne $taskName) {
                    Assert-Definition $current
                }
                $report.instanceExitedDuringStop = Stop-IfwOwnedTaskInstances $current $running
                $deadline = [DateTime]::UtcNow.AddSeconds(10)
                while ($current.GetInstances(0).Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {
                    Start-Sleep -Milliseconds 100
                }
                if ($current.GetInstances(0).Count -gt 0) { throw 'The owned task instance did not exit.' }
                $folder.DeleteTask($taskName, 0)
            }
        }
        if ($null -ne $folder -and $null -eq (Find-ThisTask)) { $report.cleanupVerified = $true }
    } catch {
        $report.cleanupError = $_.Exception.Message -replace '(?i)\bS-\d+-(?:\d+-)*\d+\b', '[account ID]'
        throw $report.cleanupError
    } finally {
        if ($VerifyCleanup) { Save-Report 'cleanup.json' } else { Save-Report 'scheduler.json' }
    }
    if (-not $report.cleanupVerified) { throw 'Private task removal was not verified.' }
}
