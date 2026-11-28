[CmdletBinding()]
param([string]$Package, [string]$Evidence, [string]$Work, [string]$Target,
      [string]$Profile, [string]$Marker, [string]$ConfigSha256, [string]$Python, [switch]$WpfPrimary, [switch]$Upload)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# The reference script is also a command with its own named parameters.
$interopArguments = @{} + $PSBoundParameters
. (Join-Path $PSScriptRoot '../../RustCompatibilityOracle/installed/windows.ps1')

function Assert-ChildDirectory([string]$Parent, [string]$Child) {
    if (-not [IO.Path]::IsPathFullyQualified($Parent) -or -not [IO.Path]::IsPathFullyQualified($Child)) {
        throw 'Expected an absolute directory within the owned scratch directory.'
    }
    $prefix = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Parent)) + [IO.Path]::DirectorySeparatorChar
    $full = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Child))
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or -not [IO.Directory]::Exists($full)) {
        throw 'Expected an existing directory strictly beneath the owned scratch directory.'
    }
    Assert-PlainPath $full
}

function Assert-InteropProfile([string]$KnownProfile, [string]$ProfilePath, [string]$MarkerPath,
                               [string]$ConfigSha256, [string]$Work, [string[]]$VerifiedOutputs = @(), [switch]$Upload) {
    if ($KnownProfile -ine $ProfilePath -or [IO.Path]::GetDirectoryName($MarkerPath) -ine $ProfilePath -or
        [IO.Path]::GetFileName($MarkerPath) -cnotmatch '^\.rw02-owned-([a-f0-9]{32})$') {
        throw 'Expected the original synthetic profile and its ownership marker.'
    }
    $token = $Matches[1]
    Assert-PlainPath $ProfilePath
    $config = Join-Path $ProfilePath 'config.yaml'
    $entries = @(Get-ChildItem -Force -LiteralPath $ProfilePath | Where-Object { $_.Name -cnotin $VerifiedOutputs })
    if ($entries.Count -ne 2 -or @($entries | Where-Object {
        $_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)
    }).Count -or -not [IO.File]::Exists($config) -or -not [IO.File]::Exists($MarkerPath) -or
        (Get-Item -Force -LiteralPath $MarkerPath).Length -ne 32 -or
        [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($MarkerPath)) -cne $token) {
        throw 'The original marker or exact synthetic profile contents differ.'
    }
    if ($ConfigSha256 -cnotmatch '^[0-9a-f]{64}$' -or (Get-Item -Force -LiteralPath $config).Length -gt 4096 -or
        (Get-FileDigest $config) -cne $ConfigSha256) { throw 'The synthetic config digest or size differs.' }
    $text = [Text.UTF8Encoding]::new($false, $true).GetString([IO.File]::ReadAllBytes($config)).Replace("`r`n", "`n")
    $configPattern = @(
        '\Aimmich:', '  serverApiUrl: "http://127\.0\.0\.1:([1-9][0-9]{0,4})/api"', '  apiKey: "synthetic-benchmark"',
        '  allowInsecureHttp: true', 'watch:', '  sources:', "    - path: '((?:[^'`n`r]|'')+)'",
        '      syncMode: uploadNew', '      includeSubdirectories: true', '      deleteAfterUpload: false',
        '      extensions: \["\.jpg"\]', 'logging:', '  target: file', '  level: Information', '  logDirectory: engine-logs', '\z'
    ) -join "`n"
    if ($Upload) {
        $configPattern = $configPattern.Replace('synthetic-benchmark', 'synthetic-installed-upload').Replace('uploadNew', 'uploadAll').Replace('\.jpg', '\.png')
    }
    if ($text -cnotmatch $configPattern -or [int]$Matches[1] -gt 65535) {
        throw 'Expected the complete loopback-only synthetic WPF config.'
    }
    $media = $Matches[2].Replace("''", "'")
    Assert-ChildDirectory $Work $media
    if ($Upload -and $media -ine (Join-Path $Work 'wpf-media')) { throw 'Expected the fixed upload media directory.' }
}

function Assert-VacantHost($State) {
    Assert-NoInterference $State
    if (-not $State.userProfile -or $State.registered.Count -or $State.relatedProducts.Count -or $State.installDirectory -or
        $State.startup.exists -or @($State.desktop | Where-Object { $_.exists }).Count -or
        $State.eventLog.exists -or $State.eventSource.exists -or $State.userMarker.exists) {
        throw 'The runner has an unrelated product registration, shortcut or file footprint.'
    }
}

