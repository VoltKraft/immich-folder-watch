# Service the fixed Japanese capability independently of the standard user's desktop.
param (
    [Parameter(Mandatory)][ValidateSet('Prepare','Restore')][string]$Action,
    [string]$InitialDirectory,
    [string]$LanguageSource
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'language-list.ps1')
. (Join-Path $PSScriptRoot 'guest-environment.ps1')
$feature = 'Language.Basic~~~ja-JP~0.0.1.0'
$cabName = 'Microsoft-Windows-LanguageFeatures-Basic-ja-jp-Package~31bf3856ad364e35~amd64~~.cab'
$cabHash = '1e2f24108e78da689d1a7607110e9c5bd564ec35119ba5e5b754cb8e059a385a'
$recordPath = Get-IfwImeCapabilityRecord
function Save-IfwServicingRecord($Record) {
    $tmp = "$recordPath.$([guid]::NewGuid()).tmp"
    [IO.File]::WriteAllText($tmp, ($Record | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    if ([IO.File]::Exists($recordPath)) { [IO.File]::Replace($tmp, $recordPath, [NullString]::Value) }
    else { [IO.File]::Move($tmp, $recordPath) }
}

function Invoke-IfwGuestCapability($Action, $InitialDirectory, $LanguageSource) {
    if ($Action -ceq 'Prepare') {
        if (Test-Path -LiteralPath $recordPath) { throw 'This disposable guest already has an IME servicing receipt.' }
        $before = Get-Content -Raw -LiteralPath (Join-Path $InitialDirectory 'observation\result.json') | ConvertFrom-Json
        $desktop = Get-Content -Raw -LiteralPath (Join-Path $InitialDirectory 'desktop.json') | ConvertFrom-Json
        if ($desktop.host -ine $env:COMPUTERNAME -or $desktop.account -ine 'ifw-test' -or
            $desktop.phase -cne 'installed' -or $desktop.source -cnotmatch '^[0-9a-f]{40}$' -or
            -not (Test-IfwMissingGuestIme $before $desktop.observerExit $desktop.source)) {
            throw 'Expected an unavailable Japanese service observed on the original active local desktop.'
        }
        $state = (Get-WindowsCapability -Online -Name $feature).State.ToString()
        if ($state -cnotin @('Installed','NotPresent')) { throw "Incomplete initial capability state: $state" }
        $record = [ordered]@{ host=$env:COMPUTERNAME; capability=$feature; source=$desktop.source
            originalCapability=$state; state='preparing'; addNeedsRestart=$false; removeNeedsRestart=$false
            installedPackages=@(); finalCapability=$null; cabSha256=$null }
        if ($state -ceq 'NotPresent') {
            $folder = Get-IfwImeMedium $LanguageSource $cabName $cabHash
            $record.cabSha256 = $cabHash
        }
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($recordPath))
        Save-IfwServicingRecord $record
        if ($state -ceq 'NotPresent') {
            $change = Add-WindowsCapability -Online -Name $feature -Source $folder.FullName -LimitAccess
            $record.addNeedsRestart = [bool]$change.RestartNeeded
            Save-IfwServicingRecord $record
            if ($record.addNeedsRestart) { throw 'Guest servicing requires a restart before observation.' }
        }
        $record.installedPackages = @(Get-WindowsPackage -Online | Where-Object {
            $_.PackageName -like 'Microsoft-Windows-LanguageFeatures-Basic-ja-jp-Package~31bf3856ad364e35~amd64~~*' -and
            $_.PackageState -eq 'Installed'
        } | ForEach-Object PackageName)
        if ((Get-WindowsCapability -Online -Name $feature).State -ne 'Installed' -or -not $record.installedPackages.Count) {
            throw 'Windows did not report the installed x64 Japanese Basic Typing package.'
        }
        $record.state = 'ready'
        Save-IfwServicingRecord $record
    } else {
        $record = Get-Content -Raw -LiteralPath $recordPath | ConvertFrom-Json
        if ($record.host -ine $env:COMPUTERNAME -or $record.capability -cne $feature -or
            $record.originalCapability -cnotin @('Installed','NotPresent')) {
            throw 'The original local capability state cannot be identified.'
        }
        if ($record.originalCapability -ceq 'NotPresent' -and (Get-WindowsCapability -Online -Name $feature).State -eq 'Installed') {
            $change = Remove-WindowsCapability -Online -Name $feature
            $record.removeNeedsRestart = [bool]$change.RestartNeeded
        }
        $record.finalCapability = (Get-WindowsCapability -Online -Name $feature).State.ToString()
        $record.state = 'restoring'
        if ($record.finalCapability -ceq $record.originalCapability -and -not $record.removeNeedsRestart) {
            $record.state = 'restored'
        }
        Save-IfwServicingRecord $record
        if ($record.state -cne 'restored') { throw 'The original guest capability state still requires restoration.' }
    }
}

Assert-IfwImeGuest
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Windows capability servicing requires an elevated session on the disposable guest.'
}
Invoke-IfwGuestCapability $Action $InitialDirectory $LanguageSource
