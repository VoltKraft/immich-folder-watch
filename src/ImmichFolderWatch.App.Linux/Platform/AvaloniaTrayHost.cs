using System.ComponentModel;
using System.Runtime.InteropServices;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using Avalonia.Threading;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging;
using Tmds.DBus.Protocol;
using AvaloniaApplication = Avalonia.Application;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class AvaloniaTrayHost : IDisposable
{
    private readonly ILogger<AvaloniaTrayHost> _logger;
    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly LocalizationService _localizationService;
    private readonly CancellationTokenSource _lifetime = new();
    private StatusNotifierItem? _item;
    private bool _disposed;

    public AvaloniaTrayHost(SyncStatusProvider syncStatusProvider,
        LocalizationService localizationService, ILogger<AvaloniaTrayHost> logger)
    {
        _logger = logger;
        _syncStatusProvider = syncStatusProvider;
        _localizationService = localizationService;
        _syncStatusProvider.PropertyChanged += OnSyncStatusChanged;
        _localizationService.LanguageChanged += OnLanguageChanged;
    }

    public bool IsTrayAvailable => _item?.IsRegistered == true;

    /// <summary>True only after the desktop watcher acknowledges registration.</summary>
    public bool IsTrayIconRegistered => IsTrayAvailable;
    public event EventHandler? OpenRequested;
    public event EventHandler? RestartRequested;
    public event EventHandler? QuitRequested;
    public event EventHandler? TrayUnavailable;
    public event EventHandler? TrayAvailable;

    public async Task StartAsync(AvaloniaApplication application, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(application);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _lifetime.Token);
        try
        {
            var address = DBusAddress.Session ?? throw new InvalidOperationException("No session D-Bus address.");
            var icon = await Dispatcher.UIThread.InvokeAsync(LoadIcon);
            linked.Token.ThrowIfCancellationRequested();
            _item = new StatusNotifierItem(address, icon.Width, icon.Height, icon.Pixels);
            _item.Activated += id => Dispatcher.UIThread.Post(() =>
            {
                if (_disposed) return;
                if (id == 1) OpenRequested?.Invoke(this, EventArgs.Empty);
                else if (id == 2) RestartRequested?.Invoke(this, EventArgs.Empty);
                else if (id == 3) QuitRequested?.Invoke(this, EventArgs.Empty);
            });
            _item.AvailabilityChanged += available => Dispatcher.UIThread.Post(() =>
            {
                if (_disposed) return;
                _logger.LogInformation("StatusNotifierWatcher registration available: {Available}", available);
                if (available) TrayAvailable?.Invoke(this, EventArgs.Empty);
                else TrayUnavailable?.Invoke(this, EventArgs.Empty);
            });
            RefreshTrayText();
            await _item.StartAsync(linked.Token).WaitAsync(TimeSpan.FromSeconds(5), linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (linked.IsCancellationRequested)
        {
            _item?.Dispose();
            _item = null;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Tray registration failed; running in window-only mode.");
            _item?.Dispose();
            _item = null;
            if (!_disposed) Dispatcher.UIThread.Post(() => TrayUnavailable?.Invoke(this, EventArgs.Empty));
        }
    }

    private static (int Width, int Height, byte[] Pixels) LoadIcon()
    {
        using var stream = AssetLoader.Open(new Uri("avares://immich-folder-watch/Assets/header-logo.png"));
        using var image = WriteableBitmap.DecodeToWidth(stream, 32);
        using var framebuffer = image.Lock();
        var raw = new byte[framebuffer.RowBytes * framebuffer.Size.Height];
        Marshal.Copy(framebuffer.Address, raw, 0, raw.Length);
        var pixels = new byte[framebuffer.Size.Width * framebuffer.Size.Height * 4];
        var bgra = framebuffer.Format == PixelFormat.Bgra8888;
        if (!bgra && framebuffer.Format != PixelFormat.Rgba8888)
            throw new InvalidOperationException("Tray image must decode to 32-bit BGRA or RGBA pixels.");
        for (var y = 0; y < framebuffer.Size.Height; y++)
        for (var x = 0; x < framebuffer.Size.Width; x++)
        {
            var source = y * framebuffer.RowBytes + x * 4;
            var target = (y * framebuffer.Size.Width + x) * 4;
            // StatusNotifierItem requires network-byte-order ARGB pixmaps.
            pixels[target] = raw[source + 3];
            pixels[target + 1] = raw[source + (bgra ? 2 : 0)];
            pixels[target + 2] = raw[source + 1];
            pixels[target + 3] = raw[source + (bgra ? 0 : 2)];
        }
        return (framebuffer.Size.Width, framebuffer.Size.Height, pixels);
    }

    private void OnSyncStatusChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(SyncStatusProvider.ServerConnection)
            or nameof(SyncStatusProvider.LastSyncCompletedUtc) or nameof(SyncStatusProvider.PendingCount)) RefreshTrayText();
    }

    private void OnLanguageChanged(object? sender, EventArgs e) => RefreshTrayText();
    private void RefreshTrayText() => Dispatcher.UIThread.Post(() =>
    {
        if (!_disposed) _item?.Update(TrayStatusText.Compose(_syncStatusProvider, _localizationService),
            Strings.Tray_Open, Strings.Tray_Restart, Strings.Tray_Quit);
    });

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _lifetime.Cancel();
        _syncStatusProvider.PropertyChanged -= OnSyncStatusChanged;
        _localizationService.LanguageChanged -= OnLanguageChanged;
        _item?.Dispose();
        _item = null;
    }
}
