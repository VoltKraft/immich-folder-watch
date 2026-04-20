using System.Windows;
using System.Windows.Media;
using Microsoft.Win32;

namespace ImmichFolderWatch.App.Services;

public sealed class ThemeWatcher
{
    private const string LightPaletteUri = "pack://application:,,,/Styles/PaletteLight.xaml";
    private const string DarkPaletteUri = "pack://application:,,,/Styles/PaletteDark.xaml";

    private static readonly Color DefaultAccent = Color.FromRgb(0x00, 0x78, 0xD4);

    private readonly Application _application;
    private bool _isDark;
    private Color _accent = DefaultAccent;

    public ThemeWatcher(Application application)
    {
        _application = application ?? throw new ArgumentNullException(nameof(application));
    }

    public event EventHandler? ThemeChanged;

    public bool IsDark => _isDark;

    public Color AccentColor => _accent;

    public void Initialize()
    {
        _isDark = DetectSystemIsDark();
        _accent = DetectAccentColor();
        ApplyPalette(_isDark);
        ApplyAccent();
    }

    public void Refresh()
    {
        var nowDark = DetectSystemIsDark();
        var nowAccent = DetectAccentColor();
        var darkChanged = nowDark != _isDark;
        var accentChanged = nowAccent != _accent;
        if (!darkChanged && !accentChanged)
        {
            return;
        }

        _isDark = nowDark;
        _accent = nowAccent;
        _application.Dispatcher.BeginInvoke(new Action(() =>
        {
            if (darkChanged)
            {
                ApplyPalette(_isDark);
            }
            ApplyAccent();
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

    private void ApplyAccent()
    {
        var accent = _accent;
        var light1 = Lighten(accent, 0.15);
        var light2 = Lighten(accent, 0.30);
        var light3 = Lighten(accent, 0.45);
        var dark1 = Darken(accent, 0.15);
        var dark2 = Darken(accent, 0.30);
        var dark3 = Darken(accent, 0.45);

        var res = _application.Resources;

        SetBrush(res, "AppAccent", accent);
        SetBrush(res, "AppAccentLight1", light1);
        SetBrush(res, "AppAccentLight2", light2);
        SetBrush(res, "AppAccentLight3", light3);
        SetBrush(res, "AppAccentDark1", dark1);
        SetBrush(res, "AppAccentDark2", dark2);
        SetBrush(res, "AppAccentDark3", dark3);

        if (_isDark)
        {
            var primary = light2;
            var hover = light3;
            var pressed = light1;
            var primaryForeground = Color.FromRgb(0x00, 0x00, 0x00);

            SetBrush(res, "AppButtonPrimaryBackground", primary);
            SetBrush(res, "AppButtonPrimaryBorder", primary);
            SetBrush(res, "AppButtonPrimaryForeground", primaryForeground);
            SetBrush(res, "AppButtonPrimaryBackgroundPointerOver", hover);
            SetBrush(res, "AppButtonPrimaryBorderPointerOver", hover);
            SetBrush(res, "AppButtonPrimaryBackgroundPressed", pressed);
            SetBrush(res, "AppButtonPrimaryBorderPressed", pressed);

            SetBrush(res, "AppTextBoxBorderFocused", primary);
            SetBrush(res, "AppStatusInfoBackground", Darken(accent, 0.50));
            SetBrush(res, "AppStatusInfoForeground", light3);
        }
        else
        {
            var primary = accent;
            var hover = dark1;
            var pressed = dark2;
            var primaryForeground = Color.FromRgb(0xFF, 0xFF, 0xFF);

            SetBrush(res, "AppButtonPrimaryBackground", primary);
            SetBrush(res, "AppButtonPrimaryBorder", primary);
            SetBrush(res, "AppButtonPrimaryForeground", primaryForeground);
            SetBrush(res, "AppButtonPrimaryBackgroundPointerOver", hover);
            SetBrush(res, "AppButtonPrimaryBorderPointerOver", hover);
            SetBrush(res, "AppButtonPrimaryBackgroundPressed", pressed);
            SetBrush(res, "AppButtonPrimaryBorderPressed", pressed);

            SetBrush(res, "AppTextBoxBorderFocused", primary);
            SetBrush(res, "AppStatusInfoBackground", Blend(accent, Color.FromRgb(0xFF, 0xFF, 0xFF), 0.82));
            SetBrush(res, "AppStatusInfoForeground", dark2);
        }
    }

    private static void SetBrush(ResourceDictionary res, string key, Color color)
    {
        var brush = new SolidColorBrush(color);
        brush.Freeze();
        res[key] = brush;
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

    private static Color DetectAccentColor()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\DWM");
            if (key?.GetValue("AccentColor") is int raw)
            {
                var value = unchecked((uint)raw);
                var r = (byte)(value & 0xFF);
                var g = (byte)((value >> 8) & 0xFF);
                var b = (byte)((value >> 16) & 0xFF);
                return Color.FromRgb(r, g, b);
            }
        }
        catch (Exception)
        {
        }

        return DefaultAccent;
    }

    private static Color Lighten(Color color, double amount)
    {
        return Blend(color, Color.FromRgb(0xFF, 0xFF, 0xFF), amount);
    }

    private static Color Darken(Color color, double amount)
    {
        return Blend(color, Color.FromRgb(0x00, 0x00, 0x00), amount);
    }

    private static Color Blend(Color source, Color target, double amount)
    {
        amount = Math.Clamp(amount, 0.0, 1.0);
        var r = (byte)Math.Round(source.R + (target.R - source.R) * amount);
        var g = (byte)Math.Round(source.G + (target.G - source.G) * amount);
        var b = (byte)Math.Round(source.B + (target.B - source.B) * amount);
        return Color.FromRgb(r, g, b);
    }
}
