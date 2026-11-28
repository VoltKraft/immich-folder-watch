param([Parameter(Mandatory)][ValidateSet('arm64','x64')][string]$Architecture)

$ErrorActionPreference = 'Stop'
$finder = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = & $finder -latest -products '*' -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'Native Visual Studio installation required.' }
Import-Module (Join-Path $installation 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $installation -SkipAutomaticLocation -DevCmdArguments "-arch=$Architecture -host_arch=$Architecture"
foreach ($name in @('cl.exe', 'lib.exe')) {
    $tool = Get-Command $name -CommandType Application -ErrorAction Stop | Select-Object -First 1
    if ((Split-Path -Leaf (Split-Path -Parent $tool.Source)) -ine $Architecture) {
        throw "Visual Studio selected the wrong target for $name."
    }
    Write-Host "Selected $name for $Architecture."
}
$env:PATH = "$env:GITHUB_WORKSPACE\artifacts\rust\toolchain\bin;$env:PATH"
