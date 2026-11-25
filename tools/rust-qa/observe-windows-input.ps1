param(
    [Parameter(Mandatory)][int]$SubjectId,
    [Parameter(Mandatory)][long]$WindowHandle,
    [Parameter(Mandatory)][string]$SubjectLog,
    [Parameter(Mandatory)][string]$OutputFile,
    [string]$SpeechCues,
    [ValidateSet('before','after')][string]$RecoveryPhase
)

$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'Use the disposable native GUI launcher.' }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
$windowSource = @'
using System;
using System.Runtime.InteropServices;
public static class IfwObservedWindow {
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint id);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber();
    [DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();
    [DllImport("user32.dll", SetLastError=true)] static extern bool SetWindowPos(IntPtr window, IntPtr order,
        int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", SetLastError=true)] static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32.dll")] static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern bool GetUserObjectInformation(
        IntPtr handle, int index, System.Text.StringBuilder value, uint bytes, out uint needed);
    static string DesktopName(IntPtr desktop) {
        var name = new System.Text.StringBuilder(256);
        uint needed;
        return GetUserObjectInformation(desktop, 2, name, 512, out needed) ? name.ToString() : null;
    }
    public static bool OnInputDesktop() {
        var input = OpenInputDesktop(0, false, 1);  // DESKTOP_READOBJECTS
        if (input == IntPtr.Zero) return false;
        try {
            var current = DesktopName(GetThreadDesktop(GetCurrentThreadId()));
            return current != null && String.Equals(current, DesktopName(input), StringComparison.OrdinalIgnoreCase);
        } finally { CloseDesktop(input); }
    }
    [StructLayout(LayoutKind.Sequential)] struct Point { public int x, y; }
    [StructLayout(LayoutKind.Sequential)] struct Mouse {
        public int x, y;
        public uint data, flags, time;
        public UIntPtr extra;
    }
    // Both supported Windows targets use a 64-bit pointer. MOUSEINPUT is the largest INPUT union member.
    [StructLayout(LayoutKind.Sequential)] struct Input { public uint type; public Mouse mouse; }
    [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr window, uint flag);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, Input[] inputs, int size);
    static bool IsSubjectAt(Point point, IntPtr window, uint expectedPid) {
        var found = WindowFromPoint(point);
        uint owner;
        return found != IntPtr.Zero && GetAncestor(found, 2) == window
            && GetWindowThreadProcessId(found, out owner) != 0 && owner == expectedPid;
    }
    public static bool SubjectAt(IntPtr window, uint expectedPid, int x, int y) {
        return IsSubjectAt(new Point {x=x, y=y}, window, expectedPid);
    }
    public static bool OrderOwnTestWindow(IntPtr window, uint expectedPid, bool topmost) {
        uint owner;
        if (!OnInputDesktop() || GetWindowThreadProcessId(window, out owner) == 0 || owner != expectedPid) return false;
        // Move only this synthetic window in the Z order, without moving, resizing or activating it.
        return SetWindowPos(window, new IntPtr(topmost ? -1 : -2), 0, 0, 0, 0, 0x0013);
    }
    public static bool ClickOwnedControl(IntPtr window, uint expectedPid, int x, int y) {
        var target = new Point { x=x, y=y };
        if (!OnInputDesktop() || !IsSubjectAt(target, window, expectedPid) || !SetCursorPos(x, y)) return false;
        Point actual;
        if (!GetCursorPos(out actual) || actual.x != x || actual.y != y || !IsSubjectAt(actual, window, expectedPid)) return false;
        var click = new[] {new Input { mouse=new Mouse { flags=2 } }, new Input { mouse=new Mouse { flags=4 } }};
        int size = Marshal.SizeOf(typeof(Input));
        uint sent = SendInput(2, click, size);
        if (sent == 1) SendInput(1, new[] { click[1] }, size);
        return sent == 2;
    }
}
'@
if ($SpeechCues) {
    $windowSource += [Environment]::NewLine + [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'windows-reader/Keyboard.cs'))
}
Add-Type -TypeDefinition $windowSource

$handle = [IntPtr]::new($WindowHandle)
$result = [ordered]@{ processId = $SubjectId; windowHandle = $WindowHandle; status = 'failed'; focus = @() }
$scope = [Windows.Automation.TreeScope]::Descendants
$root = $null

