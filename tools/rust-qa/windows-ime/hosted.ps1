# Prepare Japanese Basic Typing only when the native probe identifies a missing input service.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or
    $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') { throw 'A disposable Windows rewrite job is required.' }
$target = @{ X64='x86_64-pc-windows-msvc'; ARM64='aarch64-pc-windows-msvc' }[$env:RUNNER_ARCH]
if (-not $target -or $env:NATIVE_TARGET -cne $target) { throw 'Expected matching Windows runner architecture.' }
$gui = Join-Path $env:GITHUB_WORKSPACE 'artifacts\rust\gui-build\release\native-gui-assessment.exe'
$probe = Join-Path $PSScriptRoot 'run.py'
$parent = Join-Path $env:GITHUB_WORKSPACE "artifacts\rust\gui-native\$target\windows-ime"
if (Test-Path -LiteralPath $parent) { throw 'Expected a new native IME output directory.' }
[void](New-Item -ItemType Directory -Path $parent)
$feature = 'Language.Basic~~~ja-JP~0.0.1.0'
$serviced = $changedList = $false
$report = [ordered]@{ tested=$false; passed=$false; capability=$feature; nativeTarget=$target }

function LanguageState($List) {
    $rows = @($List | ForEach-Object {
        [ordered]@{ language=$_.LanguageTag; inputTips=@($_.InputMethodTips); handwriting=$_.Handwriting }
    })
    return (ConvertTo-Json -InputObject $rows -Depth 4 -Compress)
}

try {
    $initial = Join-Path $parent 'installed'
    & python $probe $gui $initial
    $status = $LASTEXITCODE
    $before = [IO.File]::ReadAllText((Join-Path $initial 'result.json')) | ConvertFrom-Json
    $report.initial = $before.status
    if ($status -eq 0 -and $before.status -ceq 'passed') {
        $report.tested = $true
    } elseif ($before.status -cne 'unavailable' -or -not $before.hasActiveInputDesktop) {
        throw 'The native desktop or field observation failed before a missing language service could be remedied.'
    } else {
        $current = Get-WindowsCapability -Online -Name $feature
        if (-not $current -or $current.Name -cne $feature) { throw 'This OS image does not offer Japanese Basic Typing.' }
        $report.originalCapability = $current.State.ToString()
        $original = Get-WinUserLanguageList
        $originalState = LanguageState $original
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
        $sessionList = Get-WinUserLanguageList
        if (@($sessionList.LanguageTag) -notcontains 'ja-JP') {
            [void]$sessionList.Add('ja-JP')
            $changedList = $true
            Set-WinUserLanguageList -LanguageList $sessionList -Force
        }
        $language = @(Get-WinUserLanguageList | Where-Object LanguageTag -eq 'ja-JP')
        if ($language.Count -ne 1) { throw 'The disposable account did not acquire the Japanese locale.' }
        $report.inputTips = @($language[0].InputMethodTips)
        $after = Join-Path $parent 'japanese'
        & python $probe $gui $after
        $status = $LASTEXITCODE
        $observation = [IO.File]::ReadAllText((Join-Path $after 'result.json')) | ConvertFrom-Json
        $report.afterProvisioning = $observation.status
        if ($status -ne 0 -or $observation.status -cne 'passed') {
            throw 'Native composition, commit and filename readback did not pass with the Japanese locale.'
        }
        $report.tested = $true
    }
} finally {
    try {
        try {
            if ($changedList) {
                Set-WinUserLanguageList -LanguageList $original -Force
                $report.languageListRestored = (LanguageState (Get-WinUserLanguageList)) -ceq $originalState
                if (-not $report.languageListRestored) { throw 'The original test-account language settings differ.' }
            }
        } finally {
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
        }
        $report.passed = $report.tested
    } finally {
        [IO.File]::WriteAllText((Join-Path $parent 'servicing.json'), ($report | ConvertTo-Json -Depth 5),
                               [Text.UTF8Encoding]::new($false))
    }
}
