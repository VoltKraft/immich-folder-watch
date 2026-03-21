using System.Diagnostics;
using System.ServiceProcess;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Win32;

return await Bootstrapper.RunAsync(args);

internal static class Bootstrapper
{
    public static async Task<int> RunAsync(string[] args)
    {
        if (!AdminCommandLineParser.TryParse(args, out var command, out var parseMessage, out var helpRequested))
        {
            WriteLine(parseMessage, isError: !helpRequested);
            return helpRequested ? 0 : 1;
        }

        if (command is null)
        {
            WriteLine("Failed to parse command line options.", isError: true);
            return 1;
        }

        var baseDirectory = AppContext.BaseDirectory;
        var configPath = InstallationPaths.GetConfigPath(baseDirectory);
        var defaultLogDirectory = InstallationPaths.GetLogDirectory(baseDirectory);
        var migrationService = new WindowsDataMigrationService();
        var serviceManager = new WindowsServiceManager(
            InstallationPaths.ServiceName,
            configPath,
            defaultLogDirectory);

        AdminCommandResponse response;
        try
        {
            response = command.Kind switch
            {
                AdminCommandKind.Status => CreateStatusResponse(serviceManager),
                AdminCommandKind.StartService => ExecuteServiceAction(serviceManager, static manager => manager.StartService(), "Service started successfully.", normalizeStartupType: true),
                AdminCommandKind.StopService => ExecuteServiceAction(serviceManager, static manager => manager.StopService(), "Service stopped successfully."),
                AdminCommandKind.RestartService => ExecuteServiceAction(serviceManager, static manager => manager.RestartService(), "Service restarted successfully.", normalizeStartupType: true),
                AdminCommandKind.ResumeServiceAfterUpgrade => ResumeServiceAfterUpgrade(serviceManager, configPath),
                AdminCommandKind.MigrateDataLayout => MigrateDataLayout(command, configPath, defaultLogDirectory, baseDirectory, migrationService, serviceManager),
                AdminCommandKind.ApplyVerifiedConfig => await ApplyVerifiedConfigAsync(command, configPath, serviceManager, migrationService),
                _ => throw new InvalidOperationException($"Unsupported command kind: {command.Kind}"),
            };
        }
        catch (Exception ex)
        {
            response = new AdminCommandResponse
            {
                Success = false,
                Message = ex.Message,
                Status = serviceManager.GetStatus(),
            };
        }

        WriteResponse(command.ResultFilePath, response);
        return response.Success ? 0 : 1;
    }

    private static AdminCommandResponse CreateStatusResponse(IServiceManager serviceManager)
    {
        return new AdminCommandResponse
        {
            Success = true,
            Message = "Service status retrieved successfully.",
            Status = serviceManager.GetStatus(),
        };
    }

    private static AdminCommandResponse ExecuteServiceAction(
        IServiceManager serviceManager,
        Action<IServiceManager> action,
        string successMessage,
        bool normalizeStartupType = false)
    {
        var statusBefore = serviceManager.GetStatus();
        if (normalizeStartupType)
        {
            NormalizeStartupForUserInitiatedStartOrRestart(serviceManager, statusBefore);
        }

        action(serviceManager);

        return new AdminCommandResponse
        {
            Success = true,
            Message = successMessage,
            Status = serviceManager.GetStatus(),
        };
    }

    private static AdminCommandResponse ResumeServiceAfterUpgrade(
        IServiceManager serviceManager,
        string configPath)
    {
        var markerStore = new UpgradeResumeMarkerStore();
        var wasRunningBeforeUpgrade = markerStore.ConsumeWasRunningBeforeUpgrade();
        var statusBefore = serviceManager.GetStatus();

        if (!wasRunningBeforeUpgrade)
        {
            return new AdminCommandResponse
            {
                Success = true,
                Message = "Service was not running before the upgrade. No automatic restart was needed.",
                Status = statusBefore,
            };
        }

        if (!statusBefore.Exists)
        {
            return new AdminCommandResponse
            {
                Success = false,
                Message = $"Service '{InstallationPaths.ServiceName}' is not installed after the upgrade.",
                Status = statusBefore,
            };
        }

        var verificationResult = VerifyInstalledConfig(configPath);
        if (!UpgradeServiceResumePolicy.ShouldStartService(wasRunningBeforeUpgrade, statusBefore, verificationResult))
        {
            return new AdminCommandResponse
            {
                Success = true,
                Message = BuildUpgradeResumeSkippedMessage(verificationResult, statusBefore),
                Status = statusBefore,
            };
        }

        serviceManager.StartService();

        return new AdminCommandResponse
        {
            Success = true,
            Message = "Service was running before the upgrade and was started again successfully.",
            Status = serviceManager.GetStatus(),
        };
    }

