param(
    [Parameter(Mandatory)][string]$ProfilePath,
    [Parameter(Mandatory)][string]$Binary,
    [Parameter(Mandatory)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_ACTIONS -cne 'true' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') {
    throw 'A disposable Windows rewrite runner is required.'
}
$profileDir = Get-Item -LiteralPath $ProfilePath
if ($profileDir.Parent.FullName -ine (Get-Item -LiteralPath $env:RUNNER_TEMP).FullName -or
    $profileDir.Name -notmatch '^ifw-logs-[a-zA-Z0-9_]+$') { throw 'Expected a new private runner test directory.' }
$nonce = [IO.File]::ReadAllText((Join-Path $profileDir.FullName '.ifw-native-log')).TrimEnd()
if ($nonce -cnotmatch '^[0-9a-f]{32}$') { throw 'Invalid synthetic log identifier.' }
$logName = "Q$nonce"
$source = "IfwQaLog$nonce"
$registryLog = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\$logName"
$registrySource = "$registryLog\$source"
$report = [ordered]@{ log=$logName; source=$source; passed=$false; removed=$false }
$created = $false
$reader = $null

function Invoke-Subject([string]$Mode) {
    & $Binary $Mode $nonce
    if ($LASTEXITCODE -ne 0) { throw "Native $Mode observer exited $LASTEXITCODE." }
}

try {
    if ((Test-Path -LiteralPath $registryLog) -or [Diagnostics.EventLog]::Exists($logName) -or
        [Diagnostics.EventLog]::SourceExists($source)) { throw 'The private log or source already exists.' }
    $resourceDir = New-Item -Path (Join-Path $profileDir.FullName 'resource') -ItemType Directory
    $mc = Join-Path $resourceDir.FullName 'Messages.mc'
    $sourceText = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Messages.mc'))
    $crlf = [string][char]13 + [char]10
    [IO.File]::WriteAllText($mc, $sourceText.Replace($crlf, [string][char]10).Replace([string][char]10, $crlf),
                           [Text.Encoding]::ASCII)
    $dll = Join-Path $resourceDir.FullName 'Messages.dll'
    Push-Location $resourceDir.FullName
    try {
        & mc.exe -a -h . -r . Messages.mc
        if ($LASTEXITCODE) { throw 'Windows SDK message compilation failed.' }
        & rc.exe /nologo /fo Messages.res Messages.rc
        if ($LASTEXITCODE) { throw 'Windows SDK resource compilation failed.' }
        $arch = switch ($env:RUNNER_ARCH) { 'X64' { 'X64' }; 'ARM64' { 'ARM64' }; default { throw 'Unsupported host.' } }
        & link.exe /nologo /dll /noentry /nodefaultlib "/machine:$arch" /out:Messages.dll Messages.res
        if ($LASTEXITCODE) { throw 'Native message resource linking failed.' }
    } finally { Pop-Location }
    $pe = [IO.File]::ReadAllBytes($dll)
    $offset = [BitConverter]::ToInt32($pe, 60)
    $machine = [BitConverter]::ToUInt16($pe, $offset + 4)
    $entry = [BitConverter]::ToUInt32($pe, $offset + 40)
    if ([BitConverter]::ToUInt32($pe, $offset) -ne 0x4550 -or $entry -ne 0 -or
        ($machine -ne @{ X64=0x8664; ARM64=0xaa64 }[$arch])) { throw 'Expected one native resource-only DLL.' }
    $report.messageDll = @{ machine=$arch; entryPoint=$entry; sha256=(Get-FileHash -LiteralPath $dll).Hash }

    $registration = [Diagnostics.EventSourceCreationData]::new($source, $logName)
    $registration.MessageResourceFile = $dll
    [Diagnostics.EventLog]::CreateEventSource($registration)
    $created = $true
    if ((Get-ItemPropertyValue -LiteralPath $registrySource -Name EventMessageFile) -ine $dll -or
        [Diagnostics.EventLog]::LogNameFromSourceName($source, '.') -ine $logName) {
        throw 'The runtime source does not resolve to its registered log and message resource.'
    }
    Invoke-Subject 'missing'
    Invoke-Subject 'mismatch'
    $report.refusedMissingAndWrongLog = $true
    Invoke-Subject 'event'
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        if ($null -ne $reader) { $reader.Dispose() }
        $reader = [Diagnostics.EventLog]::new($logName)
        $rows = @($reader.Entries | Where-Object { $_.Source -ceq $source } | Sort-Object Index)
        if ($rows.Count -ge 6) { break }
        Start-Sleep -Milliseconds 120
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($rows.Count -ne 6) { throw "Expected six native events, found $($rows.Count)." }
    $types = @('Information', 'Information', 'Information', 'Warning', 'Error', 'Error')
    $report.events = @()
    for ($i=0; $i -lt $rows.Count; $i++) {
        $row = $rows[$i]
        $prefix = "Category: Desktop.Fixture$($crlf)EventId: $($i + 100)$($crlf)$crlf"
        $expected = $prefix + "Grüße 二 $nonce $i" + [char]10 + "Fortsetzung"
        if ($row.InstanceId -ne 1 -or $row.EntryType.ToString() -cne $types[$i] -or
            $row.ReplacementStrings.Count -ne 1 -or $row.ReplacementStrings[0] -cne ($expected + $crlf) -or
            $row.Message.TrimEnd([char[]]$crlf) -cne $expected) { throw "Windows event $i differs." }
        $report.events += @{ index=$row.Index; id=$row.InstanceId; type=$row.EntryType.ToString(); formatted=$true }
    }
    $report.recordsMatched = $true
} finally {
    if ($null -ne $reader) { $reader.Dispose() }
    try {
        if ($created) {
            if ((Get-ItemPropertyValue -LiteralPath $registrySource -Name EventMessageFile) -ine $dll -or
                [Diagnostics.EventLog]::LogNameFromSourceName($source, '.') -ine $logName) {
                throw 'The private event source changed before cleanup.'
            }
            [Diagnostics.EventLog]::Delete($logName)
            $report.removed = -not (Test-Path -LiteralPath $registryLog)
            if (-not $report.removed) { throw 'Private log removal did not complete.' }
        }
        $report.passed = $report.recordsMatched -eq $true -and $report.removed
    } finally {
        [IO.File]::WriteAllText($OutputFile, ($report | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    }
}
