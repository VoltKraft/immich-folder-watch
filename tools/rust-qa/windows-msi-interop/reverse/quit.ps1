#Requires -Version 7.0
# Use the original installer test's own menu selection on the observer's held WPF process.
param([Parameter(Mandatory)][int]$ProcessId, [Parameter(Mandatory)][long]$Created,
      [Parameter(Mandatory)][long]$Receiver, [Parameter(Mandatory)][int]$ThreadId,
      [Parameter(Mandatory)][string]$Evidence)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or -not [Environment]::Is64BitProcess -or $env:GITHUB_ACTIONS -cne 'true' -or
    $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -or
    $env:GITHUB_REPOSITORY -ine 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') {
    throw 'Expected native PowerShell 7 on the disposable Windows rewrite runner.'
}
if ($ProcessId -le 0 -or $Created -le 0 -or $Receiver -le 0 -or $ThreadId -le 0) {
    throw 'Expected the original process, creation time, receiver HWND and UI thread.'
}
. (Join-Path $PSScriptRoot 'quit-source.ps1')
$record = [ordered]@{ pid = $ProcessId; created = $Created; receiver = $Receiver; tid = $ThreadId; status = 'incomplete' }
$process = $null
try {
    $source = Get-InstalledUpgradeQuitSource
    $record.sourceSha256 = $source.Sha256
    Add-Type -TypeDefinition $source.Code
    Add-InstalledQuitReceiverCheck
    $process = [Diagnostics.Process]::GetProcessById($ProcessId)
    # Retain the original process object across the receiver checks and the complete interaction.
    $null = $process.SafeHandle
    $image = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)) 'Immich Folder Watch/bin/ImmichFolderWatch.exe'
    if ($process.HasExited -or $process.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $Created -or
        $process.MainModule.FileName -ine [IO.Path]::GetFullPath($image) -or
        $process.SessionId -ne (Get-Process -Id $PID).SessionId -or
        -not [InstalledQuitReceiver]::Matches([IntPtr]$Receiver, [uint32]$ProcessId, [uint32]$ThreadId) -or $process.HasExited) {
        throw 'The installed WPF process, creation time, tray receiver, thread or input desktop changed.'
    }
    $result = [UpgradeTestTrayQuit]::Close($ProcessId)
    $record.rawInteraction = $result
    if ($result -cnotmatch '\Atray-menu-quit; popup=([1-9][0-9]*); verifiedHighlightedCommandId=3; nativeMouseClick\z') {
        throw 'Missing the original checked Quit command and mouse selection.'
    }
    $record.menuHwnd = [long]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture)
    $record.status = 'invoked'
}
catch { $record.error = $_.Exception.Message; throw }
finally {
    if ($null -ne $process) { $process.Dispose() }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 4))
    $file = [IO.File]::Open($Evidence, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $file.Write($bytes, 0, $bytes.Length) } finally { $file.Dispose() }
}
