[CmdletBinding()]
param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$OutputRoot = (Join-Path $PSScriptRoot "..\..\artifacts\windows\msi"),
    [string]$Version = "1.0.0",
    [switch]$FrameworkDependent
)

$ErrorActionPreference = "Stop"

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

    throw "Installer version must start with a numeric major.minor.patch value. Example: 1.0.0"
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

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$daemonProject = Join-Path $repoRoot "src\ImmichFolderWatch.Daemon\ImmichFolderWatch.Daemon.csproj"
$wixProject = Join-Path $PSScriptRoot "ImmichFolderWatch.Setup.wixproj"
$windowsConfigTemplatePath = Join-Path $PSScriptRoot "config.windows.example.yaml"
$publishRoot = Join-Path $OutputRoot "publish\$Runtime"
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
Reset-Directory -Path $msiOutputRoot

$publishArgs = @(
    "publish",
    $daemonProject,
    "-c", $Configuration,
    "-r", $Runtime,
    "-o", $publishRoot
)

if ($FrameworkDependent) {
    $publishArgs += "--no-self-contained"
}
else {
    $publishArgs += "--self-contained"
}

Write-Host "Publishing daemon for MSI packaging..."
& dotnet @publishArgs

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
}

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
