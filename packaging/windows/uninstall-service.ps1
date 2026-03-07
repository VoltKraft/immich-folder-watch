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
$preservedDirectories = @("config", "logs")

if ($null -ne (Get-ServiceInstance -Name $ServiceName)) {
    Remove-ServiceRegistration -Name $ServiceName -TimeoutSeconds 45
}

if (Test-Path -LiteralPath $installRootFull) {
    if ($RemoveData) {
        Remove-Item -LiteralPath $installRootFull -Recurse -Force
    }
    else {
        Get-ChildItem -LiteralPath $installRootFull -Force | ForEach-Object {
            if ($_.PSIsContainer) {
                if ($preservedDirectories -contains $_.Name.ToLowerInvariant()) {
                    return
                }

                Remove-Item -LiteralPath $_.FullName -Recurse -Force
                return
            }

            Remove-Item -LiteralPath $_.FullName -Force
        }
    }
}

Write-Host "Removed service '$ServiceName'."
Write-Host "Removed application binaries from $installRootFull"

if ($RemoveData) {
    Write-Host "Removed config and logs from $installRootFull"
}
else {
    Write-Host "Preserved config and logs under $installRootFull"
}
