param([Parameter(Mandatory)][string]$Disc)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if ($env:COMPUTERNAME -cne 'IFW-QA25' -or -not $principal.IsInRole('Administrator') -or
    -not (Get-CimInstance Win32_ComputerSystem).HypervisorPresent -or
    ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($Disc))).DriveType -ne 'CDRom') {
    throw 'Use the private x64 test VM, its elevated local account and read-only DVD.'
}
$marker = 'C:\Program Files\IFW-QA-CrossSession'
$area = Join-Path $marker 'transaction'
$observer = 'C:\Users\ifw-test\AppData\Local\IFW-MsiSessions\trial-transaction-01'
$original = '{50554B02-DB63-4388-A959-8F0B25856F5A}'
$successor = '{C09DB689-221F-4AE3-8C72-2D5B5C92DD82}'
$stock = 'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe'
$stockHash = 'b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675'
$endpointHash = '34a148bb978c325e9315f9ca21d4861fd9131e917137303b358320eb39ee6b9f'
$candidate = Join-Path $area 'trial.msi'
$msi = Join-Path $Disc 'shipping.msi'
$trial = 'C:\Program Files\IFW Cutover QA\msi-session-endpoint.exe'
$registry = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
$sid = ([Security.Principal.NTAccount]::new($env:COMPUTERNAME, 'ifw-test')).Translate([Security.Principal.SecurityIdentifier]).Value
if ([IO.File]::ReadAllText("$marker\marker.txt") -cne "IFW disposable installed MSI session test`n$sid`n" -or
    (Get-FileHash $msi).Hash -ine '419938c3fec0c113bf0f33dbf1a9bd4a6748df1e7930acb20fec5fc3f265a187' -or
    (Get-FileHash "$Disc\wix.nupkg").Hash -ine 'bbb8627d4914333b6b4b91e6d1fc94eea96e28349968550248d8da95cfe80ca0' -or
    (Get-FileHash "$Disc\endpoint.zip").Hash -ine '0f19d7e208bb84aa0aa9839da944cafc0cdf17ea91a3e47bae222af4bdf4b634' -or
    (Test-Path $area) -or (Test-Path "$registry\$successor")) {throw 'Expected the original, fresh synthetic installation.'}
[void](New-Item -Type Directory $area)

