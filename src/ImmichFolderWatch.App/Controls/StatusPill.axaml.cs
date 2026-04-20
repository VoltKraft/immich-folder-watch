using Avalonia;
using Avalonia.Controls;
using Avalonia.Styling;
using ImmichFolderWatch.App.Models;

namespace ImmichFolderWatch.App.Controls;

public sealed partial class StatusPill : UserControl
{
    public static readonly StyledProperty<string> TextProperty =
        AvaloniaProperty.Register<StatusPill, string>(nameof(Text), string.Empty);

    public static readonly StyledProperty<StatusTone> ToneProperty =
        AvaloniaProperty.Register<StatusPill, StatusTone>(nameof(Tone), StatusTone.Neutral);

    static StatusPill()
    {
        ToneProperty.Changed.AddClassHandler<StatusPill>((pill, _) => pill.UpdateToneClasses());
    }

    public StatusPill()
    {
        InitializeComponent();
        UpdateToneClasses();
    }

    public string Text
    {
        get => GetValue(TextProperty);
        set => SetValue(TextProperty, value);
    }

    public StatusTone Tone
    {
        get => GetValue(ToneProperty);
        set => SetValue(ToneProperty, value);
    }

    private void UpdateToneClasses()
    {
        UpdateToneClasses(RootBorder);
        UpdateToneClasses(TextPresenter);
    }

    private void UpdateToneClasses(StyledElement element)
    {
        element.Classes.Set("tone-neutral", Tone == StatusTone.Neutral);
        element.Classes.Set("tone-info", Tone == StatusTone.Info);
        element.Classes.Set("tone-success", Tone == StatusTone.Success);
        element.Classes.Set("tone-warning", Tone == StatusTone.Warning);
        element.Classes.Set("tone-error", Tone == StatusTone.Error);
    }
}
