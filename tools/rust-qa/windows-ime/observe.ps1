param(
    [Parameter(Mandatory=$true)][ValidateSet('inventory','compose')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [int]$SubjectId,
    [long]$WindowHandle,
    [string]$SubjectLog,
    [long]$SamplePipe
)
$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'Use the disposable native GUI launcher.' }
Add-Type -Path (Join-Path $PSScriptRoot 'Ime.cs')
. (Join-Path $PSScriptRoot 'language-list.ps1')
. (Join-Path $PSScriptRoot 'mode-sample.ps1')
$result = [ordered]@{ status='failed'; mode=$Mode }

function Save-Evidence {
    [IO.File]::WriteAllText($OutputFile, ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
}

function Get-Layouts {
    return @([IfwQaIme.Native]::Layouts() | ForEach-Object {
        [ordered]@{ hkl=$_.ToInt64(); language=($_.ToInt64() -band 65535)
            immIme=[IfwQaIme.Native]::ImmIsIME($_); immDescription=[IfwQaIme.Native]::Description($_) }
    })
}

if ($Mode -ceq 'inventory') {
    try {
        $result.layouts = @(Get-Layouts)
        try {
            $result.profiles = @([IfwQaIme.Native]::JapaneseProfiles() | ForEach-Object {
                [ordered]@{ type=$_.Type; language=$_.Language; clsid=$_.ClassId.ToString(); profile=$_.ProfileId.ToString()
                    category=$_.Category.ToString(); hkl=$_.Layout.ToInt64(); substitute=$_.Substitute.ToInt64()
                    enabled=(($_.Flags -band 2) -ne 0); activeForInventoryProcess=(($_.Flags -band 1) -ne 0) }
            })
            $result.enumeratedTsf = $true
        } catch {
            $result.enumeratedTsf = $false
            $result.tsfError = $_.Exception.GetBaseException().Message
        }
        try {
            $cap = @(Get-WindowsCapability -Online -Name 'Language.Basic~~~ja-JP~0.0.1.0')
            $result.japaneseBasicCapability = @($cap | ForEach-Object { [string]$_.State })
        } catch { $result.capabilityError = $_.Exception.GetBaseException().Message }
        try {
            $result.japaneseUserTips = @(foreach ($entry in (Get-IfwJapaneseLanguage (Get-WinUserLanguageList))) {
                $entry.InputMethodTips
            })
        } catch { $result.userTipsError = $_.Exception.GetBaseException().Message }
        $result.status = 'observed'
    } finally { Save-Evidence }
    return
}

function Wait-For([scriptblock]$Read, [string]$Name, [int]$Seconds=8, $Evidence=$null) {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    do {
        $value = & $Read
        if ($value) { return $value }
        Start-Sleep -Milliseconds 70
    } while ($clock.Elapsed.TotalSeconds -lt $Seconds)
    if ($null -ne $Evidence) {
        $Evidence.state = 'unavailable'
        throw "Timed out waiting for $Name. Last observation was $($Evidence.lastObservation)."
    }
    throw "Timed out waiting for $Name."
}

function Get-Label($Element) {
    if ($null -eq $Element) { return '' }
    if ($Element.Current.Name) { return $Element.Current.Name }
    $label = $Element.Current.LabeledBy
    if ($null -ne $label -and $label.Current.ProcessId -eq $SubjectId) { return $label.Current.Name }
    return ''
}

function Get-OwnedFilename {
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    if ($null -eq $root) { return }
    if ($root.Current.ProcessId -ne $SubjectId) { throw 'UIA root belongs to a different process.' }
    $condition = [Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Edit)
    $match = $null
    foreach ($el in $root.FindAll([Windows.Automation.TreeScope]::Descendants, $condition)) {
        if ($el.Current.ProcessId -eq $SubjectId -and (Get-Label $el) -ceq 'Dateiname' -and -not $el.Current.IsPassword) {
            if ($null -ne $match) { throw 'Multiple filename edits belong to the subject window.' }
            $match = $el
        }
    }
    return $match
}

function Test-OwnedFocus($Expected = $field) {
    if (-not [IfwObservedWindow]::OnInputDesktop() -or [IfwObservedWindow]::GetForegroundWindow() -ne $handle) { return $false }
    $el = [Windows.Automation.AutomationElement]::FocusedElement
    return ($null -ne $Expected -and $null -ne $el -and [Windows.Automation.Automation]::Compare($Expected, $el) -and
            $el.Current.ProcessId -eq $SubjectId -and $el.Current.IsEnabled -and $el.Current.HasKeyboardFocus -and -not $el.Current.IsPassword -and
            $el.Current.ControlType -eq [Windows.Automation.ControlType]::Edit -and (Get-Label $el) -ceq 'Dateiname')
}

function Get-Text($Element = $field) {
    $value = $null
    if ($Element.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$value)) { return [string]$value.Current.Value }
    $value = $Element.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern)
    return $value.DocumentRange.GetText(-1).TrimEnd("`r","`n")
}

