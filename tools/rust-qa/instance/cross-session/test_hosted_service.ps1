# Portable controls for the disposable service lifecycle. No live service is accessed.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hosted.ps1')

function Get-Service {
    [CmdletBinding()] param([string]$Name)
    if ($Name -cne 'seclogon') { throw 'Unexpected service lookup.' }
    $entry = [pscustomobject]@{ Name = $Name; Status = $script:state; StartType = $script:startType }
    $entry | Add-Member ScriptMethod WaitForStatus {
        param($desired, $timeout)
        if ($this.Name -cne 'seclogon' -or $desired -cne $script:state -or $timeout.TotalSeconds -ne 20) {
            throw 'Unexpected service transition.'
        }
    }
    $entry
}
function Start-Service {
    [CmdletBinding()] param($InputObject)
    if ($InputObject.Name -cne 'seclogon' -or $script:state -cne 'Stopped') { throw 'Unexpected start.' }
    $script:starts++
    if ($script:failure -ceq 'start') { throw 'Start refused.' }
    $script:state = 'Running'
}
function Stop-Service {
    [CmdletBinding()] param($InputObject)
    if ($InputObject.Name -cne 'seclogon' -or $script:state -cne 'Running') { throw 'Unexpected stop.' }
    $script:stops++
    if ($script:failure -ceq 'stop') { throw 'Stop refused.' }
    $script:state = 'Stopped'
}

$cases = @(
    @('Running', 'Manual', '', 0, 0),
    @('Stopped', 'Manual', '', 1, 1),
    @('Stopped', 'Automatic', '', 1, 1),
    @('Stopped', 'Disabled', '', 0, 0),
    @('Stopped', 'Manual', 'start', 1, 0),
    @('Stopped', 'Manual', 'observer', 1, 1),
    @('Stopped', 'Manual', 'stop', 1, 1)
)
foreach ($case in $cases) {
    $initial, $script:startType, $script:failure, $startsExpected, $stopsExpected = $case
    $script:state = $initial
    $script:starts = $script:stops = $script:observations = 0
    $record = [ordered]@{ startRequested = $false; restored = $null }
    $problem = $null
    try {
        Invoke-IfwWriterObservation $record {
            $script:observations++
            if ($script:failure -ceq 'observer') { throw 'Observer refused.' }
        }
    } catch { $problem = $_.Exception.Message }
    if ($script:starts -ne $startsExpected -or $script:stops -ne $stopsExpected -or
        $script:observations -ne 1 -or
        (($script:failure -ceq 'start') -ne ($record.preparationError -ceq 'Start refused.')) -or
        (($script:failure -ceq 'stop') -ne ($problem -ceq 'Stop refused.')) -or
        (($script:failure -ceq 'observer') -ne ($problem -ceq 'Observer refused.')) -or
        ($script:failure -cne 'stop' -and ($record.restored -ne $true -or $script:state -cne $initial))) {
        throw "Unexpected service lifecycle for [$case], receipt $($record | ConvertTo-Json -Compress), error [$problem]"
    }
}
Write-Output "$($cases.Count) hosted service controls passed."
