using System.Windows;
using Microsoft.Win32;

namespace ImmichFolderWatch.App.Services;

public sealed class ThemeWatcher
{
    private const string LightPaletteUri = "pack://application:,,,/Styles/PaletteLight.xaml";
    private const string DarkPaletteUri = "pack://application:,,,/Styles/PaletteDark.xaml";

    private readonly Application _application;
    private bool _isDark;

    public ThemeWatcher(Application application)
    {
        _application = application ?? throw new ArgumentNullException(nameof(application));
    }

    public event EventHandler? ThemeChanged;

    public bool IsDark => _isDark;

    public void Initialize()
    {
        _isDark = DetectSystemIsDark();
        ApplyPalette(_isDark);
    }

    public void Refresh()
    {
        var nowDark = DetectSystemIsDark();
        if (nowDark == _isDark)
        {
            return;
        }

        _isDark = nowDark;
        _application.Dispatcher.BeginInvoke(new Action(() =>
        {
            ApplyPalette(_isDark);
            ThemeChanged?.Invoke(this, EventArgs.Empty);
        }));
    }

    private void ApplyPalette(bool dark)
    {
        var uri = new Uri(dark ? DarkPaletteUri : LightPaletteUri, UriKind.Absolute);
        var palette = new ResourceDictionary { Source = uri };

        var merged = _application.Resources.MergedDictionaries;
        var existing = merged.FirstOrDefault(d => d.Source is not null
            && (d.Source.OriginalString.EndsWith("PaletteLight.xaml", StringComparison.OrdinalIgnoreCase)
                || d.Source.OriginalString.EndsWith("PaletteDark.xaml", StringComparison.OrdinalIgnoreCase)));

        if (existing is null)
        {
            merged.Insert(0, palette);
        }
        else
        {
            var index = merged.IndexOf(existing);
            merged[index] = palette;
        }
    }

    private static bool DetectSystemIsDark()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            if (key?.GetValue("AppsUseLightTheme") is int value)
            {
                return value == 0;
            }
        }
        catch (Exception)
        {
        }

        return false;
    }
}
