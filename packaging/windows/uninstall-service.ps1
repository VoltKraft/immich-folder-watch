[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "Immich Folder Watch"),
    [string]$DataRoot = (Join-Path $env:ProgramData "ImmichFolderWatch"),
    [string]$ServiceName = "ImmichFolderWatch",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
$scExePath = Join-Path $env:SystemRoot "System32\sc.exe"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)

    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated PowerShell session."
    }
}

function Invoke-ServiceCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    if (-not (Test-Path -LiteralPath $scExePath)) {
        throw "sc.exe not found at $scExePath"
    }

    & $scExePath @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "$scExePath $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

Assert-Administrator

$installRootFull = [System.IO.Path]::GetFullPath($InstallRoot)
$dataRootFull = [System.IO.Path]::GetFullPath($DataRoot)

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if ($existingService) {
    if ($existingService.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
        Stop-Service -Name $ServiceName -Force -ErrorAction Stop
        $existingService.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
    }

    Invoke-ServiceCommand -Arguments @("delete", $ServiceName)
    Start-Sleep -Seconds 2
}

if (Test-Path -LiteralPath $installRootFull) {
    Remove-Item -LiteralPath $installRootFull -Recurse -Force
}

if ($RemoveData -and (Test-Path -LiteralPath $dataRootFull)) {
    Remove-Item -LiteralPath $dataRootFull -Recurse -Force
}

Write-Host "Removed service '$ServiceName'."
Write-Host "Removed binaries from $installRootFull"

if ($RemoveData) {
    Write-Host "Removed data directory $dataRootFull"
}
else {
    Write-Host "Preserved data directory $dataRootFull"
}
