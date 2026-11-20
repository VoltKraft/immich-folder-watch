param(
    [Parameter(Mandatory)]
    [ValidateSet('x86_64-pc-windows-msvc', 'aarch64-pc-windows-msvc')]
    [string] $Target,
    [switch] $IsolatedVm
)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or (-not $IsolatedVm -and $env:RUNNER_ENVIRONMENT -ne 'github-hosted')) {
    throw 'A disposable Windows VM is required for the loopback SMB fixture.'
}
if ($env:IFW_RUST_SMB_FIXTURE) { throw 'An existing SMB fixture is already selected.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$evidence = Join-Path $repo "artifacts/rust/feasibility/$Target/smb"
New-Item -ItemType Directory -Path $evidence | Out-Null
$oldTemp = $env:RUNNER_TEMP
if (-not $env:RUNNER_TEMP) { $env:RUNNER_TEMP = [IO.Path]::GetTempPath() }
$oldCargo = $env:CARGO_TARGET_DIR
$oldHome = $env:CARGO_HOME
$env:CARGO_TARGET_DIR = Join-Path $repo "artifacts/rust/build/$Target"
$env:CARGO_HOME = Join-Path $repo 'artifacts/rust/cargo-home'
$id = [Guid]::NewGuid().ToString('N')
$folder = "IfwRustQa$id"
$name = $folder + '$'
$backing = Join-Path $env:RUNNER_TEMP $folder
$unc = "\\localhost\$name"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$record = [ordered]@{
    source = (git -C $repo rev-parse HEAD)
    target = $Target
    method = 'SMB loopback via ephemeral per-user share'
    status = 'failed'
}
$ownedFolder = $false
$ownedShare = $false
$opened = $null
try {
    python (Join-Path $PSScriptRoot 'check-toolchain.py') $Target
    if ($LASTEXITCODE -ne 0) { throw 'Native compiler identity check failed.' }
    New-Item -ItemType Directory -Path $backing | Out-Null
    $ownedFolder = $true
    $share = New-SmbShare -Name $name -Path $backing -FullAccess $identity.Name -Temporary `
        -EncryptData $true -CachingMode None -FolderEnumerationMode AccessBased
    $ownedShare = $true
    $access = @(Get-SmbShareAccess -Name $name)
    if ($access.Count -ne 1 -or $access[0].AccessRight -ne 'Full' -or
        $access[0].AccessControlType -ne 'Allow' -or $share.Path -ne $backing -or -not $share.EncryptData) {
        throw 'The empty share does not have the required path, encryption and single-account grant.'
    }
    $granted = [Security.Principal.NTAccount]::new($access[0].AccountName)
    if ($granted.Translate([Security.Principal.SecurityIdentifier]).Value -ne $identity.User.Value) {
        throw 'The share grant did not resolve to the fixture owner.'
    }
    $marker = [Text.Encoding]::ASCII.GetBytes("ifw-synthetic-$id")
    [IO.File]::WriteAllBytes((Join-Path $backing 'probe.txt'), $marker)
    $opened = [IO.File]::OpenRead((Join-Path $unc 'probe.txt'))
    $received = [byte[]]::new($marker.Length)
    $opened.ReadExactly($received, 0, $received.Length)
    if ([Convert]::ToHexString($received) -ne [Convert]::ToHexString($marker)) {
        throw 'The UNC reader did not reach the owned backing directory.'
    }
    $connections = @(Get-SmbConnection -ShareName $name)
    if ($connections.Count -eq 0 -or @($connections | Where-Object { -not $_.Encrypted }).Count -gt 0) {
        throw 'The expected encrypted SMB client connection was not observed.'
    }
    $record.dialects = @($connections | ForEach-Object { $_.Dialect.ToString() })
    $record.encrypted = $true
    $record.uncReadMatchedLocalBacking = $true
    $env:IFW_RUST_SMB_FIXTURE = $id
    $log = Join-Path $evidence 'tests.log'
    cargo test --manifest-path (Join-Path $repo 'rust/Cargo.toml') --frozen -p safe-fs -- --show-output 2>&1 |
        Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "Native SMB handle tests failed ($LASTEXITCODE)." }
    $markers = @(Select-String -LiteralPath $log -Pattern "^smb_fixture=$folder$")
    if ($markers.Count -eq 0) { throw 'The Rust tests did not exercise the selected UNC fixture.' }
    $record.syntheticRootsOpened = $markers.Count
    $record.status = 'passed'
} catch {
    $record.error = $_.Exception.Message
    throw
} finally {
    $env:IFW_RUST_SMB_FIXTURE = $null
    $env:CARGO_TARGET_DIR = $oldCargo
    $env:CARGO_HOME = $oldHome
    $env:RUNNER_TEMP = $oldTemp
    try {
        if ($opened) { $opened.Dispose() }
        if ($ownedShare) {
            $current = Get-SmbShare -Name $name
            if ($current.Path -ne $backing) { throw 'The owned share path changed during the test.' }
            Remove-SmbShare -Name $name -Force -Confirm:$false
            $record.shareRemoved = $true
        }
        if ($ownedFolder) {
            Remove-Item -LiteralPath $backing -Recurse -Force
            $record.scratchRemoved = $true
        }
    } catch {
        $record.status = 'failed'
        $record.cleanupError = $_.Exception.Message
        throw
    } finally {
        $record | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $evidence 'smb.json')
    }
}
