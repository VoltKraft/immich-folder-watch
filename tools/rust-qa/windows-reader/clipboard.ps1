# Loaded only for the portable NVDA case, inside the owned GUI observer.
function Confirm-ReaderField($Element) {
    $focusWindow = [IfwQaReader.Keyboard]::Focus($handle, $SubjectId)
    $focused = [Windows.Automation.AutomationElement]::FocusedElement
    if ($null -eq $focused -or $Element.Current.ProcessId -ne $SubjectId -or
        $Element.Current.IsPassword -or (Get-AccessibleName $Element) -cne 'Filename' -or
        -not [Windows.Automation.Automation]::Compare($Element, $focused)) {
        throw 'The owned, unprotected filename field lost UI Automation keyboard focus.'
    }
    return $focusWindow.ToInt64()
}

function Get-ReaderFilename($Element, [string]$Expected) {
    $focusWindow = Confirm-ReaderField $Element
    $valuePattern = $Element.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
    $textPattern = $Element.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern)
    $range = $textPattern.DocumentRange
    if ($null -eq $range -or $null -eq $valuePattern) { return $null }
    $value = $valuePattern.Current.Value
    $text = $range.GetText(-1)
    $selections = $textPattern.GetSelection()
    if ($null -eq $selections) { return $null }
    # AccessKit can return an empty COM BSTR as null. Preserve that representation
    # alongside the lengths and the independent document endpoint comparison.
    $state = [ordered]@{
        focusHwnd = $focusWindow; value = [string]$value; document = [string]$text
        valueNullBstr = $null -eq $value; documentNullBstr = $null -eq $text
        valueLength = ([string]$value).Length; documentLength = ([string]$text).Length
        documentCollapsed = $range.CompareEndpoints('Start', $range, 'End') -eq 0
        selectionCount = $selections.Length; selected = $null; selectionStart = $null; selectionEnd = $null
    }
    if ($selections.Length -eq 1) {
        $selection = $selections[0]
        $state.selected = [string]$selection.GetText(-1)
        if ($state.documentCollapsed -and $state.documentLength -eq 0 -and $state.valueLength -eq 0 -and
                $state.selected.Length -eq 0 -and $selection.CompareEndpoints('Start', $selection, 'End') -eq 0) {
            # An empty document has one insertion position.
            $state.selectionStart = 0
            $state.selectionEnd = 0
        } else {
            foreach ($endpoint in @('Start', 'End')) {
                $prefix = $range.Clone()
                $prefix.MoveEndpointByRange('End', $selection, $endpoint)
                $state["selection$endpoint"] = ([string]$prefix.GetText(-1)).Length
            }
        }
    }
    foreach ($kind in @('value', 'document', 'selected')) {
        # Only the known synthetic filename or its substrings may enter an artifact.
        if ($null -ne $state[$kind] -and $Expected.IndexOf($state[$kind], [StringComparison]::Ordinal) -lt 0) {
            $state[$kind] = '<unexpected>'
        }
    }
    return $state
}

function Send-ReaderGesture($Element, [string]$Gesture) {
    $focusWindow = Confirm-ReaderField $Element
    $sent = [IfwQaReader.Keyboard]::Press($handle, $SubjectId, $Gesture)
    $result.readerEdit.gestures += [ordered]@{ name=$Gesture; focusHwnd=$focusWindow; submitted=$sent }
}

function Wait-ReaderState($Element, [string]$Expected, [string]$Phase, [scriptblock]$Accept) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $lastFailure = $null
    do {
        try {
            $current = Get-Field 'Filename' ([Windows.Automation.ControlType]::Edit)
            if ($null -eq $current -or -not [Windows.Automation.Automation]::Compare($current,$Element)) {
                throw 'The filename field changed identity during the native clipboard observation.'
            }
            $state = Get-ReaderFilename $current $Expected
            if ($null -eq $state) {
                $lastFailure = [ordered]@{ type='missingPatternOrRange'; hresult=$null }
                $result.readerEdit.lastReadFailure[$Phase] = $lastFailure
            } else {
                $lastFailure = $null
                $result.readerEdit.states[$Phase] = $state
                if (& $Accept $state) { return $true }
            }
        } catch {
            $failure = Get-UiaReadFailure $_
            if ($null -eq $failure) { throw }
            $result.readerEdit.lastReadFailure[$Phase] = $failure
            $lastFailure = $failure
        }
        Start-Sleep -Milliseconds 70
    } while ($timer.Elapsed.TotalSeconds -lt 5)
    if ($null -ne $lastFailure) { throw "UI Automation read failed during $Phase ($($lastFailure.type) $($lastFailure.hresult))." }
    return $false
}

