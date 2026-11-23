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

function Open-IfwTrayOverflow($Record, [scriptblock]$BeforeChange = $null, [scriptblock]$BeforeAction = $null) {
    $bar = [IfwSyntheticShellObserver]::FindWindow('Shell_TrayWnd', $null)
    $explorer = Get-IfwShellOwner $bar
    if (-not $explorer -or -not [IfwSyntheticShellObserver]::IsWindowVisible($bar)) { return }
    if ((Get-IfwOverflowWindow $explorer) -ne [IntPtr]::Zero) {
        $Record.overflow = 'already visible'
        return
    }
    $root = [Windows.Automation.AutomationElement]::FromHandle($bar)
    $names = @('Show hidden icons', 'Show hidden icons.', 'Ausgeblendete Symbole einblenden', 'Ausgeblendete Symbole anzeigen')
    foreach ($name in $names) {
        $named = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty, $name)
        $elements = $root.FindAll([Windows.Automation.TreeScope]::Descendants, $named)
        if ($elements.Count -ne 1) { continue }
        $button = $elements[0]
        if ($button.Current.ProcessId -ne $explorer -or $button.Current.IsOffscreen -or
            -not $button.Current.IsEnabled -or $button.Current.ControlType -ne [Windows.Automation.ControlType]::Button) { continue }
        $provider = $null
        if ($button.TryGetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$provider)) {
            if ($provider.Current.ExpandCollapseState -ne [Windows.Automation.ExpandCollapseState]::Collapsed) { return }
            $action = @{ method = 'Expand'; provider = $provider }
        } elseif ($button.TryGetCurrentPattern([Windows.Automation.TogglePattern]::Pattern, [ref]$provider)) {
            if ($provider.Current.ToggleState -ne [Windows.Automation.ToggleState]::Off) { return }
            $action = @{ method = 'Toggle'; provider = $provider }
        } elseif ($button.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$provider)) {
            $action = @{ method = 'Invoke'; provider = $provider }
        } else { continue }
        if ((Get-IfwShellOwner $bar) -ne $explorer -or (Get-IfwOverflowWindow $explorer) -ne [IntPtr]::Zero) { return }
        if ($null -ne $BeforeChange -and -not (& $BeforeChange $bar $explorer)) { return }
        $state = @{ bar = $bar; explorer = $explorer; button = $button; action = $action; names = $names }
        if ($null -ne $BeforeAction -and -not (& $BeforeAction $state)) { return }
        $Record.overflow = 'requested'
        $Record.overflowProvider = $action.method
        if ($action.method -eq 'Expand') { $action.provider.Expand() }
        elseif ($action.method -eq 'Toggle') { $action.provider.Toggle() }
        else { $action.provider.Invoke() }
        return $state
    }
}

function Restore-IfwTrayOverflow($State, $Record, [scriptblock]$BeforeChange = $null) {
    if ($null -eq $State) { return }
    $action = $State.action
    if ((Get-IfwShellOwner $State.bar) -ne $State.explorer -or $State.button.Current.ProcessId -ne $State.explorer) {
        throw 'Explorer changed while observing the temporary flyout'
    }
    if ($null -ne $BeforeChange -and -not (& $BeforeChange $State.bar $State.explorer)) {
        throw 'The private desktop or its pinned shell changed before flyout cleanup'
    }
    $open = (Get-IfwOverflowWindow $State.explorer) -ne [IntPtr]::Zero
    if ($action.method -eq 'Expand') {
        if ($action.provider.Current.ExpandCollapseState -eq [Windows.Automation.ExpandCollapseState]::Expanded) {
            $action.provider.Collapse()
        }
    } elseif ($action.method -eq 'Toggle') {
        if ($action.provider.Current.ToggleState -eq [Windows.Automation.ToggleState]::On) { $action.provider.Toggle() }
    } elseif ($open) {
        # The same Explorer provider closes the flyout. The icon action may already have closed it.
        $action.provider.Invoke()
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
