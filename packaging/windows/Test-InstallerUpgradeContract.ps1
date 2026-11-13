[CmdletBinding()]
param(
    [string]$Path,
    [ValidateSet("x64", "arm64")][string]$ExpectedPlatform,
    [string]$ExpectedVersion
)

$ErrorActionPreference = "Stop"

function Test-UpgradeSequence {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Actions,
        [Parameter(Mandatory = $true)][hashtable]$CustomActions,
        [Parameter(Mandatory = $true)][hashtable]$CloseApplication
    )

    $closeNames = @($Actions.Keys | Where-Object { $_ -match '^Wix4CloseApplications_(X64|A64)$' })
    if ($closeNames.Count -ne 1) {
        throw "Expected exactly one native application-close action in the MSI execute sequence."
    }
    $orderedNames = @($closeNames[0], "EnsureAppClosed", "InstallValidate", "InstallInitialize", "RemoveExistingProducts", "RemoveFiles")
    $previous = 0
    foreach ($name in $orderedNames) {
        if (-not $Actions.ContainsKey($name)) {
            throw "Required MSI execute action is missing: $name"
        }
        $sequence = [int]$Actions[$name].Sequence
        if ($sequence -le $previous) {
            throw "MSI action $name must run after the preceding upgrade-contract action."
        }
        $previous = $sequence
    }
    if (-not $CustomActions.ContainsKey("EnsureAppClosed") -or
        [int]$CustomActions["EnsureAppClosed"].Type -ne 19 -or
        $Actions["EnsureAppClosed"].Condition -cne "IFW_APP_RUNNING") {
        throw "EnsureAppClosed must be a synchronous Type 19 error conditioned on IFW_APP_RUNNING."
    }
    if (-not $CustomActions.ContainsKey($closeNames[0]) -or
        (([int]$CustomActions[$closeNames[0]].Type -band 0x480) -ne 0)) {
        throw "Application-close action must execute synchronously and immediately before the transaction."
    }
    # WiX Util: CloseMessage=1 and EndSessionMessage=8. Elevated, terminate,
    # reboot and prompt flags would change this pre-transaction contract.
    if ([int]$CloseApplication.Attributes -ne 9) {
        throw "Application-close action must use only synchronous graceful-close flags."
    }
    if ($Actions[$closeNames[0]].Condition -notin @("", "1", "VersionNT > 400")) {
        throw "Application-close action must not skip an upgrade or uninstall."
    }
    if ($CloseApplication.Target -cne "ImmichFolderWatch.exe" -or
        $CloseApplication.Property -cne "IFW_APP_RUNNING" -or
        $CloseApplication.Condition -notin @("", "1")) {
        throw "Application-close detection must cover ImmichFolderWatch.exe and set IFW_APP_RUNNING."
    }
    if ([int]$CloseApplication.Timeout -lt 15000) {
        throw "Application-close action must allow at least 15 seconds for graceful shutdown."
    }
}

function Test-InstallerIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$Template,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][hashtable]$Actions,
        [Parameter(Mandatory = $true)][ValidateSet("x64", "arm64")][string]$ExpectedPlatform,
        [Parameter(Mandatory = $true)][string]$ExpectedVersion
    )

    $platform = $Template.Split(';')[0]
    if ($platform -ine $ExpectedPlatform) {
        throw "MSI platform '$platform' does not match requested '$ExpectedPlatform'."
    }
    if ($ProductVersion -cne $ExpectedVersion) {
        throw "MSI version '$ProductVersion' does not match requested '$ExpectedVersion'."
    }
    $suffix = if ($ExpectedPlatform -eq "arm64") { "A64" } else { "X64" }
    if (-not $Actions.ContainsKey("Wix4CloseApplications_$suffix")) {
        throw "MSI close action does not match requested '$ExpectedPlatform' architecture."
    }
}

