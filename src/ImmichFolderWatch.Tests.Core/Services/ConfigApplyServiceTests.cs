using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class ConfigApplyServiceTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), $"ifw-apply-{Guid.NewGuid():N}");
    private string ConfigPath => Path.Combine(_directory, "config.yaml");

    public ConfigApplyServiceTests()
    {
        Directory.CreateDirectory(Path.Combine(_directory, "media"));
        File.WriteAllText(ConfigPath, "existing configuration");
    }

    [Theory]
    [InlineData("url")]
    [InlineData("key")]
    [InlineData("path")]
    [InlineData("extensions")]
    [InlineData("watch")]
    [InlineData("retry")]
    [InlineData("logging")]
    public async Task ApplyAsync_InvalidLocalConfiguration_DoesNotCheckWriteOrRestart(string invalidSetting)
    {
        var config = CreateConfig();
        switch (invalidSetting)
        {
            case "url": config.Immich.ServerApiUrl = "not a URL"; break;
            case "key": config.Immich.ApiKey = AppConfigValidator.ExampleApiKeyPlaceholder; break;
            case "path": config.Watch.Sources[0].Path = "missing"; break;
            case "extensions": config.Watch.Sources[0].Extensions.Clear(); break;
            case "watch": config.Watch.MaxBatchSize = 0; break;
            case "retry": config.Retry.MaxAttempts = 0; break;
            case "logging": config.Logging.Level = ""; break;
        }
        var checks = 0;
        var restarts = 0;
        var service = new ConfigApplyService((_, _, _) =>
        {
            checks++;
            return Task.FromResult(PassedAccess());
        });

        var result = await service.ApplyAsync(config, ConfigPath, (_, _) =>
        {
            restarts++;
            return Task.CompletedTask;
        });

        Assert.False(result.Success);
        Assert.NotEmpty(result.Errors);
        Assert.Equal(0, checks);
        Assert.Equal(0, restarts);
        Assert.Equal("existing configuration", File.ReadAllText(ConfigPath));
    }

    [Theory]
    [InlineData("url")]
    [InlineData("key")]
    [InlineData("permission")]
    public async Task ApplyAsync_BlockingAccessFailure_ReportsResultWithoutWritingOrRestarting(string failure)
    {
        var access = new ImmichAccessCheckResult
        {
            UrlState = failure == "url" ? CheckState.Failed : CheckState.Passed,
            UrlMessage = "URL failed",
            ApiKeyState = failure == "key" ? CheckState.Failed : CheckState.Passed,
            ApiKeyMessage = "API key failed",
            PermissionsState = failure == "permission" ? CheckState.Failed : CheckState.Passed,
            PermissionResults =
            [
                new()
                {
                    DisplayName = "Asset Upload",
                    PermissionName = "asset.upload",
                    State = failure == "permission" ? CheckState.Failed : CheckState.Passed,
                    BlocksConfigVerification = true,
                    Message = "Upload permission failed",
                },
            ],
        };
        var service = new ConfigApplyService((_, _, _) => Task.FromResult(access));
        ImmichAccessCheckResult? reported = null;
        var restarted = false;

        var result = await service.ApplyAsync(CreateConfig(), ConfigPath, (_, _) =>
        {
            restarted = true;
            return Task.CompletedTask;
        }, result => reported = result);

        Assert.False(result.Success);
        Assert.Same(access, reported);
        Assert.Single(result.Errors);
        Assert.False(restarted);
        Assert.Equal("existing configuration", File.ReadAllText(ConfigPath));
    }

    [Fact]
    public async Task ApplyAsync_Success_WaitsForAccessAndRestartAndUsesNormalizedConfiguration()
    {
        var accessCompletion = new TaskCompletionSource<ImmichAccessCheckResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        var restartStarted = new TaskCompletionSource<AppConfig>(TaskCreationOptions.RunContinuationsAsynchronously);
        var restartCompletion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var config = CreateConfig();
        AppConfig? checkedConfig = null;
        var service = new ConfigApplyService((candidate, path, _) =>
        {
            Assert.Equal(ConfigPath, path);
            checkedConfig = candidate;
            return accessCompletion.Task;
        });
        var stages = new List<string>();

        var apply = service.ApplyAsync(config, ConfigPath, async (candidate, _) =>
        {
            stages.Add("restart");
            restartStarted.SetResult(candidate);
            await restartCompletion.Task;
        }, _ => stages.Add("checked"), () => stages.Add("saving"));

        Assert.False(apply.IsCompleted);
        Assert.Equal("existing configuration", File.ReadAllText(ConfigPath));
        accessCompletion.SetResult(PassedAccess());
        var restartedConfig = await restartStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.False(apply.IsCompleted);
        Assert.Equal(new[] { "checked", "saving", "restart" }, stages);
        Assert.Same(checkedConfig, restartedConfig);
        Assert.NotSame(config, restartedConfig);
        Assert.Equal("media", config.Watch.Sources[0].Path);
        Assert.Equal(Path.Combine(_directory, "media"), restartedConfig.Watch.Sources[0].Path);
        Assert.Equal(new[] { ".jpg" }, restartedConfig.Watch.Sources[0].Extensions);
        var saved = new AppConfigLoader().LoadForEditing(ConfigPath);
        Assert.Equal(restartedConfig.Watch.Sources[0].Path, saved.Watch.Sources[0].Path);
        Assert.Equal(Path.Combine(_directory, "logs"), saved.Logging.LogDirectory);
        Assert.Equal("de", saved.Localization.Language);
        Assert.Equal(new[] { ".jpg" }, saved.Watch.Sources[0].Extensions);
        restartCompletion.SetResult();
        Assert.True((await apply).Success);
    }

    [Fact]
    public async Task ApplyAsync_AccessException_ResetsBadgesAndLeavesConfigurationUntouched()
    {
        var exception = new IOException("Access check failed");
        var service = new ConfigApplyService((_, _, _) => throw exception);
        ImmichAccessCheckResult? reported = null;
        var restarted = false;
        var thrown = await Assert.ThrowsAsync<IOException>(() => service.ApplyAsync(CreateConfig(), ConfigPath, (_, _) =>
        {
            restarted = true;
            return Task.CompletedTask;
        }, result => reported = result));

        Assert.Same(exception, thrown);
        Assert.NotNull(reported);
        Assert.Equal(CheckState.Failed, reported.UrlState);
        Assert.Equal(CheckState.NotChecked, reported.ApiKeyState);
        Assert.All(reported.PermissionResults, permission => Assert.Equal(CheckState.NotChecked, permission.State));
        Assert.NotEmpty(reported.GetBlockingErrors());
        Assert.False(restarted);
        Assert.Equal("existing configuration", File.ReadAllText(ConfigPath));
    }

    [Fact]
    public async Task ApplyAsync_WriteFailure_DoesNotRestart()
    {
        var targetDirectory = Path.Combine(_directory, "directory-instead-of-file");
        Directory.CreateDirectory(targetDirectory);
        var restarted = false;
        var service = new ConfigApplyService((_, _, _) => Task.FromResult(PassedAccess()));

        await Assert.ThrowsAnyAsync<Exception>(() => service.ApplyAsync(CreateConfig(), targetDirectory, (_, _) =>
        {
            restarted = true;
            return Task.CompletedTask;
        }));

        Assert.False(restarted);
        Assert.Equal("existing configuration", File.ReadAllText(ConfigPath));
    }

    [Fact]
    public async Task ApplyAsync_RestartFailure_SurfacesErrorAndLeavesSavedConfiguration()
    {
        var exception = new InvalidOperationException("Restart failed");
        var service = new ConfigApplyService((_, _, _) => Task.FromResult(PassedAccess()));

        var thrown = await Assert.ThrowsAsync<InvalidOperationException>(() => service.ApplyAsync(CreateConfig(), ConfigPath,
            (_, _) => throw exception));

        Assert.Same(exception, thrown);
        Assert.Equal("de", new AppConfigLoader().Load(ConfigPath).Localization.Language);
    }

    [Fact]
    public async Task ApplyAsync_CancelledAfterAccess_DoesNotWriteOrRestart()
    {
        using var cancellation = new CancellationTokenSource();
        var restarted = false;
        var service = new ConfigApplyService((_, _, token) =>
        {
            Assert.Equal(cancellation.Token, token);
            cancellation.Cancel();
            return Task.FromResult(PassedAccess());
        });

        await Assert.ThrowsAsync<OperationCanceledException>(() => service.ApplyAsync(CreateConfig(), ConfigPath, (_, _) =>
        {
            restarted = true;
            return Task.CompletedTask;
        }, cancellationToken: cancellation.Token));

        Assert.False(restarted);
        Assert.Equal("existing configuration", File.ReadAllText(ConfigPath));
    }

    private static AppConfig CreateConfig() => new()
    {
        Immich = new ImmichSettings { ServerApiUrl = "https://immich.example/api", ApiKey = "test-key" },
        Watch = new WatchSettings { Sources = [new() { Path = "media", Extensions = [" JPG ", ".jpg"] }] },
        Logging = new LoggingSettings { Target = LogTargets.File, LogDirectory = "logs" },
        Localization = new LocalizationSettings { Language = "de" },
    };

    private static ImmichAccessCheckResult PassedAccess() => new()
    {
        UrlState = CheckState.Passed,
        ApiKeyState = CheckState.Passed,
        PermissionsState = CheckState.Passed,
        PermissionResults = [new() { PermissionName = "asset.upload", State = CheckState.Passed, BlocksConfigVerification = true }],
    };

    public void Dispose() => Directory.Delete(_directory, recursive: true);
}
