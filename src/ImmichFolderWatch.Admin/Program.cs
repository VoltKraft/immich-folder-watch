using System.Diagnostics;
using System.ServiceProcess;
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
        var activationStateStore = new FileActivationStateStore(InstallationPaths.GetActivationStatePath(baseDirectory));
        var serviceManager = new WindowsServiceManager(
            InstallationPaths.ServiceName,
            configPath,
            InstallationPaths.GetLogDirectory(baseDirectory),
            activationStateStore);

        AdminCommandResponse response;
        try
        {
            response = command.Kind switch
            {
                AdminCommandKind.Status => CreateStatusResponse(serviceManager),
                AdminCommandKind.StartService => ExecuteServiceAction(serviceManager, static manager => manager.StartService(), "Service started successfully.", normalizeStartupType: true),
                AdminCommandKind.StopService => ExecuteServiceAction(serviceManager, static manager => manager.StopService(), "Service stopped successfully."),
                AdminCommandKind.RestartService => ExecuteServiceAction(serviceManager, static manager => manager.RestartService(), "Service restarted successfully.", normalizeStartupType: true),
                AdminCommandKind.ApplyVerifiedConfig => await ApplyVerifiedConfigAsync(command, configPath, serviceManager, activationStateStore),
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

    private static async Task<AdminCommandResponse> ApplyVerifiedConfigAsync(
        AdminCommand command,
        string targetConfigPath,
        IServiceManager serviceManager,
        IActivationStateStore activationStateStore)
    {
        ArgumentNullException.ThrowIfNull(command.SourcePath);

        await Task.Run(() => CopyConfigAtomically(command.SourcePath, targetConfigPath));

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

        var actions = VerifiedConfigApplyPolicy.Determine(statusBefore);

        if (actions.SetAutomaticDelayedStart)
        {
            serviceManager.SetStartupType(ServiceStartupType.Automatic, delayedAutoStart: true);
        }
        else if (actions.StartService || actions.RestartService)
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

        if (actions.MarkInitialVerificationCompleted)
        {
            activationStateStore.MarkInitialVerificationCompleted();
        }

        return new AdminCommandResponse
        {
            Success = true,
            Message = BuildApplyVerifiedConfigSuccessMessage(actions),
            Status = serviceManager.GetStatus(),
        };
    }

    private static string BuildApplyVerifiedConfigSuccessMessage(ConfigApplyActions actions)
    {
        if (actions.RestartService)
        {
            return "Configuration applied and service restarted successfully.";
        }

        if (actions.StartService)
        {
            return "Configuration applied and service started successfully.";
        }

        return "Configuration applied successfully.";
    }

    private static void NormalizeStartupForUserInitiatedStartOrRestart(IServiceManager serviceManager, ServiceStatusSnapshot snapshot)
    {
        if (!UserInitiatedServiceStartPolicy.ShouldSwitchToAutomaticDelayedStart(snapshot))
        {
            return;
        }

        serviceManager.SetStartupType(ServiceStartupType.Automatic, delayedAutoStart: true);
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
    private readonly IActivationStateStore _activationStateStore;
    private readonly string _scExePath;

    public WindowsServiceManager(
        string serviceName,
        string configPath,
        string defaultLogDirectory,
        IActivationStateStore activationStateStore)
    {
        _serviceName = serviceName;
        _configPath = Path.GetFullPath(configPath);
        _defaultLogDirectory = Path.GetFullPath(defaultLogDirectory);
        _activationStateStore = activationStateStore;
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
            IsInitialVerificationCompleted = _activationStateStore.IsInitialVerificationCompleted(),
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
