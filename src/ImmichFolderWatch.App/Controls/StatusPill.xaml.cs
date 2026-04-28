using System.Windows;
using System.Windows.Controls;
using ImmichFolderWatch.App.Shared.Models;

namespace ImmichFolderWatch.App.Controls;

public sealed partial class StatusPill : UserControl
{
    public static readonly DependencyProperty TextProperty = DependencyProperty.Register(
        nameof(Text),
        typeof(string),
        typeof(StatusPill),
        new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty ToneProperty = DependencyProperty.Register(
        nameof(Tone),
        typeof(StatusTone),
        typeof(StatusPill),
        new PropertyMetadata(StatusTone.Neutral));

    public StatusPill()
    {
        InitializeComponent();
    }

    public string Text
    {
        get => (string)GetValue(TextProperty);
        set => SetValue(TextProperty, value);
    }

    public StatusTone Tone
    {
        get => (StatusTone)GetValue(ToneProperty);
        set => SetValue(ToneProperty, value);
    }
}
