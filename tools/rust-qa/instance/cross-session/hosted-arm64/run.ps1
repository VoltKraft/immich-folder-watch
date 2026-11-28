$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../../../..')).Path
$runner = [Diagnostics.Process]::GetCurrentProcess()
if (!$IsWindows -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'Arm64' -or
    $env:RUNNER_ARCH -cne 'ARM64' -or $env:RUNNER_OS -cne 'Windows' -or $runner.SessionId -le 0 -or
    $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_ACTIONS -cne 'true' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or
    $root -ine $env:GITHUB_WORKSPACE -or $env:GITHUB_WORKFLOW -cne 'Rust Windows ARM64 standard-user writer') {
    throw 'Use the dedicated rewrite branch Windows ARM64 runner in its original nonzero session.'
}
$python = (Get-Command python.exe -CommandType Application).Source
$dotnet = (Get-Command dotnet.exe -CommandType Application).Source
$output = Join-Path $root 'artifacts/rust/arm64-standard-writer'
$original = Join-Path $output 'writer.zip'
if (!(Test-Path -LiteralPath $original -PathType Leaf) -or (Test-Path -LiteralPath "$output/host.json")) {
    throw 'The validated original ARM64 archive and fresh observation are required.'
}
$uid = [guid]::NewGuid().ToString('N')
$name = 'ifwqa' + $uid.Substring(0,12)
$description = "IFW writer $uid"
$folder = Join-Path $env:ProgramData "IfwWriterArm_$uid"
$work = Join-Path $folder 'work'
$taskName = 'IfwQaCross_' + [guid]::NewGuid().ToString('N')
$taskFolderName = "IfwWriterArm_$uid"
$report = [ordered]@{ revision=$env:GITHUB_SHA; runId=$env:GITHUB_RUN_ID; runAttempt=$env:GITHUB_RUN_ATTEMPT
    runnerSession=$runner.SessionId; credentialSource='random job-local SecureString'; accountCreated=$false
    profileRemoved=$false; taskRemoved=$false; accountRemoved=$false; stageRemoved=$false; serviceRestored=$false
    userProcessesExited=$false; taskFolderRemoved=$false }