function Wait-Observation([scriptblock]$Read, [string]$Label) {
    $until = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $value = & $Read
        if ($value) { return $value }
        Start-Sleep -Milliseconds 70
    } while ([DateTime]::UtcNow -lt $until)
    throw "Timed out observing $Label."
}

function Get-AccessibleName($Element, [int]$Owner = 0) {
    $name = $Element.Current.Name
    if ($name) { return $name }
    $label = $Element.Current.LabeledBy
    if ($null -ne $label -and ($Owner -eq 0 -or $label.Current.ProcessId -eq $Owner)) { return $label.Current.Name }
    return ''
}

# UI Automation can invalidate a provider's ranges between two read-only calls.
function Get-UiaReadFailure($Record) {
    $cause = $Record.Exception.GetBaseException()
    if ($cause -is [Runtime.InteropServices.COMException] -or
        $cause.GetType().FullName -eq 'System.Windows.Automation.ElementNotAvailableException') {
        return [ordered]@{ type=$cause.GetType().FullName; hresult=('0x{0:X8}' -f $cause.HResult) }
    }
    return $null
}

function Wait-ReaderCue([string]$Name) {
    if (-not $SpeechCues) { return }
    $file = Join-Path $SpeechCues $Name
    $until = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $until) {
        if ([IO.File]::Exists($file)) { return }
        Start-Sleep -Milliseconds 70
    }
    throw "Missing NVDA speech observation for $Name."
}

function Capture-SubjectField($Element, [string]$Suffix, $ExpectedFocus = $Element) {
    # The display and text observers import this function's definition without running this script.
    function Get-FieldPngHash([string]$Path) {
        $stream = [IO.File]::OpenRead($Path)
        try {
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
            } finally { $sha.Dispose() }
        } finally { $stream.Dispose() }
    }

    $r = $Element.Current.BoundingRectangle
    $x = [int][Math]::Ceiling($r.Left + 2)
    $y = [int][Math]::Ceiling($r.Top + 2)
    $width = [int][Math]::Floor($r.Right) - $x - 2
    $height = [int][Math]::Floor($r.Bottom) - $y - 2
    if ($width -lt 10 -or $width -gt 1024 -or $height -lt 5 -or $height -gt 128) {
        throw 'Unexpected bounds for the synthetic filename field.'
    }
    $checkOwnership = {
        $focused = [Windows.Automation.AutomationElement]::FocusedElement
        if ([IfwObservedWindow]::GetForegroundWindow() -ne $handle -or -not [IfwObservedWindow]::OnInputDesktop() -or
            $null -eq $focused -or $focused.Current.ProcessId -ne $SubjectId -or
            $Element.Current.ProcessId -ne $SubjectId -or $Element.Current.IsPassword -or
            -not [Windows.Automation.Automation]::Compare($focused, $ExpectedFocus) -or
            -not $r.Equals($Element.Current.BoundingRectangle)) {
            throw 'The synthetic window lost the expected focus, field ownership or original bounds.'
        }
        foreach ($px in @($x, ($x + $width - 1))) {
            foreach ($py in @($y, ($y + $height - 1))) {
                if (-not [IfwObservedWindow]::SubjectAt($handle, $SubjectId, $px, $py)) {
                    throw 'The synthetic field is obscured on the desktop.'
                }
            }
        }
        $centerX = $x + [int][Math]::Floor($width / 2)
        $centerY = $y + [int][Math]::Floor($height / 2)
        if (-not [IfwObservedWindow]::SubjectAt($handle, $SubjectId, $centerX, $centerY)) {
            throw 'Another window obscures the synthetic field center.'
        }
    }
    $bitmap = [Drawing.Bitmap]::new($width, $height)
    try {
        $graphics = [Drawing.Graphics]::FromImage($bitmap)
        try {
            & $checkOwnership
            $graphics.CopyFromScreen($x, $y, 0, 0, $bitmap.Size)
            & $checkOwnership
        } finally { $graphics.Dispose() }
        $colors = [Collections.Generic.HashSet[int]]::new()
        for ($col = 0; $col -lt $width; $col++) {
            for ($row = 0; $row -lt $height; $row++) { [void]$colors.Add($bitmap.GetPixel($col, $row).ToArgb()) }
        }
        if ($colors.Count -lt 5) { throw 'Filename capture did not show a drawn text field.' }
        $png = "$OutputFile.$Suffix.png"
        $bitmap.Save($png, [Drawing.Imaging.ImageFormat]::Png)
        return [ordered]@{ x=$x; y=$y; width=$width; height=$height; colors=$colors.Count; sha256=(Get-FieldPngHash $png) }
    } finally { $bitmap.Dispose() }
}

