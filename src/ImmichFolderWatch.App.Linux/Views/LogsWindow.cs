using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Threading;
using ImmichFolderWatch.App.Linux.Logging;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;

namespace ImmichFolderWatch.App.Linux.Views;

/// <summary>Read-only live log access without requiring host journal permissions.</summary>
public sealed class LogsWindow : Window
{
    private readonly SessionLogBuffer _buffer;
    private readonly TextBox _output = new()
    {
        IsReadOnly = true,
        AcceptsReturn = true,
        FontFamily = Avalonia.Media.FontFamily.Parse("monospace"),
        HorizontalAlignment = HorizontalAlignment.Stretch,
        VerticalAlignment = VerticalAlignment.Stretch,
    };
    private readonly TextBlock _description = new() { TextWrapping = Avalonia.Media.TextWrapping.Wrap };
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(1) };

    public LogsWindow(SessionLogBuffer buffer)
    {
        _buffer = buffer;
        Width = 1000;
        Height = 600;
        MinWidth = 600;
        MinHeight = 300;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var content = new Grid { Margin = new Thickness(18), RowDefinitions = RowDefinitions.Parse("Auto,*") };
        _description.Margin = new Thickness(0, 0, 0, 12);
        Grid.SetRow(_output, 1);
        content.Children.Add(_description);
        content.Children.Add(_output);
        Content = content;
        _timer.Tick += (_, _) => Refresh();
        Opened += (_, _) => _timer.Start();
        Closed += (_, _) =>
        {
            _timer.Stop();
            LocalizationService.Instance.LanguageChanged -= OnLanguageChanged;
        };
        LocalizationService.Instance.LanguageChanged += OnLanguageChanged;
        UpdateLanguage();
        Refresh();
    }

    private void OnLanguageChanged(object? sender, EventArgs e) => UpdateLanguage();

    private void UpdateLanguage()
    {
        Title = Strings.ResourceManager.GetString("UI_SessionLogs", Strings.Culture) ?? "Session logs";
        _description.Text = Strings.ResourceManager.GetString("UI_SessionLogsDescription", Strings.Culture);
    }

    private void Refresh()
    {
        var text = _buffer.GetText();
        if (!string.Equals(_output.Text, text, StringComparison.Ordinal))
        {
            _output.Text = text;
        }
    }
}
