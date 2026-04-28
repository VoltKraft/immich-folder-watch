namespace ImmichFolderWatch.Core.Platform;

public interface IThemeProvider : IDisposable
{
    bool IsDark { get; }

    AccentColor Accent { get; }

    event EventHandler? ThemeChanged;

    void Initialize();

    void Refresh();
}

public readonly record struct AccentColor(byte R, byte G, byte B);
