using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Core.Configuration;

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
                            Extensions = [".png"],
                        },
                    ],
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

    [Fact]
    public void Validate_TargetEventLog_AllowsEmptyOrRelativeLogDirectory()
    {
        var watchPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-watch-{Guid.NewGuid():N}")).FullName;

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
                            AlbumName = "Screenshots",
                            Extensions = [".png"],
                        },
                    ],
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
                    Target = LogTargets.EventLog,
                    LogDirectory = string.Empty,
                },
            };

            var errors = AppConfigValidator.Validate(config);

            Assert.DoesNotContain(errors, error => error.Contains("logDirectory", StringComparison.Ordinal));
        }
        finally
        {
            Directory.Delete(watchPath, recursive: true);
        }
    }

    [Fact]
    public void Validate_TargetFile_RequiresAbsoluteLogDirectory()
    {
        var watchPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-watch-{Guid.NewGuid():N}")).FullName;

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
                            AlbumName = "Screenshots",
                            Extensions = [".png"],
                        },
                    ],
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
                    Target = LogTargets.File,
                    LogDirectory = "relative/logs",
                },
            };

            var errors = AppConfigValidator.Validate(config);

            Assert.Contains(errors, error => error.Contains("logDirectory must be an absolute path", StringComparison.Ordinal));
        }
        finally
        {
            Directory.Delete(watchPath, recursive: true);
        }
    }

    [Fact]
    public void Validate_TargetFile_EmptyLogDirectory_Errors()
    {
        var watchPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-watch-{Guid.NewGuid():N}")).FullName;

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
                            AlbumName = "Screenshots",
                            Extensions = [".png"],
                        },
                    ],
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
                    Target = LogTargets.File,
                    LogDirectory = string.Empty,
                },
            };

            var errors = AppConfigValidator.Validate(config);

            Assert.Contains(errors, error => error.Contains("logDirectory is required", StringComparison.Ordinal));
        }
        finally
        {
            Directory.Delete(watchPath, recursive: true);
        }
    }

    [Fact]
    public void Validate_RequiresExtensionsPerSource()
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
                            AlbumName = "Screenshots",
                        },
                    ],
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

            Assert.Contains("watch.sources[0].extensions must contain at least one file extension.", errors);
        }
        finally
        {
            Directory.Delete(watchPath, recursive: true);
            Directory.Delete(logPath, recursive: true);
        }
    }
}
