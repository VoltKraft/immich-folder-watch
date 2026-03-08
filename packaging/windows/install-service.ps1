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
$packageBinRoot = Join-Path $packageRoot "bin"
$installBinRoot = Join-Path $installRootFull "bin"
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
$installLogsRoot = Join-Path $dataRoot "logs"
$serviceExecutable = Join-Path $installBinRoot "ImmichFolderWatch.Daemon.exe"
$adminExecutable = Join-Path $installBinRoot "ImmichFolderWatch.Admin.exe"
$exampleConfigPath = Join-Path $packageRoot "config.example.yaml"
$defaultConfigPath = Join-Path $dataRoot "config.yaml"
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

function Get-ServiceStartupTypeFromRegistry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $serviceKeyPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    if (-not (Test-Path -LiteralPath $serviceKeyPath)) {
        return $null
    }

    $serviceKey = Get-ItemProperty -LiteralPath $serviceKeyPath -Name "Start" -ErrorAction Stop
    switch ([int]$serviceKey.Start) {
        2 { return "Automatic" }
        3 { return "Manual" }
        4 { return "Disabled" }
        default { return $null }
    }
}

function Test-ServiceDelayedAutoStart {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $serviceKeyPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    if (-not (Test-Path -LiteralPath $serviceKeyPath)) {
        return $false
    }

    $delayedValue = (Get-ItemProperty -LiteralPath $serviceKeyPath -Name "DelayedAutoStart" -ErrorAction SilentlyContinue).DelayedAutoStart
    return [int]$delayedValue -eq 1
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

if (-not (Test-Path -LiteralPath (Join-Path $packageBinRoot "ImmichFolderWatch.Gui.exe"))) {
    throw "ImmichFolderWatch.Gui.exe not found in $packageBinRoot"
}

if (-not (Test-Path -LiteralPath (Join-Path $packageBinRoot "ImmichFolderWatch.Admin.exe"))) {
    throw "ImmichFolderWatch.Admin.exe not found in $packageBinRoot"
}

if (-not (Test-Path -LiteralPath $exampleConfigPath)) {
    throw "config.example.yaml not found in $packageRoot"
}

$existingService = Get-ServiceInstance -Name $ServiceName
$startupTypeWasExplicitlyRequested = $PSBoundParameters.ContainsKey("StartupType")
$preserveDelayedAutoStart = $false
if ($null -ne $existingService) {
    if (-not $startupTypeWasExplicitlyRequested) {
        $preservedStartupType = Get-ServiceStartupTypeFromRegistry -Name $ServiceName
        if ($preservedStartupType) {
            $StartupType = if ($preservedStartupType -eq "Disabled") { "Manual" } else { $preservedStartupType }
        }
    }

    $preserveDelayedAutoStart = $StartupType -eq "Automatic" -and (Test-ServiceDelayedAutoStart -Name $ServiceName)
    Stop-ServiceRegistration -Name $ServiceName -TimeoutSeconds 45
}

if ($StartService -and $StartupType -eq "Disabled") {
    throw "Cannot start the service when StartupType is Disabled. Use -StartupType Automatic or -StartupType Manual."
}

New-Item -ItemType Directory -Path $installRootFull -Force | Out-Null
New-Item -ItemType Directory -Path $installBinRoot -Force | Out-Null
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
New-Item -ItemType Directory -Path $installLogsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null

Remove-LegacyRootAppArtifacts -SourceBinRoot $packageBinRoot -InstallRootPath $installRootFull
Get-ChildItem -LiteralPath $installBinRoot -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Copy-Item -Path (Join-Path $packageBinRoot "*") -Destination $installBinRoot -Recurse -Force

$migrationTriggered = $false
if ($useDefaultConfigPath) {
    $migrationTriggered = $true
    & $adminExecutable migrate-data-layout --legacy-install-root $installRootFull | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ImmichFolderWatch.Admin migrate-data-layout failed with exit code $LASTEXITCODE."
    }
}

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

if ($StartupType -eq "Automatic" -and ($startupTypeWasExplicitlyRequested -or $preserveDelayedAutoStart)) {
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
    if ($StartupType -eq "Disabled") {
        Write-Warning "An example config was created at $configPathFull. Verify it in the GUI before enabling the service."
    }
    else {
        Write-Warning "An example config was created at $configPathFull. Edit it before starting the service manually or switching it to automatic startup."
    }
}

Write-Host "Installed service '$ServiceName'."
Write-Host "Binaries: $installBinRoot"
Write-Host "Config:   $configPathFull"
Write-Host "Logs:     $installLogsRoot"
if ($migrationTriggered) {
    Write-Host "Data root: $dataRoot"
}