function Test-ReaderClipboard($Element, [string]$Expected) {
    $result.readerEdit = [ordered]@{ hwnd=$handle.ToInt64(); states=[ordered]@{}; gestures=@(); lastReadFailure=[ordered]@{} }
    $original = { param($s) $s.value -ceq $Expected -and $s.document -ceq $Expected -and -not $s.documentCollapsed }
    $whole = { param($s) (& $original $s) -and $s.selectionCount -eq 1 -and $s.selected -ceq $Expected -and
        $s.selectionStart -eq 0 -and $s.selectionEnd -eq $Expected.Length }
    $empty = { param($s) $s.valueLength -eq 0 -and $s.documentLength -eq 0 -and $s.documentCollapsed }
    if (-not (Wait-ReaderState $Element $Expected 'beforeCopy' $original)) { throw 'Unexpected filename before Copy.' }
    Send-ReaderGesture $Element 'SelectAll'
    if (-not (Wait-ReaderState $Element $Expected 'selectedForCopy' $whole)) { throw 'Incomplete selection for Copy.' }
    $before = [IfwObservedWindow]::GetClipboardSequenceNumber()
    Send-ReaderGesture $Element 'Copy'
    [void](Wait-Observation { [IfwObservedWindow]::GetClipboardSequenceNumber() -ne $before } 'clipboard change')
    [void](Wait-Observation { [Windows.Forms.Clipboard]::GetText() -ceq $Expected } 'copied synthetic name')
    $copied = [IfwObservedWindow]::GetClipboardSequenceNumber()
    $result.clipboardCopied = $true
    Send-ReaderGesture $Element 'SelectAll'
    $result.wholeFilenameSelectedBeforeDelete = Wait-ReaderState $Element $Expected 'selectedForDelete' $whole
    if (-not $result.wholeFilenameSelectedBeforeDelete) { throw 'Incomplete selection before native Delete.' }
    Send-ReaderGesture $Element 'Delete'
    $cleared = Wait-ReaderState $Element $Expected 'ordinaryDelete' $empty
    $phase = 'ordinaryDelete'
    if (-not $cleared) {
        if (-not (& $original $result.readerEdit.states.ordinaryDelete)) {
            throw 'Ordinary Delete produced an unexpected filename. See the native edit observations.'
        }
        Send-ReaderGesture $Element 'SelectAll'
        if (-not (Wait-ReaderState $Element $Expected 'selectedForPassThrough' $whole)) {
            throw 'The original selection could not be restored before the NVDA command.'
        }
        [void](New-Item -ItemType File -Path (Join-Path $SpeechCues 'request-pass-key'))
        Send-ReaderGesture $Element 'PassNextKey'
        Wait-ReaderCue 'pass-key-announced'
        if (-not (Wait-ReaderState $Element $Expected 'afterPassAnnouncement' $whole)) {
            throw 'The selection changed before the passed-through Delete.'
        }
        Send-ReaderGesture $Element 'Delete'
        $phase = 'nvdaPassThroughDelete'
        $cleared = Wait-ReaderState $Element $Expected $phase $empty
    }
    $after = $result.readerEdit.states[$phase]
    $result.filenameLengthAfterDelete = $after.valueLength
    $result.filenameRangeLengthAfterDelete = $after.documentLength
    $result.emptyDocumentRange = $after.documentCollapsed
    if (-not $cleared) { throw 'The owned filename did not clear after native Delete. See the edit observations.' }
    $result.readerEdit.clearedBy = $phase
    if ([IfwObservedWindow]::GetClipboardSequenceNumber() -ne $copied -or
            [Windows.Forms.Clipboard]::GetText() -cne $Expected) { throw 'The synthetic clipboard changed before Paste.' }
    Send-ReaderGesture $Element 'Paste'
    if (-not (Wait-ReaderState $Element $Expected 'pasted' $original)) {
        throw 'The Unicode paste did not restore the exact filename in both native text patterns.'
    }
    $result.unicodeClipboardRoundTrip = $true
}
