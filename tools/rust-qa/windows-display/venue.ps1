$ErrorActionPreference = 'Stop'

function Get-ListenerClass($Rows, $Service) {
    if ($Rows.Count -eq 0) { return 'none' }
    if ($null -eq $Service -or $Service.State -ne 'Running' -or $Service.ProcessId -le 0) { return 'unavailable' }
    $classification = 'loopback-only'
    foreach ($row in $Rows) {
        if ($row.OwningProcess -ne $Service.ProcessId) { return 'unavailable' }
        $address = $null
        if (-not [Net.IPAddress]::TryParse($row.LocalAddress, [ref]$address)) { return 'unavailable' }
        if ($address.IsIPv4MappedToIPv6) { $address = $address.MapToIPv4() }
        if (-not [Net.IPAddress]::IsLoopback($address)) { $classification = 'other-or-any' }
    }
    return $classification
}

if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ARCH -cne 'ARM64' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') {
    throw 'Use the native hosted ARM64 rewrite job.'
}
$record = [ordered]@{ allowTSConnections = 'unavailable'; policySource = 'unavailable'
    termService = 'unavailable'; configuredPortListeners = 'unavailable' }
try {
    $settings = @(Get-WmiObject -Namespace 'root\CIMV2\TerminalServices' -Authentication PacketPrivacy -Query (
        'SELECT AllowTSConnections,PolicySourceAllowTSConnections FROM Win32_TerminalServiceSetting'))
    if ($settings.Count -eq 1) {
        if ($settings[0].AllowTSConnections -in @(0,1)) { $record.allowTSConnections = [bool]$settings[0].AllowTSConnections }
        if ($settings[0].PolicySourceAllowTSConnections -in @(0,1)) {
            $record.policySource = @('server','group-policy')[[int]$settings[0].PolicySourceAllowTSConnections]
        }
    }
} catch { }
$service = $null
try {
    $service = Get-CimInstance -Namespace 'root\CIMV2' -Query "SELECT State,ProcessId FROM Win32_Service WHERE Name='TermService'" -OperationTimeoutSec 10
    if ($service.State -in @('Stopped','Start Pending','Stop Pending','Running','Continue Pending','Pause Pending','Paused','Unknown')) {
        $record.termService = [string]$service.State
    }
} catch { }
try {
    $port = Get-ItemPropertyValue -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name PortNumber
    if (($port -is [int] -or $port -is [uint32]) -and $port -ge 1 -and $port -le 65535) {
        $query = "SELECT LocalAddress,OwningProcess FROM MSFT_NetTCPConnection WHERE LocalPort=$port AND State=2"
        $rows = @(Get-CimInstance -Namespace 'root\StandardCimv2' -Query $query -OperationTimeoutSec 10)
        $record.configuredPortListeners = Get-ListenerClass $rows $service
    }
} catch { }
$record | ConvertTo-Json -Compress
