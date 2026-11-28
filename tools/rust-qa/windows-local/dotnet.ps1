# Run the shipping reference checks from a fresh checkout on the local QA guest.
#Requires -Version 7.3
[CmdletBinding()]
param (
    [switch]$BuildInstallers,
    [string]$OfflineNugetFeed
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if (-not $IsWindows -or $env:GITHUB_ACTIONS -or $env:COMPUTERNAME -ine 'IFW-QA25' -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
    -not (Get-CimInstance Win32_ComputerSystem).HypervisorPresent) {
    throw 'Run the .NET reference suite in the disposable local Windows x64 VM.'
}
Push-Location (Join-Path $PSScriptRoot '../../..')
try {
    $revision = git rev-parse HEAD
    $sdk = (Get-Content global.json -Raw | ConvertFrom-Json).sdk.version
    if ((dotnet --version) -ne $sdk) { throw "This revision requires .NET SDK $sdk." }
    $evidence = "artifacts/rust/local-dotnet/$revision/$([guid]::NewGuid())"
    New-Item -ItemType Directory -Path $evidence | Out-Null
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
    $env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
    $env:IFW_TEST_PWSH = (Get-Process -Id $PID).Path
    Start-Transcript -Path "$evidence/commands.log"
    try {
        dotnet --info
        foreach ($file in 'test_workflow_security.py', 'test_windows_installer.py',
            'test_msi_upgrade_contract.py', 'test_installed_upgrade.py') {
            python -B -m unittest discover -s tools/tests -p $file -v
        }
        python -B tools/prepare_reduced_avalonia.py
        if ($OfflineNugetFeed) {
            [xml]$config = Get-Content -Raw -LiteralPath NuGet.Config
            $config.SelectSingleNode("//packageSources/add[@key='nuget.org']").value = (Resolve-Path $OfflineNugetFeed).Path
            $config.SelectSingleNode("//packageSources/add[@key='immich-folder-watch-reduced']").value = (Resolve-Path artifacts/reduced-avalonia/feed).Path
            $config.SelectSingleNode("//config/add[@key='globalPackagesFolder']").value = [IO.Path]::GetFullPath('artifacts/nuget-packages', (Get-Location).Path)
            $config.Save((Join-Path (Get-Location).Path "$evidence/NuGet.Config"))
            dotnet restore ImmichFolderWatch.sln --configfile "$evidence/NuGet.Config"
        } else {
            dotnet restore ImmichFolderWatch.sln
        }
        dotnet build ImmichFolderWatch.sln --configuration Release --no-restore
        python -B tools/verify_reduced_avalonia.py
        dotnet test ImmichFolderWatch.sln --configuration Release --no-build --logger trx --results-directory "$evidence/trx"
        if ($BuildInstallers) {
            foreach ($runtime in 'win-x64', 'win-arm64') {
                & ./packaging/windows/build-msi.ps1 -Runtime $runtime
            }
        }
    } finally {
        Stop-Transcript
    }
} finally {
    Pop-Location
}
