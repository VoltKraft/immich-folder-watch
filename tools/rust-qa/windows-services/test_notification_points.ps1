# Exercise the actual pixel selection used by the UIA observer without touching a desktop.
$ErrorActionPreference = 'Stop'
$errors = $null
$source = Join-Path $PSScriptRoot 'notification.ps1'
$ast = [Management.Automation.Language.Parser]::ParseFile($source,[ref]$null,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$definition = $ast.Find({param($node) $node -is [Management.Automation.Language.StringConstantExpressionAst] -and
    $node.Value.Contains('public static class IfwNoticeDesktop')},$true)
Add-Type -TypeDefinition $definition.Value
function Contains-Point($Rect,$Point) {
    return $Rect[0] -le $Point[0] -and $Point[0] -lt $Rect[2] -and $Rect[1] -le $Point[1] -and $Point[1] -lt $Rect[3]
}
foreach ($pair in @(
        @{a=@(-10.5,-4.5,1.2,-1.1); b=@(-2.2,-5.5,10,-1.1)},
        @{a=@(0,0,100,12); b=@(0,8,100,24)},
        @{a=@(0,0,10,10); b=@(10,0,20,10)})) {
    $a = [IfwNoticeDesktop]::LabelPoint($pair.a,$pair.b)
    $b = [IfwNoticeDesktop]::LabelPoint($pair.b,$pair.a)
    if (-not (Contains-Point $pair.a $a) -or (Contains-Point $pair.b $a) -or
        -not (Contains-Point $pair.b $b) -or (Contains-Point $pair.a $b)) {
        throw 'The two labels did not yield independently attributable physical pixels'
    }
}
$same = @(0,0,20,10)
$p = [IfwNoticeDesktop]::LabelPoint($same,$same)
if (-not (Contains-Point $same $p) -or $null -ne [IfwNoticeDesktop]::LabelPoint(@(0.1,0,0.9,4),$same)) {
    throw 'An inseparable or subpixel rectangle was not identified'
}
Write-Output 'Notification pixel selection passed.'

# Run the same polling loop against a temporary sender and a title/body match that exists for only one sweep.
$watch = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -ceq 'Watch-Notice'},$true)
. ([scriptblock]::Create($watch.Extent.Text))
$token = [Guid]::NewGuid().ToString('N')
$area = Join-Path ([IO.Path]::GetTempPath()) "ifw-notice-control-$token"
[void](New-Item -ItemType Directory -Path $area -ErrorAction Stop)
$goFile = Join-Path $area 'notice.go'
$sentFile = Join-Path $area 'notice.sent'
$finishFile = Join-Path $area 'notice.finish'
$receipts = [Collections.Generic.List[hashtable]]::new()
function Emit([hashtable]$Record) { $receipts.Add($Record) }
try {
    $state = @{calls=0}
    $reader = {
        $state.calls++
        $result = @{roots=2; match=$null; errors=0; lastHresult=$null}
        if ($state.calls -eq 1) { [IO.File]::WriteAllText($goFile,$token) }
        if ($state.calls -eq 2) { $result.match = @{qpc=[Diagnostics.Stopwatch]::GetTimestamp()} }
        if ($state.calls -eq 3) { [IO.File]::WriteAllText($sentFile,$token) }
        return $result
    }
    $status = Watch-Notice $area $token $reader
    $during = $receipts[1]
    $last = $receipts[$receipts.Count-2]
    $done = $receipts[$receipts.Count-1]
    if ($status -ne 0 -or $receipts[0].released -or $receipts[0].sent -or
        -not $during.released -or $during.sent -or $null -eq $during.match -or
        $during.match.qpc -lt $during.startQpc -or $during.match.qpc -gt $during.endQpc -or
        $receipts[2].sent -or -not $receipts[3].sent -or -not $done.complete -or $done.stage -cne 'visible' -or
        $done.samples -ne $state.calls -or $last.startQpc - $done.sentObservedQpc -lt 10L * [Diagnostics.Stopwatch]::Frequency) {
        throw 'The observer missed the in-flight match or stopped before ten full seconds of post-request sampling'
    }
    [IO.File]::Delete($goFile)
    [IO.File]::Delete($sentFile)
    $receipts.Clear()
    $status = Watch-Notice $area $token { @{roots=2; match=@{qpc=[Diagnostics.Stopwatch]::GetTimestamp()}; errors=0} }
    if ($status -ne 2 -or $receipts.Count -ne 2 -or $receipts[1].stage -cne 'unavailable' -or $receipts[1].complete) {
        throw 'A pair seen before release armed the observer'
    }
    [IO.File]::WriteAllText($finishFile,$token)
    $receipts.Clear()
    $status = Watch-Notice $area $token { throw 'A cancelled trial started a query' }
    if ($status -ne 2 -or $receipts.Count -ne 1 -or $receipts[0].complete) {
        throw 'An early sender exit was recorded as a full sampling interval'
    }
    Write-Output 'Notification timing controls passed.'
} finally {
    foreach ($file in @($goFile,$sentFile,$finishFile)) { [IO.File]::Delete($file) }
    [IO.Directory]::Delete($area)
}
