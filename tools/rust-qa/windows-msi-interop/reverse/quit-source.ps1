# Read the original upgrade-test helper as data without executing the installer harness.
# Requires PowerShell 7 for the native trial and for the portable compiler control.
function Get-InstalledUpgradeQuitSource {
    param([string]$Path = (Join-Path $PSScriptRoot '../../../../packaging/windows/Test-InstalledUpgrade.ps1'))

    $raw = [IO.File]::ReadAllBytes($Path)
    $scriptText = [Text.UTF8Encoding]::new($false, $true).GetString($raw).Replace("`r`n", "`n")
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($scriptText, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'Could not parse the installed upgrade reference.' }
    $functions = @($ast.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Close-TestApplicationGracefully'
    }, $true))
    if ($functions.Count -ne 1) { throw 'Expected the unique installed upgrade Quit function.' }
    $commands = @($functions[0].Body.FindAll({ param($node)
        $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -ceq 'Add-Type'
    }, $true))
    if ($commands.Count -ne 1) { throw 'Expected the unique Add-Type in the installed upgrade Quit function.' }
    $arguments = $commands[0].CommandElements
    if ($arguments.Count -ne 3 -or $arguments[1] -isnot [Management.Automation.Language.CommandParameterAst] -or
        $arguments[1].ParameterName -cne 'TypeDefinition' -or
        $arguments[2] -isnot [Management.Automation.Language.StringConstantExpressionAst] -or
        $arguments[2].StringConstantType -ne 'SingleQuotedHereString') {
        throw 'Expected a literal native helper source in the installed upgrade Quit function.'
    }
    $code = $arguments[2].Value
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($code))).Replace('-', '').ToLowerInvariant()
    } finally { $hash.Dispose() }
    # v3.0.4, commit 4149763b7f322603a012aebad5f8a252450eb08b, with checkout CRLF normalized to LF.
    if ($digest -cne 'f50baad6accfd09afc3e86beb9908027b8498525f6a787f35d217841c86c9e5c') {
        throw 'The installed 3.0.4 native Quit source digest differs.'
    }
    return [pscustomobject]@{ Code = $code; Sha256 = $digest }
}

