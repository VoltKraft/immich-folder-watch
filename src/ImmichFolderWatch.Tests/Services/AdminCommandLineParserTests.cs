using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class AdminCommandLineParserTests
{
    [Fact]
    public void TryParse_StatusCommand_Succeeds()
    {
        var args = new[]
        {
            "status",
            "--result-file",
            "result.json",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out var command, out var message, out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(command);
        Assert.Equal(AdminCommandKind.Status, command!.Kind);
        Assert.Equal("result.json", command.ResultFilePath);
    }

    [Fact]
    public void TryParse_StartServiceCommand_Succeeds()
    {
        var args = new[]
        {
            "start-service",
            "--result-file",
            "result.json",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out var command, out var message, out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(command);
        Assert.Equal(AdminCommandKind.StartService, command!.Kind);
        Assert.Equal("result.json", command.ResultFilePath);
    }

    [Fact]
    public void TryParse_StopServiceCommand_Succeeds()
    {
        var args = new[]
        {
            "stop-service",
            "--result-file",
            "result.json",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out var command, out var message, out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(command);
        Assert.Equal(AdminCommandKind.StopService, command!.Kind);
        Assert.Equal("result.json", command.ResultFilePath);
    }

    [Fact]
    public void TryParse_RestartServiceCommand_Succeeds()
    {
        var args = new[]
        {
            "restart-service",
            "--result-file",
            "result.json",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out var command, out var message, out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(command);
        Assert.Equal(AdminCommandKind.RestartService, command!.Kind);
        Assert.Equal("result.json", command.ResultFilePath);
    }

    [Fact]
    public void TryParse_MigrateDataLayoutCommand_Succeeds()
    {
        var args = new[]
        {
            "migrate-data-layout",
            "--legacy-install-root",
            @"C:\Program Files\Immich Folder Watch",
            "--result-file",
            "result.json",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out var command, out var message, out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(command);
        Assert.Equal(AdminCommandKind.MigrateDataLayout, command!.Kind);
        Assert.Equal(@"C:\Program Files\Immich Folder Watch", command.LegacyInstallRoot);
        Assert.Equal("result.json", command.ResultFilePath);
    }

    [Fact]
    public void TryParse_ApplyVerifiedConfigWithoutSource_Fails()
    {
        var args = new[]
        {
            "apply-verified-config",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out _, out var message, out var helpRequested);

        Assert.False(parsed);
        Assert.False(helpRequested);
        Assert.Contains("--source", message);
    }

    [Fact]
    public void TryParse_ApplyVerifiedConfigWithSource_Succeeds()
    {
        var args = new[]
        {
            "apply-verified-config",
            "--source",
            "draft.yaml",
            "--result-file",
            "result.json",
        };

        var parsed = AdminCommandLineParser.TryParse(args, out var command, out var message, out var helpRequested);

        Assert.True(parsed);
        Assert.False(helpRequested);
        Assert.Equal(string.Empty, message);
        Assert.NotNull(command);
        Assert.Equal(AdminCommandKind.ApplyVerifiedConfig, command!.Kind);
        Assert.Equal("draft.yaml", command.SourcePath);
        Assert.Equal("result.json", command.ResultFilePath);
    }
}
