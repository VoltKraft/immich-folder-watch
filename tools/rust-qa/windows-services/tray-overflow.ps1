# Use the accessibility provider of the disposable session's existing Explorer taskbar.
function Get-IfwShellOwner([IntPtr]$Window) {
    if ($Window -eq [IntPtr]::Zero) { return 0 }
    [uint32]$ownerId = 0
    if (-not [IfwSyntheticShellObserver]::GetWindowThreadProcessId($Window, [ref]$ownerId)) { return 0 }
    $owner = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
    if ($null -eq $owner -or $owner.ProcessName -ine 'explorer' -or
        $owner.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId) { return 0 }
    return $ownerId
}

function Get-IfwOverflowWindow([uint32]$ExplorerId) {
    foreach ($class in @('NotifyIconOverflowWindow', 'TopLevelWindowForOverflowXamlIsland')) {
        $window = [IfwSyntheticShellObserver]::FindWindow($class, $null)
        if ($window -ne [IntPtr]::Zero -and [IfwSyntheticShellObserver]::IsWindowVisible($window) -and
            (Get-IfwShellOwner $window) -eq $ExplorerId) { return $window }
    }
    return [IntPtr]::Zero
}

function Open-IfwTrayOverflow($Record, [scriptblock]$BeforeChange = $null, [scriptblock]$BeforeAction = $null, [hashtable]$Selection = $null,
                            [switch]$SelectVisibleButton) {
    if ($SelectVisibleButton -and ($null -eq $BeforeChange -or $null -eq $BeforeAction)) {
        throw 'Visible-button selection requires both native taskbar and physical button checks'
    }
    # An interested caller retains only the checks made during this lookup of the four known names.
    if ($null -eq $Selection) { $Selection = @{} }
    $Selection.gate = 'taskbar-owner'
    $Selection.names = @()
    $bar = [IfwSyntheticShellObserver]::FindWindow('Shell_TrayWnd', $null)
    $explorer = Get-IfwShellOwner $bar
    $Selection.bar = $bar.ToInt64()
    $Selection.pid = $explorer
    if (-not $explorer) { return }
    if ($Selection.ContainsKey('expectedBar') -and
        ($Selection.bar -ne $Selection.expectedBar -or $explorer -ne $Selection.expectedPid)) {
        $Selection.gate = 'different-original-taskbar'
        return
    }
    $Selection.gate = 'taskbar-visible'
    if (-not [IfwSyntheticShellObserver]::IsWindowVisible($bar)) { return }
    $Selection.gate = 'overflow-already-visible'
    if ((Get-IfwOverflowWindow $explorer) -ne [IntPtr]::Zero) {
        $Record.overflow = 'already visible'
        return
    }
    $Selection.gate = 'known-name-selection'
    $root = [Windows.Automation.AutomationElement]::FromHandle($bar)
    $names = @('Show hidden icons', 'Show hidden icons.', 'Ausgeblendete Symbole einblenden', 'Ausgeblendete Symbole anzeigen')
    foreach ($name in $names) {
        $named = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty, $name)
        $elements = $root.FindAll([Windows.Automation.TreeScope]::Descendants, $named)
        $check = @{ name = $name; count = $elements.Count }
        $Selection.names += $check
        if (-not $SelectVisibleButton -and $elements.Count -ne 1) { continue }
        $visible = @(
            foreach ($element in $elements) {
                $current = $element.Current
                if ($current.ProcessId -ne $explorer) { $check.rejected = 'foreign-process'; continue }
                if ($current.IsOffscreen) { $check.rejected = 'offscreen'; continue }
                if (-not $current.IsEnabled) { $check.rejected = 'disabled'; continue }
                $type = $current.ControlType
                if ($type -ne [Windows.Automation.ControlType]::Button) { $check.rejected = 'not-button'; $check.controlType = $type.Id; continue }
                $element
            }
        )
        if ($SelectVisibleButton) { $check.visibleButtons = $visible.Count }
        if ($visible.Count -ne 1) { continue }
        $button = $visible[0]
        $provider = $null
        if ($button.TryGetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$provider)) {
            $state = $provider.Current.ExpandCollapseState
            if ($state -ne [Windows.Automation.ExpandCollapseState]::Collapsed) { $check.rejected = 'expand-state'; $check.state = [string]$state; return }
            $action = @{ method = 'Expand'; provider = $provider }
        } elseif ($button.TryGetCurrentPattern([Windows.Automation.TogglePattern]::Pattern, [ref]$provider)) {
            $state = $provider.Current.ToggleState
            if ($state -ne [Windows.Automation.ToggleState]::Off) { $check.rejected = 'toggle-state'; $check.state = [string]$state; return }
            $action = @{ method = 'Toggle'; provider = $provider }
        } elseif ($button.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$provider)) {
            $action = @{ method = 'Invoke'; provider = $provider }
        } else { $check.rejected = 'no-supported-pattern'; continue }
        $check.method = $action.method
        $Selection.gate = 'taskbar-owner-recheck'
        if ((Get-IfwShellOwner $bar) -ne $explorer) { return }
        $Selection.gate = 'overflow-visible-at-recheck'
        if ((Get-IfwOverflowWindow $explorer) -ne [IntPtr]::Zero) { return }
        $Selection.gate = 'before-change'
        if ($null -ne $BeforeChange -and -not (& $BeforeChange $bar $explorer)) { return }
        $state = @{ bar = $bar; explorer = $explorer; button = $button; action = $action; names = $names }
        $Selection.gate = 'before-action'
        if ($null -ne $BeforeAction -and -not (& $BeforeAction $state)) { return }
        $Selection.gate = 'requested'
        $Record.overflow = 'requested'
        $Record.overflowProvider = $action.method
        if ($action.method -eq 'Expand') { $action.provider.Expand() }
        elseif ($action.method -eq 'Toggle') { $action.provider.Toggle() }
        else { $action.provider.Invoke() }
        return $state
    }
}

