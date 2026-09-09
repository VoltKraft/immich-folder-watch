using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;
using ImmichFolderWatch.App.Shared.Models;

namespace ImmichFolderWatch.App.Linux.Controls;

/// <summary>A status label with the same semantic colors as the Windows UI.</summary>
public sealed class StatusPill : Border
{
    public static readonly StyledProperty<string?> TextProperty =
        AvaloniaProperty.Register<StatusPill, string?>(nameof(Text));

    public static readonly StyledProperty<StatusTone> ToneProperty =
        AvaloniaProperty.Register<StatusPill, StatusTone>(nameof(Tone));

    private readonly TextBlock _label = new() { FontWeight = FontWeight.SemiBold };

    public StatusPill()
    {
        CornerRadius = new CornerRadius(999);
        Padding = new Thickness(10, 6);
        Child = _label;
        ActualThemeVariantChanged += (_, _) => UpdateAppearance();
        UpdateAppearance();
    }

    public string? Text
    {
        get => GetValue(TextProperty);
        set => SetValue(TextProperty, value);
    }

    public StatusTone Tone
    {
        get => GetValue(ToneProperty);
        set => SetValue(ToneProperty, value);
    }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == TextProperty)
        {
            _label.Text = Text;
        }
        else if (change.Property == ToneProperty)
        {
            UpdateAppearance();
        }
    }

    private void UpdateAppearance()
    {
        var dark = ActualThemeVariant == ThemeVariant.Dark;
        var colors = (Tone, dark) switch
        {
            (StatusTone.Info, false) => ("#DFF0FF", "#003F73"),
            (StatusTone.Info, true) => ("#003F73", "#B4DDFF"),
            (StatusTone.Success, false) => ("#DFF6DD", "#0E5A24"),
            (StatusTone.Success, true) => ("#0E5A24", "#B4F0BA"),
            (StatusTone.Warning, false) => ("#FFF4CE", "#5F4600"),
            (StatusTone.Warning, true) => ("#5F4600", "#FFE9A6"),
            (StatusTone.Error, false) => ("#FDE7E9", "#8A1A1A"),
            (StatusTone.Error, true) => ("#8A1A1A", "#FFCDCD"),
            (_, true) => ("#3D3D3D", "#FFFFFF"),
            _ => ("#EDEDED", "#1A1A1A"),
        };
        Background = Brush.Parse(colors.Item1);
        _label.Foreground = Brush.Parse(colors.Item2);
    }
}