$pwdChars = [Security.SecureString]::new()
foreach ($char in 'Aa8!'.ToCharArray()) {$pwdChars.AppendChar($char)}
$alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!_-+'
foreach ($i in 1..48) {$pwdChars.AppendChar($alphabet[[Security.Cryptography.RandomNumberGenerator]::GetInt32($alphabet.Length)])}
$pwdChars.MakeReadOnly()
$user = $process = $before = $created = $rightsAttempted = $taskFolder = $null
$failed = $false
function Invoke-BatchAssignment([string]$Action) {
    $raw = & $python -I -B "$PSScriptRoot/batch_account.py" $Action $folder
    if ($LASTEXITCODE -ne 0) {throw "The temporary account batch-logon $Action failed."}
    return ($raw | ConvertFrom-Json)
}
function Assert-FixedTask($task) {
    $d = $task.Definition
    $principal = $d.Principal.UserId
    if ($principal -notmatch '^S-1-') {
        $principal = ([Security.Principal.NTAccount]::new($principal)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    $fixed = Join-Path $folder 'source/tools/rust-qa/instance/cross-session/worker.py'
    $area = Join-Path $work $taskName
    if ($d.RegistrationInfo.Source -cne "ImmichFolderWatch rewrite fixture $taskName" -or $principal -ne $user.SID.Value -or
        $d.Principal.RunLevel -ne 0 -or $d.Principal.LogonType -ne 1 -or $d.Triggers.Count -ne 0 -or
        $d.Actions.Count -ne 1 -or $d.Actions.Item(1).Type -ne 0 -or $d.Actions.Item(1).Path -ine $python -or
        $d.Actions.Item(1).WorkingDirectory -ine $area -or $task.Path -cne ("\$taskFolderName\$taskName") -or
        $d.Actions.Item(1).Arguments -cne ('-I -B "' + $fixed + '" "' + $area + '"')) {
        throw 'The task name matched a different definition.'
    }
}
function Assert-TaskGone {
    if (!$taskFolder) {return $true}
    $tasks = $taskFolder
    try {$task = $tasks.GetTask($taskName)}
    catch {
        if ($_.Exception.GetBaseException().HResult -eq -2147024894) {return $true}
        throw
    }
    Assert-FixedTask $task
    . (Join-Path $PSScriptRoot '../scheduler_cleanup.ps1')
    [void](Stop-IfwOwnedTaskInstances $task $null)
    $deadline = [DateTime]::UtcNow.AddSeconds(12)
    while ($task.GetInstances(0).Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {Start-Sleep -Milliseconds 100}
    if ($task.GetInstances(0).Count -gt 0) {throw 'Owned instance still running.'}
    $tasks.DeleteTask($taskName,0)
    try {[void]$tasks.GetTask($taskName)}
    catch {
        if ($_.Exception.GetBaseException().HResult -eq -2147024894) {return $true}
        throw
    }
    throw 'The owned task remains registered.'
}
function Cleanup([scriptblock]$Action, [string]$Label) {
    try {& $Action} catch {
        $report["cleanupFailure$Label"] = $_.Exception.GetBaseException().Message.Replace($name,'[test user]') -replace 'S-1-(\d+-)+\d+', '[SID]'
    }
}
try {
    $created = New-Item -ItemType Directory -Path $folder -ErrorAction Stop
    $user = New-LocalUser -Name $name -Password $pwdChars -Description $description -AccountExpires ([DateTime]::Now.AddHours(1))
    $report.accountCreated = $true
    $report.sidSha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
        [Text.Encoding]::ASCII.GetBytes($user.SID.Value))).ToLowerInvariant()
    $users = Get-LocalGroup -SID 'S-1-5-32-545'
    if (!(Get-LocalGroupMember -Group $users | Where-Object SID -eq $user.SID)) {Add-LocalGroupMember -Group $users -Member $user}
    # Inputs are writable only by machine administrators and SYSTEM. The new user may modify its own work directory.
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($entry in @(@('S-1-5-32-544','FullControl'),@('S-1-5-18','FullControl'),@($user.SID.Value,'ReadAndExecute'))) {
        $trustee = [Security.Principal.SecurityIdentifier]::new($entry[0])
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($trustee,$entry[1],
            'ContainerInherit,ObjectInherit','None','Allow'))
    }
    Set-Acl -LiteralPath $folder -AclObject $acl
    [void](New-Item -ItemType Directory -Path $work)
    $acl = Get-Acl -LiteralPath $work
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($user.SID,'Modify','ContainerInherit,ObjectInherit','None','Allow'))
    Set-Acl -LiteralPath $work -AclObject $acl
    & $python -I -B "$PSScriptRoot/inputs.py" stage $folder
    if ($LASTEXITCODE -ne 0) {throw 'Could not stage original source-bound native inputs.'}
    $launch = [ordered]@{sidSha256=$report.sidSha256; revision=$env:GITHUB_SHA; runId=$env:GITHUB_RUN_ID
        runAttempt=$env:GITHUB_RUN_ATTEMPT; dotnet=$dotnet; taskName=$taskName; runnerSession=$runner.SessionId}
    [IO.File]::WriteAllText("$folder/launch.json",($launch | ConvertTo-Json))
    $rightsAttempted = $true
    $report.grant = Invoke-BatchAssignment grant
    $schedule = New-Object -ComObject Schedule.Service
    $schedule.Connect()
    $taskRoot = $schedule.GetFolder('\')
    $folderDacl = 'D:P(A;;FA;;;SY)(A;;FA;;;BA)'
    $taskFolder = $taskRoot.CreateFolder($taskFolderName, $folderDacl)
    $report.taskFolder = $taskFolder.Path
    $descriptor = [Security.AccessControl.RawSecurityDescriptor]::new($taskFolder.GetSecurityDescriptor(4))
    $allowed = @($descriptor.DiscretionaryAcl | ForEach-Object {$_.SecurityIdentifier.Value})
    $expected = @('S-1-5-18','S-1-5-32-544')
    $report.taskFolderTrusteesMatched = $allowed.Count -eq 2 -and !(Compare-Object ($allowed | Sort-Object) ($expected | Sort-Object))
    if (!$report.taskFolderTrusteesMatched) {throw 'Unexpected trust on the new Scheduler folder.'}
    if ($taskFolder.Path -cne "\$taskFolderName" -or $taskFolder.GetTasks(1).Count -ne 0 -or $taskFolder.GetFolders(0).Count -ne 0) {
        throw 'Expected a fresh empty folder for the single standard-user task.'
    }
    $definition = $schedule.NewTask(0)
    $definition.RegistrationInfo.Source = "ImmichFolderWatch rewrite fixture $taskName"
    $qualifiedUser = "$env:COMPUTERNAME\$name"
    $definition.Principal.UserId = $qualifiedUser
    $definition.Principal.LogonType = 1  # TASK_LOGON_PASSWORD, normal local batch logon
    $definition.Principal.RunLevel = 0  # TASK_RUNLEVEL_LUA
    $definition.Settings.AllowDemandStart = $true
    $definition.Settings.DisallowStartIfOnBatteries = $false
    $definition.Settings.StopIfGoingOnBatteries = $false
    $definition.Settings.ExecutionTimeLimit = 'PT4M'
    $definition.Settings.MultipleInstances = 2
    $area = Join-Path $work $taskName
    $fixed = Join-Path $folder 'source/tools/rust-qa/instance/cross-session/worker.py'
    $action = $definition.Actions.Create(0)
    $action.Path = $python
    $action.Arguments = '-I -B "' + $fixed + '" "' + $area + '"'
    $action.WorkingDirectory = $area
    # The disposable credential is supplied only to the local scheduler API, separately from its fixed command.
    $task = $taskFolder.RegisterTaskDefinition($taskName,$definition,2,$qualifiedUser,
        [Net.NetworkCredential]::new('',$pwdChars).Password,1,$folderDacl)
    Assert-FixedTask $task
    $report.taskDefinition = [ordered]@{fixedActionMatched=$true; currentSidMatched=$true
        logonType=$task.Definition.Principal.LogonType; runLevel=$task.Definition.Principal.RunLevel
        triggers=$task.Definition.Triggers.Count; actionCount=$task.Definition.Actions.Count}
    $before = Get-Service seclogon
    $report.serviceBefore = $before.Status.ToString()
    $report.startTypeBefore = $before.StartType.ToString()
    if ($before.Status -eq 'Stopped' -and $before.StartType -in @('Automatic','Manual')) {
        Start-Service seclogon
        $before.WaitForStatus('Running',[TimeSpan]::FromSeconds(20))
    }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.UseShellExecute = $false
    $info.FileName = $python
    $info.WorkingDirectory = $work
    $info.UserName = $name
    $info.Domain = $env:COMPUTERNAME
    $info.Password = $pwdChars
    $info.LoadUserProfile = $false
    $info.CreateNoWindow = $true
    $info.Environment.Clear()
    foreach ($key in @('SystemRoot','WINDIR','COMSPEC','SystemDrive','ProgramData','ProgramFiles','ProgramFiles(x86)',
        'RUNNER_ARCH','RUNNER_OS','RUNNER_ENVIRONMENT','GITHUB_ACTIONS','GITHUB_REF','GITHUB_REPOSITORY',
        'GITHUB_WORKFLOW','GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')) {
        $value = [Environment]::GetEnvironmentVariable($key)
        if ($value) {$info.Environment[$key] = $value}
    }
    $info.Environment['PATH'] = "$env:SystemRoot\System32;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    $info.Environment['TEMP'] = $work
    $info.Environment['TMP'] = $work
    foreach ($arg in @('-I','-B',"$folder/source/tools/rust-qa/instance/cross-session/hosted-arm64/case.py",$folder)) {
        $info.ArgumentList.Add($arg)
    }
    $process = [Diagnostics.Process]::Start($info)
    $deadline = [DateTime]::UtcNow.AddSeconds(65)
    while (!(Test-Path -LiteralPath "$area/start-peer") -and !$process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
    if (!(Test-Path -LiteralPath "$area/start-peer")) {throw 'The ordinary controller did not prepare its marked guard.'}
    $running = $task.Run($null)
    $report.taskInstance = $running.InstanceGuid
    $deadline = [DateTime]::UtcNow.AddSeconds(300)
    while (!$process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        if ($task.GetInstances(0).Count -eq 0 -and $task.State -ne 2 -and
            $task.LastTaskResult -notin @(0,267009,267011)) {
            $report.taskLastResult = $task.LastTaskResult
            throw 'The registered fixed task exited unsuccessfully.'
        }
        Start-Sleep -Milliseconds 200
    }
    if (!$process.HasExited) {throw 'The ordinary-user controller did not finish in time.'}
    $report.controllerExit = $process.ExitCode
    if ($process.ExitCode -ne 0) {throw 'The ordinary-user Windows ARM64 handover failed.'}
    $deadline = [DateTime]::UtcNow.AddSeconds(12)
    while ($task.GetInstances(0).Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {Start-Sleep -Milliseconds 100}
    $report.taskLastResult = $task.LastTaskResult
    if ($task.GetInstances(0).Count -ne 0 -or $report.taskLastResult -ne 0) {throw 'The fixed task did not exit successfully.'}
} catch {
    $failed = $true
    $report.error = $_.Exception.GetBaseException().Message.Replace($name,'[test user]') -replace 'S-1-(\d+-)+\d+', '[SID]'
} finally {
    if ($null -ne $process) {
        Cleanup {
            if (!$process.HasExited) {
                $area = Join-Path $work $taskName
                if (Test-Path -LiteralPath $area) {[IO.File]::WriteAllText("$area/abort",'')}
                if (!$process.WaitForExit(30000)) {$process.Kill($true); $process.WaitForExit()}
            }
            $process.Dispose()
        } 'Process'
    }
    $pwdChars.Dispose()
    if ($user) {
        Cleanup {$report.taskRemoved = Assert-TaskGone} 'Task'
        Cleanup {
            if ($taskFolder) {
                if ($taskFolder.GetTasks(1).Count -ne 0 -or $taskFolder.GetFolders(0).Count -ne 0) {
                    throw 'The owned Scheduler folder still contains objects.'
                }
                $taskRoot.DeleteFolder($taskFolderName,0)
                try {[void]$taskRoot.GetFolder($taskFolderName)}
                catch {
                    if ($_.Exception.GetBaseException().HResult -in @(-2147024894,-2147024893)) {
                        $report.taskFolderRemoved = $true
                    } else {throw}
                }
            }
        } 'TaskFolder'
        Cleanup {
            $owner = "$env:COMPUTERNAME\$name"
            $deadline = [DateTime]::UtcNow.AddSeconds(25)
            do {
                $left = @(Get-Process -IncludeUserName | Where-Object UserName -ieq $owner)
                if (!$left.Count) {break}
                Start-Sleep -Milliseconds 250
            } while ([DateTime]::UtcNow -lt $deadline)
            $report.userProcessesExited = $left.Count -eq 0
        } 'Exit'
        Cleanup {
            $receipts = Join-Path $work 'receipts'
            foreach ($directory in @($work,$receipts)) {
                if ((Test-Path -LiteralPath $directory) -and
                    ((Get-Item -LiteralPath $directory).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    throw 'Unexpected observation directory link.'
                }
            }
            foreach ($file in @('case','original-bootstrap-done','worker-done')) {
                $path = Join-Path $work "receipts/$file.json"
                if (Test-Path -LiteralPath $path -PathType Leaf) {
                    $observed = Get-Item -LiteralPath $path
                    if (($observed.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $observed.Length -gt 512KB) {
                        throw 'Unexpected observation file.'
                    }
                    Copy-Item -LiteralPath $path -Destination "$output/$file.json"
                }
            }
        } 'Receipts'
        if ($rightsAttempted) {Cleanup {$report.restore = Invoke-BatchAssignment restore} 'Assignment'}
        Cleanup {
            $profile = Get-CimInstance Win32_UserProfile -Filter "SID='$($user.SID.Value)'"
            if ($profile) {
                $deadline = [DateTime]::UtcNow.AddSeconds(20)
                while ($profile.Loaded -and [DateTime]::UtcNow -lt $deadline) {
                    Start-Sleep -Milliseconds 300
                    $profile = Get-CimInstance Win32_UserProfile -Filter "SID='$($user.SID.Value)'"
                    if (!$profile) {break}
                }
                if ($profile) {
                    if ($profile.Loaded -or $profile.Special) {throw 'Own test profile is in use or special.'}
                    Remove-CimInstance -InputObject $profile
                }
            }
            $report.profileRemoved = $null -eq (Get-CimInstance Win32_UserProfile -Filter "SID='$($user.SID.Value)'")
        } 'Profile'
        Cleanup {
            $owned = Get-LocalUser -SID $user.SID
            if ($owned.Name -cne $name -or $owned.Description -cne $description) {throw 'Temporary user identity differs.'}
            Remove-LocalUser -SID $user.SID
            $report.accountRemoved = -not (Get-LocalUser | Where-Object SID -eq $user.SID)
        } 'User'
    }
    if ($before) {Cleanup {
        $service = Get-Service seclogon
        if ($report.serviceBefore -eq 'Stopped' -and $service.Status -ne 'Stopped') {
            Stop-Service seclogon
            $service.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(20))
        }
        $service.Refresh()
        $report.serviceRestored = $service.Status.ToString() -eq $report.serviceBefore -and $service.StartType.ToString() -eq $report.startTypeBefore
    } 'Service'}
    if ($created) {Cleanup {
        Remove-Item -LiteralPath $folder -Force -Recurse
        $report.stageRemoved = !(Test-Path -LiteralPath $folder)
    } 'Stage'}
    [IO.File]::WriteAllText("$output/host.json",($report | ConvertTo-Json -Depth 8))
}
if ($failed -or !$report.userProcessesExited -or !$report.profileRemoved -or !$report.accountRemoved -or !$report.taskRemoved -or !$report.taskFolderRemoved -or !$report.stageRemoved -or
    !$report.serviceRestored -or $report.Keys.Where({$_.StartsWith('cleanupFailure')}).Count) {throw 'See the scoped ARM64 host and case receipts.'}
