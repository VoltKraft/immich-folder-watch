using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class WindowsDataMigrationServiceTests
{
    [Fact]
    public void MigrateLegacyWindowsData_UsesExistingProgramDataConfig_AndMovesLegacyDefaultLogs()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-win-migrate-existing-");

        try
        {
            var legacyInstallRoot = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "Program Files", "Immich Folder Watch")).FullName;
            var targetDataRoot = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "ProgramData", "Immich Folder Watch")).FullName;
            var targetLogDirectory = Directory.CreateDirectory(Path.Combine(targetDataRoot, "logs")).FullName;
            var targetConfigPath = Path.Combine(targetDataRoot, "config.yaml");
            var legacyLogDirectory = Directory.CreateDirectory(InstallationPaths.GetLegacyDefaultLogDirectory(legacyInstallRoot)).FullName;
            var legacyLogFile = Path.Combine(legacyLogDirectory, "daemon.log");

            File.WriteAllText(targetConfigPath, CreateConfigYaml(targetLogDirectory));
            File.WriteAllText(legacyLogFile, "old log");

            var service = new WindowsDataMigrationService();
            var result = service.MigrateLegacyWindowsData(targetConfigPath, targetLogDirectory, legacyInstallRoot);

            Assert.True(result.UsedExistingConfig);
            Assert.False(result.ConfigMigrated);
            Assert.Equal(1, result.MovedLogFileCount);
            Assert.Equal(0, result.SkippedLogFileCount);
            Assert.True(File.Exists(Path.Combine(targetLogDirectory, "daemon.log")));
            Assert.False(File.Exists(legacyLogFile));
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void MigrateLegacyWindowsData_MigratesStructuredConfig_AndRewritesDefaultLogDirectory()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-win-migrate-structured-");

        try
        {
            var legacyInstallRoot = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "Program Files", "Immich Folder Watch")).FullName;
            var legacyConfigDirectory = Directory.CreateDirectory(Path.Combine(legacyInstallRoot, "config")).FullName;
            var legacyWatchDirectory = Directory.CreateDirectory(Path.Combine(legacyInstallRoot, "watch")).FullName;
            var legacyLogDirectory = Directory.CreateDirectory(InstallationPaths.GetLegacyDefaultLogDirectory(legacyInstallRoot)).FullName;
            var targetDataRoot = Path.Combine(tempRoot.FullName, "ProgramData", "Immich Folder Watch");
            var targetConfigPath = Path.Combine(targetDataRoot, "config.yaml");
            var targetLogDirectory = Path.Combine(targetDataRoot, "logs");
            var legacyConfigPath = Path.Combine(legacyConfigDirectory, "config.yaml");

            File.WriteAllText(
                legacyConfigPath,
                CreateConfigYaml(legacyLogDirectory, "../watch"));
            File.WriteAllText(Path.Combine(legacyLogDirectory, "daemon.log"), "old log");

            var service = new WindowsDataMigrationService();
            var result = service.MigrateLegacyWindowsData(targetConfigPath, targetLogDirectory, legacyInstallRoot);
            var migratedConfig = new AppConfigLoader().LoadForEditing(targetConfigPath);

            Assert.True(result.ConfigMigrated);
            Assert.False(result.UsedExistingConfig);
            Assert.True(result.RewroteLogDirectoryToDefault);
            Assert.Equal(1, result.MovedLogFileCount);
            Assert.Equal(0, result.SkippedLogFileCount);
            Assert.Equal(Path.GetFullPath(targetLogDirectory), migratedConfig.Logging.LogDirectory);
            Assert.Equal(Path.GetFullPath(legacyWatchDirectory), migratedConfig.Watch.Sources[0].Path);
            Assert.False(File.Exists(legacyConfigPath));
            Assert.True(File.Exists(Path.Combine(targetLogDirectory, "daemon.log")));
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void MigrateLegacyWindowsData_FallsBackToRootConfig()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-win-migrate-root-");

        try
        {
            var legacyInstallRoot = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "Program Files", "Immich Folder Watch")).FullName;
            var legacyLogDirectory = Directory.CreateDirectory(InstallationPaths.GetLegacyDefaultLogDirectory(legacyInstallRoot)).FullName;
            var targetDataRoot = Path.Combine(tempRoot.FullName, "ProgramData", "Immich Folder Watch");
            var targetConfigPath = Path.Combine(targetDataRoot, "config.yaml");
            var targetLogDirectory = Path.Combine(targetDataRoot, "logs");
            var legacyRootConfigPath = Path.Combine(legacyInstallRoot, "config.yaml");

            File.WriteAllText(legacyRootConfigPath, CreateConfigYaml(legacyLogDirectory));

            var service = new WindowsDataMigrationService();
            var result = service.MigrateLegacyWindowsData(targetConfigPath, targetLogDirectory, legacyInstallRoot);
            var migratedConfig = new AppConfigLoader().LoadForEditing(targetConfigPath);

            Assert.True(result.ConfigMigrated);
            Assert.True(result.RewroteLogDirectoryToDefault);
            Assert.Equal(Path.GetFullPath(targetLogDirectory), migratedConfig.Logging.LogDirectory);
            Assert.False(File.Exists(legacyRootConfigPath));
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void MigrateLegacyWindowsData_PreservesCustomLogDirectory()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-win-migrate-custom-");

        try
        {
            var legacyInstallRoot = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "Program Files", "Immich Folder Watch")).FullName;
            var legacyConfigDirectory = Directory.CreateDirectory(Path.Combine(legacyInstallRoot, "config")).FullName;
            var legacyDefaultLogDirectory = Directory.CreateDirectory(InstallationPaths.GetLegacyDefaultLogDirectory(legacyInstallRoot)).FullName;
            var customLogDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "custom-logs")).FullName;
            var targetDataRoot = Path.Combine(tempRoot.FullName, "ProgramData", "Immich Folder Watch");
            var targetConfigPath = Path.Combine(targetDataRoot, "config.yaml");
            var targetLogDirectory = Path.Combine(targetDataRoot, "logs");
            var legacyConfigPath = Path.Combine(legacyConfigDirectory, "config.yaml");

            File.WriteAllText(legacyConfigPath, CreateConfigYaml(customLogDirectory));
            File.WriteAllText(Path.Combine(legacyDefaultLogDirectory, "daemon.log"), "old log");

            var service = new WindowsDataMigrationService();
            var result = service.MigrateLegacyWindowsData(targetConfigPath, targetLogDirectory, legacyInstallRoot);
            var migratedConfig = new AppConfigLoader().LoadForEditing(targetConfigPath);

            Assert.True(result.ConfigMigrated);
            Assert.False(result.RewroteLogDirectoryToDefault);
            Assert.Equal(0, result.MovedLogFileCount);
            Assert.Equal(0, result.SkippedLogFileCount);
            Assert.Equal(Path.GetFullPath(customLogDirectory), migratedConfig.Logging.LogDirectory);
            Assert.True(File.Exists(Path.Combine(legacyDefaultLogDirectory, "daemon.log")));
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    [Fact]
    public void MigrateLogFiles_SkipsConflictingTargets()
    {
        var tempRoot = Directory.CreateTempSubdirectory("ifw-log-migrate-");

        try
        {
            var sourceDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "source")).FullName;
            var sourceNestedDirectory = Directory.CreateDirectory(Path.Combine(sourceDirectory, "nested")).FullName;
            var targetDirectory = Directory.CreateDirectory(Path.Combine(tempRoot.FullName, "target")).FullName;

            File.WriteAllText(Path.Combine(sourceDirectory, "daemon.log"), "source");
            File.WriteAllText(Path.Combine(sourceNestedDirectory, "archive.log"), "archive");
            File.WriteAllText(Path.Combine(targetDirectory, "daemon.log"), "target");

            var service = new WindowsDataMigrationService();
            var result = service.MigrateLogFiles(sourceDirectory, targetDirectory);

            Assert.Equal(1, result.MovedLogFileCount);
            Assert.Equal(1, result.SkippedLogFileCount);
            Assert.True(File.Exists(Path.Combine(sourceDirectory, "daemon.log")));
            Assert.True(File.Exists(Path.Combine(targetDirectory, "daemon.log")));
            Assert.True(File.Exists(Path.Combine(targetDirectory, "nested", "archive.log")));
        }
        finally
        {
            tempRoot.Delete(recursive: true);
        }
    }

    private static string CreateConfigYaml(string logDirectory, string watchPath = @"C:\watch")
    {
        return $$"""
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "demo-key"
watch:
  sources:
    - path: "{{watchPath.Replace("\\", "\\\\", StringComparison.Ordinal)}}"
      albumName: "Screenshots"
      includeSubdirectories: false
  extensions:
    - ".png"
retry:
  maxAttempts: 3
  baseDelayMilliseconds: 250
logging:
  level: "Information"
  logDirectory: "{{logDirectory.Replace("\\", "\\\\", StringComparison.Ordinal)}}"
""";
    }
}