    private static async Task<AdminCommandResponse> ApplyVerifiedConfigAsync(
        AdminCommand command,
        string targetConfigPath,
        IServiceManager serviceManager,
        WindowsDataMigrationService migrationService)
    {
        ArgumentNullException.ThrowIfNull(command.SourcePath);

        var statusBefore = serviceManager.GetStatus();
        if (!statusBefore.Exists)
        {
            return new AdminCommandResponse
            {
                Success = false,
                Message = $"Service '{InstallationPaths.ServiceName}' is not installed.",
                Status = statusBefore,
            };
        }

        var existingConfig = TryLoadConfig(targetConfigPath);
        var draftConfig = new AppConfigLoader().Load(command.SourcePath);
        var previousLogDirectory = existingConfig?.Logging.LogDirectory ?? statusBefore.LogDirectory;
        var logDirectoryChanged = !string.IsNullOrWhiteSpace(previousLogDirectory)
            && !PathEquals(previousLogDirectory, draftConfig.Logging.LogDirectory);

        var actions = VerifiedConfigApplyPolicy.Determine(statusBefore);

        if (logDirectoryChanged && statusBefore.State == ServiceRunState.Running)
        {
            serviceManager.StopService();
        }

        await Task.Run(() => CopyConfigAtomically(command.SourcePath, targetConfigPath));

        WindowsDataMigrationResult? logMigrationResult = null;
        if (logDirectoryChanged)
        {
            logMigrationResult = migrationService.MigrateLogFiles(previousLogDirectory, draftConfig.Logging.LogDirectory);
        }

        if (actions.StartService || actions.RestartService)
        {
            NormalizeStartupForUserInitiatedStartOrRestart(serviceManager, statusBefore);
        }

        if (actions.StartService)
        {
            serviceManager.StartService();
        }

        if (actions.RestartService)
        {
            serviceManager.RestartService();
        }

        return new AdminCommandResponse
        {
            Success = true,
            Message = BuildApplyVerifiedConfigSuccessMessage(actions, logMigrationResult),
            Status = serviceManager.GetStatus(),
        };
    }

    private static string BuildApplyVerifiedConfigSuccessMessage(ConfigApplyActions actions, WindowsDataMigrationResult? logMigrationResult)
    {
        var builder = new StringBuilder();

        if (actions.RestartService)
        {
            builder.Append("Configuration applied and service restarted successfully.");
        }
        else if (actions.StartService)
        {
            builder.Append("Configuration applied and service started successfully.");
        }
        else
        {
            builder.Append("Configuration applied successfully.");
        }

        AppendLogMigrationDetails(builder, logMigrationResult);
        return builder.ToString();
    }

    private static string BuildUpgradeResumeSkippedMessage(
        VerificationResult verificationResult,
        ServiceStatusSnapshot snapshot)
    {
        if (!verificationResult.Success)
        {
            return $"Service was running before the upgrade, but it was not restarted because the installed configuration is not valid: {string.Join(" | ", verificationResult.Errors)}";
        }

        return snapshot.State switch
        {
            ServiceRunState.Running => "Service is already running after the upgrade.",
            ServiceRunState.StartPending => "Service is already starting after the upgrade.",
            _ => $"Service was running before the upgrade, but it was not restarted automatically because the current service state is '{snapshot.State}'.",
        };
    }

