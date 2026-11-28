# Prepare Japanese Basic Typing only when the native probe identifies a missing input service.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or
    $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') { throw 'A disposable Windows rewrite job is required.' }
$target = @{ X64='x86_64-pc-windows-msvc'; ARM64='aarch64-pc-windows-msvc' }[$env:RUNNER_ARCH]
if (-not $target -or $env:NATIVE_TARGET -cne $target) { throw 'Expected matching Windows runner architecture.' }
$session = Join-Path $env:GITHUB_WORKSPACE 'tools\rust-qa\windows-desktop\session.py'
$parent = Join-Path $env:GITHUB_WORKSPACE "artifacts\rust\gui-native\$target\windows-ime"
if (Test-Path -LiteralPath $parent) { throw 'Expected a new native IME output directory.' }
[void](New-Item -ItemType Directory -Path $parent)
$feature = 'Language.Basic~~~ja-JP~0.0.1.0'
$serviced = $false
$report = [ordered]@{ tested=$false; passed=$false; capability=$feature; nativeTarget=$target }
. (Join-Path $PSScriptRoot 'language-list.ps1')
& (Join-Path $PSScriptRoot 'test_language_list.ps1')
& (Join-Path $PSScriptRoot 'test_mode_sample.ps1')
& (Join-Path $PSScriptRoot 'test_field_focus.ps1')
& python -B -m unittest discover -s $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'The native IME observation and cleanup controls failed.' }

try {
    $initial = Join-Path $parent 'installed'
    & python $session $target 'ime-installed'
    $status = $LASTEXITCODE
    $before = [IO.File]::ReadAllText((Join-Path $initial 'result.json')) | ConvertFrom-Json
    $report.initial = $before.status
    if (Test-IfwImeObservation $before $status) {
        $report.tested = $true
    } elseif ($status -ne 1 -or $before.status -cne 'unavailable' -or -not $before.hasActiveInputDesktop -or
              -not (Test-IfwImeProfile $before)) {
        throw 'The native desktop or field observation failed before a missing language service could be remedied.'
    } else {
        $current = Get-WindowsCapability -Online -Name $feature
        if (-not $current -or $current.Name -cne $feature) { throw 'This OS image does not offer Japanese Basic Typing.' }
        $report.originalCapability = $current.State.ToString()
        $original = Get-WinUserLanguageList
        $report.originalLanguages = @(foreach ($entry in $original) { $entry.LanguageTag })
        if ($report.originalCapability -ceq 'NotPresent') {
            $serviced = $true
            $change = Add-WindowsCapability -Online -Name $feature
            $report.servicingNeedsRestart = [bool]$change.RestartNeeded
            if ($change.RestartNeeded) { throw 'Windows servicing requires a restarted test VM.' }
        } elseif ($report.originalCapability -cne 'Installed') {
            throw 'The Windows image has an incomplete capability servicing operation.'
        }
        $report.installedCapability = (Get-WindowsCapability -Online -Name $feature).State.ToString()
        if ($report.installedCapability -cne 'Installed') { throw 'Basic Typing did not become available.' }
        $report.osPackages = @(Get-WindowsPackage -Online | Where-Object {
            $_.PackageName -like 'Microsoft-Windows-LanguageFeatures-Basic-ja-jp-Package~*' -and $_.PackageState -eq 'Installed'
        } | ForEach-Object PackageName)
        Invoke-IfwJapaneseLanguage $original $report {
            $after = Join-Path $parent 'japanese'
            & python $session $target 'ime-japanese'
            $status = $LASTEXITCODE
            $observation = [IO.File]::ReadAllText((Join-Path $after 'result.json')) | ConvertFrom-Json
            $report.afterProvisioning = $observation.status
            if (-not (Test-IfwImeObservation $observation $status)) {
                throw 'Native Japanese composition, filename readback and private-profile cleanup must all pass.'
            }
        }
        $report.tested = $true
    }
} finally {
    try {
        if ($serviced) {
            $state = (Get-WindowsCapability -Online -Name $feature).State.ToString()
            if ($state -ceq 'Installed') {
                $removed = Remove-WindowsCapability -Online -Name $feature
                $report.removalNeedsRestart = [bool]$removed.RestartNeeded
            }
            $report.finalCapability = (Get-WindowsCapability -Online -Name $feature).State.ToString()
            if ($report.finalCapability -cne $report.originalCapability) {
                throw 'The disposable OS requires further servicing before its original capability state returns.'
            }
        }
        $report.passed = $report.tested
    } finally {
        [IO.File]::WriteAllText((Join-Path $parent 'servicing.json'), ($report | ConvertTo-Json -Depth 5),
                               [Text.UTF8Encoding]::new($false))
    }
}
