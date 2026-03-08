using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public sealed class WindowsDataMigrationService
{
    private readonly AppConfigLoader _configLoader;
    private readonly AppConfigWriter _configWriter;

    public WindowsDataMigrationService()
        : this(new AppConfigLoader(), new AppConfigWriter())
    {
    }

    public WindowsDataMigrationService(AppConfigLoader configLoader, AppConfigWriter configWriter)
    {
        _configLoader = configLoader ?? throw new ArgumentNullException(nameof(configLoader));
        _configWriter = configWriter ?? throw new ArgumentNullException(nameof(configWriter));
    }

    public WindowsDataMigrationResult MigrateLegacyWindowsData(string targetConfigPath, string targetLogDirectory, string legacyInstallRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(targetConfigPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetLogDirectory);
        ArgumentException.ThrowIfNullOrWhiteSpace(legacyInstallRoot);

        var targetConfigFullPath = Path.GetFullPath(targetConfigPath);
        var targetLogDirectoryFullPath = Path.GetFullPath(targetLogDirectory);
        var legacyInstallRootFullPath = Path.GetFullPath(legacyInstallRoot);

        if (File.Exists(targetConfigFullPath))
        {
            var existingConfig = TryLoadConfig(targetConfigFullPath);
            var moveLogsToProgramData = existingConfig is not null
                && PathEquals(existingConfig.Logging.LogDirectory, targetLogDirectoryFullPath);
            var existingConfigLogMigrationResult = moveLogsToProgramData
                ? MigrateLogFiles(InstallationPaths.GetLegacyDefaultLogDirectory(legacyInstallRootFullPath), targetLogDirectoryFullPath)
                : new WindowsDataMigrationResult();

            return new WindowsDataMigrationResult
            {
                UsedExistingConfig = true,
                MovedLogFileCount = existingConfigLogMigrationResult.MovedLogFileCount,
                SkippedLogFileCount = existingConfigLogMigrationResult.SkippedLogFileCount,
            };
        }

        var structuredConfigPath = InstallationPaths.GetLegacyStructuredConfigPath(legacyInstallRootFullPath);
        var rootConfigPath = InstallationPaths.GetLegacyRootConfigPath(legacyInstallRootFullPath);
        var sourceConfigPath = File.Exists(structuredConfigPath)
            ? structuredConfigPath
            : File.Exists(rootConfigPath)
                ? rootConfigPath
                : null;

        if (string.IsNullOrWhiteSpace(sourceConfigPath))
        {
            return new WindowsDataMigrationResult();
        }

        var migratedConfig = _configLoader.Load(sourceConfigPath);
        var legacyDefaultLogDirectory = InstallationPaths.GetLegacyDefaultLogDirectory(legacyInstallRootFullPath);
        var rewriteLogDirectory = PathEquals(migratedConfig.Logging.LogDirectory, legacyDefaultLogDirectory);
        if (rewriteLogDirectory)
        {
            migratedConfig.Logging.LogDirectory = targetLogDirectoryFullPath;
        }

        var targetConfigDirectory = Path.GetDirectoryName(targetConfigFullPath)
            ?? throw new InvalidOperationException("The target config path does not have a parent directory.");
        Directory.CreateDirectory(targetConfigDirectory);
        File.WriteAllText(targetConfigFullPath, _configWriter.Serialize(migratedConfig));
        File.Delete(sourceConfigPath);

        var logMigrationResult = rewriteLogDirectory
            ? MigrateLogFiles(legacyDefaultLogDirectory, targetLogDirectoryFullPath)
            : new WindowsDataMigrationResult();

        DeleteDirectoryIfEmpty(Path.GetDirectoryName(sourceConfigPath));
        DeleteDirectoryIfEmpty(Path.GetDirectoryName(structuredConfigPath));

        return new WindowsDataMigrationResult
        {
            ConfigMigrated = true,
            RewroteLogDirectoryToDefault = rewriteLogDirectory,
            MovedLogFileCount = logMigrationResult.MovedLogFileCount,
            SkippedLogFileCount = logMigrationResult.SkippedLogFileCount,
        };
    }

    public WindowsDataMigrationResult MigrateLogFiles(string sourceLogDirectory, string targetLogDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceLogDirectory);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetLogDirectory);

        var sourceFullPath = Path.GetFullPath(sourceLogDirectory);
        var targetFullPath = Path.GetFullPath(targetLogDirectory);

        if (PathEquals(sourceFullPath, targetFullPath) || !Directory.Exists(sourceFullPath))
        {
            return new WindowsDataMigrationResult();
        }

        Directory.CreateDirectory(targetFullPath);

        var movedCount = 0;
        var skippedCount = 0;

        foreach (var sourceFile in Directory.GetFiles(sourceFullPath, "*", SearchOption.AllDirectories))
        {
            var relativePath = Path.GetRelativePath(sourceFullPath, sourceFile);
            var targetFile = Path.Combine(targetFullPath, relativePath);
            var targetDirectory = Path.GetDirectoryName(targetFile);
            if (!string.IsNullOrWhiteSpace(targetDirectory))
            {
                Directory.CreateDirectory(targetDirectory);
            }

            if (File.Exists(targetFile))
            {
                skippedCount++;
                continue;
            }

            File.Move(sourceFile, targetFile);
            movedCount++;
        }

        DeleteEmptyDirectoriesRecursively(sourceFullPath, deleteRoot: true);

        return new WindowsDataMigrationResult
        {
            MovedLogFileCount = movedCount,
            SkippedLogFileCount = skippedCount,
        };
    }

    private static bool PathEquals(string? left, string? right)
    {
        if (string.IsNullOrWhiteSpace(left) || string.IsNullOrWhiteSpace(right))
        {
            return false;
        }

        return string.Equals(
            Path.GetFullPath(left),
            Path.GetFullPath(right),
            StringComparison.OrdinalIgnoreCase);
    }

    private AppConfig? TryLoadConfig(string configPath)
    {
        try
        {
            return _configLoader.Load(configPath);
        }
        catch
        {
            return null;
        }
    }

    private static void DeleteDirectoryIfEmpty(string? directoryPath)
    {
        if (string.IsNullOrWhiteSpace(directoryPath) || !Directory.Exists(directoryPath))
        {
            return;
        }

        if (Directory.EnumerateFileSystemEntries(directoryPath).Any())
        {
            return;
        }

        Directory.Delete(directoryPath, recursive: false);
    }

    private static void DeleteEmptyDirectoriesRecursively(string directoryPath, bool deleteRoot)
    {
        if (!Directory.Exists(directoryPath))
        {
            return;
        }

        foreach (var childDirectory in Directory.GetDirectories(directoryPath))
        {
            DeleteEmptyDirectoriesRecursively(childDirectory, deleteRoot: true);
        }

        if (!deleteRoot)
        {
            return;
        }

        if (!Directory.EnumerateFileSystemEntries(directoryPath).Any())
        {
            Directory.Delete(directoryPath, recursive: false);
        }
    }
}
