[CmdletBinding()]
param(
    [string]$PackageRoot = $PSScriptRoot,
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "Immich Folder Watch"),
    [string]$DataRoot = (Join-Path $env:ProgramData "ImmichFolderWatch"),
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

function New-ScOption {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    return "$Name= $Value"
}

function Get-ScStartType {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    switch ($Value) {
        "Automatic" { return "auto" }
        "Manual" { return "demand" }
        "Disabled" { return "disabled" }
        default { throw "Unsupported startup type: $Value" }
    }
}

function Get-ServiceLogonArguments {
    if ($null -ne $Credential) {
        return @(
            (New-ScOption -Name "obj" -Value $Credential.UserName),
            (New-ScOption -Name "password" -Value $Credential.GetNetworkCredential().Password)
        )
    }

    $accountName = switch ($BuiltInAccount) {
        "LocalSystem" { "LocalSystem" }
        "LocalService" { "NT AUTHORITY\LocalService" }
        "NetworkService" { "NT AUTHORITY\NetworkService" }
        default { throw "Unsupported service account: $BuiltInAccount" }
    }

    return @((New-ScOption -Name "obj" -Value $accountName))
}

Assert-Administrator

$installRootFull = [System.IO.Path]::GetFullPath($InstallRoot)
$dataRootFull = [System.IO.Path]::GetFullPath($DataRoot)
$packageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
$packageAppRoot = Join-Path $packageRoot "app"
$serviceExecutable = Join-Path $installRootFull "ImmichFolderWatch.Daemon.exe"
$exampleConfigPath = Join-Path $packageRoot "config.example.yaml"

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $dataRootFull "config.yaml"
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

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService -and $existingService.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
    Stop-Service -Name $ServiceName -Force -ErrorAction Stop
    $existingService.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
}

New-Item -ItemType Directory -Path $installRootFull -Force | Out-Null
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null

Copy-Item -Path (Join-Path $packageAppRoot "*") -Destination $installRootFull -Recurse -Force

$createdExampleConfig = $false
if (-not (Test-Path -LiteralPath $configPathFull)) {
    Copy-Item -LiteralPath $exampleConfigPath -Destination $configPathFull
    $createdExampleConfig = $true
}

$startMode = Get-ScStartType -Value $StartupType
$logonArguments = Get-ServiceLogonArguments

if ($existingService) {
    $serviceArguments = @(
        "config", $ServiceName,
        (New-ScOption -Name "binPath" -Value $serviceCommand),
        (New-ScOption -Name "start" -Value $startMode),
        (New-ScOption -Name "DisplayName" -Value $DisplayName)
    ) + $logonArguments

    Invoke-ServiceCommand -Arguments $serviceArguments
}
else {
    $serviceArguments = @(
        "create", $ServiceName,
        (New-ScOption -Name "binPath" -Value $serviceCommand),
        (New-ScOption -Name "start" -Value $startMode),
        (New-ScOption -Name "DisplayName" -Value $DisplayName)
    ) + $logonArguments

    Invoke-ServiceCommand -Arguments $serviceArguments
}

Invoke-ServiceCommand -Arguments @(
    "description", $ServiceName,
    "Watches local folders and uploads new media to Immich."
)

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
