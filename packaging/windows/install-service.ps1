[CmdletBinding()]
param(
    [string]$PackageRoot = $PSScriptRoot,
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "Immich Folder Watch"),
    [string]$ConfigPath,
    [string]$ServiceName = "ImmichFolderWatch",
    [string]$DisplayName = "Immich Folder Watch",
    [ValidateSet("Manual", "Automatic", "Disabled")]
    [string]$StartupType = "Automatic",
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
$packageBinRoot = Join-Path $packageRoot "bin"
$installBinRoot = Join-Path $installRootFull "bin"
$installConfigRoot = Join-Path $installRootFull "config"
$installLogsRoot = Join-Path $installRootFull "logs"
$serviceExecutable = Join-Path $installBinRoot "ImmichFolderWatch.Daemon.exe"
$exampleConfigPath = Join-Path $packageRoot "config.example.yaml"
$legacyConfigPath = Join-Path $installRootFull "config.yaml"
$defaultConfigPath = Join-Path $installConfigRoot "config.yaml"
$useDefaultConfigPath = -not $PSBoundParameters.ContainsKey("ConfigPath")

function Remove-LegacyRootAppArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceBinRoot,
        [Parameter(Mandatory = $true)]
        [string]$InstallRootPath
    )

    Get-ChildItem -LiteralPath $SourceBinRoot -Force | ForEach-Object {
        $legacyPath = Join-Path $InstallRootPath $_.Name
        if (-not (Test-Path -LiteralPath $legacyPath)) {
            return
        }

        Remove-Item -LiteralPath $legacyPath -Recurse -Force
    }
}

if (-not $ConfigPath) {
    $ConfigPath = $defaultConfigPath
}

$configPathFull = [System.IO.Path]::GetFullPath($ConfigPath)
$configDirectory = Split-Path -Path $configPathFull -Parent
$serviceCommand = "`"$serviceExecutable`" --config `"$configPathFull`""

if (-not (Test-Path -LiteralPath $packageBinRoot)) {
    throw "Published bin folder not found: $packageBinRoot"
}

if (-not (Test-Path -LiteralPath (Join-Path $packageBinRoot "ImmichFolderWatch.Daemon.exe"))) {
    throw "ImmichFolderWatch.Daemon.exe not found in $packageBinRoot"
}

if (-not (Test-Path -LiteralPath $exampleConfigPath)) {
    throw "config.example.yaml not found in $packageRoot"
}

$existingService = Get-ServiceInstance -Name $ServiceName
if ($null -ne $existingService) {
    Stop-ServiceRegistration -Name $ServiceName -TimeoutSeconds 45
}

New-Item -ItemType Directory -Path $installRootFull -Force | Out-Null
New-Item -ItemType Directory -Path $installBinRoot -Force | Out-Null
New-Item -ItemType Directory -Path $installConfigRoot -Force | Out-Null
New-Item -ItemType Directory -Path $installLogsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null

Remove-LegacyRootAppArtifacts -SourceBinRoot $packageBinRoot -InstallRootPath $installRootFull
Get-ChildItem -LiteralPath $installBinRoot -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Copy-Item -Path (Join-Path $packageBinRoot "*") -Destination $installBinRoot -Recurse -Force

$createdExampleConfig = $false
if ($useDefaultConfigPath -and (Test-Path -LiteralPath $legacyConfigPath)) {
    if (Test-Path -LiteralPath $defaultConfigPath) {
        Write-Warning "Legacy config remains at $legacyConfigPath because $defaultConfigPath already exists. The service will use $defaultConfigPath."
    }
    else {
        Move-Item -LiteralPath $legacyConfigPath -Destination $defaultConfigPath
        Write-Host "Migrated legacy config to $defaultConfigPath"
    }
}

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

if ($StartupType -eq "Automatic") {
    Invoke-ServiceCommand -Arguments @(
        "config", $ServiceName,
        (New-ScOption -Name "start" -Value "delayed-auto")
    )
}

Invoke-ServiceCommand -Arguments @(
    "failure", $ServiceName,
    (New-ScOption -Name "reset" -Value "86400"),
    (New-ScOption -Name "actions" -Value 'restart/5000/restart/15000/""/0')
)

if ($StartService) {
    Start-Service -Name $ServiceName
}
elseif ($createdExampleConfig) {
    Write-Warning "An example config was created at $configPathFull. Edit it before the next system boot or before starting the service manually."
}

Write-Host "Installed service '$ServiceName'."
Write-Host "Binaries: $installBinRoot"
Write-Host "Config:   $configPathFull"
Write-Host "Logs:     $installLogsRoot"