function Get-FieldPixelDifference([string]$BeforeFile, [string]$AfterFile, $BeforeFrame, $AfterFrame, [int]$Dpi) {
    if ($Dpi -le 0 -or $BeforeFrame.x -ne $AfterFrame.x -or $BeforeFrame.y -ne $AfterFrame.y) {
        throw 'The two field frames require the same origin and a positive window DPI.'
    }
    $before = [Drawing.Bitmap]::new($BeforeFile)
    try {
        $after = [Drawing.Bitmap]::new($AfterFile)
        try {
            if ($before.Size -ne $after.Size -or $before.Width -ne $BeforeFrame.width -or $before.Height -ne $BeforeFrame.height -or
                $after.Width -ne $AfterFrame.width -or $after.Height -ne $AfterFrame.height) {
                throw 'The stationary physical field crop changed size.'
            }
            $columns = [Collections.Generic.HashSet[int]]::new()
            $rows = [Collections.Generic.HashSet[int]]::new()
            $changed = 0
            for ($y = 0; $y -lt $before.Height; $y++) {
                for ($x = 0; $x -lt $before.Width; $x++) {
                    if ($before.GetPixel($x, $y).ToArgb() -ne $after.GetPixel($x, $y).ToArgb()) {
                        [void]$columns.Add($x)
                        [void]$rows.Add($y)
                        $changed++
                    }
                }
            }
            # Count distinct columns and rows so a blinking or displaced insertion caret cannot qualify the edit.
            $material = $columns.Count -ge [Math]::Ceiling(6 * $Dpi / 96) -and $rows.Count -ge [Math]::Ceiling(3 * $Dpi / 96)
            return [ordered]@{pixels=$changed; columns=$columns.Count; rows=$rows.Count; textChanged=$material}
        } finally { $after.Dispose() }
    } finally { $before.Dispose() }
}

function Get-Field([string]$Name, $Role) {
    $condition = [Windows.Automation.PropertyCondition]::new(
        [Windows.Automation.AutomationElement]::ControlTypeProperty, $Role)
    foreach ($element in $root.FindAll($scope, $condition)) {
        if ((Get-AccessibleName $element) -ceq $Name) { return $element }
    }
    return $null
}

function Get-InitialEditor([ValidateSet('Dateiname','Kennwort')][string]$Name, $Condition) {
    # A null label has not been fully checked. Never persist provider-supplied text.
    $scan = [ordered]@{ requested=$Name; editCount=$null; Dateiname=$null; Kennwort=$null }
    $result.initialEditorSearch = $scan
    try {
        $elements = $root.FindAll($scope, $Condition)
        $scan.editCount = $elements.Count
        foreach ($element in $elements) {
            if ($element.Current.ProcessId -ne $SubjectId) { throw 'The UI Automation editor changed ownership.' }
            $label = Get-AccessibleName $element $SubjectId
            if ($label -cin @('Dateiname','Kennwort')) { $scan[$label] = $true }
            if ($label -ceq $Name) { return $element }
        }
        foreach ($expected in @('Dateiname','Kennwort')) {
            if ($null -eq $scan[$expected]) { $scan[$expected] = $false }
        }
    } catch {
        $failure = Get-UiaReadFailure $_
        if ($failure) {
            $scan.providerError = $failure
            throw 'UI Automation could not finish reading the owned German editors.'
        }
        throw
    }
    return $null
}

function Get-SubjectFocus {
    $element = [Windows.Automation.AutomationElement]::FocusedElement
    if ($null -ne $element -and $element.Current.ProcessId -eq $SubjectId) {
        return (Get-AccessibleName $element)
    }
    return ''
}

