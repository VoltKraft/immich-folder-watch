[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CandidateMsi,
    [Parameter(Mandatory = $true)][string]$CandidatePublishDirectory,
    [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
    [string]$CandidateVersion = "3.0.4"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# This test installs/uninstalls system software and must never run on a user's PC.
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne "true" -or $env:RUNNER_ENVIRONMENT -ne "github-hosted") {
    throw "Installed upgrade tests require a disposable GitHub-hosted Windows runner."
}
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Installed upgrade tests require an elevated runner."
}
if ([version]$CandidateVersion -le [version]"3.0.3") { throw "Candidate MSI must be newer than 3.0.3." }

$CandidateMsi = (Resolve-Path -LiteralPath $CandidateMsi).Path
$CandidatePublishDirectory = (Resolve-Path -LiteralPath $CandidatePublishDirectory).Path
$EvidenceDirectory = [IO.Path]::GetFullPath($EvidenceDirectory)
[void](New-Item -ItemType Directory -Path $EvidenceDirectory -Force)
$installDirectory = Join-Path $env:ProgramFiles "Immich Folder Watch\bin"
$userDirectory = Join-Path $env:LOCALAPPDATA "Immich Folder Watch"
$configPath = Join-Path $userDirectory "config.yaml"
$sentinelPath = Join-Path $userDirectory "upgrade-test-sentinel.txt"
$exePath = Join-Path $installDirectory "ImmichFolderWatch.exe"
$startupShortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "Immich Folder Watch.lnk"
$legacyDirectory = Join-Path $env:ProgramData "Immich Folder Watch"
$baselineMsi = Join-Path $EvidenceDirectory "immich-folder-watch-3.0.3-win-x64.msi"
$summaryPath = Join-Path $EvidenceDirectory "upgrade-result.json"
$summary = [ordered]@{
    sourceCommit = $env:GITHUB_SHA
    baselineVersion = "3.0.3"
    candidateMsiVersion = $CandidateVersion
    candidateMsiSha256 = (Get-FileHash -LiteralPath $CandidateMsi -Algorithm SHA256).Hash
    status = "running"
    rebootPerformed = $false
}
$testOwnsInstallation = $false
$cleanupFailed = $false

function Get-InstalledProducts {
    foreach ($root in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")) {
        foreach ($key in @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
            $entry = Get-ItemProperty -LiteralPath $key.PSPath
            if ($entry.PSObject.Properties["DisplayName"] -and $entry.DisplayName -eq "Immich Folder Watch") {
                [pscustomobject]@{ ProductCode = $key.PSChildName; Version = $entry.DisplayVersion }
            }
        }
    }
}

function Get-PendingAppOperations {
    $key = Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager"
    foreach ($name in @("PendingFileRenameOperations", "PendingFileRenameOperations2")) {
        if ($key.PSObject.Properties[$name]) {
            foreach ($value in @($key.$name)) {
                if ($value -like "*Immich Folder Watch*") { [string]$value }
            }
        }
    }
}

function Invoke-TestMsi {
    param([string]$Operation, [string]$Package, [string]$LogName)
    $logPath = Join-Path $EvidenceDirectory $LogName
    $arguments = "$Operation `"$Package`" /qn /norestart /L*V `"$logPath`""
    $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList $arguments -PassThru
    try {
        if (-not $process.WaitForExit(300000)) {
            $process.Kill()
            throw "MSI operation timed out; see $logName."
        }
        $process.Refresh()
        $exitCode = $process.ExitCode
        if ($exitCode -ne 0) {
            throw "MSI operation failed or requires a reboot (exit $exitCode); see $logName."
        }
        return $exitCode
    }
    finally { $process.Dispose() }
}

