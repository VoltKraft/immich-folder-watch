using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Configuration;

public sealed class AppConfigLoaderTests
{
    [Fact]
    public void Load_ParsesExpectedValues()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-test-");

        try
        {
            var watchPath = tempRoot.FullName.Replace("\\", "\\\\", StringComparison.Ordinal);
            var configPath = Path.Combine(tempRoot.FullName, "config.yml");

            var yaml = $"""
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources:
    - path: "{watchPath}"
      albumName: "Screenshots"
      includeSubdirectories: true
  extensions:
    - PNG
    - .JPG
  batchIntervalSeconds: 6
  maxBatchSize: 10
  fileReadyTimeoutSeconds: 20
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Debug"
  logDirectory: "logs"
""";

            File.WriteAllText(configPath, yaml);

            var loader = new AppConfigLoader();
            var config = loader.Load(configPath);

            Assert.Equal("https://immich.example.com/api", config.Immich.ServerApiUrl);
            Assert.Equal("demo-key", config.Immich.ApiKey);
            Assert.Single(config.Watch.Sources);
            Assert.Equal("Screenshots", config.Watch.Sources[0].AlbumName);
            Assert.True(config.Watch.Sources[0].IncludeSubdirectories);
            Assert.Contains(".png", config.Watch.Extensions);
            Assert.Contains(".jpg", config.Watch.Extensions);
            Assert.Equal(6, config.Watch.BatchIntervalSeconds);
            Assert.Equal(10, config.Watch.MaxBatchSize);
            Assert.Equal(20, config.Watch.FileReadyTimeoutSeconds);
            Assert.Equal(4, config.Retry.MaxAttempts);
            Assert.Equal(250, config.Retry.BaseDelayMilliseconds);
            Assert.Equal("Debug", config.Logging.Level);
            Assert.Equal("logs", config.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }
}
