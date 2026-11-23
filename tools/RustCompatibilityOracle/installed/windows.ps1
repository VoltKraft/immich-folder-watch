[CmdletBinding()]
param([string]$Package, [string]$Seed, [string]$Evidence)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# The File identifiers are also the entry names in each original embedded cabinet.
# The digest covers ordinally sorted UTF-8 lines: ID<TAB>decimal size<TAB>lowercase SHA-256<LF>.
function Get-ReleasePayload([string]$Architecture) {
    switch ($Architecture) {
        x64 {
            return @{
                productCode = '{50554B02-DB63-4388-A959-8F0B25856F5A}'
                packageCode = '{19DC3747-2CBD-4D6A-9960-AB0AA4B65947}'
                files = 439; bytes = 149235325; machine = 0x8664
                digest = '96711b33e8d8e72228ab213b733438a972dc4ada44f9cfbf973e13244a250940'
            }
        }
        arm64 {
            return @{
                productCode = '{A947D312-F16F-4F10-8F47-92F33393028A}'
                packageCode = '{A16B20CA-66EB-43A4-A98E-4FA850897F89}'
                files = 438; bytes = 160659509; machine = 0xaa64
                digest = '8a0d6104742f6b3e5f448f70064afc4cdcb3e3feda1759d2b2e21652c003c8ab'
            }
        }
        default { throw "Unsupported Windows architecture '$Architecture'." }
    }
}

function Get-HostedArchitecture {
    if (-not $IsWindows -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
        $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -ine 'VoltKraft/immich-folder-watch' -or
        $env:GITHUB_REF -cne 'refs/heads/rewrite/rust' -or $env:GITHUB_SHA -cnotmatch '^[0-9a-f]{40}$') {
        throw 'The native MSI baseline requires this rewrite branch on a disposable GitHub-hosted Windows runner.'
    }
    $checkout = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
    if ($checkout -ine $env:GITHUB_WORKSPACE -or (& git -C $checkout rev-parse HEAD) -cne $env:GITHUB_SHA) {
        throw 'The fixture must run from the exact revision checked out by the hosted job.'
    }
    $arch = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    if ($arch -notin @('x64', 'arm64') -or $arch -ine $env:RUNNER_ARCH -or
        $arch -ine [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()) {
        throw 'The hosted runner, operating system and PowerShell process must have the same native architecture.'
    }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'The disposable runner must be elevated.'
    }
    return $arch
}

function Assert-PlainPath([string]$ItemPath) {
    # Include parents: testing the leaf alone would accept files reached through a junction.
    $part = [IO.Path]::GetFullPath($ItemPath)
    while ($part) {
        try { $entry = Get-Item -Force -LiteralPath $part -ErrorAction Stop }
        catch [Management.Automation.ItemNotFoundException] { $entry = $null }
        if ($entry -and ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing a path through a reparse point: $part"
        }
        $part = [IO.Path]::GetDirectoryName($part)
    }
}

function Get-FixturePath([string]$ItemPath) {
    if (-not $ItemPath -or -not [IO.Path]::IsPathFullyQualified($ItemPath)) { throw 'Expected an absolute fixture path.' }
    $full = [IO.Path]::GetFullPath($ItemPath)
    foreach ($base in @($env:RUNNER_TEMP, $env:GITHUB_WORKSPACE)) {
        if (-not $base) { continue }
        $prefix = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($base)) + [IO.Path]::DirectorySeparatorChar
        if ($full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
            Assert-PlainPath $full
            return $full
        }
    }
    throw 'Fixture inputs and evidence must be inside the runner temporary directory or checkout.'
}

function Assert-Absent([string]$ItemPath) {
    try { [void](Get-Item -LiteralPath $ItemPath -Force -ErrorAction Stop) }
    catch [Management.Automation.ItemNotFoundException] { return }
    throw "Refusing to overwrite an existing path: $ItemPath"
}

function New-FixtureDirectory([string]$ItemPath) {
    Assert-PlainPath $ItemPath
    Assert-Absent $ItemPath
    [void](New-Item -ItemType Directory -Path $ItemPath -ErrorAction Stop)
}

function Get-FileDigest([string]$ItemPath) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $ItemPath).Hash.ToLowerInvariant()
}