function Test-SubjectLayout {
    return ([IfwQaIme.Native]::OwnedThread($handle, $SubjectId) -eq $threadId -and
            [IfwQaIme.Native]::GetKeyboardLayout($threadId) -eq $japanese)
}

function Read-LayoutFilename($Evidence) {
    $Evidence.attempts++
    if (-not (Test-SubjectLayout)) { $Evidence.lastObservation = 'subject-layout-changed'; return }
    try {
        $candidate = Get-OwnedFilename
        if ($null -eq $candidate) { $Evidence.lastObservation = 'filename-missing'; return }
        if (-not (Test-OwnedFocus $candidate)) { $Evidence.lastObservation = 'filename-unfocused'; return }
        $text = Get-Text $candidate
        if ($text -cne $expected) { $Evidence.lastObservation = 'unexpected-filename'; throw 'Unexpected initial synthetic filename.' }
        $Evidence.state = 'observed'
        $Evidence.lastObservation = 'focused-filename-read'
        return @{ element=$candidate; text=$text }
    } catch [Windows.Automation.ElementNotAvailableException] {
        $Evidence.lastObservation = 'element-became-unavailable'
    }
}

function Send-Key([string]$Name) {
    if (-not (Test-SubjectLayout)) { throw 'The original window thread no longer has the selected Japanese layout.' }
    if (-not (Test-OwnedFocus)) { throw 'The normal subject filename does not own foreground and keyboard focus.' }
    [IfwQaIme.Native]::SendFixtureKey($handle, $SubjectId, $Name)
}

function Get-Trace([long]$Offset) {
    $file = [IO.File]::Open($SubjectLog, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        [void]$file.Seek($Offset, [IO.SeekOrigin]::Begin)
        $reader = [IO.StreamReader]::new($file, [Text.Encoding]::UTF8)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $file.Dispose() }
}

function Set-OwnedLayout([IntPtr]$Layout) {
    if (-not [IfwObservedWindow]::OnInputDesktop()) { throw 'The input desktop changed.' }
    [IfwQaIme.Native]::RequestLayout($handle, $SubjectId, $Layout)
    [void](Wait-For { [IfwQaIme.Native]::GetKeyboardLayout($threadId) -eq $Layout } 'subject input locale')
}