function Read-MsiRows {
    param([object]$Database, [string]$Query, [string[]]$Columns)

    $view = $null
    try {
        $view = $Database.GetType().InvokeMember("OpenView", "InvokeMethod", $null, $Database, @($Query))
        $view.GetType().InvokeMember("Execute", "InvokeMethod", $null, $view, $null) | Out-Null
        while ($true) {
            $record = $view.GetType().InvokeMember("Fetch", "InvokeMethod", $null, $view, $null)
            if ($null -eq $record) { break }
            try {
                $row = @{}
                for ($index = 0; $index -lt $Columns.Count; $index++) {
                    $row[$Columns[$index]] = [string]$record.GetType().InvokeMember(
                        "StringData", "GetProperty", $null, $record, ($index + 1))
                }
                $row
            }
            finally {
                [void][Runtime.InteropServices.Marshal]::ReleaseComObject($record)
            }
        }
    }
    finally {
        if ($null -ne $view) {
            try { $view.GetType().InvokeMember("Close", "InvokeMethod", $null, $view, $null) | Out-Null }
            finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($view) }
        }
    }
}

function Test-InstallerUpgradeContract {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet("x64", "arm64")][string]$ExpectedPlatform,
        [Parameter(Mandatory = $true)][string]$ExpectedVersion
    )

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $installer = $null
    $database = $null
    try {
        $installer = New-Object -ComObject WindowsInstaller.Installer
        # Read-only mode: validation must not alter the artifact being shipped.
        $database = $installer.GetType().InvokeMember("OpenDatabase", "InvokeMethod", $null, $installer, @($resolvedPath, 0))
        $actions = @{}
        foreach ($row in @(Read-MsiRows $database 'SELECT `Action`, `Condition`, `Sequence` FROM `InstallExecuteSequence`' @("Action", "Condition", "Sequence"))) {
            $actions[$row.Action] = $row
        }
        $customActions = @{}
        foreach ($row in @(Read-MsiRows $database 'SELECT `Action`, `Type` FROM `CustomAction`' @("Action", "Type"))) {
            $customActions[$row.Action] = $row
        }
        $closeRows = @(Read-MsiRows $database 'SELECT `Target`, `Condition`, `Attributes`, `Property`, `Timeout` FROM `Wix4CloseApplication`' @("Target", "Condition", "Attributes", "Property", "Timeout"))
        if ($closeRows.Count -ne 1) { throw "Expected exactly one application-close definition in the MSI." }
        $summary = $null
        try {
            $summary = $database.GetType().InvokeMember("SummaryInformation", "GetProperty", $null, $database, @(0))
            $template = [string]$summary.GetType().InvokeMember("Property", "GetProperty", $null, $summary, 7)
        }
        finally {
            if ($null -ne $summary) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($summary) }
        }
        $versions = @(Read-MsiRows $database 'SELECT `Value` FROM `Property` WHERE `Property` = ''ProductVersion''' @("Value"))
        if ($versions.Count -ne 1) { throw "Expected one ProductVersion in the MSI." }
        Test-InstallerIdentity -Template $template -ProductVersion $versions[0].Value -Actions $actions `
            -ExpectedPlatform $ExpectedPlatform -ExpectedVersion $ExpectedVersion
        Test-UpgradeSequence -Actions $actions -CustomActions $customActions -CloseApplication $closeRows[0]
        Write-Host "MSI upgrade contract verified for $ExpectedPlatform $ExpectedVersion`: process closure precedes removal inside the transaction."
    }
    finally {
        if ($null -ne $database) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($database) }
        if ($null -ne $installer) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($installer) }
    }
}

# Dot sourcing exposes the pure contract check for fixture-based regression tests.
if ($MyInvocation.InvocationName -ne ".") {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw "Specify the built MSI using -Path." }
    if ([string]::IsNullOrWhiteSpace($ExpectedPlatform) -or [string]::IsNullOrWhiteSpace($ExpectedVersion)) {
        throw "Specify the requested MSI identity using -ExpectedPlatform and -ExpectedVersion."
    }
    Test-InstallerUpgradeContract -Path $Path -ExpectedPlatform $ExpectedPlatform -ExpectedVersion $ExpectedVersion
}
