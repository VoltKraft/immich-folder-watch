using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App.Services;

public sealed class TrayIconHost : IDisposable
{
    private const int WM_USER = 0x0400;
    private const int WM_TRAYICON = WM_USER + 1;
    private const int WM_LBUTTONDBLCLK = 0x0203;
    private const int WM_RBUTTONUP = 0x0205;
    private const int WM_CONTEXTMENU = 0x007B;

    private const uint NIM_ADD = 0x0;
    private const uint NIM_MODIFY = 0x1;
    private const uint NIM_DELETE = 0x2;
    private const uint NIM_SETVERSION = 0x4;

    private const uint NIF_MESSAGE = 0x1;
    private const uint NIF_ICON = 0x2;
    private const uint NIF_TIP = 0x4;

    private const uint NOTIFYICON_VERSION_4 = 4;

    private const uint TPM_RETURNCMD = 0x0100;
    private const uint TPM_RIGHTBUTTON = 0x0002;
    private const uint TPM_BOTTOMALIGN = 0x0020;
    private const uint TPM_RIGHTALIGN = 0x0008;

    private const uint MF_STRING = 0x0;
    private const uint MF_SEPARATOR = 0x800;

    private const int MenuIdOpen = 1;
    private const int MenuIdRestart = 2;
    private const int MenuIdQuit = 3;

    private static readonly IntPtr HWND_MESSAGE = new(-3);
    private static readonly Guid IconGuid = new("27A1B1E9-6CD6-4F69-8B69-1D0C41E45C7E");

    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly LocalizationService _localizationService;
    private readonly HwndSource _messageWindow;
    private readonly IntPtr _hIcon;
    private readonly Guid _iconGuid;
    private bool _added;
    private bool _disposed;

    public event Action? OpenGuiRequested;
    public event Action? RestartRequested;
    public event Action? QuitRequested;

    public TrayIconHost(SyncStatusProvider syncStatusProvider, ThemeWatcher themeWatcher, LocalizationService localizationService)
    {
        ArgumentNullException.ThrowIfNull(themeWatcher);
        _syncStatusProvider = syncStatusProvider ?? throw new ArgumentNullException(nameof(syncStatusProvider));
        _localizationService = localizationService ?? throw new ArgumentNullException(nameof(localizationService));
        _iconGuid = IconGuid;

        TryEnableDarkMenus();

        var parameters = new HwndSourceParameters("ImmichFolderWatchTrayReceiver")
        {
            ParentWindow = HWND_MESSAGE,
            WindowStyle = 0,
            ExtendedWindowStyle = 0,
            Width = 0,
            Height = 0,
        };
        _messageWindow = new HwndSource(parameters);
        _messageWindow.AddHook(WndProc);

        _hIcon = LoadApplicationIcon();

        AddTrayIcon();
        _syncStatusProvider.PropertyChanged += OnSyncStatusProviderPropertyChanged;
        _localizationService.LanguageChanged += OnLanguageChanged;
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _syncStatusProvider.PropertyChanged -= OnSyncStatusProviderPropertyChanged;
        _localizationService.LanguageChanged -= OnLanguageChanged;

        if (_added)
        {
            var data = CreateBaseData();
            Shell_NotifyIconW(NIM_DELETE, ref data);
            _added = false;
        }

        _messageWindow.RemoveHook(WndProc);
        _messageWindow.Dispose();

        if (_hIcon != IntPtr.Zero)
        {
            DestroyIcon(_hIcon);
        }
    }

    private void AddTrayIcon()
    {
        var data = CreateBaseData();
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        data.uCallbackMessage = WM_TRAYICON;
        data.hIcon = _hIcon;
        data.szTip = TrimTooltip(ComposeTooltip());

        if (!Shell_NotifyIconW(NIM_ADD, ref data))
        {
            return;
        }

        _added = true;

        var versionData = CreateBaseData();
        versionData.uTimeoutOrVersion = NOTIFYICON_VERSION_4;
        Shell_NotifyIconW(NIM_SETVERSION, ref versionData);
    }

    private NOTIFYICONDATAW CreateBaseData()
    {
        return new NOTIFYICONDATAW
        {
            cbSize = (uint)Marshal.SizeOf<NOTIFYICONDATAW>(),
            hWnd = _messageWindow.Handle,
            uID = 1,
            szTip = string.Empty,
            szInfo = string.Empty,
            szInfoTitle = string.Empty,
            guidItem = _iconGuid,
        };
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg != WM_TRAYICON)
        {
            return IntPtr.Zero;
        }

        var mouseMessage = (int)((ulong)lParam.ToInt64() & 0xFFFF);
        switch (mouseMessage)
        {
            case WM_LBUTTONDBLCLK:
                OpenGuiRequested?.Invoke();
                handled = true;
                break;
            case WM_RBUTTONUP:
            case WM_CONTEXTMENU:
                ShowContextMenu();
                handled = true;
                break;
        }

