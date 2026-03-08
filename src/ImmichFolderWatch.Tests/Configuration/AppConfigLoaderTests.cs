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
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");

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
            Assert.Equal(Path.GetFullPath(Path.Combine(tempRoot.FullName, "logs")), config.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_ResolvesRelativePathsAgainstConfigDirectory()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-relative-");

        try
        {
            var watchDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "watch"));
            var configDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "config"));
            var configPath = Path.Combine(configDirectory.FullName, "config.yaml");

            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources:
    - path: "../watch"
      albumName: "Screenshots"
      includeSubdirectories: false
  extensions:
    - ".png"
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "logs"
""";

            File.WriteAllText(configPath, yaml);

            var loader = new AppConfigLoader();
            var config = loader.Load(configPath);

            Assert.Equal(Path.GetFullPath(watchDirectory.FullName), config.Watch.Sources[0].Path);
            Assert.Equal(Path.GetFullPath(Path.Combine(configDirectory.FullName, "logs")), config.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_ResolvesParentRelativeLogDirectoryAgainstConfigDirectory()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-parent-log-");

        try
        {
            var watchDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "watch"));
            var configDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "config"));
            var configPath = Path.Combine(configDirectory.FullName, "config.yaml");

            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources:
    - path: "../watch"
      albumName: "Screenshots"
      includeSubdirectories: false
  extensions:
    - ".png"
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "../logs"
""";

            File.WriteAllText(configPath, yaml);

            var loader = new AppConfigLoader();
            var config = loader.Load(configPath);

            Assert.Equal(Path.GetFullPath(watchDirectory.FullName), config.Watch.Sources[0].Path);
            Assert.Equal(Path.GetFullPath(Path.Combine(tempRoot.FullName, "logs")), config.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void LoadForEditing_PreservesRelativePaths()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-edit-");

        try
        {
            var configDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "config"));
            var configPath = Path.Combine(configDirectory.FullName, "config.yaml");

            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources:
    - path: "../watch"
      albumName: "Screenshots"
      includeSubdirectories: false
  extensions:
    - ".png"
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "../logs"
""";

            File.WriteAllText(configPath, yaml);

            var loader = new AppConfigLoader();
            var config = loader.LoadForEditing(configPath);

            Assert.Equal("../watch", config.Watch.Sources[0].Path);
            Assert.Equal("../logs", config.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }
}
