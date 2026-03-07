[CmdletBinding()]
param(
    [string]$PackageRoot = $PSScriptRoot,
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "Immich Folder Watch"),
    [string]$ConfigPath,
    [string]$ServiceName = "ImmichFolderWatch",
    [string]$DisplayName = "Immich Folder Watch",
    [ValidateSet("Manual", "Automatic", "Disabled")]
    [string]$StartupType = "Manual",
    [ValidateSet("LocalSystem", "LocalService", "NetworkService")]
    [string]$BuiltInAccount = "LocalSystem",
    [System.Management.Automation.PSCredential]$Credential,
    [switch]$StartService
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "service-management.ps1")

function Get-ServiceCredential {
    if ($null -ne $Credential) {
        return $Credential
    }

    switch ($BuiltInAccount) {
        "LocalSystem" {
            return $null
        }
        "LocalService" {
            return New-Object System.Management.Automation.PSCredential(
                "NT AUTHORITY\LocalService",
                (ConvertTo-SecureString "" -AsPlainText -Force))
        }
        "NetworkService" {
            return New-Object System.Management.Automation.PSCredential(
                "NT AUTHORITY\NetworkService",
                (ConvertTo-SecureString "" -AsPlainText -Force))
        }
        default {
            throw "Unsupported service account: $BuiltInAccount"
        }
    }
}

Assert-Administrator

$installRootFull = [System.IO.Path]::GetFullPath($InstallRoot)
$packageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
$packageAppRoot = Join-Path $packageRoot "app"
$serviceExecutable = Join-Path $installRootFull "ImmichFolderWatch.Daemon.exe"
$exampleConfigPath = Join-Path $packageRoot "config.example.yaml"

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $installRootFull "config.yaml"
}

$configPathFull = [System.IO.Path]::GetFullPath($ConfigPath)
$configDirectory = Split-Path -Path $configPathFull -Parent
$serviceCommand = "`"$serviceExecutable`" --config `"$configPathFull`""

if (-not (Test-Path -LiteralPath $packageAppRoot)) {
    throw "Published app folder not found: $packageAppRoot"
}

if (-not (Test-Path -LiteralPath (Join-Path $packageAppRoot "ImmichFolderWatch.Daemon.exe"))) {
    throw "ImmichFolderWatch.Daemon.exe not found in $packageAppRoot"
}

if (-not (Test-Path -LiteralPath $exampleConfigPath)) {
    throw "config.example.yaml not found in $packageRoot"
}

$existingService = Get-ServiceInstance -Name $ServiceName
if ($null -ne $existingService) {
    Stop-ServiceRegistration -Name $ServiceName -TimeoutSeconds 45
}

New-Item -ItemType Directory -Path $installRootFull -Force | Out-Null
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null

Copy-Item -Path (Join-Path $packageAppRoot "*") -Destination $installRootFull -Recurse -Force

$createdExampleConfig = $false
if (-not (Test-Path -LiteralPath $configPathFull)) {
    Copy-Item -LiteralPath $exampleConfigPath -Destination $configPathFull
    $createdExampleConfig = $true
}

$serviceCredential = Get-ServiceCredential

if ($null -ne $existingService) {
    Remove-ServiceRegistration -Name $ServiceName -TimeoutSeconds 45
}

$newServiceParameters = @{
    Name = $ServiceName
    BinaryPathName = $serviceCommand
    DisplayName = $DisplayName
    Description = "Watches local folders and uploads new media to Immich."
    StartupType = $StartupType
}

if ($null -ne $serviceCredential) {
    $newServiceParameters.Credential = $serviceCredential
}

New-Service @newServiceParameters | Out-Null

Invoke-ServiceCommand -Arguments @(
    "failure", $ServiceName,
    (New-ScOption -Name "reset" -Value "86400"),
    (New-ScOption -Name "actions" -Value 'restart/5000/restart/15000/""/0')
)

if ($StartService) {
    Start-Service -Name $ServiceName
}
elseif ($createdExampleConfig) {
    Write-Warning "An example config was created at $configPathFull. Edit it before starting the service."
}

Write-Host "Installed service '$ServiceName'."
Write-Host "Binaries: $installRootFull"
Write-Host "Config:   $configPathFull"
