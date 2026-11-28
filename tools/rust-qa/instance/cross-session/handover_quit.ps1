#Requires -Version 7.0
# Select the installed reference application's ordinary Quit on its own marked RDP desktop.
param([Parameter(Mandatory)][int]$ProcessId, [Parameter(Mandatory)][long]$Created,
      [Parameter(Mandatory)][long]$Root, [Parameter(Mandatory)][long]$Receiver,
      [Parameter(Mandatory)][int]$ThreadId, [Parameter(Mandatory)][string]$Evidence)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or $env:COMPUTERNAME -cne 'IFW-QA25' -or
    $env:LOCALAPPDATA -ine 'C:\Users\ifw-test\AppData\Local' -or
    [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64' -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'Expected the local x64 test RDP session.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$marker = 'C:\Program Files\IFW-QA-CrossSession\marker.txt'
$admin = [Security.Principal.WindowsBuiltInRole]::Administrator
if ([Security.Principal.WindowsPrincipal]::new($identity).IsInRole($admin) -or
    [IO.File]::ReadAllText($marker) -cne "IFW disposable installed MSI session test`n$($identity.User.Value)`n") {
    throw 'Expected the marked synthetic standard user.'
}
$area = [IO.FileInfo]::new($Evidence).Directory
if ($area.Name -cne 'wpf-handover' -or $area.Parent.Name -notlike 'trial-*' -or
    $area.Parent.Parent.FullName -ine (Join-Path $env:LOCALAPPDATA 'IFW-MsiSessions') -or
    [IO.Path]::GetFileName($Evidence) -cne 'quit-menu.json' -or [IO.File]::Exists($Evidence)) {
    throw 'Expected a new handover evidence file.'
}
# WTS gives the actual session protocol even when a startup hook has no SESSIONNAME.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class HandoverRdp {
    [DllImport("wtsapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
    static extern bool WTSQuerySessionInformationW(IntPtr server, int session, int kind, out IntPtr data, out int size);
    [DllImport("wtsapi32.dll")] static extern void WTSFreeMemory(IntPtr data);
    public static bool Active(int session) {
        foreach (int kind in new[] {8, 16}) {
            IntPtr data;
            int size;
            if (!WTSQuerySessionInformationW(IntPtr.Zero, session, kind, out data, out size)) return false;
            try {
                if (kind == 8 ? size < 4 || Marshal.ReadInt32(data) != 0 : size < 2 || Marshal.ReadInt16(data) != 2) return false;
            } finally { WTSFreeMemory(data); }
        }
        return true;
    }
}
'@
if (-not [HandoverRdp]::Active([Diagnostics.Process]::GetCurrentProcess().SessionId)) { throw 'An active test RDP session is required.' }
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
. "$repo/tools/rust-qa/windows-msi-interop/reverse/quit-source.ps1"
$source = Get-InstalledUpgradeQuitSource -Path "$repo/packaging/windows/Test-InstalledUpgrade.ps1"
Add-Type -TypeDefinition $source.Code
Add-InstalledQuitReceiverCheck
$record = [ordered]@{ pid=$ProcessId; created=$Created; root=$Root; receiver=$Receiver; tid=$ThreadId
    sourceSha256=$source.Sha256; status='incomplete'; stage='identity' }
$proc = [Diagnostics.Process]::GetProcessById($ProcessId)
$observer = $null
try {
    $null = $proc.SafeHandle
    $image = 'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe'
    if ($proc.HasExited -or $Root -le 0 -or $Receiver -le 0 -or $Root -eq $Receiver -or $ThreadId -le 0 -or
        $proc.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $Created -or $proc.MainModule.FileName -ine $image -or
        (Get-FileHash -LiteralPath $image).Hash -ine 'b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675' -or
        $proc.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId -or
        -not [InstalledQuitReceiver]::Matches([IntPtr]$Receiver,[uint32]$ProcessId,[uint32]$ThreadId)) {
        throw 'The installed WPF process or its tray receiver changed.'
    }
    $observer = [InstalledQuitReceiver]::new()
    $close = [UpgradeTestTrayQuit].GetMethod('Close',[type[]]@([int])).CreateDelegate([Func[int,string]])
    $record.rawInteraction = $observer.Invoke([IntPtr]$Root,[IntPtr]$Receiver,[uint32]$ProcessId,[uint32]$ThreadId,$close)
    if ($record.rawInteraction -cnotmatch '\Atray-menu-quit; popup=([1-9][0-9]*); verifiedHighlightedCommandId=3; nativeMouseClick\z') {
        throw 'Quit was not selected on the original WPF popup.'
    }
    $record.menuHwnd = [long]$Matches[1]
    $record.status = 'invoked'
} catch {
    $record.error = $_.Exception.Message
    throw
} finally {
    if ($null -ne $observer) {
        $record.anchor = $observer.anchor
        $record.stage = $observer.stage
        if ($null -ne $observer.diagnostic) { $record.diagnostic = $observer.diagnostic }
    }
    $proc.Dispose()
    $bytes = [Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 8))
    $stream = [IO.File]::Open($Evidence,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
}