function Write-Record([string]$ItemPath, $Record) {
    $json = ($Record | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $stream = [IO.File]::Open($ItemPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Get-TargetName([string]$MsiName) {
    $name = $MsiName.Split('|')[-1]
    if (-not $name -or $name -in @('.', '..') -or $name -match '[\\/:*?"<>|\x00-\x1f]') {
        throw "Unsafe MSI destination name '$MsiName'."
    }
    return $name
}

function Get-FileLayout($DirectoryRows, $ComponentRows, $FileRows) {
    $directories = @{}
    foreach ($row in $DirectoryRows) { $directories.Add($row.Directory, $row) }
    $root = $directories['INSTALLFOLDER']
    $bin = $directories['BINDIR']
    if ($root.Parent -cne 'ProgramFiles64Folder' -or (Get-TargetName $root.Name) -cne 'Immich Folder Watch' -or
        $bin.Parent -cne 'INSTALLFOLDER' -or $bin.Name -cne 'bin') { throw 'Unexpected MSI destination root.' }
    $components = @{}
    foreach ($row in $ComponentRows) { $components.Add($row.Component, $row.Directory) }
    $layout = @{}
    $destinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($row in $FileRows) {
        $relative = Get-TargetName $row.Name
        $directory = $components[$row.Component]
        $seen = [Collections.Generic.HashSet[string]]::new()
        while ($directory -cne 'BINDIR') {
            if (-not $directory -or -not $directories.ContainsKey($directory) -or -not $seen.Add($directory)) {
                throw "MSI file $($row.File) has no destination under BINDIR."
            }
            $entry = $directories[$directory]
            $target = $entry.Name.Split(':')[0]
            if ($target -cne '.') { $relative = [IO.Path]::Combine((Get-TargetName $target), $relative) }
            $directory = $entry.Parent
        }
        if ($row.File -cnotmatch '^[A-Za-z0-9._]+$' -or -not $destinations.Add($relative)) {
            throw "Invalid or duplicated MSI file destination: $relative"
        }
        $layout.Add($row.File, @{ path = $relative; bytes = [long]$row.Bytes })
    }
    return $layout
}

function Get-ReleaseIntegration($CustomActions, $Sequence, $Shortcuts, [string]$Architecture) {
    $suffix = @{ x64 = 'X64'; arm64 = 'A64' }[$Architecture]
    $reviewed = @('EnsureAppClosed', "Wix4CloseApplications_$suffix", "Wix4CloseApplicationsDeferred_$suffix",
        "Wix4CheckRebootRequired_$suffix")
    $actions = @($CustomActions | ForEach-Object { $_.Action })
    $scheduled = @($Sequence | ForEach-Object { $_.Action })
    if ($actions.Count -ne $reviewed.Count -or (Compare-Object $actions $reviewed -CaseSensitive) -or
        $scheduled.Count -ne 29 -or $scheduled -cnotcontains "Wix4CloseApplications_$suffix" -or
        $scheduled -ccontains 'MigrateLegacyUserConfig' -or $scheduled -ccontains 'RelaunchAppAfterUpgrade') {
        throw 'Unexpected custom actions or sequence in the original release MSI.'
    }
    if ($Shortcuts.Count -ne 1) { throw 'Expected one authored desktop shortcut in the release MSI.' }
    $link = $Shortcuts[0]
    if ($link.Shortcut -cne 'DesktopShortcut' -or $link.Directory -cne 'DesktopFolder' -or
        $link.Component -cne 'DesktopShortcutComponent' -or $link.Target -cne '[BINDIR]ImmichFolderWatch.exe' -or
        $link.Arguments -cne '' -or $link.WorkingDirectory -cne 'INSTALLFOLDER') {
        throw 'The compiled desktop shortcut differs from the original release.'
    }
    return [ordered]@{ customActions = $actions; installExecuteSequence = $Sequence; shortcut = $link }
}

function Read-ReleaseMsi([string]$MsiPath, [string]$Architecture, $Expected) {
    . (Join-Path $PSScriptRoot '../../../packaging/windows/Test-InstallerUpgradeContract.ps1')
    Test-InstallerUpgradeContract -Path $MsiPath -ExpectedPlatform $Architecture -ExpectedVersion '3.0.4'
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $db = $null
    $summary = $null
    try {
        $db = $installer.GetType().InvokeMember('OpenDatabase', 'InvokeMethod', $null, $installer, @($MsiPath, 0))
        $summary = $db.GetType().InvokeMember('SummaryInformation', 'GetProperty', $null, $db, @(0))
        $template = [string]$summary.GetType().InvokeMember('Property', 'GetProperty', $null, $summary, 7)
        $packageCode = [string]$summary.GetType().InvokeMember('Property', 'GetProperty', $null, $summary, 9)
        $properties = @{}
        foreach ($row in (Read-MsiRows $db 'SELECT `Property`, `Value` FROM `Property`' @('Property', 'Value'))) {
            $properties[$row.Property] = $row.Value
        }
        if ($template -ine "$Architecture;1033" -or $packageCode -ine $Expected.packageCode -or
            $properties['ProductCode'] -ine $Expected.productCode -or $properties['ALLUSERS'] -cne '1' -or
            $properties['ProductName'] -cne 'Immich Folder Watch' -or $properties['Manufacturer'] -cne 'VoltKraft' -or
            $properties['UpgradeCode'] -ine '{F82E51D6-6D61-4A5D-B8AA-9D84A5D0D57D}') { throw 'Original MSI identity changed.' }
        $dirs = @(Read-MsiRows $db 'SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`' @('Directory', 'Parent', 'Name'))
        $components = @(Read-MsiRows $db 'SELECT `Component`, `Directory_` FROM `Component`' @('Component', 'Directory'))
        $files = @(Read-MsiRows $db 'SELECT `File`, `Component_`, `FileName`, `FileSize` FROM `File`' @('File', 'Component', 'Name', 'Bytes'))
        $actions = @(Read-MsiRows $db 'SELECT `Action` FROM `CustomAction` ORDER BY `Action`' @('Action'))
        $sequence = @(Read-MsiRows $db 'SELECT `Action`, `Sequence` FROM `InstallExecuteSequence` ORDER BY `Sequence`' @('Action', 'Sequence'))
        $shortcutSql = 'SELECT `Shortcut`, `Directory_`, `Component_`, `Target`, `Arguments`, `WkDir` FROM `Shortcut`'
        $shortcuts = @(Read-MsiRows $db $shortcutSql @('Shortcut', 'Directory', 'Component', 'Target', 'Arguments', 'WorkingDirectory'))
        $layout = Get-FileLayout $dirs $components $files
        if ($layout.Count -ne $Expected.files -or $layout.AppExecutableFile.path -cne 'ImmichFolderWatch.exe' -or
            $layout.SqliteNativeFile.path -cne 'e_sqlite3.dll') { throw 'Original MSI file table changed.' }
        return @{
            layout = $layout
            integration = Get-ReleaseIntegration $actions $sequence $shortcuts $Architecture
            identity = [ordered]@{ productCode = $properties.ProductCode; packageCode = $packageCode; template = $template
                upgradeCode = $properties.UpgradeCode; productName = $properties.ProductName
                manufacturer = $properties.Manufacturer; version = $properties.ProductVersion; allUsers = $properties.ALLUSERS }
        }
    }
    finally {
        foreach ($object in @($summary, $db, $installer)) {
            if ($null -ne $object) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($object) }
        }
    }
}

function Get-VerifiedPayload([string]$Bin, $Layout, $Expected) {
    Assert-PlainPath $Bin
    $entries = @(Get-ChildItem -LiteralPath $Bin -Recurse -Force)
    if (@($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count -ne 0 -or
        @($entries | Where-Object { -not $_.PSIsContainer }).Count -ne $Layout.Count) {
        throw 'Installed payload has links or an unexpected file count.'
    }
    [string[]]$ids = @($Layout.Keys)
    [Array]::Sort($ids, [StringComparer]::Ordinal)
    $lines = [Text.StringBuilder]::new()
    $record = [ordered]@{}
    [long]$total = 0
    foreach ($id in $ids) {
        $file = $Layout[$id]
        $path = Join-Path $Bin $file.path
        $info = Get-Item -LiteralPath $path -Force
        if ($info.PSIsContainer -or $info.Length -ne $file.bytes) { throw "Installed file size differs for '$id'." }
        $digest = Get-FileDigest $path
        $record[$id] = [ordered]@{ path = $file.path; bytes = $info.Length; sha256 = $digest }
        $size = $info.Length.ToString([Globalization.CultureInfo]::InvariantCulture)
        [void]$lines.Append("$id`t$size`t$digest`n")
        $total += $info.Length
    }
    $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($lines.ToString()))).ToLowerInvariant()
    if ($digest -cne $Expected.digest -or $total -ne $Expected.bytes -or $ids.Length -ne $Expected.files) {
        throw 'Installed bytes differ from the original release cabinet.'
    }
    return [ordered]@{ files = $ids.Length; bytes = $total; sha256 = $digest; entries = $record }
}

function Get-PeMachine([string]$ItemPath) {
    $reader = [IO.BinaryReader]::new([IO.File]::OpenRead($ItemPath))
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw 'Missing MZ header in installed file.' }
        $reader.BaseStream.Position = 0x3c
        $reader.BaseStream.Position = $reader.ReadUInt32()
        if ($reader.ReadUInt32() -ne 0x4550) { throw 'Missing PE signature in installed file.' }
        return $reader.ReadUInt16()
    }
    finally { $reader.Dispose() }
}

