using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Core.Configuration;

public sealed class AppConfigLoaderTests
{
    [Fact]
    public void Load_MigratesLegacyWatchExtensionsToSourceExtensions()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-test-");

        try
        {
            var watchPath = tempRoot.FullName.Replace("\\", "\\\\", StringComparison.Ordinal);
            var logPath = Path.Combine(tempRoot.FullName, "logs").Replace("\\", "\\\\", StringComparison.Ordinal);
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
  logDirectory: "{logPath}"
""";

            File.WriteAllText(configPath, yaml);

            var loader = new AppConfigLoader();
            var config = loader.Load(configPath);

            Assert.Equal("https://immich.example.com/api", config.Immich.ServerApiUrl);
            Assert.Equal("demo-key", config.Immich.ApiKey);
            Assert.Single(config.Watch.Sources);
            Assert.Equal("Screenshots", config.Watch.Sources[0].AlbumName);
            Assert.True(config.Watch.Sources[0].IncludeSubdirectories);
            Assert.False(config.Watch.Sources[0].DeleteAfterUpload);
            Assert.Contains(".png", config.Watch.Sources[0].Extensions);
            Assert.Contains(".jpg", config.Watch.Sources[0].Extensions);
            Assert.Empty(config.Watch.Extensions);
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
    public void Load_PreservesDeleteAfterUpload()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-delete-after-upload-");

        try
        {
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");
            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources:
    - path: "watch"
      syncMode: "uploadAll"
      deleteAfterUpload: true
      extensions:
        - ".jpg"
logging:
  level: "Information"
  logDirectory: "logs"
""";
            File.WriteAllText(configPath, yaml);

            var config = new AppConfigLoader().LoadForEditing(configPath);
            var runtime = AppConfigLoader.NormalizeForRuntime(config, tempRoot.FullName);

            Assert.True(config.Watch.Sources[0].DeleteAfterUpload);
            Assert.True(runtime.Watch.Sources[0].DeleteAfterUpload);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_PrefersSourceSpecificFiltersOverLegacyWatchExtensions()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-source-filters-");

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
      excludeDirectories:
        - private
        - "  **/cache  "
        - private
      excludeFileNames:
        - Thumbs.db
        - "*.tmp"
        - THUMBS.DB
  extensions:
    - ".gif"
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
            var config = loader.LoadForEditing(configPath);
            var source = config.Watch.Sources[0];

            Assert.Equal([".png", ".jpg"], source.Extensions);
            Assert.Equal(["private", "**/cache"], source.ExcludeDirectories);
            Assert.Equal(["Thumbs.db", "*.tmp"], source.ExcludeFileNames);
            Assert.Empty(config.Watch.Extensions);
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
            Assert.Contains(".png", config.Watch.Sources[0].Extensions);
            Assert.Empty(config.Watch.Extensions);
            Assert.Equal("../logs", config.Logging.LogDirectory);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_ReadsLocalizationLanguage()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-locale-");

        try
        {
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");
            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources: []
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "logs"
localization:
  language: "de"
""";
            File.WriteAllText(configPath, yaml);

            var config = new AppConfigLoader().Load(configPath);

            Assert.Equal("de", config.Localization.Language);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_MissingLocalizationSection_DefaultsToAuto()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-locale-default-");

        try
        {
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");
            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources: []
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "logs"
""";
            File.WriteAllText(configPath, yaml);

            var config = new AppConfigLoader().Load(configPath);

            Assert.Equal("auto", config.Localization.Language);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_BlankLocalizationLanguage_NormalizesToAuto()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-locale-blank-");

        try
        {
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");
            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources: []
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "logs"
localization:
  language: "   "
""";
            File.WriteAllText(configPath, yaml);

            var config = new AppConfigLoader().Load(configPath);

            Assert.Equal("auto", config.Localization.Language);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_MissingLoggingTarget_DefaultsToEventLog()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-target-default-");

        try
        {
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");
            var yaml = """
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources: []
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "logs"
""";
            File.WriteAllText(configPath, yaml);

            var config = new AppConfigLoader().Load(configPath);

            Assert.Equal(LogTargets.EventLog, config.Logging.Target);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Theory]
    [InlineData("file", "file")]
    [InlineData("FILE", "file")]
    [InlineData("eventLog", "eventLog")]
    [InlineData("bogus", "eventLog")]
    public void Load_LoggingTarget_NormalizesValue(string yamlValue, string expected)
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-config-target-normalize-");

        try
        {
            var configPath = Path.Combine(tempRoot.FullName, "config.yaml");
            var yaml = $"""
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources: []
retry:
  maxAttempts: 4
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  target: "{yamlValue}"
  logDirectory: "logs"
""";
            File.WriteAllText(configPath, yaml);

            var config = new AppConfigLoader().Load(configPath);

            Assert.Equal(expected, config.Logging.Target);
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }
}