function Add-InstalledQuitReceiverCheck {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public sealed class InstalledQuitReceiver
{
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int x, y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int left, top, right, bottom; }
    public sealed class Window
    {
        public long hwnd, root;
        public uint pid, tid, rootPid, rootTid;
    }
    public sealed class Anchor
    {
        public string dpiContext;
        public Rect? clientRect;
        public Point? point, cursor, physicalCursor;
        public Window before, after;
    }
    public sealed class Popup
    {
        public Window window, hit;
        public long owner, menu;
        public int itemCount;
        public uint? lastId;
        public Rect? quitRect;
    }
    public sealed class Diagnostic
    {
        public Window foreground, root, receiver;
        public readonly List<Popup> popups = new List<Popup>();
        public bool enumerated;
    }
    public Anchor anchor = new Anchor();
    public string stage = "identity";
    public Diagnostic diagnostic;
    public string diagnosticError;

    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern IntPtr FindWindowExW(IntPtr parent, IntPtr after, string className, string title);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
    [DllImport("user32.dll")] private static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern bool GetUserObjectInformationW(IntPtr handle, int index, out int value, int size, out int needed);
    [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr hwnd, uint command);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool GetClientRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll")] private static extern bool ClientToScreen(IntPtr hwnd, ref Point point);
    [DllImport("user32.dll")] private static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] private static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] private static extern bool GetPhysicalCursorPos(out Point point);
    [DllImport("user32.dll")] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] private static extern IntPtr GetThreadDpiAwarenessContext();
    [DllImport("user32.dll")] private static extern bool AreDpiAwarenessContextsEqual(IntPtr a, IntPtr b);
    private delegate bool EnumWindow(IntPtr hwnd, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool EnumThreadWindows(uint thread, EnumWindow callback, IntPtr parameter);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int GetClassNameW(IntPtr hwnd, StringBuilder name, int length);
    [DllImport("user32.dll", ExactSpelling = true)]
    private static extern IntPtr SendMessageTimeoutW(IntPtr hwnd, uint msg, UIntPtr wp, IntPtr lp, uint flags, uint milliseconds, out UIntPtr result);
    [DllImport("user32.dll")] private static extern int GetMenuItemCount(IntPtr menu);
    [DllImport("user32.dll")] private static extern uint GetMenuItemID(IntPtr menu, int position);
    [DllImport("user32.dll")] private static extern bool GetMenuItemRect(IntPtr hwnd, IntPtr menu, uint item, out Rect rect);

    private static bool IsInputDesktop(uint thread)
    {
        IntPtr desktop = GetThreadDesktop(thread);
        int receivesInput, needed;
        return desktop != IntPtr.Zero &&
            GetUserObjectInformationW(desktop, 6, out receivesInput, sizeof(int), out needed) && receivesInput != 0;
    }

    public static bool Matches(IntPtr receiver, uint expectedPid, uint expectedThread)
    {
        var messages = new IntPtr(-3);
        const string title = "ImmichFolderWatchTrayReceiver";
        uint pid;
        return receiver != IntPtr.Zero && FindWindowExW(messages, IntPtr.Zero, null, title) == receiver &&
            GetWindowThreadProcessId(receiver, out pid) == expectedThread && pid == expectedPid &&
            IsInputDesktop(expectedThread) && IsInputDesktop(GetCurrentThreadId());
    }

    private static Window Identify(IntPtr hwnd)
    {
        var result = new Window { hwnd = hwnd.ToInt64() };
        if (hwnd != IntPtr.Zero)
        {
            result.tid = GetWindowThreadProcessId(hwnd, out result.pid);
            var root = GetAncestor(hwnd, 2); // GA_ROOT
            result.root = root.ToInt64();
            if (root != IntPtr.Zero) result.rootTid = GetWindowThreadProcessId(root, out result.rootPid);
        }
        return result;
    }

    public static bool IsOwnedHit(Window hit, long root, uint pid, uint tid)
    {
        return root > 0 && pid != 0 && tid != 0 && hit != null && hit.hwnd > 0 && hit.root == root &&
            hit.pid == pid && hit.tid == tid && hit.rootPid == pid && hit.rootTid == tid;
    }

    public static Point Interior(Rect rect)
    {
        long width = (long)rect.right - rect.left, height = (long)rect.bottom - rect.top;
        if (width < 4 || height < 4) throw new InvalidOperationException("The original client rectangle has no interior menu anchor.");
        // The shipping menu opens above and to the left of GetCursorPos().
        return new Point { x = (int)(rect.left + 3 * width / 4), y = (int)(rect.top + 3 * height / 4) };
    }

    public bool Confirmed(Rect current, long root, uint pid, uint tid)
    {
        return anchor.clientRect.Equals(current) && anchor.point.Equals(Interior(current)) &&
            anchor.cursor.Equals(anchor.point) && anchor.physicalCursor.Equals(anchor.point) &&
            IsOwnedHit(anchor.before, root, pid, tid) && IsOwnedHit(anchor.after, root, pid, tid);
    }

    private static Rect ClientScreenRect(IntPtr root)
    {
        if (!GetClientRect(root, out Rect rect)) throw new InvalidOperationException("Cannot measure the original client rectangle.");
        var origin = new Point { x = rect.left, y = rect.top };
        var end = new Point { x = rect.right, y = rect.bottom };
        if (!ClientToScreen(root, ref origin) || !ClientToScreen(root, ref end))
            throw new InvalidOperationException("Cannot map the original client rectangle to the screen.");
        return new Rect { left = origin.x, top = origin.y, right = end.x, bottom = end.y };
    }

    private static void CheckIdentity(IntPtr root, IntPtr receiver, uint pid, uint tid)
    {
        if (root == receiver || !Matches(receiver, pid, tid) || !IsOwnedHit(Identify(root), root.ToInt64(), pid, tid) ||
            !IsWindowVisible(root) || IsIconic(root))
            throw new InvalidOperationException("The original visible WPF root, tray receiver or input desktop changed.");
    }

    private static Diagnostic Inspect(IntPtr root, IntPtr receiver, uint pid, uint tid)
    {
        var result = new Diagnostic { root = Identify(root), receiver = Identify(receiver), foreground = Identify(GetForegroundWindow()) };
        // Observe only popups on the original UI thread; never send a query to a foreign window.
        result.enumerated = EnumThreadWindows(tid, (hwnd, unused) => {
            if (GetWindowThreadProcessId(hwnd, out uint ownerPid) != tid || ownerPid != pid) return true;
            var name = new StringBuilder(32);
            if (GetClassNameW(hwnd, name, name.Capacity) == 0 || name.ToString() != "#32768") return true;
            var popup = new Popup { window = Identify(hwnd), owner = GetWindow(hwnd, 4).ToInt64(), itemCount = -1 }; // GW_OWNER
            result.popups.Add(popup);
            if (GetWindowThreadProcessId(hwnd, out ownerPid) == tid && ownerPid == pid &&
                SendMessageTimeoutW(hwnd, 0x01E1, UIntPtr.Zero, IntPtr.Zero, 3, 250, out UIntPtr handle) != IntPtr.Zero)
            {
                var menu = new IntPtr(unchecked((long)handle.ToUInt64())); // MN_GETHMENU
                popup.menu = menu.ToInt64();
                if (menu != IntPtr.Zero) popup.itemCount = GetMenuItemCount(menu);
                if (popup.itemCount > 0)
                {
                    int last = popup.itemCount - 1;
                    popup.lastId = GetMenuItemID(menu, last);
                    if (popup.lastId == 3 && GetMenuItemRect(IntPtr.Zero, menu, (uint)last, out Rect rect) &&
                        rect.right > rect.left && rect.bottom > rect.top)
                    {
                        popup.quitRect = rect;
                        var middle = new Point { x = (int)(rect.left + ((long)rect.right - rect.left) / 2),
                                                 y = (int)(rect.top + ((long)rect.bottom - rect.top) / 2) };
                        popup.hit = Identify(WindowFromPoint(middle));
                    }
                }
            }
            return result.popups.Count < 8;
        }, IntPtr.Zero);
        return result;
    }

    public string Invoke(IntPtr root, IntPtr receiver, uint pid, uint tid, Func<int, string> close)
    {
        var pmv2 = new IntPtr(-4);
        var previous = SetThreadDpiAwarenessContext(pmv2);
        if (previous == IntPtr.Zero) throw new InvalidOperationException("Cannot set the observer thread DPI context.");
        try
        {
            if (!AreDpiAwarenessContextsEqual(GetThreadDpiAwarenessContext(), pmv2))
                throw new InvalidOperationException("Expected per-monitor-v2 screen coordinates.");
            anchor.dpiContext = "per-monitor-v2";
            CheckIdentity(root, receiver, pid, tid);
            stage = "anchor-before";
            var rect = ClientScreenRect(root);
            anchor.clientRect = rect;
            var point = Interior(rect);
            anchor.point = point;
            anchor.before = Identify(WindowFromPoint(point));
            if (!IsOwnedHit(anchor.before, root.ToInt64(), pid, tid))
                throw new InvalidOperationException("The menu anchor does not hit the original WPF client.");
            stage = "anchor-position";
            if (!SetCursorPos(point.x, point.y)) throw new InvalidOperationException("Cannot position the cursor on the original WPF client.");
            stage = "anchor-after";
            if (!GetCursorPos(out Point cursor) || !GetPhysicalCursorPos(out Point physical))
                throw new InvalidOperationException("Cannot read the positioned cursor.");
            anchor.cursor = cursor; anchor.physicalCursor = physical;
            anchor.after = Identify(WindowFromPoint(cursor));
            CheckIdentity(root, receiver, pid, tid);
            if (!Confirmed(ClientScreenRect(root), root.ToInt64(), pid, tid))
                throw new InvalidOperationException("The confirmed menu anchor, client rectangle or original WPF root changed.");
            stage = "original-close";
            return close(checked((int)pid));
        }
        catch
        {
            try
            {
                if (IsInputDesktop(tid) && IsInputDesktop(GetCurrentThreadId()))
                    diagnostic = Inspect(root, receiver, pid, tid);
            }
            catch (Exception e) { diagnosticError = e.Message; }
            throw;
        }
        finally
        {
            if (SetThreadDpiAwarenessContext(previous) == IntPtr.Zero)
                throw new InvalidOperationException("Cannot restore the observer thread DPI context.");
        }
    }
}
'@
}
