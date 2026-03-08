[CmdletBinding()]
param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$OutputRoot,
    [string]$Version = "1.4.0",
    [switch]$FrameworkDependent
)

$ErrorActionPreference = "Stop"

function Get-ScriptRoot {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        return $PSScriptRoot
    }

    if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) {
        return Split-Path -Parent $PSCommandPath
    }

    if (-not [string]::IsNullOrWhiteSpace($MyInvocation.MyCommand.Path)) {
        return Split-Path -Parent $MyInvocation.MyCommand.Path
    }

    throw "Unable to determine the script directory."
}

function Initialize-DotnetEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CacheRoot
    )

    if ([string]::IsNullOrWhiteSpace($env:DOTNET_CLI_HOME)) {
        $env:DOTNET_CLI_HOME = Join-Path $CacheRoot "dotnet-cli"
    }

    if ([string]::IsNullOrWhiteSpace($env:NUGET_PACKAGES)) {
        $env:NUGET_PACKAGES = Join-Path $env:DOTNET_CLI_HOME ".nuget\packages"
    }

    if ([string]::IsNullOrWhiteSpace($env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE)) {
        $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = "1"
    }

    New-Item -ItemType Directory -Path $env:DOTNET_CLI_HOME -Force | Out-Null
    New-Item -ItemType Directory -Path $env:NUGET_PACKAGES -Force | Out-Null
}

function Reset-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }

    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Get-InstallerVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value -match '^(\d+)\.(\d+)\.(\d+)') {
        return "$($Matches[1]).$($Matches[2]).$($Matches[3])"
    }

    throw "Installer version must start with a numeric major.minor.patch value. Example: 1.1.0"
}

function Get-InstallerPlatform {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    switch ($Value) {
        "win-x64" { return "x64" }
        "win-arm64" { return "arm64" }
        default { throw "Unsupported runtime '$Value'. Expected win-x64 or win-arm64." }
    }
}

$scriptRoot = Get-ScriptRoot
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = [System.IO.Path]::GetTempPath()
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $scriptRoot "..\..\artifacts\windows\msi"
}

$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
Initialize-DotnetEnvironment -CacheRoot (Join-Path $localAppData "ImmichFolderWatch")

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
$daemonProject = Join-Path $repoRoot "src\ImmichFolderWatch.Daemon\ImmichFolderWatch.Daemon.csproj"
$guiProject = Join-Path $repoRoot "src\ImmichFolderWatch.Gui\ImmichFolderWatch.Gui.csproj"
$adminProject = Join-Path $repoRoot "src\ImmichFolderWatch.Admin\ImmichFolderWatch.Admin.csproj"
$wixProject = Join-Path $scriptRoot "ImmichFolderWatch.Setup.wixproj"
$windowsConfigTemplatePath = Join-Path $scriptRoot "config.windows.example.yaml"
$publishRoot = Join-Path $OutputRoot "publish\$Runtime"
$publishTempRoot = Join-Path $OutputRoot "publish-tmp\$Runtime"
$msiOutputRoot = Join-Path $OutputRoot "package"
$installerVersion = Get-InstallerVersion -Value $Version
$installerPlatform = Get-InstallerPlatform -Value $Runtime
$msiFileName = "immich-folder-watch-$installerVersion-$Runtime.msi"
$finalMsiPath = Join-Path $OutputRoot $msiFileName

if (-not (Test-Path -LiteralPath $wixProject)) {
    throw "WiX project not found: $wixProject"
}

if (-not (Test-Path -LiteralPath $windowsConfigTemplatePath)) {
    throw "Windows config template not found: $windowsConfigTemplatePath"
}

Reset-Directory -Path $publishRoot
Reset-Directory -Path $publishTempRoot
Reset-Directory -Path $msiOutputRoot

function Publish-ProjectOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$ProjectName
    )

    $projectPublishRoot = Join-Path $publishTempRoot $ProjectName
    Reset-Directory -Path $projectPublishRoot

    $publishArgs = @(
        "publish",
        $ProjectPath,
        "-c", $Configuration,
        "-r", $Runtime,
        "-o", $projectPublishRoot
    )

    if ($FrameworkDependent) {
        $publishArgs += "--no-self-contained"
    }
    else {
        $publishArgs += "--self-contained"
    }

    Write-Host "Publishing $ProjectName for MSI packaging..."
    & dotnet @publishArgs

    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish for $ProjectName failed with exit code $LASTEXITCODE."
    }

    Copy-Item -Path (Join-Path $projectPublishRoot "*") -Destination $publishRoot -Recurse -Force
}

Publish-ProjectOutput -ProjectPath $daemonProject -ProjectName "daemon"
Publish-ProjectOutput -ProjectPath $guiProject -ProjectName "gui"
Publish-ProjectOutput -ProjectPath $adminProject -ProjectName "admin"

$buildArgs = @(
    "build",
    $wixProject,
    "-c", $Configuration,
    "-p:InstallerPlatform=$installerPlatform",
    "-p:InstallerVersion=$installerVersion",
    "-p:PublishedAppDir=$publishRoot",
    "-p:ExampleConfigPath=$windowsConfigTemplatePath",
    "-p:OutputPath=$msiOutputRoot\"
)

Write-Host "Building MSI installer..."
& dotnet @buildArgs

if ($LASTEXITCODE -ne 0) {
    throw "dotnet build for WiX project failed with exit code $LASTEXITCODE."
}

$builtMsi = Get-ChildItem -Path $msiOutputRoot -Filter *.msi -Recurse | Sort-Object LastWriteTimeUtc | Select-Object -Last 1
if ($null -eq $builtMsi) {
    throw "No MSI output was found under $msiOutputRoot."
}

if (Test-Path -LiteralPath $finalMsiPath) {
    Remove-Item -LiteralPath $finalMsiPath -Force
}

Copy-Item -LiteralPath $builtMsi.FullName -Destination $finalMsiPath
Write-Host "MSI installer ready at $finalMsiPath"
