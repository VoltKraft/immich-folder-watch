param([int]$ProcessId, [Int64]$Created, [Int64]$Hwnd, [string]$Work)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$area = Join-Path $Work 'rust-return'
$app = 'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe'
if ($env:COMPUTERNAME -cne 'IFW-QA25' -or $env:USERNAME -cne 'ifw-test' -or
    [IO.Path]::GetFullPath($Work) -ine 'C:\Users\ifw-test\AppData\Local\IFW-MsiSessions\trial-transaction-01' -or
    !(Test-Path "$area\prepared.json" -PathType Leaf) -or
    (Get-FileHash $app).Hash -ine 'b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675') {
    throw 'Expected the private profile and installed 3.0.4 application.'
}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')
$strings = @{}
$xml = [Xml.XmlDocument]::new()
$xml.Load((Join-Path $repo 'src\ImmichFolderWatch.App.Shared\Resources\Strings.de.resx'))
foreach ($node in $xml.DocumentElement.data) { $strings[$node.name] = [string]$node.value }
function BoundRoot {
    $process = Get-Process -Id $ProcessId
    if ($process.Path -ine $app -or $process.StartTime.ToFileTimeUtc() -ne $Created -or
        $process.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) {throw 'Original WPF identity changed'}
    $root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
    if ($root.Current.NativeWindowHandle -ne $Hwnd -or $root.Current.ProcessId -ne $ProcessId -or
        $root.Current.Name -cne 'Immich Folder Watch' -or $root.Current.IsOffscreen) {throw 'Original WPF window changed'}
    return $root
}
function FindOwned($type, $label) {
    $end = [DateTime]::UtcNow.AddSeconds(6)
    do {
        $condition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,$type)
        $found = @((BoundRoot).FindAll([Windows.Automation.TreeScope]::Descendants,$condition) | Where-Object {
            $_.Current.ProcessId -eq $ProcessId -and $_.Current.Name -ceq $label -and $_.Current.IsEnabled -and !$_.Current.IsOffscreen
        })
        if ($found.Count -gt 1) {throw "Ambiguous owned control: $label"}
        if ($found.Count -eq 1) {return $found[0]}
        Start-Sleep -Milliseconds 120
    } while ([DateTime]::UtcNow -lt $end)
    throw "Missing visible owned control: $label"
}
function SelectOwned($item) {
    if ($item.Current.ProcessId -ne $ProcessId -or $item.Current.IsOffscreen) {throw 'Selection owner changed'}
    $item.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
}
$record = [ordered]@{pid=$ProcessId;created=$Created;hwnd=$Hwnd;session=[Diagnostics.Process]::GetCurrentProcess().SessionId
    image=$app;status='started';sourceSha256=(Get-FileHash $PSCommandPath).Hash.ToLowerInvariant()}
try {
    SelectOwned (FindOwned ([Windows.Automation.ControlType]::ListItem) $strings['UI_Folders'])
    $list = FindOwned ([Windows.Automation.ControlType]::List) $strings['UI_WatchSources']
    $condition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,[Windows.Automation.ControlType]::ListItem)
    $entries = @($list.FindAll([Windows.Automation.TreeScope]::Children,$condition))
    $record.sourceCount = $entries.Count
    if ($entries.Count -ne 1) {throw 'Expected one source in the returned configuration'}
    SelectOwned $entries[0]
    SelectOwned (FindOwned ([Windows.Automation.ControlType]::TabItem) $strings['UI_General'])
    $field = FindOwned ([Windows.Automation.ControlType]::Edit) $strings['UI_ImmichAlbumName']
    $record.label = $field.Current.Name
    $record.runtimeId = @($field.GetRuntimeId())
    $record.fieldPid = $field.Current.ProcessId
    $record.album = $field.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).Current.Value
    $record.windowName = (BoundRoot).Current.Name
    if ($record.album -cne 'Rust – Grüße 日本語 😀: # null') {throw 'Installed WPF returned a different album'}
    $record.status = 'read'
} catch {
    $record.error = $_.Exception.Message
    throw
} finally {
    [IO.File]::WriteAllText((Join-Path $area 'uia.json'),($record | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