    private static AdminCommandResponse MigrateDataLayout(
        AdminCommand command,
        string configPath,
        string defaultLogDirectory,
        string baseDirectory,
        WindowsDataMigrationService migrationService,
        IServiceManager serviceManager)
    {
        var legacyInstallRoot = string.IsNullOrWhiteSpace(command.LegacyInstallRoot)
            ? InstallationPaths.GetInstallRoot(baseDirectory)
            : Path.GetFullPath(command.LegacyInstallRoot);

        var migrationResult = migrationService.MigrateLegacyWindowsData(configPath, defaultLogDirectory, legacyInstallRoot);
        var message = BuildDataLayoutMigrationMessage(migrationResult, configPath, defaultLogDirectory);

        return new AdminCommandResponse
        {
            Success = true,
            Message = message,
            Status = serviceManager.GetStatus(),
        };
    }

    private static string BuildDataLayoutMigrationMessage(
        WindowsDataMigrationResult migrationResult,
        string configPath,
        string logDirectory)
    {
        if (migrationResult.UsedExistingConfig)
        {
            var existingLayoutMessage = new StringBuilder($"ProgramData data layout already initialized at {configPath}.");
            AppendLogMigrationDetails(existingLayoutMessage, migrationResult);
            return existingLayoutMessage.ToString();
        }

        if (!migrationResult.ConfigMigrated && migrationResult.MovedLogFileCount == 0 && migrationResult.SkippedLogFileCount == 0)
        {
            return "No legacy Program Files data needed to be migrated.";
        }

        var builder = new StringBuilder("ProgramData data layout migration completed successfully.");
        if (migrationResult.ConfigMigrated)
        {
            builder.Append($" Config migrated to {configPath}.");
        }

        if (migrationResult.RewroteLogDirectoryToDefault)
        {
            builder.Append($" logging.logDirectory was updated to {logDirectory}.");
        }

        AppendLogMigrationDetails(builder, migrationResult);
        return builder.ToString();
    }

    private static void NormalizeStartupForUserInitiatedStartOrRestart(IServiceManager serviceManager, ServiceStatusSnapshot snapshot)
    {
        if (!UserInitiatedServiceStartPolicy.ShouldSwitchToAutomaticDelayedStart(snapshot))
        {
            return;
        }

        serviceManager.SetStartupType(ServiceStartupType.Automatic, delayedAutoStart: true);
    }

    private static VerificationResult VerifyInstalledConfig(string configPath)
    {
        try
        {
            var config = new AppConfigLoader().Load(configPath);
            var validationErrors = AppConfigValidator.Validate(config);
            return validationErrors.Count > 0
                ? VerificationResult.Failed(validationErrors)
                : VerificationResult.Passed();
        }
        catch (Exception ex)
        {
            return VerificationResult.Failed([$"Configuration file could not be loaded: {ex.Message}"]);
        }
    }

    private static AppConfig? TryLoadConfig(string configPath)
    {
        if (!File.Exists(configPath))
        {
            return null;
        }

        return new AppConfigLoader().Load(configPath);
    }

    private static bool PathEquals(string left, string right)
    {
        return string.Equals(
            Path.GetFullPath(left),
            Path.GetFullPath(right),
            StringComparison.OrdinalIgnoreCase);
    }

    private static void AppendLogMigrationDetails(StringBuilder builder, WindowsDataMigrationResult? migrationResult)
    {
        if (migrationResult is null)
        {
            return;
        }

        if (migrationResult.MovedLogFileCount > 0)
        {
            builder.Append($" Moved {migrationResult.MovedLogFileCount} log file(s).");
        }

        if (migrationResult.SkippedLogFileCount > 0)
        {
            builder.Append($" Skipped {migrationResult.SkippedLogFileCount} conflicting log file(s) already present in the target directory.");
        }
    }

