[CmdletBinding()]
param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$OutputRoot,
    [string]$Version,
    [switch]$FrameworkDependent,
    [switch]$Zip
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

$scriptRoot = Get-ScriptRoot
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = [System.IO.Path]::GetTempPath()
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $scriptRoot "..\..\artifacts\windows"
}

$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
Initialize-DotnetEnvironment -CacheRoot (Join-Path $localAppData "ImmichFolderWatch")

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
$daemonProject = Join-Path $repoRoot "src\ImmichFolderWatch.Daemon\ImmichFolderWatch.Daemon.csproj"
$guiProject = Join-Path $repoRoot "src\ImmichFolderWatch.Gui\ImmichFolderWatch.Gui.csproj"
$adminProject = Join-Path $repoRoot "src\ImmichFolderWatch.Admin\ImmichFolderWatch.Admin.csproj"
$windowsConfigTemplatePath = Join-Path $scriptRoot "config.windows.example.yaml"
$packageRoot = Join-Path $OutputRoot "immich-folder-watch-$Runtime"
$publishRoot = Join-Path $packageRoot "bin"
$publishTempRoot = Join-Path $OutputRoot "publish-tmp\$Runtime"
$zipPath = "$packageRoot.zip"

if (-not (Test-Path -LiteralPath $windowsConfigTemplatePath)) {
    throw "Windows config template not found: $windowsConfigTemplatePath"
}

Reset-Directory -Path $packageRoot
Reset-Directory -Path $publishTempRoot
New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null

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

    if ($Version) {
        $publishArgs += "/p:Version=$Version"
    }

    Write-Host "Publishing $ProjectName for $Runtime..."
    & dotnet @publishArgs

    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish for $ProjectName failed with exit code $LASTEXITCODE."
    }

    Copy-Item -Path (Join-Path $projectPublishRoot "*") -Destination $publishRoot -Recurse -Force
}

Publish-ProjectOutput -ProjectPath $daemonProject -ProjectName "daemon"
Publish-ProjectOutput -ProjectPath $guiProject -ProjectName "gui"
Publish-ProjectOutput -ProjectPath $adminProject -ProjectName "admin"

Copy-Item -LiteralPath (Join-Path $scriptRoot "install-service.ps1") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $scriptRoot "uninstall-service.ps1") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $scriptRoot "service-management.ps1") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $scriptRoot "README.md") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $scriptRoot "installer.stub.md") -Destination $packageRoot
Copy-Item -LiteralPath $windowsConfigTemplatePath -Destination (Join-Path $packageRoot "config.example.yaml")

if ($Zip) {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath
    Write-Host "Created package archive at $zipPath"
}

Write-Host "Installer bundle ready at $packageRoot"
