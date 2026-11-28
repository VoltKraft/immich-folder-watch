$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'mode-sample.ps1')

$head = 'IME_MODE sample=2 state=observed thread=23 hkl=68224017 imeRequested=true'
$read = ConvertFrom-IfwModeSample "$head open=true conversion=9`r`n" 2 23
if ($read.state -cne 'observed' -or -not $read.open -or $read.conversionFlags -ne 9 -or
    $read.layout -ne 68224017 -or -not $read.imeRequested) { throw 'Lost an observed conversion mode.' }
$plain = ConvertFrom-IfwModeSample "$head open=false conversion=0`n" 2 23
$unknown = ConvertFrom-IfwModeSample "$head open=true conversion=unavailable`n" 2 23
if ($plain.open -or $null -eq $plain.conversionFlags -or $plain.conversionFlags -ne 0 -or
    $null -ne $unknown.conversionFlags -or -not $unknown.open) { throw 'Closed, alphanumeric and unsupported modes differ.' }
$line = "$head open=false conversion=0`n"
if ($null -ne (ConvertFrom-IfwModeSample $line 3 23) -or
    $null -ne (ConvertFrom-IfwModeSample $line.TrimEnd() 2 23) -or
    (ConvertFrom-IfwModeSample $line 2 24).state -cne 'invalid-response' -or
    (ConvertFrom-IfwModeSample ($line + $line) 2 23).state -cne 'ambiguous-response') {
    throw 'A stale, partial, wrong-thread or repeated reply was used.'
}
$none = ConvertFrom-IfwModeSample "IME_MODE sample=2 state=no-context thread=23 hkl=68224017 imeRequested=false`n" 2 23
if ($none.state -cne 'no-context' -or $none.imeRequested -or $none.Contains('open')) { throw 'An absent context produced a mode.' }

function Test-OwnedFocus { return $testFieldFocused }
function Get-Trace([long]$Offset) { return $line }
$SubjectLog = $PSCommandPath
$threadId = 23
$sampleWriter = [IO.MemoryStream]::new()
try {
    $testFieldFocused = $false
    if ((Get-IfwModeSample 2).state -cne 'observer-field-unfocused' -or $sampleWriter.Length -ne 0) {
        throw 'A request escaped the field focus check.'
    }
    $testFieldFocused = $true
    if ((Get-IfwModeSample 2).state -cne 'observed' -or $sampleWriter.Length -ne 1 -or
        $sampleWriter.ToArray()[0] -ne 50) { throw 'Expected one private-pipe phase byte.' }
} finally { $sampleWriter.Dispose() }
