[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "Immich Folder Watch"),
    [string]$ServiceName = "ImmichFolderWatch",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "service-management.ps1")

Assert-Administrator

$installRootFull = [System.IO.Path]::GetFullPath($InstallRoot)
$programDataRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)
if ([string]::IsNullOrWhiteSpace($programDataRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramData)) {
        $programDataRoot = $env:ProgramData
    }
    else {
        $programDataRoot = "C:\ProgramData"
    }
}

$dataRoot = Join-Path $programDataRoot "Immich Folder Watch"

if ($null -ne (Get-ServiceInstance -Name $ServiceName)) {
    Remove-ServiceRegistration -Name $ServiceName -TimeoutSeconds 45
}

if (Test-Path -LiteralPath $installRootFull) {
    Remove-Item -LiteralPath $installRootFull -Recurse -Force
}

if ($RemoveData -and (Test-Path -LiteralPath $dataRoot)) {
    Remove-Item -LiteralPath $dataRoot -Recurse -Force
}

Write-Host "Removed service '$ServiceName'."
Write-Host "Removed application binaries from $installRootFull"

if ($RemoveData) {
    Write-Host "Removed config and logs from $dataRoot"
}
else {
    Write-Host "Preserved config and logs under $dataRoot"
}