function Get-ProfileHashes([string]$ProfilePath) {
    Assert-PlainPath $ProfilePath
    $entries = @(Get-ChildItem -LiteralPath $ProfilePath -Force)
    if ($entries.Count -ne 2) { throw 'Expected exactly two regular synthetic profile files.' }
    $hashes = [ordered]@{}
    foreach ($name in @('config.yaml', 'sync-state.db')) {
        $path = Join-Path $ProfilePath $name
        $item = Get-Item -LiteralPath $path -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            $item.Length -le 0 -or $item.Length -gt 16777216) { throw "Invalid synthetic profile file '$name'." }
        $hashes[$name] = Get-FileDigest $path
    }
    return $hashes
}

function Assert-Profile([string]$ProfilePath, $Expected) {
    $actual = Get-ProfileHashes $ProfilePath
    foreach ($name in $actual.Keys) {
        if ($actual[$name] -cne $Expected[$name]) { throw "The original profile bytes changed in '$name'." }
    }
    return $actual
}

function Copy-Profile([string]$Source, [string]$Destination, $Expected) {
    [void](Assert-Profile $Source $Expected)
    foreach ($name in $Expected.Keys) { [IO.File]::Copy((Join-Path $Source $name), (Join-Path $Destination $name), $false) }
    [void](Assert-Profile $Destination $Expected)
}

