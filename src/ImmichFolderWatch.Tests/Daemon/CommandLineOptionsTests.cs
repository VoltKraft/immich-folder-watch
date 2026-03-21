using System.Reflection;
using ImmichFolderWatch.Daemon;

namespace ImmichFolderWatch.Tests.Daemon;

public sealed class CommandLineOptionsTests
{
    [Fact]
    public void TryParse_ConfigArgument_Succeeds()
    {
        var parsed = CommandLineOptions.TryParse(
            new[] { "--config", "config.yaml" },
            out var options,
            out var message,
            out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(options);
        Assert.Equal("config.yaml", options!.ConfigPath);
        Assert.False(options.VersionRequested);
    }

    [Theory]
    [InlineData("--version")]
    [InlineData("-v")]
    public void TryParse_VersionArgument_Succeeds(string argument)
    {
        var parsed = CommandLineOptions.TryParse(
            new[] { argument },
            out var options,
            out var message,
            out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(options);
        Assert.Null(options!.ConfigPath);
        Assert.True(options.VersionRequested);
    }

    [Theory]
    [InlineData("--help")]
    [InlineData("-h")]
    public void TryParse_HelpArgument_ReturnsHelp(string argument)
    {
        var parsed = CommandLineOptions.TryParse(
            new[] { argument },
            out var options,
            out var message,
            out var helpRequested);

        Assert.False(parsed);
        Assert.True(helpRequested);
        Assert.Equal(CommandLineOptions.Usage, message);
        Assert.Null(options);
    }

    [Theory]
    [InlineData()]
    [InlineData("--version", "--config", "config.yaml")]
    [InlineData("--config")]
    [InlineData("--config", "")]
    public void TryParse_InvalidArguments_Fails(params string[] args)
    {
        var parsed = CommandLineOptions.TryParse(
            args,
            out var options,
            out var message,
            out var helpRequested);

        Assert.False(parsed);
        Assert.False(helpRequested);
        Assert.Equal($"Invalid arguments. {CommandLineOptions.Usage}", message);
        Assert.Null(options);
    }
}

public sealed class BootstrapperTests
{
    private static readonly object ConsoleLock = new();

    [Fact]
    public void RunAsync_VersionArgument_PrintsProductVersionAndExitsZero()
    {
        var expectedVersion = GetAssemblyVersion();
        var originalOut = Console.Out;
        var originalError = Console.Error;
        using var output = new StringWriter();
        using var error = new StringWriter();

        int exitCode;

        lock (ConsoleLock)
        {
            Console.SetOut(output);
            Console.SetError(error);
            try
            {
                exitCode = Bootstrapper.RunAsync(new[] { "--version" }).GetAwaiter().GetResult();
            }
            finally
            {
                Console.SetOut(originalOut);
                Console.SetError(originalError);
            }
        }

        Assert.Equal(0, exitCode);
        Assert.Equal(expectedVersion, output.ToString().Trim());
        Assert.Equal(string.Empty, error.ToString());
    }

    private static string GetAssemblyVersion()
    {
        var informationalVersion = typeof(Bootstrapper)
            .Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
            ?.InformationalVersion;

        if (!string.IsNullOrWhiteSpace(informationalVersion))
        {
            var plusIndex = informationalVersion.IndexOf('+');
            return plusIndex >= 0
                ? informationalVersion[..plusIndex]
                : informationalVersion;
        }

        return "1.6.0";
    }
}