function Get-InstalledPackageCode($Identity) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    try {
        $code = [string]$installer.GetType().InvokeMember('ProductInfo', 'GetProperty', $null, $installer,
            @($Identity.productCode, 'PackageCode'))
        if ($code -ine $Identity.packageCode) { throw 'The registered Windows Installer package code differs.' }
        return $code
    }
    finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($installer) }
}

function Complete-InteropRemoval($Paths, $Identity, [string]$Evidence, $Receipt) {
    if (@($Receipt.operations | Where-Object { $_.timedOut }).Count) {
        throw 'The installer transaction timed out. Discard the disposable runner.'
    }
    $current = Get-HostState $Paths $Identity
    Assert-NoInterference $current
    if ($current.registered.Count -or $current.relatedProducts.Count) {
        Assert-OwnedRegistration $current $Identity
        $Receipt.cleanup.packageCode = Get-InstalledPackageCode $Identity
        Invoke-ReleaseMsi '/x' $Identity.productCode (Join-Path $Evidence 'uninstall.log') $Receipt.operations $Identity
    } elseif ($Receipt.checkpoints.Contains('installed')) {
        throw 'The observed installation disappeared before the owned uninstall.'
    }
    $after = Get-HostState $Paths $Identity
    $Receipt.checkpoints.after = $after
    Assert-Removed $after
    Assert-VacantHost $after
    $Receipt.cleanup.msiRemoved = $true
}