function Remove-OwnedProfile([string]$ProfilePath, $Expected) {
    Assert-PlainPath $ProfilePath
    $remaining = @(Get-ChildItem -LiteralPath $ProfilePath -Force)
    foreach ($file in $remaining) {
        if (-not $Expected.Contains($file.Name) -or $file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (Get-FileDigest $file.FullName) -cne $Expected[$file.Name]) {
            throw "Unrecognized profile contents left untouched: $($file.Name)"
        }
    }
    foreach ($file in $remaining) { [IO.File]::Delete($file.FullName) }
    [IO.Directory]::Delete($ProfilePath, $false)
    Assert-Absent $ProfilePath
}

function Get-HostPaths {
    $paths = @{}
    foreach ($item in @{
        install = 'ProgramFiles'; profile = 'LocalApplicationData'; legacy = 'CommonApplicationData'
        startup = 'Startup'; desktop = 'DesktopDirectory'; publicDesktop = 'CommonDesktopDirectory'
    }.GetEnumerator()) {
        $parent = [Environment]::GetFolderPath($item.Value, [Environment+SpecialFolderOption]::DoNotVerify)
        if (-not $parent -or -not [IO.Path]::IsPathFullyQualified($parent)) { throw "Unavailable Windows folder '$($item.Value)'." }
        $name = if ($item.Key -in @('startup', 'desktop', 'publicDesktop')) { 'Immich Folder Watch.lnk' } else { 'Immich Folder Watch' }
        $paths[$item.Key] = Join-Path $parent $name
    }
    $paths.bin = Join-Path $paths.install 'bin'
    $paths.exe = Join-Path $paths.bin 'ImmichFolderWatch.exe'
    $paths.service = 'HKLM:\SYSTEM\CurrentControlSet\Services\ImmichFolderWatch'
    $paths.eventLog = 'HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Immich Folder Watch'
    $paths.eventSource = $paths.eventLog + '\Immich Folder Watch'
    $paths.staleSource = 'HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application\Immich Folder Watch'
    $paths.userMarker = 'HKCU:\SOFTWARE\ImmichFolderWatch'
    return $paths
}

function Get-Registrations([string]$ProductCode) {
    foreach ($hive in @('HKLM:', 'HKCU:')) {
        foreach ($software in @('SOFTWARE', 'SOFTWARE\WOW6432Node')) {
            $root = "$hive\$software\Microsoft\Windows\CurrentVersion\Uninstall"
            if (-not (Test-Path -LiteralPath $root)) { continue }
            foreach ($key in (Get-ChildItem -LiteralPath $root)) {
                try {
                    $name = $key.GetValue('DisplayName')
                    if ($name -ieq 'Immich Folder Watch' -or $key.PSChildName -ieq $ProductCode) {
                        [ordered]@{ root = $root; productCode = $key.PSChildName; displayName = $name
                            version = $key.GetValue('DisplayVersion'); publisher = $key.GetValue('Publisher')
                            windowsInstaller = $key.GetValue('WindowsInstaller') }
                    }
                }
                finally { $key.Close() }
            }
        }
    }
}

function Get-RelatedProducts([string]$UpgradeCode) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $list = $null
    try {
        $list = $installer.GetType().InvokeMember('RelatedProducts', 'GetProperty', $null, $installer, @($UpgradeCode))
        $count = $list.GetType().InvokeMember('Count', 'GetProperty', $null, $list, $null)
        for ($index = 0; $index -lt $count; $index++) {
            [string]$list.GetType().InvokeMember('Item', 'GetProperty', $null, $list, $index)
        }
    }
    finally {
        if ($null -ne $list) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($list) }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($installer)
    }
}

