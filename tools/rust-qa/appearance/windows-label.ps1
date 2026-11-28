param(
    [Parameter(Mandatory)][int]$SubjectId,
    [Parameter(Mandatory)][long]$WindowHandle,
    [Parameter(Mandatory)][ValidateSet('original','changed','restored')][string]$Phase,
    [Parameter(Mandatory)][string]$OutputFile
)
$ErrorActionPreference = 'Stop'
if ($env:IFW_QA_ISOLATED -cne '1') { throw 'A synthetic Windows profile is required.' }
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Drawing
$qa = Split-Path $PSScriptRoot
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $qa 'observe-windows-input.ps1'),[ref]$null,[ref]$errors)
$bridge = @($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
    $n.StringConstantType -eq 'SingleQuotedHereString' -and $n.Value.Contains('public static class IfwObservedWindow {')},$true))
if ($errors -or $bridge.Count -ne 1) { throw 'Could not locate the shared native window observer.' }
$native = @'
public static class IfwContrastWindows {
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int left, top, right, bottom; }
    [DllImport("user32.dll")] public static extern IntPtr GetTopWindow(IntPtr parent);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out Rect rect);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr window);
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    static extern bool GetUserObjectInformation(IntPtr obj, int index, System.Text.StringBuilder value, uint bytes, out uint needed);
    public static string ThreadDesktopName() {
        var name = new System.Text.StringBuilder(256);
        uint needed;
        return GetUserObjectInformation(GetThreadDesktop(GetCurrentThreadId()), 2, name, 512, out needed)
            ? name.ToString() : null;
    }
}
'@
$guard = @'
public static class IfwPassiveLabel {
    public static void RequireRegion(string desktop, IntPtr window, uint pid, int x, int y, int width, int height) {
        uint owner;
        if (!IfwObservedWindow.OnInputDesktop() ||
                !String.Equals(IfwContrastWindows.ThreadDesktopName(), desktop, StringComparison.OrdinalIgnoreCase) ||
                IfwObservedWindow.GetWindowThreadProcessId(window, out owner) == 0 || owner != pid ||
                !IfwContrastWindows.IsWindowVisible(window) || IfwContrastWindows.IsIconic(window))
            throw new InvalidOperationException("The label window is unavailable on its owned input desktop.");
        if (width < 4 || width > 512 || height < 4 || height > 96)
            throw new InvalidOperationException("Unexpected label bounds.");
        int right = checked(x + width), bottom = checked(y + height);
        // WindowFromPoint skips disabled windows. Also rule out any visible top-level window
        // above the subject whose rectangle covers a crop pixel, including transparent overlays.
        var top = IfwContrastWindows.GetTopWindow(IntPtr.Zero);
        for (int i = 0; top != window; ++i) {
            if (i == 256 || top == IntPtr.Zero)
                throw new InvalidOperationException("Could not establish the label window's Z order.");
            if (IfwContrastWindows.IsWindowVisible(top)) {
                IfwContrastWindows.Rect rect;
                if (!IfwContrastWindows.GetWindowRect(top, out rect) ||
                        rect.right < rect.left || rect.bottom < rect.top ||
                        (Math.Max(x, rect.left) < Math.Min(right, rect.right) &&
                         Math.Max(y, rect.top) < Math.Min(bottom, rect.bottom)))
                    throw new InvalidOperationException("Could not confirm an unobstructed label rectangle.");
            }
            top = IfwContrastWindows.GetWindow(top, 2); // GW_HWNDNEXT, immediately below this window
        }
        for (int j = y; j < bottom; ++j)
            for (int i = x; i < right; ++i)
                if (!IfwObservedWindow.SubjectAt(window, pid, i, j))
                    throw new InvalidOperationException("A label pixel does not hit the owned window.");
    }
}
'@
Add-Type -TypeDefinition ($bridge[0].Value + [Environment]::NewLine + $native + [Environment]::NewLine + $guard)
$handle = [IntPtr]::new($WindowHandle)
$report = [ordered]@{phase=$Phase; pid=$SubjectId; hwnd=$WindowHandle; status='failed'; samples=@()}
$oldDpi = [IfwContrastWindows]::SetThreadDpiAwarenessContext([IntPtr]::new(-4))
try {
    if ($oldDpi -eq [IntPtr]::Zero) { throw 'Cannot determine physical label coordinates.' }
    $ready = Get-Content -LiteralPath (Join-Path (Split-Path $OutputFile) 'control/ready.json') -Raw | ConvertFrom-Json
    if ($ready.desktop -cnotmatch '^IfwQa_[a-f0-9]{32}$' -or $ready.pid -ne $SubjectId -or $ready.hwnd -ne $WindowHandle) {
        throw 'The label window differs from the private desktop receipt.'
    }
    [uint32]$owner = 0
    $root = [Windows.Automation.AutomationElement]::FromHandle($handle)
    if (-not [IfwObservedWindow]::GetWindowThreadProcessId($handle,[ref]$owner) -or $owner -ne $SubjectId -or
        $root.Current.ProcessId -ne $SubjectId -or -not [IfwObservedWindow]::OnInputDesktop()) {
        throw 'The window and input desktop do not belong to this test.'
    }
    $text = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ControlTypeProperty,
                                                        [Windows.Automation.ControlType]::Text)
    $name = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty, 'Dateiname')
    $condition = [Windows.Automation.AndCondition]::new($text, $name)
    $until = [DateTime]::UtcNow.AddSeconds(7)
    do {
        $labels = $root.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)
        if ($labels.Count -eq 1) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $until)
    if ($labels.Count -ne 1) { throw 'The owned GUI has no unique Dateiname static label.' }
    $label = $labels.Item(0)
    $bounds = $label.Current.BoundingRectangle
    $x = [int][Math]::Ceiling($bounds.Left)
    $y = [int][Math]::Ceiling($bounds.Top)
    $width = [int][Math]::Floor($bounds.Right) - $x
    $height = [int][Math]::Floor($bounds.Bottom) - $y
    if ($label.Current.ProcessId -ne $SubjectId -or $label.Current.IsOffscreen -or $width -lt 4 -or $width -gt 512 -or
        $height -lt 4 -or $height -gt 96) { throw 'The static label has no usable owned capture rectangle.' }
    $report.label = 'Dateiname'
    $report.rect = @($x,$y,$width,$height)
    $report.runtimeId = $label.GetRuntimeId()
    foreach ($index in 1..2) {
        $bitmap = [Drawing.Bitmap]::new($width,$height,[Drawing.Imaging.PixelFormat]::Format24bppRgb)
        try {
            $graphics = [Drawing.Graphics]::FromImage($bitmap)
            try {
                [IfwPassiveLabel]::RequireRegion($ready.desktop,$handle,$SubjectId,$x,$y,$width,$height)
                $graphics.CopyFromScreen($x,$y,0,0,$bitmap.Size,[Drawing.CopyPixelOperation]::SourceCopy)
                [IfwPassiveLabel]::RequireRegion($ready.desktop,$handle,$SubjectId,$x,$y,$width,$height)
            } finally { $graphics.Dispose() }
            if ($label.Current.ProcessId -ne $SubjectId -or $label.Current.Name -cne 'Dateiname' -or
                -not $bounds.Equals($label.Current.BoundingRectangle)) { throw 'The owned label changed during capture.' }
            $image = "$OutputFile.$index.bmp"
            $bitmap.Save($image,[Drawing.Imaging.ImageFormat]::Bmp)
            $report.samples += @{file=[IO.Path]::GetFileName($image); sha256=(Get-FileHash -Algorithm SHA256 $image).Hash.ToLowerInvariant()}
        } finally { $bitmap.Dispose() }
        if ($index -eq 1) { Start-Sleep -Milliseconds 130 }
    }
    $report.status = 'observed'
} catch { $report.error = $_.Exception.GetBaseException().Message; throw }
finally {
    if ($oldDpi -ne [IntPtr]::Zero) { [void][IfwContrastWindows]::SetThreadDpiAwarenessContext($oldDpi) }
    [IO.File]::WriteAllText($OutputFile,($report | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
