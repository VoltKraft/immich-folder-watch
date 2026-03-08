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
                        },
                    },
                    Extensions =
                    {
                        ".png",
                        ".jpg",
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
                    LogDirectory = "../logs",
                },
            };

            var writer = new AppConfigWriter();
            File.WriteAllText(configPath, writer.Serialize(config));

            var roundTrip = new AppConfigLoader().LoadForEditing(configPath);
            var normalized = AppConfigLoader.NormalizeForRuntime(roundTrip, configDirectory.FullName);

            Assert.Equal("../watch", roundTrip.Watch.Sources[0].Path);
            Assert.Equal("Screenshots", roundTrip.Watch.Sources[0].AlbumName);
            Assert.True(roundTrip.Watch.Sources[0].IncludeSubdirectories);
            Assert.Contains(".png", roundTrip.Watch.Extensions);
            Assert.Contains(".jpg", roundTrip.Watch.Extensions);
            Assert.Equal(7, roundTrip.Watch.BatchIntervalSeconds);
            Assert.Equal(20, roundTrip.Watch.MaxBatchSize);
            Assert.Equal(40, roundTrip.Watch.FileReadyTimeoutSeconds);
            Assert.Equal("Warning", roundTrip.Logging.Level);
            Assert.Equal("../logs", roundTrip.Logging.LogDirectory);
            Assert.Equal(Path.GetFullPath(Path.Combine(tempRoot.FullName, "watch")), normalized.Watch.Sources[0].Path);
            Assert.Equal(Path.GetFullPath(Path.Combine(tempRoot.FullName, "logs")), normalized.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }
}
