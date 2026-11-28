$ErrorActionPreference = 'Stop'
if ($env:OS -ceq 'Windows_NT') {
    Add-Type -AssemblyName UIAutomationTypes
} else {
    Add-Type 'namespace System.Windows.Automation { public class ElementNotAvailableException : System.Exception {} }'
}
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'observe.ps1'), [ref]$null, [ref]$errors)
if ($errors.Count) { throw $errors[0] }
foreach ($name in @('Wait-For', 'Read-LayoutFilename', 'Send-Key')) {
    $definition = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name }, $true)
    . ([scriptblock]::Create($definition.Extent.Text))
}

$expected = 'synthetic filename'
$owned = [object]::new()
$other = [object]::new()
$field = $owned
$fixture = @{ layouts=$true; focused=$owned; reads=0; fields=[Collections.Queue]::new(); text=$expected }
function Test-SubjectLayout { return $fixture.layouts }
function Get-OwnedFilename { if ($fixture.fields.Count) { return $fixture.fields.Dequeue() } }
function Test-OwnedFocus($Candidate=$field) { return [object]::ReferenceEquals($Candidate, $fixture.focused) }
function Get-Text($Candidate) {
    if (-not [object]::ReferenceEquals($Candidate, $fixture.focused)) { throw 'Read from an unfocused field.' }
    $fixture.reads++
    if ($fixture.reads -eq 1) { throw [Windows.Automation.ElementNotAvailableException]::new() }
    return $fixture.text
}

# The first refresh exposes no field, the next is unfocused and the third disappears during its text read.
foreach ($candidate in @($null, $other, $owned, $owned)) { $fixture.fields.Enqueue($candidate) }
$evidence = @{ state='waiting'; attempts=0; lastObservation='pending' }
$ready = Wait-For { Read-LayoutFilename $evidence } 'fixture filename' -Evidence $evidence
if ($ready.text -cne $expected -or -not [object]::ReferenceEquals($ready.element, $owned) -or
    $evidence.attempts -ne 4 -or $evidence.state -cne 'observed' -or $fixture.reads -ne 2) {
    throw 'The newly focused field was not reacquired after all three transient observations.'
}

foreach ($reason in @('subject-layout-changed', 'filename-missing', 'filename-unfocused', 'unexpected-filename')) {
    $fixture.layouts = $reason -cne 'subject-layout-changed'
    if ($reason -ceq 'filename-unfocused') { $fixture.fields.Enqueue($other) }
    if ($reason -ceq 'unexpected-filename') { $fixture.fields.Enqueue($owned); $fixture.text = 'different' }
    $evidence = @{ state='waiting'; attempts=0; lastObservation='pending' }
    $failure = $null
    try { $null = Wait-For { Read-LayoutFilename $evidence } 'fixture filename' -Seconds 0 -Evidence $evidence }
    catch { $failure = $_ }
    if ($null -eq $failure -or $evidence.lastObservation -cne $reason -or $evidence.attempts -ne 1) {
        throw "Incorrect evidence for $reason."
    }
    if ($reason -ceq 'unexpected-filename') {
        if ($failure.Exception.Message -cne 'Unexpected initial synthetic filename.') { throw 'A different value was retried.' }
    } elseif ($evidence.state -cne 'unavailable' -or -not $failure.Exception.Message.Contains($reason)) {
        throw 'The timeout lost the last observation.'
    }
}

foreach ($layout in @($false, $true)) {
    $fixture.layouts = $layout
    $fixture.focused = $other
    $message = $null
    try { Send-Key 'a' } catch { $message = $_.Exception.Message }
    $required = if ($layout) { 'does not own foreground and keyboard focus' } else { 'no longer has the selected Japanese layout' }
    if (-not $message -or -not $message.Contains($required)) { throw 'An unqualified key reached the native input bridge.' }
}
