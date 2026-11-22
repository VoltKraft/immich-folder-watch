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