function Get-PendingOperations {
    $key = Get-Item -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager'
    try {
        foreach ($name in @('PendingFileRenameOperations', 'PendingFileRenameOperations2')) {
            foreach ($value in @($key.GetValue($name))) {
                if ($value -match 'Immich ?Folder ?Watch') { [string]$value }
            }
        }
    }
    finally { $key.Close() }
}

function Get-RegistryValues([string]$KeyPath, [string[]]$Names) {
    $exists = Test-Path -LiteralPath $KeyPath
    $values = [ordered]@{}
    $valueNames = @()
    $subkeys = @()
    if ($exists) {
        $key = Get-Item -LiteralPath $KeyPath
        try {
            $valueNames = @($key.GetValueNames())
            $subkeys = @($key.GetSubKeyNames())
            foreach ($name in $Names) {
                if ($name -in $valueNames) {
                    $values[$name] = $key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                }
            }
        }
        finally { $key.Close() }
    }
    return [ordered]@{ exists = $exists; values = $values; valueNames = $valueNames; subkeys = $subkeys }
}

function Get-Shortcut([string]$LinkPath) {
    Assert-PlainPath $LinkPath
    $exists = Test-Path -LiteralPath $LinkPath
    if (-not $exists) { return [ordered]@{ path = $LinkPath; exists = $false } }
    if (-not [IO.File]::Exists($LinkPath)) { throw 'Expected a regular shortcut file.' }
    $shell = New-Object -ComObject WScript.Shell
    $link = $null
    try {
        $link = $shell.CreateShortcut($LinkPath)
        return [ordered]@{ path = $LinkPath; exists = $true; target = $link.TargetPath; arguments = $link.Arguments
            workingDirectory = $link.WorkingDirectory; sha256 = Get-FileDigest $LinkPath }
    }
    finally {
        if ($null -ne $link) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($link) }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}

function Get-HostState($Paths, $Identity) {
    return [ordered]@{
        registered = @(Get-Registrations $Identity.productCode)
        relatedProducts = @(Get-RelatedProducts $Identity.upgradeCode)
        installDirectory = Test-Path -LiteralPath $Paths.install
        userProfile = Test-Path -LiteralPath $Paths.profile
        legacyProgramData = Test-Path -LiteralPath $Paths.legacy
        legacyService = Test-Path -LiteralPath $Paths.service
        staleApplicationSource = Test-Path -LiteralPath $Paths.staleSource
        appProcesses = @(Get-Process -Name 'ImmichFolderWatch' -ErrorAction SilentlyContinue).Count
        pendingAppOperations = @(Get-PendingOperations)
        eventLog = Get-RegistryValues $Paths.eventLog @('MaxSize', 'Retention', '(Default)')
        eventSource = Get-RegistryValues $Paths.eventSource @('TypesSupported', 'EventMessageFile')
        userMarker = Get-RegistryValues $Paths.userMarker @('DesktopShortcutInstalled')
        startup = Get-Shortcut $Paths.startup
        desktop = @(@($Paths.desktop, $Paths.publicDesktop) | Select-Object -Unique | ForEach-Object { Get-Shortcut $_ })
    }
}

function Assert-NoInterference($State) {
    if ($State.legacyProgramData -or $State.legacyService -or $State.staleApplicationSource -or
        $State.appProcesses -ne 0 -or $State.pendingAppOperations.Count -ne 0) {
        throw 'A legacy directory/service/source, application process or pending product operation was found.'
    }
}

function Assert-OwnedRegistration($State, $Identity) {
    if ($State.registered.Count -ne 1 -or $State.relatedProducts.Count -ne 1 -or
        $State.relatedProducts[0] -ine $Identity.productCode) { throw 'The expected MSI is not the sole registered related product.' }
    $arp = $State.registered[0]
    if ($arp.productCode -ine $Identity.productCode -or $arp.version -cne $Identity.version -or
        $arp.displayName -cne $Identity.productName -or $arp.publisher -cne $Identity.manufacturer -or
        $arp.windowsInstaller -ne 1 -or $arp.root -ine 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall') {
        throw 'Installed product identity or per-machine ARP registration differs.'
    }
}

function Assert-Shortcut($Link, [string]$Target, [string]$Arguments) {
    if (-not $Link.exists -or $Link.target -ine $Target -or $Link.arguments -cne $Arguments) {
        throw "Unexpected shortcut target or arguments at '$($Link.path)'."
    }
}

