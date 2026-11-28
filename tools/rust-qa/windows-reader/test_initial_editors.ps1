# Exercise the input driver's evidence without accessing a desktop or an application.
$ErrorActionPreference = 'Stop'
$source = Join-Path (Split-Path $PSScriptRoot) 'observe-windows-input.ps1'
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$null, [ref]$errors)
if ($errors) { throw 'Could not parse the input driver.' }
foreach ($name in @('Get-InitialEditor','Get-AccessibleName','Get-UiaReadFailure')) {
    $nodes = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name}, $true))
    if ($nodes.Count -ne 1) { throw "Expected one definition of $name." }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
$result = @{}
$SubjectId = 123
$scope = 'owned descendants'
$root = [pscustomobject]@{ editors=@(); providerUnavailable=$false }
$root | Add-Member ScriptMethod FindAll {
    param($treeScope, $condition)
    if ($treeScope -cne 'owned descendants' -or $condition -cne 'owned editors') { throw 'Unexpected query.' }
    if ($this.providerUnavailable) { throw [Runtime.InteropServices.COMException]::new('Private provider message', -2147220991) }
    return ,$this.editors
}
function Editor([string]$Name, $Label=$null) {
    return [pscustomobject]@{Current=[pscustomobject]@{ProcessId=$SubjectId; Name=$Name; LabeledBy=$Label}}
}
function Expect($condition, $message) { if (-not $condition) { throw $message } }
$found = Get-InitialEditor 'Dateiname' 'owned editors'
$scan = $result.initialEditorSearch
Expect ($null -eq $found -and $scan.editCount -eq 0 -and $false -eq $scan.Dateiname -and $false -eq $scan.Kennwort) 'Empty query'
$foreign = [pscustomobject]@{Current=[pscustomobject]@{ProcessId=456}}
$foreign.Current | Add-Member ScriptProperty Name {throw 'Tried to read a foreign label'}
$root.editors = @((Editor 'Private synthetic label'), (Editor '' $foreign), (Editor '' (Editor 'Kennwort')))
$found = Get-InitialEditor 'Dateiname' 'owned editors'
$scan = $result.initialEditorSearch
Expect ($null -eq $found -and $scan.editCount -eq 3 -and $false -eq $scan.Dateiname -and $true -eq $scan.Kennwort) 'Wrong labels'
Expect (($scan | ConvertTo-Json -Compress) -notmatch 'Private') 'Leaked provider text'
$root.editors = @((Editor 'Dateiname'), (Editor 'Kennwort'))
$found = Get-InitialEditor 'Dateiname' 'owned editors'
$scan = $result.initialEditorSearch
Expect ([object]::ReferenceEquals($found,$root.editors[0]) -and $scan.editCount -eq 2 -and $true -eq $scan.Dateiname -and $null -eq $scan.Kennwort) 'Early successful match'
$root.providerUnavailable = $true
try {
    Get-InitialEditor 'Kennwort' 'owned editors'
    throw 'Provider failure should abort the search.'
} catch {
    if ($_.Exception.Message -cne 'UI Automation could not finish reading the owned German editors.') { throw }
}
$scan = $result.initialEditorSearch
Expect ($scan.requested -ceq 'Kennwort' -and $null -eq $scan.editCount -and $null -eq $scan.Dateiname -and $null -eq $scan.Kennwort) 'Incomplete snapshot'
Expect ($scan.providerError.type -ceq 'System.Runtime.InteropServices.COMException' -and $scan.providerError.hresult -ceq '0x80040201') 'Provider details'
Expect (($scan | ConvertTo-Json -Compress) -notmatch 'Private') 'Leaked provider exception message'
Write-Output 'Initial editor evidence controls passed.'
