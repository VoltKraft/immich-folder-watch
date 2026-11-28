param(
    [Parameter(Mandatory)][string]$Binary,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$QaRoot = (Split-Path $PSScriptRoot),
    [ValidatePattern('^IfwQa_[a-f0-9]{32}$')][string]$HostedDesktop
)

$ErrorActionPreference = 'Stop'
if ($HostedDesktop) {
    if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
        $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ARCH -cne 'ARM64' -or $env:IFW_QA_LOCAL_WINDOWS -or
        $env:GITHUB_REPOSITORY -cne 'VoltKraft/immich-folder-watch' -or $env:GITHUB_REF -cne 'refs/heads/rewrite/rust') {
        throw 'Select the private desktop of the native ARM64 rewrite runner.'
    }
} elseif ($env:COMPUTERNAME -ine 'IFW-QA25' -or $env:USERNAME -ine 'ifw-test' -or
          $env:GITHUB_ACTIONS -or $env:RUNNER_ENVIRONMENT -or -not [Environment]::Is64BitProcess) {
    throw 'Select the local disposable x64 Windows console and standard QA account.'
}
$binaryPath = (Resolve-Path $Binary).Path
$out = (New-Item -ItemType Directory -Path $OutputDirectory -ErrorAction Stop).FullName
$token = [Guid]::NewGuid().ToString('N')
$parent = if ($HostedDesktop) { (Resolve-Path $env:RUNNER_TEMP).Path } else { $out }
$trial = (New-Item -ItemType Directory -Path (Join-Path $parent "ifw-rw02-$token")).FullName
[IO.File]::WriteAllText((Join-Path $trial 'inventory.owner'), $token, [Text.Encoding]::ASCII)
[IO.File]::WriteAllBytes((Join-Path $trial 'launcher.pid'), [byte[]]@())
$report = [ordered]@{ status='failed'; binarySha256=(Get-FileHash $binaryPath).Hash; stages=[ordered]@{} }
$primary = $null
$secondary = $null
$handle = [IntPtr]::Zero
$initial = 'Gr' + [char]0xfc + [char]0xdf + 'e ' + [char]0x2013 + ' Sommer.jpg'

function Start-Subject {
    $info = [Diagnostics.ProcessStartInfo]::new($binaryPath)
    $info.UseShellExecute = $false
    $info.WorkingDirectory = $trial
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($name in @('HOME','USERPROFILE','TEMP','TMP','APPDATA','LOCALAPPDATA')) {
        $info.EnvironmentVariables[$name] = $trial
    }
    $info.EnvironmentVariables['IFW_QA_ISOLATED'] = '1'
    if (-not $HostedDesktop) {
        $info.EnvironmentVariables['IFW_QA_LOCAL_WINDOWS'] = '1'
        $info.EnvironmentVariables['IFW_QA_LOCAL_TEMP'] = $out
    }
    $info.EnvironmentVariables['IFW_QA_WINDOWS_LAUNCHER'] = '1'
    $info.EnvironmentVariables['IFW_QA_INVENTORY_TOKEN'] = $token
    $info.EnvironmentVariables['IFW_QA_INVENTORY_ROOT'] = $trial
    $info.EnvironmentVariables['IFW_QA_LAUNCHER_SID'] = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $info.EnvironmentVariables['WGPU_DX12_COMPILER'] = 'Fxc'
    $process = [Diagnostics.Process]::Start($info)
    return @{ process=$process; stdout=$process.StandardOutput.ReadToEndAsync(); stderr=$process.StandardError.ReadToEndAsync() }
}

function Get-SubjectWindow {
    $primary.process.Refresh()
    if ($primary.process.HasExited) { throw 'The original primary exited.' }
    if ($primary.process.MainWindowTitle -cne 'Desktop input probe') { return [IntPtr]::Zero }
    return $primary.process.MainWindowHandle
}

function Read-Filename {
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    [uint32]$owner = 0
    $thread = [IfwObservedWindow]::GetWindowThreadProcessId($handle,[ref]$owner)
    if (-not $thread -or $owner -ne $primary.process.Id -or $root.Current.ProcessId -ne $owner) {
        throw 'The window does not belong to the original live primary.'
    }
    if ($HostedDesktop -and [IfwSelectionDesktop]::ThreadName($thread) -cne $HostedDesktop) {
        throw 'The owned GUI window is outside the selected private desktop.'
    }
    $field = Get-Field 'Dateiname' ([Windows.Automation.ControlType]::Edit)
    if ($null -eq $field -or $field.Current.IsPassword -or $field.Current.ProcessId -ne $owner) {
        throw 'The normal filename editor is unavailable.'
    }
    return $field
}

