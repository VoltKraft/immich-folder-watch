using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Configuration;

public sealed class AppConfigWriterTests
{
    [Fact]
    public void Serialize_RoundTripsThroughEditingLoader()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-write-");

        try
        {
            var configDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "config"));
            var configPath = Path.Combine(configDirectory.FullName, "config.yaml");
            var logDirectory = Path.Combine(tempRoot.FullName, "logs");

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
                    {
                        new WatchSourceSettings
                        {
                            Path = "../watch",
                            AlbumName = "Screenshots",
                            IncludeSubdirectories = true,
                            Extensions =
                            {
                                ".png",
                                ".jpg",
                            },
                            ExcludeDirectories =
                            {
                                "private",
                                "**/cache",
                            },
                            ExcludeFileNames =
                            {
                                "Thumbs.db",
                                "*.tmp",
                            },
                        },
                    },
                    Extensions =
                    {
                        ".legacy",
                    },
                    BatchIntervalSeconds = 7,
                    MaxBatchSize = 20,
                    FileReadyTimeoutSeconds = 40,
                },
                Retry = new RetrySettings
                {
                    MaxAttempts = 3,
                    BaseDelayMilliseconds = 350,
                },
                Logging = new LoggingSettings
                {
                    Level = "Warning",
                    LogDirectory = logDirectory,
                },
                Localization = new LocalizationSettings
                {
                    Language = "de",
                },
            };

            var writer = new AppConfigWriter();
            var yaml = writer.Serialize(config);
            File.WriteAllText(configPath, yaml);

            var roundTrip = new AppConfigLoader().LoadForEditing(configPath);
            var normalized = AppConfigLoader.NormalizeForRuntime(roundTrip, configDirectory.FullName);

            Assert.DoesNotContain($"{Environment.NewLine}  extensions:{Environment.NewLine}", yaml, StringComparison.Ordinal);
            Assert.Equal("../watch", roundTrip.Watch.Sources[0].Path);
            Assert.Equal("Screenshots", roundTrip.Watch.Sources[0].AlbumName);
            Assert.True(roundTrip.Watch.Sources[0].IncludeSubdirectories);
            Assert.Equal([".png", ".jpg"], roundTrip.Watch.Sources[0].Extensions);
            Assert.Equal(["private", "**/cache"], roundTrip.Watch.Sources[0].ExcludeDirectories);
            Assert.Equal(["Thumbs.db", "*.tmp"], roundTrip.Watch.Sources[0].ExcludeFileNames);
            Assert.Empty(roundTrip.Watch.Extensions);
            Assert.Equal(7, roundTrip.Watch.BatchIntervalSeconds);
            Assert.Equal(20, roundTrip.Watch.MaxBatchSize);
            Assert.Equal(40, roundTrip.Watch.FileReadyTimeoutSeconds);
            Assert.Equal("Warning", roundTrip.Logging.Level);
            Assert.Equal(logDirectory, roundTrip.Logging.LogDirectory);
            Assert.Equal(Path.GetFullPath(Path.Combine(tempRoot.FullName, "watch")), normalized.Watch.Sources[0].Path);
            Assert.Equal([".png", ".jpg"], normalized.Watch.Sources[0].Extensions);
            Assert.Equal(Path.GetFullPath(logDirectory), normalized.Logging.LogDirectory);
            Assert.Equal("de", roundTrip.Localization.Language);
            Assert.Contains("language: de", yaml, StringComparison.Ordinal);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Serialize_MissingLocalization_EmitsAutoDefault()
    {
        var config = new AppConfig
        {
            Immich = new ImmichSettings { ServerApiUrl = "https://x", ApiKey = "k" },
            Watch = new WatchSettings(),
            Retry = new RetrySettings(),
            Logging = new LoggingSettings { Level = "Information", LogDirectory = "logs" },
        };

        var yaml = new AppConfigWriter().Serialize(config);

        Assert.Contains("language: auto", yaml, StringComparison.Ordinal);
    }
}
