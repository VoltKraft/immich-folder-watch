using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.LogicalTree;
using ImmichFolderWatch.App.Linux.Logging;
using ImmichFolderWatch.App.Linux.Views;
using Microsoft.Extensions.Logging;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class SessionLogTests
{
    [Fact]
    public void Buffer_BoundsRetainedHistoryAndTruncatesLargeEntries()
    {
        var buffer = new SessionLogBuffer(capacity: 2);
        buffer.Append("discarded");
        buffer.Append("retained");
        buffer.Append(new string('x', 100_000));

        var text = buffer.GetText();
        Assert.DoesNotContain("discarded", text);
        Assert.StartsWith("retained" + Environment.NewLine, text);
        Assert.EndsWith("…", text);
        Assert.True(text.Length < 10_000);
    }

    [Fact]
    public void ReplacingWorkerProvider_RetainsHistoryAndCapturesNewFailures()
    {
        var buffer = new SessionLogBuffer();
        using (var firstHost = new SessionLoggerProvider(buffer))
        {
            firstHost.CreateLogger("FirstHost").LogInformation("Before restart");
        }

        using (var secondHost = new SessionLoggerProvider(buffer))
        {
            secondHost.CreateLogger("SecondHost").LogError(new IOException("Synthetic failure"), "After restart");
        }

        var text = buffer.GetText();
        Assert.Contains("FirstHost: Before restart", text);
        Assert.Contains("SecondHost: After restart", text);
        Assert.Contains("Synthetic failure", text);
    }

    [AvaloniaFact]
    public void LogsWindow_ShowsSessionHistoryInReadOnlyEditor()
    {
        var buffer = new SessionLogBuffer();
        buffer.Append("Synthetic upload completed.");
        var window = new LogsWindow(buffer);
        try
        {
            window.Show();
            var editor = Assert.Single(window.GetLogicalDescendants().OfType<TextBox>());
            Assert.True(editor.IsReadOnly);
            Assert.Equal(buffer.GetText(), editor.Text);
        }
        finally
        {
            window.Close();
        }
    }
}