        return IntPtr.Zero;
    }

    private void ShowContextMenu()
    {
        if (!GetCursorPos(out var point))
        {
            return;
        }

        var menu = CreatePopupMenu();
        if (menu == IntPtr.Zero)
        {
            return;
        }

        try
        {
            AppendMenuW(menu, MF_STRING, (IntPtr)MenuIdOpen, Strings.Tray_Open);
            AppendMenuW(menu, MF_SEPARATOR, IntPtr.Zero, string.Empty);
            AppendMenuW(menu, MF_STRING, (IntPtr)MenuIdRestart, Strings.Tray_Restart);
            AppendMenuW(menu, MF_SEPARATOR, IntPtr.Zero, string.Empty);
            AppendMenuW(menu, MF_STRING, (IntPtr)MenuIdQuit, Strings.Tray_Quit);

            SetForegroundWindow(_messageWindow.Handle);

            var selection = TrackPopupMenuEx(
                menu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RIGHTALIGN,
                point.X,
                point.Y,
                _messageWindow.Handle,
                IntPtr.Zero);

            switch (selection)
            {
                case MenuIdOpen:
                    OpenGuiRequested?.Invoke();
                    break;
                case MenuIdRestart:
                    RestartRequested?.Invoke();
                    break;
                case MenuIdQuit:
                    QuitRequested?.Invoke();
                    break;
            }
        }
        finally
        {
            DestroyMenu(menu);
        }
    }

    private void OnSyncStatusProviderPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (!IsTooltipProperty(e.PropertyName))
        {
            return;
        }

        RefreshTooltip();
    }

    private void OnLanguageChanged(object? sender, EventArgs e)
    {
        RefreshTooltip();
    }

    private static bool IsTooltipProperty(string? propertyName)
    {
        return propertyName is nameof(SyncStatusProvider.ServerConnection)
            or nameof(SyncStatusProvider.LastSyncCompletedUtc)
            or nameof(SyncStatusProvider.PendingCount);
    }

    private void RefreshTooltip()
    {
        var tooltip = TrimTooltip(ComposeTooltip());
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null)
        {
            UpdateTooltip(tooltip);
            return;
        }

        dispatcher.BeginInvoke(new Action(() =>
        {
            if (!_disposed)
            {
                UpdateTooltip(tooltip);
            }
        }));
    }

    private string ComposeTooltip()
    {
        var server = _syncStatusProvider.ServerConnection switch
        {
            ServerConnectionState.Ok => Strings.Server_Ok,
            ServerConnectionState.Error => Strings.Server_Error,
            ServerConnectionState.Checking => Strings.Server_Checking,
            _ => Strings.Server_Unknown,
        };

        var lastSync = _syncStatusProvider.LastSyncCompletedUtc.HasValue
            ? _syncStatusProvider.LastSyncCompletedUtc.Value.ToLocalTime().ToString("HH:mm", _localizationService.CurrentCulture)
            : "—";

        var culture = _localizationService.CurrentCulture;
        return string.Create(culture, $"Immich Folder Watch\n{Strings.UI_ServerConnection}: {server}\n{Strings.Tooltip_LastSync}: {lastSync}\n{Strings.Tooltip_Queue}: {_syncStatusProvider.PendingCount}");
    }

    private void UpdateTooltip(string tooltip)
    {
        if (!_added)
        {
            return;
        }

        var data = CreateBaseData();
        data.uFlags = NIF_TIP;
        data.szTip = tooltip;
        Shell_NotifyIconW(NIM_MODIFY, ref data);
    }

    private static string TrimTooltip(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return "Immich Folder Watch";
        }

        return value.Length > 127 ? value[..127] : value;
    }

    private static IntPtr LoadApplicationIcon()
    {
        try
        {
            var processPath = Environment.ProcessPath;
            if (!string.IsNullOrWhiteSpace(processPath) && File.Exists(processPath))
            {
                var large = new IntPtr[1];
                var small = new IntPtr[1];
                var count = ExtractIconExW(processPath, 0, large, small, 1);
                if (count > 0)
                {
                    if (small[0] != IntPtr.Zero)
                    {
                        if (large[0] != IntPtr.Zero)
                        {
                            DestroyIcon(large[0]);
                        }
                        return small[0];
                    }

                    if (large[0] != IntPtr.Zero)
                    {
                        return large[0];
                    }
                }
            }
        }
        catch (Exception)
        {
        }

        return LoadIconW(IntPtr.Zero, (IntPtr)32512);
    }

    private static void TryEnableDarkMenus()
    {
        try
        {
            var hModule = LoadLibraryW("uxtheme.dll");
            if (hModule == IntPtr.Zero)
            {
                return;
            }

            var proc = GetProcAddress(hModule, (IntPtr)135);
            if (proc == IntPtr.Zero)
            {
                return;
            }

            var setPreferredAppMode = Marshal.GetDelegateForFunctionPointer<SetPreferredAppModeDelegate>(proc);
            setPreferredAppMode(PreferredAppMode.AllowDark);
        }
        catch (Exception)
        {
        }
    }

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int SetPreferredAppModeDelegate(PreferredAppMode mode);

    private enum PreferredAppMode
    {
        Default = 0,
        AllowDark = 1,
        ForceDark = 2,
        ForceLight = 3,
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NOTIFYICONDATAW
    {
        public uint cbSize;
        public IntPtr hWnd;
        public uint uID;
        public uint uFlags;
        public uint uCallbackMessage;
        public IntPtr hIcon;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string szTip;

        public uint dwState;
        public uint dwStateMask;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string szInfo;

        public uint uTimeoutOrVersion;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)]
        public string szInfoTitle;

        public uint dwInfoFlags;
        public Guid guidItem;
        public IntPtr hBalloonIcon;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int X;
        public int Y;
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool Shell_NotifyIconW(uint dwMessage, ref NOTIFYICONDATAW lpData);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int ExtractIconExW(string lpszFile, int nIconIndex, IntPtr[] phIconLarge, IntPtr[] phIconSmall, uint nIcons);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool DestroyIcon(IntPtr hIcon);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadIconW(IntPtr hInstance, IntPtr lpIconName);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr CreatePopupMenu();

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool DestroyMenu(IntPtr hMenu);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool AppendMenuW(IntPtr hMenu, uint uFlags, IntPtr uIDNewItem, string lpNewItem);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int TrackPopupMenuEx(IntPtr hMenu, uint uFlags, int x, int y, IntPtr hwnd, IntPtr lptpm);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool GetCursorPos(out POINT lpPoint);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryW(string lpLibFileName);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr hModule, IntPtr lpProcName);
}
