using Avalonia;
using Avalonia.Controls;
using Avalonia.Styling;
using ImmichFolderWatch.Gui.Models;

namespace ImmichFolderWatch.Gui.Controls;

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
        SetClass(element, "tone-neutral", Tone == StatusTone.Neutral);
        SetClass(element, "tone-info", Tone == StatusTone.Info);
        SetClass(element, "tone-success", Tone == StatusTone.Success);
        SetClass(element, "tone-warning", Tone == StatusTone.Warning);
        SetClass(element, "tone-error", Tone == StatusTone.Error);
    }

    private static void SetClass(StyledElement element, string className, bool enabled)
    {
        if (enabled)
        {
            if (!element.Classes.Contains(className))
            {
                element.Classes.Add(className);
            }

            return;
        }

        element.Classes.Remove(className);
    }
}
