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
    param([string]$Operation, [string]$Package, [string]$LogName, [switch]$AllowGuardRefusal)
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
        if ($exitCode -ne 0 -and -not ($AllowGuardRefusal -and $exitCode -eq 1603)) {
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
                    sessionId = $Process.SessionId
                    windowHandle = $Process.MainWindowHandle.ToInt64()
                    loadedRuntimeModules = @($modules | ForEach-Object { $_.FileName })
                }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Application did not expose a responsive window with app-local runtime modules within 90 seconds."
}

function Get-InstalledSnapshot {
    $snapshot = [ordered]@{}
    foreach ($file in @(Get-ChildItem -LiteralPath $installDirectory -File -Recurse | Sort-Object FullName)) {
        $relative = [IO.Path]::GetRelativePath($installDirectory, $file.FullName)
        $snapshot[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    }
    if ($snapshot.Count -lt 5) { throw "Installed baseline snapshot is unexpectedly empty." }
    return $snapshot
}

function Assert-SafeRunningRefusal {
    param([System.Collections.IDictionary]$BaselineSnapshot, [string]$BaselineProductCode,
        [string]$ConfigHash, [string]$SentinelHash, [Diagnostics.Process]$Process)
    $log = Get-Content -LiteralPath (Join-Path $EvidenceDirectory "running-app-upgrade.log") -Raw
    if ($log -notmatch '(?im)^Action ended [^\r\n]*: EnsureAppClosed\. Return value 3\.' -or
        $log -notmatch '(?im)^Property\(S\): IFW_APP_RUNNING = 1\s*$') {
        throw "Exit 1603 was not the expected running-application guard refusal."
    }
    # A generic 1603 or a rollback after removal is not evidence of safe early refusal.
    if ($log -match '(?im)(?:Doing action: |^Action start [^\r\n]*: )(?:InstallValidate|InstallInitialize|RemoveExistingProducts|RemoveFiles|InstallFiles)(?:\.|\s|$)') {
        throw "Running-app refusal occurred after a forbidden install/removal action began."
    }
    $after = Get-InstalledSnapshot
    if ($after.Count -ne $BaselineSnapshot.Count) { throw "Safe refusal changed the installed file set." }
    foreach ($name in $BaselineSnapshot.Keys) {
        if (-not $after.Contains($name) -or $after[$name] -ne $BaselineSnapshot[$name]) {
            throw "Safe refusal changed or removed baseline payload: $name"
        }
    }
    $products = @(Get-InstalledProducts)
    if ($products.Count -ne 1 -or $products[0].ProductCode -ne $BaselineProductCode -or $products[0].Version -ne "3.0.3") {
        throw "Safe refusal changed baseline product registration."
    }
    if ((Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash -ne $ConfigHash -or
        (Get-FileHash -LiteralPath $sentinelPath -Algorithm SHA256).Hash -ne $SentinelHash) {
        throw "Safe refusal changed synthetic user data."
    }
    if (@(Get-PendingAppOperations).Count -ne 0) { throw "Safe refusal left pending application file operations." }
    $Process.Refresh()
    if ($Process.HasExited) { throw "Expected refused-upgrade baseline process is no longer running." }
}

function Close-TestApplicationGracefully {
    param([Diagnostics.Process]$Process)
    # Exercise the real tray Quit command, including the application's normal
    # shutdown handlers. Never terminate a process to make the upgrade pass.
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
public static class UpgradeTestTrayQuit
{
    private delegate bool EnumWindowsProc(IntPtr window, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr parameter);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string className, string title);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder name, int length);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool PostMessage(IntPtr window, uint message, UIntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SendMessageTimeout(IntPtr window, uint message, UIntPtr wParam,
        IntPtr lParam, uint flags, uint timeout, out UIntPtr result);
    [DllImport("user32.dll")] private static extern int GetMenuItemCount(IntPtr menu);
    [DllImport("user32.dll")] private static extern uint GetMenuItemID(IntPtr menu, int position);
    [DllImport("user32.dll")] private static extern uint GetMenuState(IntPtr menu, uint item, uint flags);
    [StructLayout(LayoutKind.Sequential)] private struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct MouseInput
    {
        public int X, Y;
        public uint MouseData, Flags, Time;
        public UIntPtr ExtraInfo;
    }
    [StructLayout(LayoutKind.Sequential)] private struct Input { public uint Type; public MouseInput Mouse; }
    [DllImport("user32.dll")] private static extern bool GetMenuItemRect(IntPtr window, IntPtr menu, uint item, out Rect rect);
    [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] private static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] private static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, Input[] input, int size);
    private static bool OwnedWindow(IntPtr window, int processId)
    {
        if (!IsWindow(window)) return false;
        GetWindowThreadProcessId(window, out uint owner);
        return owner == processId;
    }
    private static string ClassName(IntPtr window)
    {
        var name = new StringBuilder(256);
        GetClassName(window, name, name.Capacity);
        return name.ToString();
    }
    public static string Describe(int processId)
    {
        var entries = new List<string>();
        EnumWindows((window, parameter) => {
            if (OwnedWindow(window, processId)) entries.Add("top-level " + window + " " + ClassName(window));
            return entries.Count < 64;
        }, IntPtr.Zero);
        var message = IntPtr.Zero;
        for (int count = 0; count < 256; count++)
        {
            message = FindWindowEx(new IntPtr(-3), message, null, null);
            if (message == IntPtr.Zero) break;
            if (OwnedWindow(message, processId)) entries.Add("message-only " + message + " " + ClassName(message));
        }
        return string.Join(Environment.NewLine, entries);
    }
    private static void PostOwned(IntPtr window, int processId, uint message, uint key, IntPtr parameter)
    {
        if (!OwnedWindow(window, processId)) throw new InvalidOperationException("Tray window ownership changed.");
        if (!PostMessage(window, message, new UIntPtr(key), parameter))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not post tray interaction.");
    }
    private static IntPtr MenuFor(IntPtr popup, int processId)
    {
        if (!OwnedWindow(popup, processId) || ClassName(popup) != "#32768") return IntPtr.Zero;
        // MN_GETHMENU is the documented query for a native popup menu's HMENU.
        if (SendMessageTimeout(popup, 0x01E1, UIntPtr.Zero, IntPtr.Zero, 3, 1000, out UIntPtr result) == IntPtr.Zero)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Popup menu query failed or timed out.");
        return new IntPtr(unchecked((long)result.ToUInt64()));
    }
    public static string Close(int processId)
    {
        var receiver = IntPtr.Zero;
        var cursor = IntPtr.Zero;
        for (int count = 0; count < 256; count++)
        {
            cursor = FindWindowEx(new IntPtr(-3), cursor, null, "ImmichFolderWatchTrayReceiver");
            if (cursor == IntPtr.Zero) break;
            if (!OwnedWindow(cursor, processId)) continue;
            if (receiver != IntPtr.Zero) throw new InvalidOperationException("Multiple matching tray receivers.");
            receiver = cursor;
        }
        if (receiver == IntPtr.Zero) throw new InvalidOperationException("The test application's tray receiver was not found.");
        // TrayIconHost handles WM_TRAYICON/WM_CONTEXTMENU by opening its real menu.
        PostOwned(receiver, processId, 0x0401, 0, new IntPtr(0x007B));
        var timer = Stopwatch.StartNew();
        var popup = IntPtr.Zero;
        var menu = IntPtr.Zero;
        int last = -1;
        while (timer.ElapsedMilliseconds < 10000 && popup == IntPtr.Zero)
        {
            var candidates = new List<IntPtr>();
            EnumWindows((window, parameter) => {
                if (OwnedWindow(window, processId) && ClassName(window) == "#32768") candidates.Add(window);
                return true;
            }, IntPtr.Zero);
            if (candidates.Count > 1) throw new InvalidOperationException("Multiple application popup menus are open.");
            if (candidates.Count == 1)
            {
                var candidate = MenuFor(candidates[0], processId);
                int count = candidate == IntPtr.Zero ? -1 : GetMenuItemCount(candidate);
                // Exact menu shape and IDs from TrayIconHost; never select a guessed entry.
                if (count == 5 && GetMenuItemID(candidate, 0) == 1 && GetMenuItemID(candidate, 2) == 2 &&
                    GetMenuItemID(candidate, count - 1) == 3)
                {
                    popup = candidates[0]; menu = candidate; last = count - 1;
                }
            }
            if (popup == IntPtr.Zero) Thread.Sleep(100);
        }
        if (popup == IntPtr.Zero) throw new InvalidOperationException("The expected tray popup menu did not appear.");
        // Use actual input on this disposable runner. Never click unless the
        // verified Quit rectangle is under this exact process-owned popup.
        if (!GetMenuItemRect(IntPtr.Zero, menu, (uint)last, out Rect rect) ||
            rect.Right <= rect.Left || rect.Bottom <= rect.Top)
            throw new InvalidOperationException("Cannot locate the verified Quit menu rectangle.");
        var point = new Point { X = rect.Left + (rect.Right - rect.Left) / 2,
                                Y = rect.Top + (rect.Bottom - rect.Top) / 2 };
        if (WindowFromPoint(point) != popup || !OwnedWindow(popup, processId))
            throw new InvalidOperationException("Another window covers the verified Quit entry.");
        if (!SetCursorPos(point.X, point.Y)) throw new InvalidOperationException("Cannot move the test cursor to Quit.");
        timer.Restart();
        bool highlighted = false;
        while (timer.ElapsedMilliseconds < 5000)
        {
            if (MenuFor(popup, processId) != menu) throw new InvalidOperationException("Tray popup changed before Quit.");
            uint state = GetMenuState(menu, (uint)last, 0x0400); // MF_BYPOSITION
            if (state != uint.MaxValue && (state & 0x0080) != 0 && (state & 0x0003) == 0)
            {
                highlighted = true;
                break;
            }
            Thread.Sleep(100);
        }
        if (!highlighted) throw new InvalidOperationException("The tray Quit item was not highlighted and enabled.");
        if (GetMenuItemID(menu, last) != 3) throw new InvalidOperationException("Tray Quit command changed.");
        if (!GetCursorPos(out Point actual) || actual.X != point.X || actual.Y != point.Y ||
            WindowFromPoint(actual) != popup || !OwnedWindow(popup, processId))
            throw new InvalidOperationException("Test cursor or popup ownership changed before Quit.");
        var clicks = new[] {
            new Input { Type = 0, Mouse = new MouseInput { Flags = 0x0002 } },
            new Input { Type = 0, Mouse = new MouseInput { Flags = 0x0004 } }
        };
        if (SendInput(2, clicks, Marshal.SizeOf(typeof(Input))) != 2)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not click the verified Quit entry.");
        return "tray-menu-quit; popup=" + popup + "; verifiedHighlightedCommandId=3; nativeMouseClick";
    }
}
'@
    $diagnosticsPath = Join-Path $EvidenceDirectory "tray-quit-windows.log"
    [UpgradeTestTrayQuit]::Describe($Process.Id) | Set-Content -LiteralPath $diagnosticsPath -Encoding utf8
    try {
        $interaction = [UpgradeTestTrayQuit]::Close($Process.Id)
        if (-not $Process.WaitForExit(30000)) { throw "Application did not exit after selecting the real tray Quit command." }
        $Process.Refresh()
        if ($Process.ExitCode -ne 0) { throw "Tray Quit ended with application exit code $($Process.ExitCode)." }
        return $interaction
    }
    catch {
        [UpgradeTestTrayQuit]::Describe($Process.Id) | Add-Content -LiteralPath $diagnosticsPath -Encoding utf8
        throw
    }
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
    $baselineSnapshot = Get-InstalledSnapshot
    $baselineSnapshot | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory "baseline-payload.json") -Encoding utf8
    $oldProducts | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory "baseline-registration.json") -Encoding utf8
    $oldProcess = Start-Process -FilePath $exePath -PassThru
    $summary.baselineApplication = Wait-ForApplication $oldProcess
    $oldProcess.Refresh()
    if ($oldProcess.HasExited) { throw "Baseline application exited before upgrade began." }
    $summary.upgradeStartedWithProcessId = $oldProcess.Id
    $summary.runningUpgradeExitCode = Invoke-TestMsi /i $CandidateMsi "running-app-upgrade.log" -AllowGuardRefusal
    if ($summary.runningUpgradeExitCode -eq 1603) {
        Assert-SafeRunningRefusal -BaselineSnapshot $baselineSnapshot -BaselineProductCode $summary.baselineProductCode -ConfigHash $configHash -SentinelHash $sentinelHash -Process $oldProcess
        $summary.runningUpgradeOutcome = "safely-refused"
        $summary.refusalPreservedPayloadFiles = $baselineSnapshot.Count
        $summary.refusalPreservedRegistrationAndUserData = $true
        $summary.gracefulCloseInteraction = Close-TestApplicationGracefully -Process $oldProcess
        $summary.trayQuitGracefulClose = "completed"
        $summary.closedApplicationRetryExitCode = Invoke-TestMsi /i $CandidateMsi "closed-app-upgrade-retry.log"
    }
    else {
        $summary.runningUpgradeOutcome = "completed"
    }
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
