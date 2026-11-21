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
$encoded = Get-IfwLanguageState (Read-LanguageFixture)
if ((ConvertFrom-Json $encoded).Count -ne 2 -or $initial -ceq $encoded) { throw 'Language snapshot lost an entry' }
$entries.RemoveAt(1)
if ((Get-IfwLanguageState (Read-LanguageFixture)) -cne $initial) { throw 'The original language snapshot differs' }
Write-Output 'Language list enumeration and restoration passed'