    private static void CopyConfigAtomically(string sourcePath, string targetPath)
    {
        var sourceFullPath = Path.GetFullPath(sourcePath);
        if (!File.Exists(sourceFullPath))
        {
            throw new FileNotFoundException($"Source config file not found: {sourceFullPath}", sourceFullPath);
        }

        var targetFullPath = Path.GetFullPath(targetPath);
        var targetDirectory = Path.GetDirectoryName(targetFullPath)
            ?? throw new InvalidOperationException("The target config path does not have a parent directory.");

        Directory.CreateDirectory(targetDirectory);

        var replacementPath = Path.Combine(targetDirectory, $"{Path.GetFileName(targetFullPath)}.new");
        if (File.Exists(replacementPath))
        {
            File.Delete(replacementPath);
        }

        File.Copy(sourceFullPath, replacementPath, overwrite: true);

        try
        {
            if (File.Exists(targetFullPath))
            {
                File.Replace(replacementPath, targetFullPath, destinationBackupFileName: null, ignoreMetadataErrors: true);
            }
            else
            {
                File.Move(replacementPath, targetFullPath);
            }
        }
        finally
        {
            if (File.Exists(replacementPath))
            {
                File.Delete(replacementPath);
            }
        }
    }

    private static void WriteResponse(string? resultFilePath, AdminCommandResponse response)
    {
        var json = JsonSerializer.Serialize(
            response,
            new JsonSerializerOptions
            {
                WriteIndented = true,
            });

        if (!string.IsNullOrWhiteSpace(resultFilePath))
        {
            var fullPath = Path.GetFullPath(resultFilePath);
            var directory = Path.GetDirectoryName(fullPath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            File.WriteAllText(fullPath, json);
            return;
        }

        WriteLine(json, isError: !response.Success);
    }

    private static void WriteLine(string message, bool isError)
    {
        if (isError)
        {
            Console.Error.WriteLine(message);
            return;
        }

        Console.WriteLine(message);
    }
}

internal sealed class WindowsServiceManager : IServiceManager
{
    private static readonly TimeSpan ServiceTimeout = TimeSpan.FromSeconds(30);

    private readonly string _serviceName;
    private readonly string _configPath;
    private readonly string _defaultLogDirectory;
    private readonly string _scExePath;

    public WindowsServiceManager(
        string serviceName,
        string configPath,
        string defaultLogDirectory)
    {
        _serviceName = serviceName;
        _configPath = Path.GetFullPath(configPath);
        _defaultLogDirectory = Path.GetFullPath(defaultLogDirectory);
        _scExePath = Path.Combine(Environment.SystemDirectory, "sc.exe");
    }

    public ServiceStatusSnapshot GetStatus()
    {
        var exists = ServiceExists();
        return new ServiceStatusSnapshot
        {
            ServiceName = _serviceName,
            Exists = exists,
            State = exists ? GetRunState() : ServiceRunState.NotInstalled,
            StartupType = exists ? GetStartupType() : ServiceStartupType.Unknown,
            DelayedAutoStart = exists && GetDelayedAutoStart(),
            ConfigPath = _configPath,
            LogDirectory = ResolveLogDirectory(),
        };
    }

    public void SetStartupType(ServiceStartupType startupType, bool delayedAutoStart)
    {
        var startValue = startupType switch
        {
            ServiceStartupType.Automatic when delayedAutoStart => "delayed-auto",
            ServiceStartupType.Automatic => "auto",
            ServiceStartupType.Manual => "demand",
            ServiceStartupType.Disabled => "disabled",
            _ => throw new InvalidOperationException($"Unsupported startup type: {startupType}"),
        };

        RunScCommand("config", _serviceName, "start=", startValue);

        var serviceKeyPath = $@"SYSTEM\CurrentControlSet\Services\{_serviceName}";
        using var serviceKey = Registry.LocalMachine.OpenSubKey(serviceKeyPath, writable: true)
            ?? throw new InvalidOperationException($"Service registry key not found: {serviceKeyPath}");

        serviceKey.SetValue("DelayedAutoStart", delayedAutoStart ? 1 : 0, RegistryValueKind.DWord);
    }

    public void StartService()
    {
        using var controller = CreateController();
        if (controller.Status == ServiceControllerStatus.Running)
        {
            return;
        }

        controller.Start();
        controller.WaitForStatus(ServiceControllerStatus.Running, ServiceTimeout);
    }

