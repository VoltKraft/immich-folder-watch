function Get-IfwJapaneseLanguage($List) {
    foreach ($item in $List) {
        if ($item.LanguageTag -ieq 'ja-JP') { $item }
    }
}

function Get-IfwLanguageState($List) {
    $rows = @(foreach ($item in $List) {
        [ordered]@{ language=$item.LanguageTag; inputTips=@($item.InputMethodTips); handwriting=$item.Handwriting }
    })
    return (ConvertTo-Json -InputObject $rows -Depth 4 -Compress)
}
