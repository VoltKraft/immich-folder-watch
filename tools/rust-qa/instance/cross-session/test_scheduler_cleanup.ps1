# Portable replay of the owned task exiting during COM enumeration or stop.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scheduler_cleanup.ps1')
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public sealed class IfwRunningTestTask {
    public string Failure, InstanceGuid = "owned";
    public int Stops;
    internal void Check(string operation) {
        if (Failure == operation)
            throw new COMException("No running instance", unchecked((int)0x8004130B));
    }
    public void Stop() {
        Stops++;
        Check("stop");
        if (Failure == "denied")
            throw new COMException("Access denied", unchecked((int)0x80070005));
    }
}
public sealed class IfwTestInstances {
    public int Count;
    public IfwRunningTestTask Member;
    public IfwRunningTestTask Item(int index) {
        if (index != 1) throw new InvalidOperationException();
        Member.Check("item");
        return Member;
    }
}
public sealed class IfwRegisteredTestTask {
    public int Queries, Remaining;
    public IfwRunningTestTask Member = new IfwRunningTestTask();
    public IfwTestInstances GetInstances(int flags) {
        if (flags != 0) throw new InvalidOperationException();
        Queries++;
        return new IfwTestInstances {Count = Queries == 1 ? 1 : Remaining, Member = Member};
    }
}
'@

$cases = @(
    @('',       'owned', 0, $false, $false, 1),
    @('item',   'owned', 0, $false, $true,  0),
    @('stop',   'owned', 0, $false, $true,  1),
    @('stop',   'owned', 1, $true,  $null,  1),
    @('denied', 'owned', 0, $true,  $null,  1),
    @('',       'other', 0, $true,  $null,  0)
)
foreach ($case in $cases) {
    $operation, $expectedId, $remaining, $expectError, $expectedResult, $stops = $case
    $task = [IfwRegisteredTestTask]::new()
    $task.Remaining = $remaining
    $task.Member.Failure = $operation
    $expected = [pscustomobject]@{InstanceGuid=$expectedId}
    $failed = $false
    $result = $null
    try { $result = Stop-IfwOwnedTaskInstances $task $expected } catch { $failed = $true }
    if ($failed -ne $expectError -or $result -ne $expectedResult -or $task.Member.Stops -ne $stops) {
        throw "Unexpected private task cleanup for [$case]"
    }
}
Write-Output "$($cases.Count) owned scheduler cleanup controls passed."
