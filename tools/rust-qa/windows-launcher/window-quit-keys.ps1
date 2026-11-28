# Real keyboard traversal and activation on the live, owned fallback window.
function Invoke-KeyboardQuit($Root, $Button, [IntPtr]$Handle, [int]$Owner, $Report) {
    $qa = Split-Path $PSScriptRoot
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $qa 'observe-windows-input.ps1'), [ref]$null, [ref]$errors)
    $bridge = @($ast.FindAll({ param($a)
        $a -is [Management.Automation.Language.StringConstantExpressionAst] -and
        $a.StringConstantType -eq 'SingleQuotedHereString' -and $a.Value.Contains('public static class IfwObservedWindow {')
    }, $true))
    if ($errors -or $bridge.Count -ne 1) { throw 'The original native foreground bridge is missing.' }
    Add-Type -TypeDefinition ($bridge[0].Value + [Environment]::NewLine + [IO.File]::ReadAllText((Join-Path $qa 'windows-reader/Keyboard.cs')))

    function Read-OwnedName($State) {
        if ($State.Name) { return $State.Name }
        if ($null -ne $State.LabeledBy -and $State.LabeledBy.Current.ProcessId -eq $Owner) {
            return $State.LabeledBy.Current.Name
        }
        return ''
    }
    function Find-Control([string]$Name, $Type) {
        $typeCondition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty, $Type)
        $all = $Root.FindAll([Windows.Automation.TreeScope]::Descendants, $typeCondition)
        $found = @($all | Where-Object {
            $c = $_.Current
            $c.ProcessId -eq $Owner -and (Read-OwnedName $c) -ceq $Name
        })
        if ($found.Count -ne 1) { throw "Expected exactly one owned control named $Name." }
        return $found[0]
    }
    function Wait-Focused($Expected, [string]$Name) {
        $limit = [DateTime]::UtcNow.AddSeconds(5)
        do {
            $active = [Windows.Automation.AutomationElement]::FocusedElement
            if ($null -ne $active -and $Expected.Current.HasKeyboardFocus -and
                [Windows.Automation.Automation]::Compare($Expected, $active)) {
                $state = $Expected.Current
                $actualName = Read-OwnedName $state
                if ($state.ProcessId -ne $Owner -or !$state.IsEnabled -or $state.IsOffscreen -or
                    $actualName -cne $Name -or !$state.IsKeyboardFocusable -or $state.BoundingRectangle.IsEmpty) {
                    throw 'Focused control is unavailable or its name changed.'
                }
                $focus = [IfwQaReader.Keyboard]::Focus($Handle, $Owner)
                return [ordered]@{ name=$actualName; pid=$state.ProcessId; role=$state.ControlType.ProgrammaticName
                    foregroundHwnd=[IfwObservedWindow]::GetForegroundWindow().ToInt64()
                    nativeFocusHwnd=$focus.ToInt64(); runtimeId=@($Expected.GetRuntimeId())
                    hasKeyboardFocus=$state.HasKeyboardFocus; isPassword=$state.IsPassword }
            }
            Start-Sleep -Milliseconds 60
        } while ([DateTime]::UtcNow -lt $limit)
        throw "The expected control did not own keyboard focus: $Name."
    }

    $filename = Find-Control 'Dateiname' ([Windows.Automation.ControlType]::Edit)
    $password = Find-Control 'Kennwort' ([Windows.Automation.ControlType]::Edit)
    $language = Find-Control 'English' ([Windows.Automation.ControlType]::Button)
    $Report.focus = @()
    $Report.keys = @()
    $Report.buttonRuntimeId = @($Button.GetRuntimeId())
    # Establish the starting control only. Every subsequent focus move is a physical Tab.
    [void][IfwObservedWindow]::SetForegroundWindow($Handle)
    $filename.SetFocus()
    foreach ($item in @(
        @{name='Dateiname'; element=$filename; key='Tab'},
        @{name='Kennwort'; element=$password; key='Tab'},
        @{name='English'; element=$language; key='Tab'},
        @{name='Beenden'; element=$Button; key='Space'}
    )) {
        $Report.focus += Wait-Focused $item.element $item.name
        $sent = [IfwQaReader.Keyboard]::Press($Handle, $Owner, $item.key)
        $Report.keys += [ordered]@{key=$item.key; events=$sent}
    }
}