function Assert-InstalledState($State, $Paths, $Identity) {
    Assert-NoInterference $State
    Assert-OwnedRegistration $State $Identity
    $desktop = @($State.desktop | Where-Object { $_.exists })
    if (-not $State.installDirectory -or -not $State.userProfile -or $desktop.Count -ne 1 -or
        $State.userMarker.values['DesktopShortcutInstalled'] -ne 1 -or
        $State.eventLog.values['MaxSize'] -ne 1048576 -or $State.eventLog.values['Retention'] -ne 0 -or
        $State.eventSource.values['TypesSupported'] -ne 7 -or
        $State.eventSource.values['EventMessageFile'] -ine '%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\EventLogMessages.dll') {
        throw 'Installed Windows shortcuts, event registration, user registry marker or directories differ.'
    }
    Assert-Shortcut $desktop[0] $Paths.exe ''
    if ($State.startup.exists) { throw 'Unexpected Startup shortcut for a stopped application.' }
}

function Assert-Removed($State) {
    Assert-NoInterference $State
    if ($State.startup.exists) { throw 'Unexpected Startup shortcut left untouched after uninstall.' }
    if ($State.registered.Count -ne 0 -or $State.relatedProducts.Count -ne 0 -or $State.installDirectory -or
        @($State.desktop | Where-Object { $_.exists }).Count -ne 0 -or $State.userMarker.values.Count -ne 0 -or
        $State.eventLog.values.Count -ne 0 -or $State.eventSource.values.Count -ne 0) {
        throw 'Uninstall retained an MSI registration, installed file tree, desktop shortcut or authored registry value.'
    }
}

function Read-MsiOperationLog([string]$Log, [string]$LogPath, [ValidateSet('/i', '/fp', '/x')][string]$Operation, $Identity) {
    $lines = $Log.TrimEnd([char[]]"`r`n") -split '\r?\n'
    if ($lines.Count -lt 3 -or $lines[0] -cnotmatch '^=== Verbose logging started: .+ ===$' -or
        $lines[-2] -cnotmatch '^MSI \(c\) .+: MainEngineThread is returning 0$' -or
        $lines[-1] -cnotmatch '^=== Verbose logging stopped: .+ ===$') {
        throw "Incomplete successful Windows Installer log: $LogPath"
    }
    foreach ($line in @("Property(S): ProductCode = $($Identity.productCode)",
                         "Property(S): PackageCode = $($Identity.packageCode)", "Property(S): MsiLogFileLocation = $LogPath")) {
        if ($lines -inotcontains $line) { throw "Windows Installer log identity differs: $line" }
    }
    $suffix = if ($Identity.template -ieq 'x64;1033') { 'X64' } else { 'A64' }
    $starts = @([regex]::Matches($Log, '(?m)^Action start [\d:]+: (\w+)\.\r?$') | ForEach-Object { $_.Groups[1].Value })
    foreach ($action in @("Wix4CloseApplications_$suffix", 'InstallInitialize', 'InstallFinalize', 'INSTALL')) {
        if ($starts -cnotcontains $action -or $Log -cnotmatch "(?m)^Action ended [\d:]+: $action\. Return value 1\.\r?$") {
            throw "Missing completed Windows Installer action '$action' in $LogPath"
        }
    }
    if ($starts -ccontains 'MigrateLegacyUserConfig' -or $starts -ccontains 'RelaunchAppAfterUpgrade') {
        throw "Unexpected migration or GUI relaunch action in $LogPath"
    }
    $verb, $result = switch ($Operation) {
        '/i'  { 'installed', 'Installation' }
        '/fp' { 'reconfigured', 'Reconfiguration' }
        '/x'  { 'removed', 'Removal' }
    }
    $success = "Windows Installer $verb the product. Product Name: $($Identity.productName). Product Version: $($Identity.version). " +
               "Product Language: 1033. Manufacturer: $($Identity.manufacturer). $result success or error status: 0."
    if ($Log -cnotmatch "(?m)^MSI \(s\) [^\r\n]+: $([regex]::Escape($success))\r?$") {
        throw "Missing successful product $result in $LogPath"
    }
    $fileOp = if ($Operation -eq '/x') { 'FileRemove\([^)\r\n]*\bFileName=e_sqlite3\.dll,' }
              else { 'FileCopy\([^)\r\n]*\bSourceCabKey=SqliteNativeFile,DestName=e_sqlite3\.dll,' }
    if ($Log -cnotmatch "(?m)^MSI \(s\) [^\r\n]+: Executing op: $fileOp" -or
        ($Operation -eq '/fp' -and $lines -inotcontains 'Property(S): REINSTALLMODE = p') -or
        ($Operation -eq '/x' -and $lines -cnotcontains 'Property(S): REMOVE = ALL')) {
        throw "Missing requested $Operation file operation in $LogPath"
    }
    return [ordered]@{ migrationActionStarted = $false; guiRelaunchActionStarted = $false
        actionStarts = $starts.Count; productOperation = $result; sqliteFileOperation = $true }
}