function Wait-ForApplication {
    param([Diagnostics.Process]$Process)
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Application exited before startup verification (exit $($Process.ExitCode))." }
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero -and $Process.Responding) {
            $modules = @($Process.Modules | Where-Object { $_.ModuleName -in @("coreclr.dll", "hostpolicy.dll") })
            if ($modules.Count -eq 2) {
                foreach ($module in $modules) {
                    if (-not [string]::Equals([IO.Path]::GetDirectoryName($module.FileName), $installDirectory, [StringComparison]::OrdinalIgnoreCase)) {
                        throw "Application loaded runtime from outside its installed payload: $($module.FileName)"
                    }
                }
                Start-Sleep -Seconds 3
                $Process.Refresh()
                if ($Process.HasExited -or -not $Process.Responding) { throw "Application did not remain responsive after startup." }
                return [ordered]@{
                    processId = $Process.Id
                    windowHandle = $Process.MainWindowHandle.ToInt64()
                    loadedRuntimeModules = @($modules | ForEach-Object { $_.FileName })
                }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Application did not expose a responsive window with app-local runtime modules within 90 seconds."
}

function Assert-InstalledPayload {
    $checked = @()
    foreach ($source in @(Get-ChildItem -LiteralPath $CandidatePublishDirectory -File -Recurse)) {
        if ($source.Extension -eq ".pdb") { continue }
        $relative = [IO.Path]::GetRelativePath($CandidatePublishDirectory, $source.FullName)
        $destination = Join-Path $installDirectory $relative
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) { throw "Installed payload is missing $relative." }
        $expected = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash
        $actual = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($actual -ne $expected) { throw "Installed payload hash mismatch: $relative" }
        $checked += [ordered]@{ path = $relative; sha256 = $actual }
    }
    foreach ($required in @("ImmichFolderWatch.exe", "hostfxr.dll", "hostpolicy.dll", "coreclr.dll", "ImmichFolderWatch.runtimeconfig.json")) {
        if ($required -notin @($checked | ForEach-Object { $_.path })) { throw "Candidate publish output itself omits $required." }
    }
    if ($checked.Count -lt 5) { throw "Candidate payload is unexpectedly empty." }
    $checked | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory "installed-payload.json") -Encoding utf8
    return $checked.Count
}

# All preconditions precede installation and ownership of cleanup.
if (@(Get-InstalledProducts).Count -ne 0 -or (Test-Path -LiteralPath $installDirectory) -or
    (Test-Path -LiteralPath $userDirectory) -or (Test-Path -LiteralPath $legacyDirectory) -or
    (Test-Path -LiteralPath $startupShortcut) -or @(Get-Process -Name ImmichFolderWatch -ErrorAction SilentlyContinue).Count -ne 0) {
    throw "Runner is not clean; refusing to touch an existing installation or user data."
}
if (@(Get-PendingAppOperations).Count -ne 0) { throw "Runner has pre-existing deferred application file operations." }