function Read-Stage($Field) {
    $textPattern = $Field.GetCurrentPattern([Windows.Automation.TextPattern]::Pattern)
    $valuePattern = $Field.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
    $active = [Windows.Automation.AutomationElement]::FocusedElement
    $foreground = [IfwObservedWindow]::GetForegroundWindow()
    $state = [ordered]@{ pid=$Field.Current.ProcessId; hwnd=$handle.ToInt64(); inputDesktop=[IfwObservedWindow]::OnInputDesktop()
        foregroundHwnd=$foreground.ToInt64(); foreground=($foreground -eq $handle); hasKeyboardFocus=$Field.Current.HasKeyboardFocus
        focusedElementMatches=($null -ne $active -and [Windows.Automation.Automation]::Compare($Field,$active))
        document=$textPattern.DocumentRange.GetText(-1); value=$valuePattern.Current.Value; selection=$null }
    $ranges = @($textPattern.GetSelection())
    if ($ranges.Count -eq 1) {
        $prefix = $textPattern.DocumentRange.Clone()
        $prefix.MoveEndpointByRange('End',$ranges[0],'Start')
        $state.selection = @{start=$prefix.GetText(-1).Length; text=$ranges[0].GetText(-1)}
    }
    return $state
}

function Expect-Stage([string]$Stage, [string]$Value, [int]$Start, [string]$Selected) {
    [void](Wait-Observation {
        try { $state = Read-Stage (Read-Filename) }
        catch {
            $report.stages[$Stage + 'ReadError'] = $_.Exception.GetBaseException().Message
            return $false
        }
        $report.stages[$Stage] = $state
        return $state.foreground -and $state.inputDesktop -and $state.focusedElementMatches -and
            $state.hasKeyboardFocus -and $state.document -ceq $Value -and $state.value -ceq $Value -and
            $null -ne $state.selection -and $state.selection.start -eq $Start -and $state.selection.text -ceq $Selected
    } $Stage)
}

function Send-FilenameKey([string]$Keys) {
    $state = Read-Stage (Read-Filename)
    if (-not ($state.foreground -and $state.inputDesktop -and $state.focusedElementMatches -and $state.hasKeyboardFocus)) {
        throw 'The original normal filename field lost keyboard focus before input.'
    }
    [Windows.Forms.SendKeys]::SendWait($Keys)
}

function Wait-Stage([scriptblock]$Read, [string]$Label) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $value = & $Read
        if ($value) { return $value }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out observing $Label."
}

function Save-Process($Child, [string]$Name) {
    if (-not $Child.process.WaitForExit(10000)) {
        $report[$Name + 'Terminated'] = $true
        $Child.process.Kill()
        $Child.process.WaitForExit()
    }
    $report[$Name + 'Exit'] = $Child.process.ExitCode
    [IO.File]::WriteAllText((Join-Path $out "$Name.log"), $Child.stdout.GetAwaiter().GetResult())
    [IO.File]::WriteAllText((Join-Path $out "$Name.stderr"), $Child.stderr.GetAwaiter().GetResult())
}