    public void StopService()
    {
        using var controller = CreateController();
        if (controller.Status == ServiceControllerStatus.Stopped)
        {
            return;
        }

        controller.Stop();
        controller.WaitForStatus(ServiceControllerStatus.Stopped, ServiceTimeout);
    }

    public void RestartService()
    {
        using var controller = CreateController();
        if (controller.Status != ServiceControllerStatus.Stopped)
        {
            controller.Stop();
            controller.WaitForStatus(ServiceControllerStatus.Stopped, ServiceTimeout);
        }

        controller.Start();
        controller.WaitForStatus(ServiceControllerStatus.Running, ServiceTimeout);
    }

    private bool ServiceExists()
    {
        return ServiceController.GetServices()
            .Any(service => string.Equals(service.ServiceName, _serviceName, StringComparison.OrdinalIgnoreCase));
    }

    private ServiceController CreateController()
    {
        if (!ServiceExists())
        {
            throw new InvalidOperationException($"Service '{_serviceName}' is not installed.");
        }

        return new ServiceController(_serviceName);
    }

    private ServiceRunState GetRunState()
    {
        using var controller = CreateController();
        return controller.Status switch
        {
            ServiceControllerStatus.Running => ServiceRunState.Running,
            ServiceControllerStatus.Stopped => ServiceRunState.Stopped,
            ServiceControllerStatus.StartPending => ServiceRunState.StartPending,
            ServiceControllerStatus.StopPending => ServiceRunState.StopPending,
            ServiceControllerStatus.Paused => ServiceRunState.Paused,
            _ => ServiceRunState.Unknown,
        };
    }

    private ServiceStartupType GetStartupType()
    {
        var serviceKeyPath = $@"SYSTEM\CurrentControlSet\Services\{_serviceName}";
        using var serviceKey = Registry.LocalMachine.OpenSubKey(serviceKeyPath, writable: false);
        var startValue = serviceKey?.GetValue("Start") as int? ?? Convert.ToInt32(serviceKey?.GetValue("Start") ?? -1);

        return startValue switch
        {
            2 => ServiceStartupType.Automatic,
            3 => ServiceStartupType.Manual,
            4 => ServiceStartupType.Disabled,
            _ => ServiceStartupType.Unknown,
        };
    }

    private bool GetDelayedAutoStart()
    {
        var serviceKeyPath = $@"SYSTEM\CurrentControlSet\Services\{_serviceName}";
        using var serviceKey = Registry.LocalMachine.OpenSubKey(serviceKeyPath, writable: false);
        var delayedValue = serviceKey?.GetValue("DelayedAutoStart");
        return delayedValue is not null && Convert.ToInt32(delayedValue) == 1;
    }

    private string ResolveLogDirectory()
    {
        if (!File.Exists(_configPath))
        {
            return _defaultLogDirectory;
        }

        try
        {
            var config = new AppConfigLoader().Load(_configPath);
            return string.IsNullOrWhiteSpace(config.Logging.LogDirectory)
                ? _defaultLogDirectory
                : config.Logging.LogDirectory;
        }
        catch
        {
            return _defaultLogDirectory;
        }
    }

    private void RunScCommand(params string[] arguments)
    {
        if (!File.Exists(_scExePath))
        {
            throw new FileNotFoundException($"sc.exe not found at {_scExePath}", _scExePath);
        }

        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = _scExePath,
                UseShellExecute = false,
                RedirectStandardError = true,
                RedirectStandardOutput = true,
            },
        };

        foreach (var argument in arguments)
        {
            process.StartInfo.ArgumentList.Add(argument);
        }

        process.Start();
        process.WaitForExit();

        if (process.ExitCode == 0)
        {
            return;
        }

        var errorText = process.StandardError.ReadToEnd();
        if (string.IsNullOrWhiteSpace(errorText))
        {
            errorText = process.StandardOutput.ReadToEnd();
        }

        throw new InvalidOperationException(
            $"sc.exe {string.Join(' ', arguments)} failed with exit code {process.ExitCode}: {errorText.Trim()}");
    }
}
