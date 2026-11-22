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

function Wait-For([scriptblock]$Read, [string]$Name, [int]$Seconds=8) {
    $until = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $value = & $Read
        if ($value) { return $value }
        Start-Sleep -Milliseconds 70
    } while ([DateTime]::UtcNow -lt $until)
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
    if ($root.Current.ProcessId -ne $SubjectId) { throw 'UIA root belongs to a different process.' }
    $condition = [Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Edit)
    foreach ($el in $root.FindAll([Windows.Automation.TreeScope]::Descendants, $condition)) {
        if ($el.Current.ProcessId -eq $SubjectId -and (Get-Label $el) -ceq 'Dateiname' -and -not $el.Current.IsPassword) { return $el }
    }
}

function Test-OwnedFocus {
    if (-not [IfwObservedWindow]::OnInputDesktop() -or [IfwObservedWindow]::GetForegroundWindow() -ne $handle) { return $false }
    $el = [Windows.Automation.AutomationElement]::FocusedElement
    return ($null -ne $el -and $el.Current.ProcessId -eq $SubjectId -and -not $el.Current.IsPassword -and
            $el.Current.ControlType -eq [Windows.Automation.ControlType]::Edit -and (Get-Label $el) -ceq 'Dateiname')
}

function Get-Text {
    $value = $null
    if ($field.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$value)) { return [string]$value.Current.Value }
    $value = $field.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern)
    return $value.DocumentRange.GetText(-1).TrimEnd("`r","`n")
}

function Send-Key([string]$Name) {
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
    $field = Get-OwnedFilename
    $initial = Get-Text
    $expected = 'Gr' + [char]0xfc + [char]0xdf + 'e ' + [char]0x2013 + ' Sommer.jpg'
    if ($initial -cne $expected) { throw 'Unexpected initial synthetic filename.' }
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
