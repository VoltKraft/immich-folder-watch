function Get-IfwJapaneseLanguage($List) {
    foreach ($item in $List) {
        if ($item.LanguageTag -in @('ja', 'ja-JP')) { $item }
    }
}

function Get-IfwLanguageState($List) {
    $rows = @(foreach ($item in $List) {
        [ordered]@{ language=$item.LanguageTag; inputTips=@($item.InputMethodTips); handwriting=$item.Handwriting }
    })
    return (ConvertTo-Json -InputObject $rows -Depth 4 -Compress)
}

function Test-IfwImeProfile($Observation) {
    return ($null -ne $Observation -and $null -eq $Observation.PSObject.Properties['error'] -and
            $Observation.profileRemoved -is [bool] -and $Observation.profileRemoved)
}

function Test-IfwImeObservation($Observation, [int]$ExitCode) {
    return ($ExitCode -eq 0 -and (Test-IfwImeProfile $Observation) -and $Observation.status -ceq 'passed' -and
            $Observation.compositionObserved -is [bool] -and $Observation.compositionObserved)
}

# Invoke the supplied observer while the original desktop account has its Japanese keyboard.
function Invoke-IfwJapaneseLanguage($OriginalList, $Report, [scriptblock]$Observe) {
    $originalState = Get-IfwLanguageState $OriginalList
    $changedList = $false
    try {
        $sessionList = Get-WinUserLanguageList
        if (@(Get-IfwJapaneseLanguage $sessionList).Count -eq 0) {
            $newList = New-WinUserLanguageList -Language 'ja-JP'
            $entry = @(Get-IfwJapaneseLanguage $newList)
            if ($entry.Count -ne 1) { throw 'Windows did not construct a Japanese input language.' }
            [void]$sessionList.Add($entry[0])
            if (@(Get-IfwJapaneseLanguage $sessionList).Count -ne 1) { throw 'The proposed language list is incomplete.' }
            $changedList = $true
            Set-WinUserLanguageList -LanguageList $sessionList -Force
        }
        $report.requestedLanguages = @(foreach ($entry in $sessionList) { $entry.LanguageTag })
        $until = [DateTime]::UtcNow.AddSeconds(25)
        do {
            $actual = Get-WinUserLanguageList
            $language = @(Get-IfwJapaneseLanguage $actual)
            if ($language.Count -eq 1) { break }
            Start-Sleep -Milliseconds 300
        } while ([DateTime]::UtcNow -lt $until)
        $report.currentLanguages = @(foreach ($entry in $actual) { $entry.LanguageTag })
        if ($language.Count -ne 1) { throw 'The disposable account did not acquire the Japanese locale.' }
        $report.inputTips = @($language[0].InputMethodTips)
        & $Observe
    } finally {
        if ($changedList) {
            Set-WinUserLanguageList -LanguageList $OriginalList -Force
            $Report.languageListRestored = (Get-IfwLanguageState (Get-WinUserLanguageList)) -ceq $originalState
            if (-not $Report.languageListRestored) { throw 'The original test-account language settings differ.' }
        }
    }
}