function Invoke-ReleaseMsi([string]$Switch, [string]$Subject, [string]$LogPath, $Operations, $Identity) {
    Assert-Absent $LogPath
    $entry = [ordered]@{ operation = $Switch; subject = $Subject; log = [IO.Path]::GetFileName($LogPath)
        exitCode = $null; timedOut = $false }
    [void]$Operations.Add($entry)
    $start = [Diagnostics.ProcessStartInfo]::new((Join-Path $env:SystemRoot 'System32\msiexec.exe'))
    $start.UseShellExecute = $false
    foreach ($argument in @($Switch, $Subject, '/qn', '/norestart', '/L*V', $LogPath)) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($start)
    try {
        if (-not $process.WaitForExit(300000)) {
            $entry.timedOut = $true
            $process.Kill()
            throw 'Windows Installer timed out. The disposable runner must be discarded.'
        }
        $entry.exitCode = $process.ExitCode
        if ($entry.exitCode -ne 0) { throw "Windows Installer returned $($entry.exitCode). See $($entry.log)." }
        $entry.actions = Read-MsiOperationLog (Get-Content -Raw -LiteralPath $LogPath) $LogPath $Switch $Identity
    }
    finally { $process.Dispose() }
}

function Invoke-InstalledBaseline([string]$Package, [string]$Seed, [string]$Evidence) {
    $architecture = Get-HostedArchitecture
    $package = Get-FixturePath $Package
    $seed = Get-FixturePath $Seed
    $evidence = Get-FixturePath $Evidence
    New-FixtureDirectory $evidence
    $release = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'release.json') | ConvertFrom-Json -AsHashtable
    $target = "windows-$architecture"
    $asset = $release.assets[$target]
    $expected = Get-ReleasePayload $architecture
    $receipt = [ordered]@{
        format = 'ifw-shipping-msi-baseline-v1'; status = 'failed'; target = $target
        sourceCommit = $env:GITHUB_SHA; releaseCommit = $release.commit; workflowRun = $env:GITHUB_RUN_ID
        os = [Runtime.InteropServices.RuntimeInformation]::OSDescription; package = $asset
        operations = [Collections.Generic.List[object]]::new(); checkpoints = [ordered]@{}; cleanup = [ordered]@{}
    }
    $ownProfile = $false
    $installationStarted = $false
    $installRemoved = $false
    $failure = $null
    try {
        $item = Get-Item -LiteralPath $package -Force
        if ($item.PSIsContainer -or $item.Name -cne $asset.name -or $item.Length -ne $asset.bytes -or
            (Get-FileDigest $package) -cne $asset.sha256) { throw 'The release MSI name, size or digest differs.' }
        $msi = Read-ReleaseMsi $package $architecture $expected
        $receipt.identity = $msi.identity
        $receipt.integration = $msi.integration
        $hashes = Get-ProfileHashes $seed
        $config = Join-Path $PSScriptRoot '../../../rust/tests/fixtures/legacy/windows/config/defaults.written.yaml'
        if ($hashes['config.yaml'] -cne (Get-FileDigest $config)) { throw 'Expected the checked-in synthetic Windows YAML.' }
        $receipt.seed = $hashes
        $paths = Get-HostPaths
        # Require an empty product footprint before creating the stopped synthetic profile.
        foreach ($name in @('install', 'profile', 'legacy', 'startup', 'desktop', 'publicDesktop')) {
            Assert-PlainPath $paths[$name]
            Assert-Absent $paths[$name]
        }
        foreach ($name in @('service', 'eventLog', 'staleSource', 'userMarker')) { Assert-Absent $paths[$name] }
        $clean = Get-HostState $paths $msi.identity
        $receipt.checkpoints.before = $clean
        Assert-NoInterference $clean
        if ($clean.registered.Count -ne 0 -or $clean.relatedProducts.Count -ne 0) {
            throw 'A related MSI or ARP registration already exists.'
        }
        New-FixtureDirectory $paths.profile
        $ownProfile = $true
        Copy-Profile $seed $paths.profile $hashes
        $installationStarted = $true
        Invoke-ReleaseMsi '/i' $package (Join-Path $evidence 'install.log') $receipt.operations $msi.identity
        foreach ($stage in @('installed', 'repaired')) {
            if ($stage -eq 'repaired') {
                # The source, destination and bytes of this one owned component were verified after install.
                $challenge = $payload.entries['SqliteNativeFile']
                $path = Join-Path $paths.bin 'e_sqlite3.dll'
                Assert-PlainPath $path
                if ($challenge.path -cne 'e_sqlite3.dll' -or (Get-FileDigest $path) -cne $challenge.sha256) {
                    throw 'The owned file changed before the repair challenge.'
                }
                [IO.File]::Delete($path)
                Assert-Absent $path
                $receipt.checkpoints.beforeRepair = [ordered]@{
                    missing = $challenge.path; originalSha256 = $challenge.sha256
                    profile = Assert-Profile $paths.profile $hashes
                }
                Invoke-ReleaseMsi '/fp' $package (Join-Path $evidence 'repair.log') $receipt.operations $msi.identity
            }
            $state = Get-HostState $paths $msi.identity
            $receipt.checkpoints[$stage] = $state
            Assert-InstalledState $state $paths $msi.identity
            $state.profile = Assert-Profile $paths.profile $hashes
            $payload = Get-VerifiedPayload $paths.bin $msi.layout $expected
            $native = [ordered]@{}
            foreach ($name in @('ImmichFolderWatch.exe', 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll', 'e_sqlite3.dll')) {
                $machine = Get-PeMachine (Join-Path $paths.bin $name)
                if ($machine -ne $expected.machine) { throw "Unexpected PE architecture in '$name'." }
                $native[$name] = $machine
            }
            Write-Record (Join-Path $evidence "payload-$stage.json") $payload
            $state.payload = [ordered]@{ files = $payload.files; bytes = $payload.bytes; sha256 = $payload.sha256
                sqliteSha256 = $payload.entries['SqliteNativeFile'].sha256; peMachine = $native }
        }
        Invoke-ReleaseMsi '/x' $msi.identity.productCode (Join-Path $evidence 'uninstall.log') $receipt.operations $msi.identity
        $installRemoved = $true
        $removed = Get-HostState $paths $msi.identity
        $receipt.checkpoints.uninstalled = $removed
        Assert-Removed $removed
        $removed.profile = Assert-Profile $paths.profile $hashes
        $kept = Join-Path $evidence 'retained'
        New-FixtureDirectory $kept
        Copy-Profile $paths.profile $kept $hashes
        if ((Get-FileDigest $package) -cne $asset.sha256) { throw 'The source MSI changed during the trial.' }
    }
    catch {
        $failure = $_
        $receipt.error = $_.Exception.Message
    }
    finally {
        $cleanupErrors = [Collections.Generic.List[string]]::new()
        $timedOut = @($receipt.operations | Where-Object { $_.timedOut }).Count -ne 0
        if ($timedOut) { $cleanupErrors.Add('Installer service transaction may still be active. Discard this disposable runner.') }
        if ($installationStarted -and -not $timedOut) {
            try {
                if (-not $installRemoved) {
                    $current = Get-HostState $paths $msi.identity
                    Assert-NoInterference $current
                    if ($current.registered.Count -or $current.relatedProducts.Count) {
                        Assert-OwnedRegistration $current $msi.identity
                        Invoke-ReleaseMsi '/x' $msi.identity.productCode (Join-Path $evidence 'cleanup-uninstall.log') $receipt.operations $msi.identity
                    }
                }
                $after = Get-HostState $paths $msi.identity
                Assert-Removed $after
                $receipt.cleanup.startupAbsent = -not $after.startup.exists
                $receipt.cleanup.msiRemoved = $true
                $receipt.cleanup.remainingRegistryKeys = @(
                    foreach ($name in @('eventLog', 'eventSource', 'userMarker')) {
                        if ($after[$name].exists) { $paths[$name] }
                    }
                )
            }
            catch { $cleanupErrors.Add($_.Exception.Message) }
        }
        if ($ownProfile -and -not $timedOut) {
            try {
                Remove-OwnedProfile $paths.profile $hashes
                $receipt.cleanup.syntheticProfileRemoved = $true
            }
            catch { $cleanupErrors.Add($_.Exception.Message) }
        }
        $receipt.cleanup.errors = $cleanupErrors
        if ($null -eq $failure -and $cleanupErrors.Count -eq 0) { $receipt.status = 'passed' }
        Write-Record (Join-Path $evidence 'result.json') $receipt
    }
    if ($failure) { throw $failure }
    if ($cleanupErrors.Count -gt 0) { throw ($cleanupErrors -join [Environment]::NewLine) }
}

# Dot sourcing exposes the readback and ownership checks to the portable fixture.
if ($MyInvocation.InvocationName -ne '.') { Invoke-InstalledBaseline $Package $Seed $Evidence }
