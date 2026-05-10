using ImmichFolderWatch.Core.Logging;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Tests.Core.Logging;

public sealed class JournaldLoggingExtensionsTests
{
    [Fact]
    public void IsJournaldDetected_ReturnsTrue_WhenFlatpakIdSet()
    {
        using var flatpak = new EnvVarScope("FLATPAK_ID", "io.github.test.App");
        using var stream = new EnvVarScope("JOURNAL_STREAM", null);
        using var invocation = new EnvVarScope("INVOCATION_ID", null);

        Assert.True(JournaldLoggingExtensions.IsJournaldDetected());
    }

    [Fact]
    public void IsJournaldDetected_ReturnsTrue_WhenJournalStreamSet()
    {
        using var flatpak = new EnvVarScope("FLATPAK_ID", null);
        using var stream = new EnvVarScope("JOURNAL_STREAM", "8:1234567");
        using var invocation = new EnvVarScope("INVOCATION_ID", null);

        Assert.True(JournaldLoggingExtensions.IsJournaldDetected());
    }

    [Fact]
    public void IsJournaldDetected_ReturnsTrue_WhenInvocationIdSet()
    {
        using var flatpak = new EnvVarScope("FLATPAK_ID", null);
        using var stream = new EnvVarScope("JOURNAL_STREAM", null);
        using var invocation = new EnvVarScope("INVOCATION_ID", "abcdef0123456789");

        Assert.True(JournaldLoggingExtensions.IsJournaldDetected());
    }

    [Fact]
    public void IsJournaldDetected_ReturnsFalse_WhenNoEnvVarsSet()
    {
        using var flatpak = new EnvVarScope("FLATPAK_ID", null);
        using var stream = new EnvVarScope("JOURNAL_STREAM", null);
        using var invocation = new EnvVarScope("INVOCATION_ID", null);

        Assert.False(JournaldLoggingExtensions.IsJournaldDetected());
    }

    [Fact]
    public void AddJournaldConsoleIfDetected_NoOps_WhenNotDetectedAndNotForced()
    {
        using var flatpak = new EnvVarScope("FLATPAK_ID", null);
        using var stream = new EnvVarScope("JOURNAL_STREAM", null);
        using var invocation = new EnvVarScope("INVOCATION_ID", null);

        var services = new ServiceCollection();
        services.AddLogging(builder => builder.AddJournaldConsoleIfDetected());

        using var provider = services.BuildServiceProvider();
        var logger = provider.GetRequiredService<ILogger<JournaldLoggingExtensionsTests>>();

        logger.LogInformation("smoke");
    }

    [Fact]
    public void AddJournaldConsoleIfDetected_AttachesProvider_WhenForced()
    {
        using var flatpak = new EnvVarScope("FLATPAK_ID", null);
        using var stream = new EnvVarScope("JOURNAL_STREAM", null);
        using var invocation = new EnvVarScope("INVOCATION_ID", null);

        var services = new ServiceCollection();
        services.AddLogging(builder => builder.AddJournaldConsoleIfDetected(force: true));

        using var provider = services.BuildServiceProvider();
        var logger = provider.GetRequiredService<ILogger<JournaldLoggingExtensionsTests>>();

        logger.LogInformation("smoke");
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
