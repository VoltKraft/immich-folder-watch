# Exercise the actual transition and rollback code with a synthetic toggle.
$ErrorActionPreference = 'Stop'
$tokens = $errors = $null
$source = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'toast_settings.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($fn in @('Save-Intent','Confirm-Intent','Set-TestDnd')) {
    $body = $source.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $fn
    }, $false)
    if ($body.Count -ne 1) { throw "Missing original function $fn" }
    . ([scriptblock]::Create($body[0].Extent.Text))
}
function Read-Switch($window, $id) {
    if ($id -cne $dndId) { throw 'The test setter read another control.' }
    return @{ state = $window.Current.ToggleState }
}
function Trial($actionName, $master, $state) {
    $Action = $actionName
    $report = @{ status = 'observed'; scriptSha256 = 'fixture-digest'
                 notifications = @{ state = $master }; doNotDisturb = @{ state = $state; enabled = $true } }
    Set-TestDnd $pattern $pattern
    return $report
}
function Must-Fail([scriptblock]$case) {
    $caught = $false
    try { & $case | Out-Null } catch { $caught = $true }
    if (!$caught) { throw 'An invalid transition unexpectedly succeeded.' }
}
$dndId = 'synthetic-dnd'
$session = 23
$area = [IO.Directory]::CreateDirectory((Join-Path ([IO.Path]::GetTempPath()) ('ifw-dnd-' + [guid]::NewGuid().ToString('N'))))
$intentPath = Join-Path $area.FullName 'intent.json'
$pattern = [pscustomobject]@{ Current = [pscustomobject]@{ ToggleState = 'On' }; Calls = 0; FailAfterChanging = $false }
$pattern | Add-Member ScriptMethod Toggle {
    $this.Calls++
    $this.Current.ToggleState = if ($this.Current.ToggleState -ceq 'On') { 'Off' } else { 'On' }
    if ($this.FailAfterChanging) { throw 'Synthetic provider failure after a toggle.' }
}
try {
    Must-Fail { Trial 'Permit' 'Off' 'On' }
    Must-Fail { Trial 'Restore' 'On' 'On' }
    if ($pattern.Calls -or (Test-Path $intentPath)) { throw 'A refused request changed the switch.' }

    $pattern.FailAfterChanging = $true
    Must-Fail { Trial 'Permit' 'On' 'On' }
    if ($pattern.Current.ToggleState -cne 'Off' -or !(Test-Path $intentPath)) { throw 'Missing durable rollback intent.' }
    $pattern.FailAfterChanging = $false
    $restored = Trial 'Restore' 'On' 'Off'
    if ($restored.status -cne 'restored' -or $pattern.Current.ToggleState -cne 'On' -or $pattern.Calls -ne 2) {
        throw 'The changed switch was not restored after a provider failure.'
    }
    $again = Trial 'Restore' 'On' 'On'
    if ($again.status -cne 'restored' -or $pattern.Calls -ne 2) { throw 'A second restore changed the switch.' }
    $session = 24
    Must-Fail { Trial 'Restore' 'On' 'Off' }
    if ($pattern.Calls -ne 2) { throw 'An unrelated session changed the switch.' }
    [IO.File]::Delete($intentPath)
    $pattern.Current.ToggleState = 'Off'
    $asFound = Trial 'Permit' 'On' 'Off'
    if ($asFound.status -cne 'permitted' -or (Test-Path $intentPath) -or $pattern.Calls -ne 2) {
        throw 'A permitted original setting acquired a spurious rollback.'
    }
} finally {
    [IO.File]::Delete($intentPath)
    $area.Delete()
}
Write-Output 'Notification switch ownership, failure recovery and idempotent restoration passed.'
