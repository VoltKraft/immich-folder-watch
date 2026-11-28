function Stop-IfwOwnedTaskInstances {
    param($Registered, $Running)

    $instances = $Registered.GetInstances(0)
    try {
        for ($index = $instances.Count; $index -gt 0; $index--) {
            $member = $instances.Item($index)
            if ($null -ne $Running -and $member.InstanceGuid -ne $Running.InstanceGuid) {
                throw 'An unexpected instance appeared under the private task name.'
            }
            [void]$member.Stop()
        }
    } catch {
        # The enumerated member may exit before its identity or Stop is read.
        # Accept SCHED_E_TASK_NOT_RUNNING only after a fresh empty enumeration.
        if ($_.Exception.GetBaseException().HResult -ne [int]0x8004130B -or
            $Registered.GetInstances(0).Count -ne 0) {
            throw
        }
        return $true
    }
    return $false
}