$original = $null
$changed = $false
$sampleWriter = $null
try {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    # Compile the existing constrained ownership/click bridge without running its separate keyboard scenario.
    $shared = Join-Path (Split-Path $PSScriptRoot) 'observe-windows-input.ps1'
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($shared, [ref]$null, [ref]$parseErrors)
    $source = @($ast.FindAll({ param($node)
        $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
            $node.StringConstantType -eq 'SingleQuotedHereString' -and $node.Value.Contains('public static class IfwObservedWindow {')
    }, $true))
    if ($parseErrors -or $source.Count -ne 1) { throw 'The shared Windows ownership bridge could not be identified.' }
    Add-Type -TypeDefinition $source[0].Value
    $handle = [IntPtr]::new($WindowHandle)
    $threadId = [IfwQaIme.Native]::OwnedThread($handle, $SubjectId)
    if ($SamplePipe -ne 0) {
        $pipe = $null
        try {
            $pipe = [Microsoft.Win32.SafeHandles.SafeFileHandle]::new([IntPtr]::new($SamplePipe), $true)
            $sampleWriter = [IO.FileStream]::new($pipe, [IO.FileAccess]::Write, 1, $false)
        } catch {
            $result.samplePipeError = $_.Exception.GetBaseException().Message
            if ($null -ne $pipe) { $pipe.Dispose() }
        }
    }
    $result.subjectId = $SubjectId
    $result.threadId = $threadId
    $result.windowHandle = $WindowHandle
    $field = Wait-For { Get-OwnedFilename } 'normal German filename'
    if (-not [IfwObservedWindow]::OnInputDesktop()) { throw 'The observer is outside the input desktop.' }
    $result.setForeground = [IfwObservedWindow]::SetForegroundWindow($handle)
    try { $field.SetFocus() } catch { $result.uiaFocusError = $_.Exception.GetBaseException().Message }
    if (-not (Test-OwnedFocus)) {
        $rect = $field.Current.BoundingRectangle
        if ($rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0) { throw 'The owned filename has no screen geometry.' }
        $x = [int]($rect.Left + $rect.Width/2)
        $y = [int]($rect.Top + $rect.Height/2)
        $raised = $false
        try {
            if (-not [IfwObservedWindow]::SubjectAt($handle,$SubjectId,$x,$y)) {
                $raised = [IfwObservedWindow]::OrderOwnTestWindow($handle,$SubjectId,$true)
                if ($raised) { Start-Sleep -Milliseconds 150 }
            }
            $result.ownedClick = [IfwObservedWindow]::ClickOwnedControl($handle,$SubjectId,$x,$y)
        } finally {
            if ($raised) { [void][IfwObservedWindow]::OrderOwnTestWindow($handle,$SubjectId,$false) }
        }
    }
    [void](Wait-For { Test-OwnedFocus } 'own filename foreground focus')
    $original = [IfwQaIme.Native]::GetKeyboardLayout($threadId)
    $result.originalLayout = $original.ToInt64()
    $layouts = @([IfwQaIme.Native]::Layouts() | Where-Object { ($_.ToInt64() -band 65535) -eq 0x0411 })
    if ($layouts.Count -eq 0) { throw 'The subject desktop has no loaded Japanese input locale.' }
    $japanese = if (($original.ToInt64() -band 65535) -eq 0x0411) { $original } else { $layouts[0] }
    if ($original -ne $japanese) {
        $changed = $true
        Set-OwnedLayout $japanese
    }
    $result.selectedLayout = [IfwQaIme.Native]::GetKeyboardLayout($threadId).ToInt64()
    $expected = 'Gr' + [char]0xfc + [char]0xdf + 'e ' + [char]0x2013 + ' Sommer.jpg'
    $result.fieldAfterLayout = [ordered]@{ state='waiting'; attempts=0; lastObservation='pending' }
    $ready = Wait-For { Read-LayoutFilename $result.fieldAfterLayout } 'the focused filename on the original window after Japanese layout selection' -Evidence $result.fieldAfterLayout
    $field = $ready.element
    $initial = $ready.text
    Send-Key 'end'
    $result.attempts = @()
    $composing = $false
    $sample = 1
    foreach ($gesture in @('ime-on', 'alt-backquote')) {
        $attempt = [ordered]@{ modeGesture=$gesture }
        $result.attempts += $attempt
        $attempt.beforeModeGesture = Get-IfwModeSample $sample
        Send-Key $gesture
        Start-Sleep -Milliseconds 200
        $attempt.beforeA = Get-IfwModeSample ($sample + 1)
        $offset = (Get-Item -LiteralPath $SubjectLog).Length
        Send-Key 'a'
        $until = [DateTime]::UtcNow.AddSeconds(5)
        do {
            $trace = Get-Trace $offset
            if ($trace -match '(?m)^IME preedit chars=[1-9][0-9]*\r?$') { $composing=$true; break }
            Start-Sleep -Milliseconds 80
        } while ([DateTime]::UtcNow -lt $until)
        $attempt.preeditBeforeEnter = $composing
        $attempt.afterA = Get-IfwModeSample ($sample + 2)
        if ((Get-Trace $offset) -match '(?m)^IME commit chars=[1-9][0-9]*\r?$') { throw 'The IME committed before the observed Enter gesture.' }
        if ($composing) { break }
        if ((Get-Text) -cne ($initial + 'a')) { throw 'A plain lower-case a was not the only added character.' }
        $attempt.literalAConfirmed = $true
        Send-Key 'backspace'
        [void](Wait-For { (Get-Text) -ceq $initial } 'clean retry of the synthetic filename')
        $attempt.originalFilenameRestored = $true
        $sample += 3
    }
    if (-not $composing) { throw 'No nonempty native preedit arrived after an ordinary A key.' }
    $offset = (Get-Item -LiteralPath $SubjectLog).Length
    Send-Key 'enter'
    [void](Wait-For { (Get-Trace $offset) -match '(?m)^IME commit chars=1\r?$' } 'one-character native commit')
    [void](Wait-For { (Get-Text) -ceq ($initial + [char]0x3042) } 'committed U+3042 through UI Automation')
    $result.preeditBeforeEnter = $true
    $result.commitAfterEnter = $true
    $result.committedCodePoint = 'U+3042'
    $result.normalFilenameConfirmed = $true
    $result.afterCommit = Get-IfwModeSample 7
    $result.status = 'passed'
} catch {
    $result.error = $_.Exception.GetBaseException().Message
    throw
} finally {
    try {
        if ($changed -and [IfwQaIme.Native]::GetKeyboardLayout($threadId) -ne $original) { Set-OwnedLayout $original }
        if ($null -ne $original) {
            $result.restoredLayout = [IfwQaIme.Native]::GetKeyboardLayout($threadId).ToInt64()
            if ($result.restoredLayout -ne $result.originalLayout) { throw 'Subject input locale restoration failed.' }
        }
    } catch {
        $result.status='failed'
        $result.restoreError=$_.Exception.GetBaseException().Message
        throw
    } finally {
        if ($null -ne $sampleWriter) {
            try { $sampleWriter.Dispose() } catch { $result.samplePipeCloseError = $_.Exception.GetBaseException().Message }
        }
        Save-Evidence
    }
}