function Send-SubjectKeys([string]$Keys) {
    [uint32]$owner = 0
    [void][IfwObservedWindow]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -ne $SubjectId -or -not [IfwObservedWindow]::OnInputDesktop() -or
        [IfwObservedWindow]::GetForegroundWindow() -ne $handle) {
        throw 'The synthetic window does not own foreground input.'
    }
    [Windows.Forms.SendKeys]::SendWait($Keys)
}

function Get-FieldText($Element) {
    $pattern = $null
    if ($Element.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        return $pattern.Current.Value
    }
    if ($Element.TryGetCurrentPattern([Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
        return $pattern.DocumentRange.GetText(64)
    }
    throw 'The filename editor provides neither ValuePattern nor TextPattern.'
}

function Get-FilenameTextPattern($Element) {
    if ($Element.Current.ProcessId -ne $SubjectId -or $Element.Current.IsPassword -or
        (Get-AccessibleName $Element) -cne 'Filename' -or (Get-SubjectFocus) -cne 'Filename') {
        throw 'The translated synthetic filename editor does not own the current selection.'
    }
    $pattern = $null
    if (-not $Element.TryGetCurrentPattern([Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
        throw 'The synthetic filename editor does not expose a native text range.'
    }
    return $pattern
}

function Test-WholeFilenameSelected($Element, [string]$Expected) {
    $ranges = (Get-FilenameTextPattern $Element).GetSelection()
    return $ranges.Count -eq 1 -and $ranges[0].GetText(64) -ceq $Expected
}

function Test-SubjectLogLine([string]$Line) {
    $stream = [IO.File]::Open($SubjectLog, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $reader = [IO.StreamReader]::new($stream)
        try {
            while ($null -ne ($entry = $reader.ReadLine())) {
                if ($entry -ceq $Line) { return $true }
            }
            return $false
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

try {
    [uint32]$owner = 0
    [void][IfwObservedWindow]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -ne $SubjectId) { throw 'The HWND does not belong to the observed child.' }
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    if ($root.Current.ProcessId -ne $SubjectId) { throw 'UI Automation returned a different process.' }
    $result.dpi = [IfwObservedWindow]::GetDpiForWindow($handle)
    $result.monitorCount = [Windows.Forms.Screen]::AllScreens.Length
    $bounds = [Windows.Forms.Screen]::FromHandle($handle).Bounds
    $result.monitorPixels = @($bounds.Width, $bounds.Height)
    if ($result.dpi -eq 0) { throw 'Could not observe the native window DPI.' }
    $edit = [Windows.Automation.ControlType]::Edit
    $button = [Windows.Automation.ControlType]::Button
    $ownedEditors = [Windows.Automation.AndCondition]::new(
        [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty, $edit),
        [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ProcessIdProperty, $SubjectId))
    $file = Wait-Observation { Get-InitialEditor 'Dateiname' $ownedEditors } 'German filename label'
    $password = Wait-Observation { Get-InitialEditor 'Kennwort' $ownedEditors } 'German password label'
    $english = Wait-Observation { Get-Field 'English' $button } 'language button'
    $result.germanLabels = @((Get-AccessibleName $file), (Get-AccessibleName $password), (Get-AccessibleName $english))
    $result.passwordProperty = $password.Current.IsPassword
    foreach ($element in @($file, $password, $english)) {
        if (-not $element.Current.IsKeyboardFocusable) { throw 'A named control is not keyboard focusable.' }
    }
    if (-not $result.passwordProperty) { throw 'Password editor lacks its UI Automation protected property.' }
    if ($RecoveryPhase -ceq 'after') {
        $until = [DateTime]::UtcNow.AddSeconds(3)
        do {
            $result.focusBeforeActivation = Get-SubjectFocus
            if ($result.focusBeforeActivation -ceq 'Dateiname') { break }
            Start-Sleep -Milliseconds 75
        } while ([DateTime]::UtcNow -lt $until)
    }
    $result.onInputDesktop = [IfwObservedWindow]::OnInputDesktop()
    $result.session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    $result.activeConsoleSession = [IfwObservedWindow]::WTSGetActiveConsoleSessionId()
    $result.activation = [ordered]@{ setForeground = [IfwObservedWindow]::SetForegroundWindow($handle) }
    if ([IfwObservedWindow]::GetForegroundWindow() -ne $handle -and $result.onInputDesktop) {
        try { $file.SetFocus(); $result.activation.uiaFocus = 'requested' }
        catch { $result.activation.uiaFocus = 'unavailable' }
        if ([IfwObservedWindow]::GetForegroundWindow() -ne $handle) {
            $rect = $file.Current.BoundingRectangle
            if (-not $rect.IsEmpty -and $rect.Width -gt 0 -and $rect.Height -gt 0) {
                $targetX = [int]($rect.Left + $rect.Width / 2)
                $targetY = [int]($rect.Top + $rect.Height / 2)
                $result.activation.ownedAtPoint = [IfwObservedWindow]::SubjectAt($handle, $SubjectId, $targetX, $targetY)
                $result.activation.fieldCenter = @($targetX, $targetY)
                $raised = $false
                try {
                    if (-not $result.activation.ownedAtPoint) {
                        $raised = [IfwObservedWindow]::OrderOwnTestWindow($handle, $SubjectId, $true)
                        $result.activation.raisedOwnWindow = $raised
                        if ($raised) { Start-Sleep -Milliseconds 125 }
                    }
                    $result.activation.ownedControlClick = [IfwObservedWindow]::ClickOwnedControl($handle, $SubjectId, $targetX, $targetY)
                } finally {
                    if ($raised) { [void][IfwObservedWindow]::OrderOwnTestWindow($handle, $SubjectId, $false) }
                }
            }
        }
    }
    $result.foreground = Wait-Observation { [IfwObservedWindow]::GetForegroundWindow() -eq $handle } 'owned foreground'
    if ($RecoveryPhase) {
        $draft = 'recoverydraft'
        if ($RecoveryPhase -ceq 'before') {
            for ($i = 0; $i -lt 6 -and (Get-SubjectFocus) -cne 'Dateiname'; $i++) {
                Send-SubjectKeys '{TAB}'
                Start-Sleep -Milliseconds 125
            }
            if ((Get-SubjectFocus) -cne 'Dateiname') { throw 'Cannot seed the focused filename.' }
            Send-SubjectKeys '^a'
            Send-SubjectKeys $draft
        } else {
            if ((Get-FieldText $file) -cne $draft) { throw 'The replacement window lost the edited filename.' }
            if ((Get-SubjectFocus) -cne 'Dateiname') { throw 'The replacement did not focus the filename.' }
            $result.restoredFrame = Capture-SubjectField $file 'restored'
            Send-SubjectKeys '{END}'
            Send-SubjectKeys 'after'
            $draft += 'after'
        }
        [void](Wait-Observation { (Get-FieldText $file) -ceq $draft } 'native filename edit')
        Start-Sleep -Milliseconds 160
        if ($RecoveryPhase -ceq 'after') {
            [void](Wait-Observation {
                $result.editedFrame = Capture-SubjectField $file 'edited'
                $result.difference = Get-FieldPixelDifference "$OutputFile.restored.png" "$OutputFile.edited.png" $result.restoredFrame $result.editedFrame $result.dpi
                $result.difference.textChanged
            } 'material changes in the stationary filename pixels')
            if ($result.focusBeforeActivation -cne 'Dateiname') { throw 'Native focus required observer intervention after recovery.' }
        } else {
            $result.editedFrame = Capture-SubjectField $file 'edited'
        }
        $result.draft = $draft
        $result.status = 'passed'
        return
    }
    for ($i = 0; $i -lt 7; $i++) {
        $name = Get-SubjectFocus
        if ($name -cin @('Dateiname','Kennwort','English')) { $result.focus += $name }
        if ($name -cin @('Dateiname', 'Kennwort')) { Wait-ReaderCue $name }
        if ($name -ceq 'Kennwort') { break }
        Send-SubjectKeys '{TAB}'
        Start-Sleep -Milliseconds 125
    }
    if ((Get-SubjectFocus) -cne 'Kennwort') { throw 'Tab did not reach the password editor.' }
    $length = 0
    foreach ($key in @('x','y','z')) {
        if ((Get-SubjectFocus) -cne 'Kennwort') { throw 'The synthetic password editor lost focus.' }
        Send-SubjectKeys $key
        $length++
        [void](Wait-Observation {
            Test-SubjectLogLine "EDIT masked chars=$length"
        } 'password edit length')
        Wait-ReaderCue "mask-$length"
    }
    $result.passwordCharactersTyped = $length
    # A protected provider may reject access, omit a pattern, or return masks.
    # Record only the behavior, never the provider's returned password string.
    $result.passwordPatterns = [ordered]@{}
    foreach ($kind in @('Value','Text')) {
        $pattern = $null
        $id = if ($kind -eq 'Value') { [Windows.Automation.ValuePattern]::Pattern }
              else { [Windows.Automation.TextPattern]::Pattern }
        if (-not $password.TryGetCurrentPattern($id, [ref]$pattern)) {
            $result.passwordPatterns[$kind] = 'unavailable'
            continue
        }
        try {
            $value = if ($kind -eq 'Value') { $pattern.Current.Value }
                     else { $pattern.DocumentRange.GetText(8) }
        } catch {
            $result.passwordPatterns[$kind] = 'access-refused'
            continue
        }
        if ($value -and $value -cne ([string][char]0x2022 * 3)) {
            throw 'Protected text provider exposed an unexpected value.'
        }
        $result.passwordPatterns[$kind] = if ($value) { 'three-masks' } else { 'empty' }
    }
    Send-SubjectKeys '{TAB}'
    [void](Wait-Observation { (Get-SubjectFocus) -ceq 'English' } 'language button focus')
    $result.focus += 'English'
    Wait-ReaderCue 'English'
    Send-SubjectKeys ' '
    $file = Wait-Observation { Get-Field 'Filename' $edit } 'English filename label'
    $password = Wait-Observation { Get-Field 'Password' $edit } 'English password label'
    $result.englishLabels = @((Get-AccessibleName $file), (Get-AccessibleName $password))
    Send-SubjectKeys '{TAB}'
    [void](Wait-Observation { (Get-SubjectFocus) -ceq 'Filename' } 'translated filename focus')
    $result.focus += 'Filename'
    Wait-ReaderCue 'Filename'
    $expected = 'Gr' + [char]0xfc + [char]0xdf + 'e ' + [char]0x2013 + ' Sommer.jpg'
    if ($SpeechCues) {
        . (Join-Path $PSScriptRoot 'windows-reader/clipboard.ps1')
        Test-ReaderClipboard $file $expected
        $result.status = 'passed'
        return
    }
    if ((Get-FieldText $file) -cne $expected) { throw 'Synthetic Unicode filename differs before copy.' }
    $before = [IfwObservedWindow]::GetClipboardSequenceNumber()
    Send-SubjectKeys '^a'
    [void](Wait-Observation { Test-WholeFilenameSelected $file $expected } 'whole filename selected for copy')
    Send-SubjectKeys '^c'
    [void](Wait-Observation { [IfwObservedWindow]::GetClipboardSequenceNumber() -ne $before } 'clipboard change')
    [void](Wait-Observation { [Windows.Forms.Clipboard]::GetText() -ceq $expected } 'copied synthetic name')
    $result.clipboardCopied = $true
    # A reader can process its own selection announcements after the copy command.
    Send-SubjectKeys '^a'
    $result.wholeFilenameSelectedBeforeDelete = Wait-Observation {
        Test-WholeFilenameSelected $file $expected
    } 'whole filename selected for deletion'
    Send-SubjectKeys '{DELETE}'
    [void](Wait-Observation {
        $range = (Get-FilenameTextPattern $file).DocumentRange
        $value = Get-FieldText $file
        $result.filenameLengthAfterDelete = ([string]$value).Length
        $result.filenameRangeLengthAfterDelete = ([string]$range.GetText(64)).Length
        $result.emptyDocumentRange = $range.CompareEndpoints(
            [Windows.Automation.Text.TextPatternRangeEndpoint]::Start, $range,
            [Windows.Automation.Text.TextPatternRangeEndpoint]::End) -eq 0
        $result.emptyDocumentRange -and $result.filenameRangeLengthAfterDelete -eq 0 -and
            $result.filenameLengthAfterDelete -eq 0
    } 'empty filename after clear')
    Send-SubjectKeys '^v'
    [void](Wait-Observation { (Get-FieldText $file) -ceq $expected } 'native Unicode paste')
    $result.unicodeClipboardRoundTrip = $true
    $result.status = 'passed'
} catch {
    $result.error = $_.Exception.Message
    throw
} finally {
    [IO.File]::WriteAllText($OutputFile, ($result | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
}
