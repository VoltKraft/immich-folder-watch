using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Configuration;

public sealed class AppConfigValidatorTests
{
    [Fact]
    public void Validate_AllowsEmptyAlbumName()
    {
        var watchPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-watch-{Guid.NewGuid():N}")).FullName;
        var logPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-logs-{Guid.NewGuid():N}")).FullName;

        try
        {
            var config = new AppConfig
            {
                Immich = new ImmichSettings
                {
                    ServerApiUrl = "https://immich.example.com/api",
                    ApiKey = "demo-key",
                },
                Watch = new WatchSettings
                {
                    Sources =
                    [
                        new WatchSourceSettings
                        {
                            Path = watchPath,
                            AlbumName = string.Empty,
                        },
                    ],
                    Extensions = [".png"],
                    BatchIntervalSeconds = 5,
                    MaxBatchSize = 25,
                    FileReadyTimeoutSeconds = 30,
                },
                Retry = new RetrySettings
                {
                    MaxAttempts = 5,
                    BaseDelayMilliseconds = 500,
                },
                Logging = new LoggingSettings
                {
                    Level = "Information",
                    LogDirectory = logPath,
                },
            };

            var errors = AppConfigValidator.Validate(config);

            Assert.DoesNotContain(errors, error => error.Contains("albumName", StringComparison.Ordinal));
        }
        finally
        {
            Directory.Delete(watchPath, recursive: true);
            Directory.Delete(logPath, recursive: true);
        }
    }
}
