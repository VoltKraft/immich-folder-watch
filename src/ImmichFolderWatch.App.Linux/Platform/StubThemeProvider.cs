using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class StubThemeProvider : IThemeProvider
{
    public bool IsDark => false;

    public AccentColor Accent => new(0, 120, 215);

    public event EventHandler? ThemeChanged
    {
        add { }
        remove { }
    }

    public void Initialize()
    {
    }

    public void Refresh()
    {
    }

    public void Dispose()
    {
    }
}
