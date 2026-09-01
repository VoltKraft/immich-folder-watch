using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.Tests.Core.Platform;

[Collection("Environment variables")]
public sealed class XdgPlatformPathsTests
{
    [Fact]
    public void Default_ProductFolderName_IsKebabCaseSlug()
    {
        var paths = new XdgPlatformPaths();

        Assert.Equal("immich-folder-watch", paths.ProductFolderName);
    }

    [Fact]
    public void GetConfigPath_HonoursXdgConfigHome()
    {
        using var scope = new EnvVarScope("XDG_CONFIG_HOME", "/tmp/xdg-cfg");

        var paths = new XdgPlatformPaths();

        Assert.Equal(
            Path.Combine("/tmp/xdg-cfg", "immich-folder-watch", "config.yaml"),
            paths.GetConfigPath());
    }

    [Fact]
    public void GetConfigPath_FallsBackToHomeDotConfig_WhenXdgConfigHomeUnset()
    {
        using var configScope = new EnvVarScope("XDG_CONFIG_HOME", null);
        using var homeScope = new EnvVarScope("HOME", "/home/tester");

        var paths = new XdgPlatformPaths();

        Assert.Equal(
            Path.Combine("/home/tester", ".config", "immich-folder-watch", "config.yaml"),
            paths.GetConfigPath());
    }

    [Fact]
    public void GetSyncDatabasePath_IsBesideConfigFile()
    {
        using var scope = new EnvVarScope("XDG_CONFIG_HOME", "/tmp/xdg-cfg");

        var paths = new XdgPlatformPaths();

        Assert.Equal(
            Path.GetDirectoryName(paths.GetConfigPath()),
            Path.GetDirectoryName(paths.GetSyncDatabasePath()));
        Assert.Equal("sync-state.db", Path.GetFileName(paths.GetSyncDatabasePath()));
    }

    [Fact]
    public void GetLogDirectory_HonoursXdgStateHome()
    {
        using var scope = new EnvVarScope("XDG_STATE_HOME", "/tmp/xdg-state");

        var paths = new XdgPlatformPaths();

        Assert.Equal(
            Path.Combine("/tmp/xdg-state", "immich-folder-watch", "logs"),
            paths.GetLogDirectory());
    }

    [Fact]
    public void GetLogDirectory_FallsBackToHomeLocalState_WhenXdgStateHomeUnset()
    {
        using var stateScope = new EnvVarScope("XDG_STATE_HOME", null);
        using var homeScope = new EnvVarScope("HOME", "/home/tester");

        var paths = new XdgPlatformPaths();

        Assert.Equal(
            Path.Combine("/home/tester", ".local", "state", "immich-folder-watch", "logs"),
            paths.GetLogDirectory());
    }

    [Fact]
    public void Custom_ProductFolderName_IsRespected()
    {
        using var scope = new EnvVarScope("XDG_CONFIG_HOME", "/tmp/xdg-cfg");

        var paths = new XdgPlatformPaths("custom-app");

        Assert.Equal(
            Path.Combine("/tmp/xdg-cfg", "custom-app", "config.yaml"),
            paths.GetConfigPath());
    }

    [Fact]
    public void Constructor_RejectsBlankProductFolderName()
    {
        Assert.Throws<ArgumentException>(() => new XdgPlatformPaths("   "));
    }

    private sealed class EnvVarScope : IDisposable
    {
        private readonly string _name;
        private readonly string? _previous;

        public EnvVarScope(string name, string? value)
        {
            _name = name;
            _previous = Environment.GetEnvironmentVariable(name);
            Environment.SetEnvironmentVariable(name, value);
        }

        public void Dispose() => Environment.SetEnvironmentVariable(_name, _previous);
    }
}
