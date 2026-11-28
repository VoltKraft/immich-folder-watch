# Exercise scoped servicing, including recovery after a partially successful install, without a Windows image.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'language-list.ps1')
. (Join-Path $PSScriptRoot 'guest-environment.ps1')
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'guest-capability.ps1'), [ref]$null, [ref]$errors)
if ($errors.Count) { throw $errors[0] }
foreach ($name in @('Save-IfwServicingRecord','Invoke-IfwGuestCapability')) {
    $func = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name}, $true)
    . ([scriptblock]::Create($func.Extent.Text))
}
$feature = 'Language.Basic~~~ja-JP~0.0.1.0'
$cabName = 'fixture.cab'
$cabHash = 'fixture-hash'
$source = 'a' * 40
$desktop = @{host=$env:COMPUTERNAME; account='ifw-test'; phase='installed'; observerExit=1; source=$source}
$before = @{status='unavailable'; profileRemoved=$true; hasActiveInputDesktop=$true; source=$source; prerequisite='no loaded Japanese input locale'}
function Get-IfwImeMedium($Path,$Name,$Hash) {
    if ($Path -cne 'offline-dvd' -or $Name -cne $cabName -or $Hash -cne $cabHash) { throw 'Unexpected offline source.' }
    return [pscustomobject]@{FullName=$Path}
}
function Get-WindowsCapability([switch]$Online,$Name) {
    if (-not $Online -or $Name -cne $feature) { throw 'Only the live guest and fixed capability may be queried.' }
    return [pscustomobject]@{State=$fixture.state}
}
function Add-WindowsCapability([switch]$Online,$Name,$Source,[switch]$LimitAccess) {
    if (-not $Online -or -not $LimitAccess -or $Name -cne $feature -or $Source -cne 'offline-dvd') { throw 'Unexpected servicing source.' }
    $fixture.add++
    $fixture.state='Installed'
    if ($fixture.interrupt) { throw 'Synthetic interrupted servicing call.' }
    return [pscustomobject]@{RestartNeeded=$false}
}
function Remove-WindowsCapability([switch]$Online,$Name) {
    if (-not $Online -or $Name -cne $feature) { throw 'Unexpected capability removal.' }
    $fixture.remove++
    $fixture.state='NotPresent'
    return [pscustomobject]@{RestartNeeded=$false}
}
function Get-WindowsPackage([switch]$Online) {
    return [pscustomobject]@{PackageName='Microsoft-Windows-LanguageFeatures-Basic-ja-jp-Package~31bf3856ad364e35~amd64~~10.0.26100.1'; PackageState='Installed'}
}
$work = Join-Path ([IO.Path]::GetTempPath()) ('ifw-ime-controls-' + [guid]::NewGuid())
try {
    [void][IO.Directory]::CreateDirectory((Join-Path $work 'observation'))
    $desktop | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $work 'desktop.json')
    $initial = Join-Path $work 'observation/result.json'
    foreach ($case in @('missing','installed','interrupted','wrong-desktop','missing-source')) {
        $orig = if ($case -ceq 'installed') { 'Installed' } else { 'NotPresent' }
        $fixture = @{state=$orig; add=0; remove=0; interrupt=$case -ceq 'interrupted'}
        $before.hasActiveInputDesktop = $case -cne 'wrong-desktop'
        $before | ConvertTo-Json | Set-Content -LiteralPath $initial
        $medium = if ($case -ceq 'missing-source') { 'missing' } else { 'offline-dvd' }
        $recordPath = Join-Path $work "$case.json"
        $failed = $false
        try { Invoke-IfwGuestCapability Prepare $work $medium } catch { $failed = $true }
        $shouldFail = $case -cin @('interrupted','wrong-desktop','missing-source')
        if ($failed -ne $shouldFail) { throw "Incorrect prepare result for $case." }
        if ($case -cin @('wrong-desktop','missing-source')) {
            if ($fixture.add -or (Test-Path $recordPath)) { throw 'An unqualified observation or source began servicing.' }
            continue
        }
        $beforeRestore = Get-Content -Raw $recordPath | ConvertFrom-Json
        $expectedState = if ($case -ceq 'interrupted') { 'preparing' } else { 'ready' }
        if ($beforeRestore.state -cne $expectedState) { throw "Lost original servicing state for $case." }
        Invoke-IfwGuestCapability Restore
        $result = Get-Content -Raw $recordPath | ConvertFrom-Json
        $changes = [int]($orig -ceq 'NotPresent')
        if ($result.state -cne 'restored' -or $result.originalCapability -cne $orig -or $result.finalCapability -cne $orig -or
            $fixture.add -ne $changes -or $fixture.remove -ne $changes) { throw "Incorrect capability restoration for $case." }
    }
} finally {
    if ([IO.Directory]::Exists($work)) { [IO.Directory]::Delete($work, $true) }
}
Write-Output 'Five local guest servicing controls passed.'
