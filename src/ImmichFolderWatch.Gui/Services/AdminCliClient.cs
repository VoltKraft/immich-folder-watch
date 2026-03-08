using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Gui.Services;

internal sealed class AdminCliClient
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    private readonly string _adminExecutablePath;

    public AdminCliClient(string adminExecutablePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(adminExecutablePath);
        _adminExecutablePath = Path.GetFullPath(adminExecutablePath);
    }

    public Task<AdminCommandResponse> GetStatusAsync(CancellationToken cancellationToken)
    {
        return InvokeAsync(
            new[]
            {
                "status",
            },
            elevate: false,
            cancellationToken);
    }

    public Task<AdminCommandResponse> StartServiceAsync(CancellationToken cancellationToken)
    {
        return InvokeAsync(
            new[]
            {
                "start-service",
            },
            elevate: true,
            cancellationToken);
    }

    public Task<AdminCommandResponse> StopServiceAsync(CancellationToken cancellationToken)
    {
        return InvokeAsync(
            new[]
            {
                "stop-service",
            },
            elevate: true,
            cancellationToken);
    }

    public Task<AdminCommandResponse> RestartServiceAsync(CancellationToken cancellationToken)
    {
        return InvokeAsync(
            new[]
            {
                "restart-service",
            },
            elevate: true,
            cancellationToken);
    }

    public Task<AdminCommandResponse> ApplyVerifiedConfigAsync(string sourcePath, CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourcePath);

        return InvokeAsync(
            new[]
            {
                "apply-verified-config",
                "--source",
                sourcePath,
            },
            elevate: true,
            cancellationToken);
    }

    private async Task<AdminCommandResponse> InvokeAsync(string[] arguments, bool elevate, CancellationToken cancellationToken)
    {
        if (!File.Exists(_adminExecutablePath))
        {
            throw new FileNotFoundException($"Admin helper not found: {_adminExecutablePath}", _adminExecutablePath);
        }

        var resultPath = Path.Combine(Path.GetTempPath(), $"ifw-admin-result-{Guid.NewGuid():N}.json");
        try
        {
            using var process = new Process
            {
                StartInfo = CreateStartInfo(arguments, elevate, resultPath),
            };

            try
            {
                process.Start();
            }
            catch (Win32Exception) when (elevate)
            {
                throw;
            }

            await process.WaitForExitAsync(cancellationToken);

            if (!File.Exists(resultPath))
            {
                throw new InvalidOperationException($"The admin helper did not write a result file. Exit code: {process.ExitCode}");
            }

            var json = await File.ReadAllTextAsync(resultPath, cancellationToken);
            return JsonSerializer.Deserialize<AdminCommandResponse>(json, JsonOptions)
                ?? throw new InvalidOperationException("The admin helper returned an empty response.");
        }
        finally
        {
            if (File.Exists(resultPath))
            {
                File.Delete(resultPath);
            }
        }
    }

    private ProcessStartInfo CreateStartInfo(string[] arguments, bool elevate, string resultPath)
    {
        var allArguments = arguments
            .Concat(new[]
            {
                "--result-file",
                resultPath,
            })
            .Select(QuoteArgument);

        var startInfo = new ProcessStartInfo
        {
            FileName = _adminExecutablePath,
            WorkingDirectory = Path.GetDirectoryName(_adminExecutablePath) ?? AppContext.BaseDirectory,
            UseShellExecute = elevate,
            CreateNoWindow = !elevate,
            Arguments = string.Join(" ", allArguments),
        };

        if (elevate)
        {
            startInfo.Verb = "runas";
        }

        return startInfo;
    }

    private static string QuoteArgument(string argument)
    {
        if (string.IsNullOrEmpty(argument))
        {
            return "\"\"";
        }

        if (!argument.Any(char.IsWhiteSpace) && !argument.Contains('"'))
        {
            return argument;
        }

        return $"\"{argument.Replace("\"", "\\\"", StringComparison.Ordinal)}\"";
    }
}