function Invoke-MsiInterop([string]$Package, [string]$Evidence, [string]$Work, [string]$Target,
                           [string]$Profile, [string]$Marker, [string]$ConfigSha256, [string]$Python, [switch]$WpfPrimary, [switch]$Upload) {
    $arch = Get-HostedArchitecture
    if ($WpfPrimary -and $Upload) { throw 'Choose one installed observation.' }
    if ($Target -cne @{ x64 = 'x86_64-pc-windows-msvc'; arm64 = 'aarch64-pc-windows-msvc' }[$arch]) {
        throw 'The Rust target differs from the native runner and PowerShell.'
    }
    $package = Get-FixturePath $Package
    $evidence = Get-FixturePath $Evidence
    $work = Get-FixturePath $Work
    Assert-ChildDirectory $env:RUNNER_TEMP $work
    if (-not [IO.Directory]::Exists($evidence)) { throw 'Expected the evidence directory created by the supervisor.' }
    $parent = (Get-Process -Id $PID).Parent
    try {
        if ($null -eq $parent -or -not [IO.Path]::IsPathFullyQualified($Python) -or
            $parent.MainModule.FileName -ine $Python -or [IO.Path]::GetFileName($Python) -ine 'python.exe') {
            throw 'The observer must use the current supervising Python executable.'
        }
    }
    finally { if ($null -ne $parent) { $parent.Dispose() } }
    foreach ($file in @('install.log', 'uninstall.log', 'installed.json', 'payload-installed.json', 'msi-result.json')) {
        Assert-Absent (Join-Path $evidence $file)
    }
    $release = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../../RustCompatibilityOracle/installed/release.json') |
        ConvertFrom-Json -AsHashtable
    $asset = $release.assets["windows-$arch"]
    $expected = Get-ReleasePayload $arch
    $receipt = [ordered]@{ format = 'ifw-msi-interop-operations-v1'; status = 'failed'; target = $Target
        sourceCommit = $env:GITHUB_SHA; workflowRun = $env:GITHUB_RUN_ID; releaseCommit = $release.commit; package = $asset
        operations = [Collections.Generic.List[object]]::new(); checkpoints = [ordered]@{}; cleanup = [ordered]@{} }
    $attempted = $false
    try {
        $item = Get-Item -LiteralPath $package -Force
        if ($item.PSIsContainer -or $item.Name -cne $asset.name -or $item.Length -ne $asset.bytes -or
            (Get-FileDigest $package) -cne $asset.sha256) { throw 'The original 3.0.4 release MSI differs.' }
        $msi = Read-ReleaseMsi $package $arch $expected
        $receipt.identity = $msi.identity
        $receipt.integration = $msi.integration
        $paths = Get-HostPaths
        Assert-InteropProfile $paths.profile $Profile $Marker $ConfigSha256 $work -Upload:$Upload
        foreach ($name in @('install', 'legacy', 'startup', 'desktop', 'publicDesktop')) {
            Assert-PlainPath $paths[$name]
            Assert-Absent $paths[$name]
        }
        foreach ($name in @('service', 'eventLog', 'staleSource', 'userMarker')) { Assert-Absent $paths[$name] }
        $before = Get-HostState $paths $msi.identity
        $receipt.checkpoints.before = $before
        Assert-VacantHost $before
        $attempted = $true
        Invoke-ReleaseMsi '/i' $package (Join-Path $evidence 'install.log') $receipt.operations $msi.identity
        $state = Get-HostState $paths $msi.identity
        $receipt.checkpoints.installed = $state
        Assert-InstalledState $state $paths $msi.identity
        $state.packageCode = Get-InstalledPackageCode $msi.identity
        Assert-InteropProfile $paths.profile $Profile $Marker $ConfigSha256 $work -Upload:$Upload
        $payload = Get-VerifiedPayload $paths.bin $msi.layout $expected
        Write-Record (Join-Path $evidence 'payload-installed.json') $payload
        $native = [ordered]@{}
        foreach ($name in @('ImmichFolderWatch.exe', 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll', 'e_sqlite3.dll')) {
            $native[$name] = Get-PeMachine (Join-Path $paths.bin $name)
            if ($native[$name] -ne $expected.machine) { throw "Unexpected PE machine in installed '$name'." }
        }
        # Hold the hashed apphost against writes or deletion until the observed secondary exits.
        $image = [IO.File]::OpenRead($paths.exe)
        try {
            $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($image)).ToLowerInvariant()
            if ($digest -cne $payload.entries.AppExecutableFile.sha256) { throw 'The installed executable changed.' }
            $installed = [ordered]@{ format = 'ifw-installed-msi-interop-v1'; target = $Target; sourceCommit = $env:GITHUB_SHA
                workflowRun = $env:GITHUB_RUN_ID; releaseCommit = $release.commit; package = $asset; identity = $msi.identity
                exe = $paths.exe; exeSha256 = $digest; peMachine = $native; payloadSha256 = $payload.sha256
                configSha256 = $ConfigSha256; state = $state }
            if ($WpfPrimary -or $Upload) {
                $installLog = Join-Path $evidence 'install.log'
                $installed.installTransaction = [ordered]@{ operation = $receipt.operations[0]; nativePath = $installLog
                    sha256 = Get-FileDigest $installLog }
            }
            Write-Record (Join-Path $evidence 'installed.json') $installed
            $observer = if ($Upload) { 'upload/observe.py' } elseif ($WpfPrimary) { 'reverse/observe.py' } else { 'observe.py' }
            & $Python -B (Join-Path $PSScriptRoot $observer) $Target $evidence $work $paths.exe
            if ($LASTEXITCODE -ne 0) { throw "The installed WPF observation returned $LASTEXITCODE." }
        }
        finally { $image.Dispose() }
        $outputs = @()
        if ($WpfPrimary -or $Upload) {
            . (Join-Path $PSScriptRoot 'reverse/profile.ps1')
            $outputs = @(Get-ReverseProfileEntries $Profile $evidence -Upload:$Upload)
        }
        Assert-InteropProfile $paths.profile $Profile $Marker $ConfigSha256 $work $outputs -Upload:$Upload
        if ((Get-FileDigest $package) -cne $asset.sha256) { throw 'The release MSI changed during observation.' }
    }
    catch { $receipt.error = $_.Exception.Message }
    finally {
        if ($attempted) {
            try { Complete-InteropRemoval $paths $msi.identity $evidence $receipt }
            catch { $receipt.cleanup.error = $_.Exception.Message }
        }
        if (-not $receipt.Contains('error') -and -not $receipt.cleanup.Contains('error')) { $receipt.status = 'passed' }
        Write-Record (Join-Path $evidence 'msi-result.json') $receipt
    }
    if ($receipt.status -ne 'passed') { throw (@($receipt['error'], $receipt.cleanup['error']) -ne $null -join [Environment]::NewLine) }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-MsiInterop @interopArguments }
