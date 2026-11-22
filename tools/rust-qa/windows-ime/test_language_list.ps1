# Get-WinUserLanguageList returns a typed list, which a cmdlet can emit as one pipeline item.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'language-list.ps1')
$entries = [Collections.Generic.List[object]]::new()
$entries.Add([pscustomobject]@{LanguageTag='en-US'; InputMethodTips=@('0409:00000409'); Handwriting=$false})
$initial = Get-IfwLanguageState $entries
function Read-LanguageFixture { Write-Output -NoEnumerate $entries }
if (@(Get-IfwJapaneseLanguage (Read-LanguageFixture)).Count) { throw 'Unexpected Japanese profile in the control list' }
$entries.Add([pscustomobject]@{LanguageTag='ja-JP'; InputMethodTips=@('0411:test'); Handwriting=$false})
$actual = @(Get-IfwJapaneseLanguage (Read-LanguageFixture))
if ($actual.Count -ne 1 -or $actual[0].InputMethodTips[0] -cne '0411:test') { throw 'Nested language list lookup failed' }
$entries[1].LanguageTag = 'ja'
$actual = @(Get-IfwJapaneseLanguage (Read-LanguageFixture))
if ($actual.Count -ne 1 -or $actual[0].LanguageTag -cne 'ja' -or $actual[0].InputMethodTips[0] -cne '0411:test') {
    throw 'Windows returned the neutral Japanese tag without its input profile'
}
$entries[1].LanguageTag = 'ja-Latn'
if (@(Get-IfwJapaneseLanguage (Read-LanguageFixture)).Count) { throw 'Unexpected Japanese input language variant' }
$entries[1].LanguageTag = 'ja-JP'
$encoded = Get-IfwLanguageState (Read-LanguageFixture)
if ((ConvertFrom-Json $encoded).Count -ne 2 -or $initial -ceq $encoded) { throw 'Language snapshot lost an entry' }
$entries.RemoveAt(1)
if ((Get-IfwLanguageState (Read-LanguageFixture)) -cne $initial) { throw 'The original language snapshot differs' }
Write-Output 'Language list enumeration and restoration passed'

$observed = [pscustomobject]@{ status='passed'; compositionObserved=$true; profileRemoved=$true }
if (-not (Test-IfwImeObservation $observed 0)) { throw 'A clean composition receipt was rejected' }
if (Test-IfwImeObservation $observed 1) { throw 'A failed observer exit was accepted' }
foreach ($incomplete in @(
    [pscustomobject]@{ status='passed'; error='WinError 32' },
    [pscustomobject]@{ status='passed'; compositionObserved=$true; profileRemoved=$true; error='WinError 32' },
    [pscustomobject]@{ status='passed'; compositionObserved=$true; profileRemoved=$false },
    [pscustomobject]@{ status='passed'; compositionObserved=$false; profileRemoved=$true },
    [pscustomobject]@{ status='passed'; compositionObserved=$true; profileRemoved='false' },
    [pscustomobject]@{ status='unavailable'; compositionObserved=$true; profileRemoved=$true }
)) {
    if (Test-IfwImeObservation $incomplete 0) { throw 'An incomplete native IME trial was accepted' }
}
Write-Output 'Native IME receipt requires an observed composition and a removed profile'
