param([ValidateSet('x86_64-pc-windows-msvc', 'aarch64-pc-windows-msvc')][string]$Target)

function Invoke-IfwWriterObservation {
    param([System.Collections.IDictionary]$Record, [scriptblock]$Observe)

    $timeout = [TimeSpan]::FromSeconds(20)
    try {
        try {
            $before = Get-Service -Name seclogon -ErrorAction Stop
            $Record.initialStatus = $before.Status.ToString()
            $Record.startType = $before.StartType.ToString()
            if ($Record.initialStatus -eq 'Stopped' -and $Record.startType -in @('Manual', 'Automatic')) {
                $Record.startRequested = $true
                Start-Service -InputObject $before -ErrorAction Stop
                $before.WaitForStatus('Running', $timeout)
            }
            $Record.observedStatus = (Get-Service -Name seclogon -ErrorAction Stop).Status.ToString()
        } catch {
            $Record.preparationError = $_.Exception.Message
        }
        # Both actual lock trials retain their own results if the service is unavailable.
        & $Observe
    } finally {
        if ($Record.initialStatus) {
            $current = Get-Service -Name seclogon -ErrorAction Stop
            if ($Record.startRequested -and $current.Status -ne 'Stopped') {
                Stop-Service -InputObject $current -ErrorAction Stop
                $current.WaitForStatus('Stopped', $timeout)
            }
            $after = Get-Service -Name seclogon -ErrorAction Stop
            $Record.finalStatus = $after.Status.ToString()
            $Record.finalStartType = $after.StartType.ToString()
            $Record.restored = $Record.finalStatus -eq $Record.initialStatus -and $Record.finalStartType -eq $Record.startType
            if (-not $Record.restored) { throw 'Secondary Logon did not return to its original state.' }
        }
    }
}

if ($MyInvocation.InvocationName -eq '.') { return }
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$expectedTarget = @{ X64 = 'x86_64-pc-windows-msvc'; ARM64 = 'aarch64-pc-windows-msvc' }[[string]$env:RUNNER_ARCH]
if (-not $IsWindows -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -ine 'VoltKraft/immich-folder-watch' -or
    $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or $root -ne $env:GITHUB_WORKSPACE -or
    -not $expectedTarget -or $Target -cne $expectedTarget) {
    throw 'This observation requires the native disposable rewrite/rust Windows job.'
}
$area = Join-Path $root "artifacts/rust/instance-native/$Target"
$receipt = Join-Path $area 'hosted-secondary-logon.json'
if ((Test-Path -LiteralPath $receipt) -or (Test-Path -LiteralPath (Join-Path $area 'cross-session'))) {
    throw 'The service and writer observation require fresh output paths.'
}
[IO.Directory]::CreateDirectory($area) | Out-Null
$record = [ordered]@{ revision = $env:GITHUB_SHA; run = $env:GITHUB_RUN_ID; target = $Target
    wrapperSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    service = 'seclogon'; observer = 'cross-session/observe.py'; startRequested = $false; restored = $null }
try {
    Invoke-IfwWriterObservation $record {
        & python (Join-Path $PSScriptRoot 'observe.py') $Target --output (Join-Path $area 'cross-session')
        $record.observerExit = $LASTEXITCODE
    }
} catch {
    $record.error = $_.Exception.Message
    throw
} finally {
    [IO.File]::WriteAllText($receipt, ($record | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
}
exit $record.observerExit
