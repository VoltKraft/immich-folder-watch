# Exercise the original logged-on user's input system and restore its language settings.
param (
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Binary,
    [Parameter(Mandatory)][string]$Receipt,
    [Parameter(Mandatory)][string]$CompilerRevision,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][ValidateSet('installed','japanese')][string]$Phase
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'language-list.ps1')
. (Join-Path $PSScriptRoot 'guest-environment.ps1')
Assert-IfwImeGuest
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($env:USERNAME -ine 'ifw-test' -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run the desktop trial in the non-elevated ifw-test session.'
}
$report = [ordered]@{ host=$env:COMPUTERNAME; account=$env:USERNAME; phase=$Phase; source=$CompilerRevision
    session=[Diagnostics.Process]::GetCurrentProcess().SessionId; passed=$false }
$observe = {
    $path = Join-Path $Output 'observation'
    & $Python -B (Join-Path $PSScriptRoot 'run.py') $Binary $path --isolated-vm --build-receipt $Receipt --build-source $CompilerRevision
    $report.observerExit = $LASTEXITCODE
    $result = Get-Content -Raw -LiteralPath (Join-Path $path 'result.json') | ConvertFrom-Json
    $report.status = $result.status
    if (Test-IfwImeObservation $result $report.observerExit) { return }
    if ($Phase -ceq 'installed' -and (Test-IfwMissingGuestIme $result $report.observerExit $CompilerRevision)) { return }
    throw 'The native Windows input, filename or profile cleanup did not pass.'
}
try {
    if ($Phase -ceq 'installed') {
        & $observe
    } else {
        $record = Get-Content -Raw -LiteralPath (Get-IfwImeCapabilityRecord) | ConvertFrom-Json
        if ($record.host -ine $env:COMPUTERNAME -or $record.source -cne $CompilerRevision -or
            $record.capability -cne 'Language.Basic~~~ja-JP~0.0.1.0' -or $record.state -cne 'ready') {
            throw 'The local servicing receipt does not identify this prepared trial.'
        }
        $original = Get-WinUserLanguageList
        $report.originalLanguages = @(foreach ($entry in $original) { $entry.LanguageTag })
        Invoke-IfwJapaneseLanguage $original $report $observe
    }
    $report.passed = $report.status -ceq 'passed'
} finally {
    [IO.File]::WriteAllText((Join-Path $Output 'desktop.json'), ($report | ConvertTo-Json -Depth 5),
                           [Text.UTF8Encoding]::new($false))
}
if (-not $report.passed) { exit 3 }