try {
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms
    $scope = [Windows.Automation.TreeScope]::Descendants
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $QaRoot 'observe-windows-input.ps1'),[ref]$null,[ref]$errors)
    $bridge = @($ast.FindAll({ param($a) $a -is [Management.Automation.Language.StringConstantExpressionAst] -and
        $a.StringConstantType -eq 'SingleQuotedHereString' -and $a.Value.Contains('public static class IfwObservedWindow {') },$true))
    if ($errors -or $bridge.Count -ne 1) { throw 'Cannot load the shared native window observer.' }
    Add-Type -TypeDefinition $bridge[0].Value
    if ($HostedDesktop) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class IfwSelectionDesktop {
    [DllImport("user32.dll")] static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    static extern bool GetUserObjectInformation(IntPtr handle, int index, StringBuilder value, uint bytes, out uint needed);
    public static string ThreadName(uint id) {
        var name = new StringBuilder(256);
        uint needed;
        return GetUserObjectInformation(GetThreadDesktop(id), 2, name, 512, out needed) ? name.ToString() : null;
    }
}
'@
        $report.observerDesktop = [IfwSelectionDesktop]::ThreadName([IfwSelectionDesktop]::GetCurrentThreadId())
        if ($report.observerDesktop -cne $HostedDesktop) { throw 'The observer did not start on the private desktop.' }
    }
    foreach ($name in 'Get-AccessibleName','Get-Field','Wait-Observation') {
        $defs = @($ast.FindAll({ param($a) $a -is [Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -ceq $name },$true))
        if ($defs.Count -ne 1) { throw "Missing shared observer $name." }
        . ([scriptblock]::Create($defs[0].Extent.Text))
    }
    if (-not [IfwObservedWindow]::OnInputDesktop()) { throw 'Expected the unlocked input desktop.' }
    $primary = Start-Subject
    $report.primaryPid = $primary.process.Id
    $report.primaryCreated = $primary.process.StartTime.ToFileTimeUtc().ToString()
    $primary.process.StandardInput.BaseStream.WriteByte(84) # T, synthetic tray available
    $primary.process.StandardInput.BaseStream.Flush()
    $handle = Wait-Stage { $h = Get-SubjectWindow; if ($h -ne [IntPtr]::Zero) { $h } } 'first visible HWND'
    $report.firstHwnd = $handle.ToInt64()
    $field = Wait-Stage { try { Read-Filename } catch { $report.firstReadError = $_.Exception.GetBaseException().Message; $null } } 'first normal editor'
    [void][IfwObservedWindow]::SetForegroundWindow($handle)
    try { $field.SetFocus() } catch { $report.initialFocusError = $_.Exception.GetBaseException().Message }
    $first = Read-Stage (Read-Filename)
    if (-not ($first.foreground -and $first.focusedElementMatches -and $first.hasKeyboardFocus)) {
        $box = $field.Current.BoundingRectangle
        $report.initialFocusClick = [IfwObservedWindow]::ClickOwnedControl($handle,$primary.process.Id,
            [int]($box.Left + $box.Width / 2),[int]($box.Top + $box.Height / 2))
    }
    [void](Wait-Observation { $s=Read-Stage (Read-Filename); $s.foreground -and $s.focusedElementMatches -and $s.hasKeyboardFocus } 'initial filename focus')
    Send-FilenameKey '{HOME}'
    foreach ($n in 1..5) { Send-FilenameKey '{RIGHT}' }
    foreach ($n in 1..3) { Send-FilenameKey '+{LEFT}' }
    Expect-Stage beforeClose $initial 2 $initial.Substring(2,3)
    if (-not $primary.process.CloseMainWindow()) { throw 'WM_CLOSE was not accepted.' }
    [void](Wait-Observation { (Get-SubjectWindow) -eq [IntPtr]::Zero } 'first window close')
    $report.closedAlive = -not $primary.process.HasExited
    $secondary = Start-Subject
    $report.secondaryPid = $secondary.process.Id
    $secondary.process.StandardInput.Close()
    Save-Process $secondary 'secondary'
    if ($report.secondaryExit -ne 0) { throw 'Second launch failed.' }
    $handle = Wait-Observation { $h = Get-SubjectWindow; if ($h -ne [IntPtr]::Zero) { $h } } 'reopened original primary'
    $report.reopenedHwnd = $handle.ToInt64()
    # No focus, foreground, pointer or ValuePattern requests after the normal close.
    Expect-Stage afterReopen $initial 2 $initial.Substring(2,3)
    Send-FilenameKey '+{LEFT}'
    Expect-Stage afterShiftLeft $initial 1 $initial.Substring(1,4)
    Send-FilenameKey 'x'
    Expect-Stage afterReplacement ('Gx' + $initial.Substring(5)) 2 ''
    $report.status = 'passed'
} catch {
    $report.error = $_.Exception.GetBaseException().Message
    $report.line = $_.InvocationInfo.ScriptLineNumber
} finally {
    if ($primary) {
        if (-not $primary.process.HasExited) {
            $primary.process.StandardInput.BaseStream.WriteByte(81) # Q, ordinary controller Quit
            $primary.process.StandardInput.BaseStream.Flush()
        }
        Save-Process $primary 'primary'
    }
    if ($report.status -eq 'passed') {
        $p = [IO.File]::ReadAllText((Join-Path $out 'primary.log'))
        $s = [IO.File]::ReadAllText((Join-Path $out 'secondary.log'))
        $release = $p.IndexOf('WINDOW_RELEASED passes=')
        $open = $p.IndexOf("LAUNCHER_OPEN client=$($report.secondaryPid)")
        $foreground = $p.IndexOf("WINDOW_FOREGROUND_REQUEST pid=$($report.primaryPid) hwnd=$($report.reopenedHwnd) accepted=true")
        if ($report.primaryExit -ne 0 -or $report.secondaryExit -ne 0 -or
            $p -notmatch "(?m)^LAUNCHER_PRIMARY pid=$($report.primaryPid)\r?$" -or
            $p -notmatch "(?m)^LAUNCHER_OPEN client=$($report.secondaryPid)\r?$" -or
            $s -notmatch "(?m)^LAUNCHER_SECONDARY server=$($report.primaryPid)\r?$" -or
            $s -notmatch "(?m)^LAUNCHER_FOREGROUND_GRANT server=$($report.primaryPid) state=granted\r?$" -or
            $release -lt 0 -or $open -le $release -or $foreground -le $open -or $p.IndexOf('DRAINED passes=') -le $foreground) {
            $report.status = 'failed'
            $report.error = 'The native launcher, window or drain receipts are incomplete.'
        }
    }
    if ($HostedDesktop) {
        [IO.Directory]::Delete($trial, $true)
        $report.profileRemoved = -not [IO.Directory]::Exists($trial)
    }
    [IO.File]::WriteAllText((Join-Path $out 'selection.json'), ($report | ConvertTo-Json -Depth 7), [Text.UTF8Encoding]::new($false))
}
if ($report.status -ne 'passed') { throw $report.error }