try {
    Invoke-WebRequest -Uri "https://github.com/VoltKraft/immich-folder-watch/releases/download/v3.0.3/immich-folder-watch-3.0.3-win-x64.msi" -OutFile $baselineMsi
    $baselineHash = (Get-FileHash -LiteralPath $baselineMsi -Algorithm SHA256).Hash
    if ($baselineHash -ne "E2559768224568EAAE67DB9B19B82D8390720FFB9692CFE6248F69F08042CC6C") {
        throw "Released baseline MSI SHA-256 mismatch."
    }
    $summary.baselineMsiSha256 = $baselineHash
    $testOwnsInstallation = $true
    $summary.baselineInstallExitCode = Invoke-TestMsi /i $baselineMsi "baseline-install.log"
    $oldProducts = @(Get-InstalledProducts)
    if ($oldProducts.Count -ne 1 -or $oldProducts[0].Version -ne "3.0.3") { throw "Baseline product registration is incorrect." }
    $summary.baselineProductCode = $oldProducts[0].ProductCode

    [void](New-Item -ItemType Directory -Path $userDirectory -Force)
    # Empty credentials and source list are intentionally invalid for synchronization.
    # Startup still exercises the real WPF host and tray without an Immich connection.
    "immich:`n  serverApiUrl: ''`n  apiKey: ''`nwatch:`n  sources: []`n" | Set-Content -LiteralPath $configPath -Encoding utf8
    "Synthetic upgrade preservation sentinel" | Set-Content -LiteralPath $sentinelPath -Encoding utf8
    $configHash = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
    $sentinelHash = (Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash
    $oldProcess = Start-Process -FilePath $exePath -PassThru
    $summary.baselineApplication = Wait-ForApplication $oldProcess
    $oldProcess.Refresh()
    if ($oldProcess.HasExited) { throw "Baseline application exited before upgrade began." }
    $summary.upgradeStartedWithProcessId = $oldProcess.Id
    $summary.upgradeExitCode = Invoke-TestMsi /i $CandidateMsi "running-app-upgrade.log"
    if (-not $oldProcess.WaitForExit(30000)) { throw "Old application process remained alive after upgrade." }
    $summary.oldProcessExited = $true
    $oldProcess.Dispose()

    $newProducts = @(Get-InstalledProducts)
    if ($newProducts.Count -ne 1 -or $newProducts[0].Version -ne $CandidateVersion -or
        $newProducts[0].ProductCode -eq $summary.baselineProductCode) {
        throw "Upgrade did not replace the baseline product registration with the candidate."
    }
    $summary.candidateProductCode = $newProducts[0].ProductCode
    $summary.verifiedPayloadFiles = Assert-InstalledPayload
    if ((Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash -ne $configHash -or
        (Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash -ne $sentinelHash) {
        throw "Upgrade changed the synthetic per-user configuration or sentinel."
    }
    $summary.userDataPreserved = $true
    $pending = @(Get-PendingAppOperations)
    $summary.pendingAppFileOperations = $pending
    if ($pending.Count -ne 0) { throw "Upgrade left deferred application file operations; a reboot test is required." }

    $processes = @(Get-Process -Name ImmichFolderWatch -ErrorAction SilentlyContinue)
    if ($processes.Count -gt 1) { throw "Multiple application instances remain after upgrade." }
    $newProcess = if ($processes.Count -eq 1) { $processes[0] } else { Start-Process -FilePath $exePath -PassThru }
    if (-not [string]::Equals($newProcess.Path, $exePath, [StringComparison]::OrdinalIgnoreCase)) { throw "Unexpected application path after upgrade." }
    $summary.candidateApplication = Wait-ForApplication $newProcess
    $newProcess.Dispose()
    $summary.status = "passed"
}
catch {
    $summary.status = "failed"
    $summary.failure = $_.Exception.Message
    throw
}
finally {
    if ($testOwnsInstallation) {
        try {
            # Cleanup occurs only after evidence collection, never to make the upgrade pass.
            foreach ($cleanupProcess in @(Get-Process -Name ImmichFolderWatch -ErrorAction SilentlyContinue)) {
                try {
                    $cleanupProcess.Kill()
                    if (-not $cleanupProcess.WaitForExit(30000)) { throw "Application did not exit for cleanup." }
                }
                finally { $cleanupProcess.Dispose() }
            }
            foreach ($product in @(Get-InstalledProducts)) {
                [void](Invoke-TestMsi /x $product.ProductCode "cleanup-uninstall.log")
            }
            if (@(Get-InstalledProducts).Count -ne 0) { throw "Test product registration remains after cleanup." }
            if (Test-Path -LiteralPath $startupShortcut) { Remove-Item -LiteralPath $startupShortcut -Force }
            if (Test-Path -LiteralPath $userDirectory) {
                $logDirectory = Join-Path $userDirectory "logs"
                if (Test-Path -LiteralPath $logDirectory) { Copy-Item -LiteralPath $logDirectory -Destination (Join-Path $EvidenceDirectory "application-logs") -Recurse -Force }
                Remove-Item -LiteralPath $userDirectory -Recurse -Force
            }
            $summary.cleanup = "passed"
        }
        catch {
            $cleanupFailed = $true
            $summary.cleanup = "failed"
            $summary.cleanupFailure = $_.Exception.Message
            $summary.status = "failed"
            Write-Warning "Disposable-runner cleanup failed: $($_.Exception.Message)"
        }
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    # Keep logs and JSON evidence, not the already-public baseline installer binary.
    if (Test-Path -LiteralPath $baselineMsi) { Remove-Item -LiteralPath $baselineMsi -Force }
}
if ($cleanupFailed) { throw "Installed-upgrade checks passed but disposable-runner cleanup failed." }