function Restore-IfwTrayOverflow($State, $Record, [scriptblock]$BeforeChange = $null, [scriptblock]$BeforeClose = $null) {
    if ($null -eq $State) { return }
    $action = $State.action
    if ((Get-IfwShellOwner $State.bar) -ne $State.explorer -or $State.button.Current.ProcessId -ne $State.explorer) {
        throw 'Explorer changed while observing the temporary flyout'
    }
    if ($null -ne $BeforeChange -and -not (& $BeforeChange $State.bar $State.explorer)) {
        throw 'The private desktop or its pinned shell changed before flyout cleanup'
    }
    $open = (Get-IfwOverflowWindow $State.explorer) -ne [IntPtr]::Zero
    $shouldClose = switch ($action.method) {
        'Expand' { $action.provider.Current.ExpandCollapseState -eq [Windows.Automation.ExpandCollapseState]::Expanded }
        'Toggle' { $action.provider.Current.ToggleState -eq [Windows.Automation.ToggleState]::On }
        'Invoke' { $open }
    }
    if ($shouldClose) {
        # The icon action may have dismissed its flyout since the compatibility visibility lookup.
        if ($null -ne $BeforeClose -and -not (& $BeforeClose $State.bar $State.explorer)) { return }
        switch ($action.method) {
            'Expand' { $action.provider.Collapse() }
            'Toggle' { $action.provider.Toggle() }
            'Invoke' { $action.provider.Invoke() }
        }
    }
    $until = [DateTime]::UtcNow.AddSeconds(3)
    do {
        if ($null -ne $BeforeChange -and -not (& $BeforeChange $State.bar $State.explorer)) {
            throw 'The private Explorer changed before its flyout closure could be verified'
        }
        if ((Get-IfwOverflowWindow $State.explorer) -eq [IntPtr]::Zero) {
            $Record.overflowClosed = $true
            return
        }
        Start-Sleep -Milliseconds 80
    } while ([DateTime]::UtcNow -lt $until)
    throw 'The temporary Explorer flyout remained visible'
}
