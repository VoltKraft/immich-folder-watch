# Read a complete response for a single private-pipe request. A layout alone never implies conversion.
function ConvertFrom-IfwModeSample([string]$Trace, [byte]$Sample, [uint32]$SubjectThread) {
    $rows = [regex]::Matches($Trace, "(?m)^IME_MODE sample=$Sample ([^\r\n]+)\r?\n")
    if ($rows.Count -eq 0) { return }
    if ($rows.Count -ne 1) { return [ordered]@{ state='ambiguous-response' } }
    $payload = $rows[0].Groups[1].Value
    if ($payload -cmatch '^state=(field-unfocused|no-window|no-owned-focus)$') {
        return [ordered]@{ state=$Matches[1] }
    }
    if ($payload -cnotmatch '^state=(no-context|release-failed|observed) thread=([0-9]+) hkl=([0-9]+) imeRequested=(true|false)(?: open=(true|false) conversion=([0-9]+|unavailable))?$') {
        return [ordered]@{ state='invalid-response' }
    }
    $state,$thread,$layout,$requested,$open,$flags = $Matches[1],$Matches[2],$Matches[3],$Matches[4],$Matches[5],$Matches[6]
    if ([uint32]$thread -ne $SubjectThread -or (($state -ceq 'observed') -ne [bool]$open)) {
        return [ordered]@{ state='invalid-response' }
    }
    $mode = [ordered]@{ state=$state; threadId=[uint32]$thread; layout=[uint64]$layout; imeRequested=($requested -ceq 'true') }
    if ($state -ceq 'observed') {
        $mode.open = $open -ceq 'true'
        $mode.conversionFlags = $null
        if ($flags -cne 'unavailable') { $mode.conversionFlags = [uint32]$flags }
    }
    return $mode
}

function Get-IfwModeSample([ValidateRange(1,7)][byte]$Sample) {
    try {
        if (-not (Test-OwnedFocus)) { return [ordered]@{ state='observer-field-unfocused' } }
        if ($null -eq $sampleWriter) { return [ordered]@{ state='no-sample-pipe' } }
        $offset = (Get-Item -LiteralPath $SubjectLog).Length
        $sampleWriter.WriteByte(48 + $Sample)
        $sampleWriter.Flush()
        $clock = [Diagnostics.Stopwatch]::StartNew()
        do {
            $mode = ConvertFrom-IfwModeSample (Get-Trace $offset) $Sample $threadId
            if ($null -ne $mode) { return $mode }
            Start-Sleep -Milliseconds 20
        } while ($clock.ElapsedMilliseconds -lt 1000)
        return [ordered]@{ state='no-response' }
    } catch { return [ordered]@{ state='sample-error'; error=$_.Exception.GetBaseException().Message } }
}
