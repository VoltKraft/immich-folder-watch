[CmdletBinding()]
param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$OutputRoot = (Join-Path $PSScriptRoot "..\..\artifacts\windows"),
    [string]$Version,
    [switch]$FrameworkDependent,
    [switch]$Zip
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

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$daemonProject = Join-Path $repoRoot "src\ImmichFolderWatch.Daemon\ImmichFolderWatch.Daemon.csproj"
$guiProject = Join-Path $repoRoot "src\ImmichFolderWatch.Gui\ImmichFolderWatch.Gui.csproj"
$adminProject = Join-Path $repoRoot "src\ImmichFolderWatch.Admin\ImmichFolderWatch.Admin.csproj"
$windowsConfigTemplatePath = Join-Path $PSScriptRoot "config.windows.example.yaml"
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

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install-service.ps1") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "uninstall-service.ps1") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "service-management.ps1") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "installer.stub.md") -Destination $packageRoot
Copy-Item -LiteralPath $windowsConfigTemplatePath -Destination (Join-Path $packageRoot "config.example.yaml")

if ($Zip) {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath
    Write-Host "Created package archive at $zipPath"
}

Write-Host "Installer bundle ready at $packageRoot"