function Wait-ForObserver([string]$Phase) {
    $deadline = [DateTime]::UtcNow.AddMinutes(7)
    while (!(Test-Path "$observer\$Phase.ok")) {
        if ([DateTime]::UtcNow -gt $deadline) {throw "RDP observer timed out at $Phase"}
        Start-Sleep -Milliseconds 250
    }
}
function Check-Stage([string]$Phase, [bool]$InstalledStock) {
    $legacyProcesses = @(Get-Process -Name ImmichFolderWatch -ErrorAction SilentlyContinue)
    if ($legacyProcesses.Count -ne 0 -or (Test-Path $stock) -ne $InstalledStock -or
        (Test-Path "$registry\$original") -ne $InstalledStock -or (Test-Path $trial) -eq $InstalledStock -or
        (Test-Path "$registry\$successor") -eq $InstalledStock) {throw "Unexpected registration, executable or running WPF at $Phase"}
    $shortcuts = @()
    foreach ($path in @('C:\Users\Public\Desktop', 'C:\Users\ifw-test\Desktop', "$env:USERPROFILE\Desktop")) {
        $link = Join-Path $path 'Immich Folder Watch.lnk'
        if (Test-Path $link) {
            $target = (New-Object -ComObject WScript.Shell).CreateShortcut($link).TargetPath
            if ($target -ine $stock) {throw "Unexpected original desktop target at $Phase"}
            $shortcuts += $link
        }
    }
    if (($shortcuts.Count -gt 0) -ne $InstalledStock) {throw "Unexpected registered desktop launch path at $Phase"}
    $package = if ($InstalledStock) {$original} else {$successor}
    $image = if ($InstalledStock) {$stock} else {$trial}
    $expectedHash = if ($InstalledStock) {$stockHash} else {$endpointHash}
    $hash = (Get-FileHash $image).Hash
    if ($hash -ine $expectedHash) {throw "Unexpected installed payload at $Phase"}
    [ordered]@{phase=$Phase; product=$package; version=(Get-ItemProperty "$registry\$package").DisplayVersion
        image=$image; sha256=$hash; shortcuts=$shortcuts; runningWpf=$legacyProcesses.Count} |
        ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 "$area\$Phase.json"
}
function Invoke-TrialMsi([string]$Phase, [int]$Expected, [string[]]$Options) {
    if (@(Get-Process -Name ImmichFolderWatch -ErrorAction SilentlyContinue).Count) {throw 'Drain WPF in all sessions before this trial.'}
    $log = Join-Path $area "$Phase.log"
    $arguments = @($Options) + @('/qn','/norestart','/l*v',"`"$log`"")
    $p = Start-Process msiexec.exe -PassThru -ArgumentList $arguments
    if (!$p.WaitForExit(90000)) {throw "Windows Installer timed out at $Phase"}
    if ($p.ExitCode -ne $Expected) {throw "Unexpected Windows Installer exit $($p.ExitCode) at $Phase"}
    return $p.ExitCode
}
try {
    Copy-Item "$marker\install.log" "$area\original-install.log"
    Copy-Item "$marker\installed.json" "$area\original-install.json"
    Push-Location $area
    try {
        & tar.exe -xf "$Disc\wix.nupkg" tools/net472/x64
        if ($LASTEXITCODE) {throw 'Could not extract WiX'}
        & tar.exe -xf "$Disc\endpoint.zip" msi-session-endpoint.exe
        if ($LASTEXITCODE -or (Get-FileHash .\msi-session-endpoint.exe).Hash -ine $endpointHash) {throw 'Invalid native endpoint'}
        & .\tools\net472\x64\wix.exe build -arch x64 -d "Endpoint=$area\msi-session-endpoint.exe" "$Disc\Cutover.wxs" -o $candidate *> "$area\compiler.log"
        if ($LASTEXITCODE -or !(Test-Path $candidate)) {throw 'Private successor MSI failed to compile'}
    } finally {Pop-Location}
    $admin = [ordered]@{candidateSha256=(Get-FileHash $candidate).Hash; compilerSha256=(Get-FileHash "$Disc\wix.nupkg").Hash
                        wixSourceSha256=(Get-FileHash "$Disc\Cutover.wxs").Hash; exits=[ordered]@{}}
    Wait-ForObserver 'baseline'
    Check-Stage 'baseline' $true
    $admin.exits.failedUpgrade = Invoke-TrialMsi 'failed-upgrade' 1603 @('/i',"`"$candidate`"",'IFW_CUTOVER_TEST=1','IFW_ROLLBACK=1')
    Check-Stage 'rolled-back' $true
    [IO.File]::WriteAllText("$area\rolled-back.ready",'')
    Wait-ForObserver 'rolled-back'
    $admin.exits.upgrade = Invoke-TrialMsi 'upgrade' 0 @('/i',"`"$candidate`"",'IFW_CUTOVER_TEST=1')
    Check-Stage 'committed' $false
    [IO.File]::WriteAllText("$area\committed.ready",'')
    Wait-ForObserver 'committed'
    $admin.exits.removeTrial = Invoke-TrialMsi 'remove-trial' 0 @('/x',$successor)
    $admin.exits.reinstallOriginal = Invoke-TrialMsi 'reinstall-original' 0 @('/i',"`"$msi`"")
    Check-Stage 'restored' $true
    $admin | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "$area\admin.json"
    [IO.File]::WriteAllText("$area\restored.ready",'')
} catch {
    $_ | Out-String | Set-Content -Encoding UTF8 "$area\failure.log"
    throw
}
