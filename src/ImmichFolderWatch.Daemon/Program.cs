using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Daemon;
using ImmichFolderWatch.Daemon.Logging;
using ImmichFolderWatch.Daemon.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Reflection;

return await Bootstrapper.RunAsync(args);

internal static class Bootstrapper
{
    private static readonly string ProductVersion = GetProductVersion();

    public static async Task<int> RunAsync(string[] args)
    {
        if (!CommandLineOptions.TryParse(args, out var options, out var parseMessage, out var helpRequested))
        {
            Console.WriteLine(parseMessage);
            return helpRequested ? 0 : 1;
        }

        if (options is null)
        {
            Console.Error.WriteLine("Failed to parse command line options.");
            return 1;
        }

        var loader = new AppConfigLoader();
        AppConfig appConfig;

        try
        {
            appConfig = loader.Load(options.ConfigPath);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Failed to load config: {ex.Message}");
            return 1;
        }

        var validationErrors = AppConfigValidator.Validate(appConfig);
        if (validationErrors.Count > 0)
        {
            Console.Error.WriteLine("Configuration validation failed:");
            foreach (var error in validationErrors)
            {
                Console.Error.WriteLine($"- {error}");
            }

            return 1;
        }

        Directory.CreateDirectory(appConfig.Logging.LogDirectory);

        var logLevel = LogLevelParser.Parse(appConfig.Logging.Level);

        using var host = Host.CreateDefaultBuilder(args)
            .UseWindowsService(options =>
            {
                options.ServiceName = "Immich Folder Watch";
            })
            .ConfigureLogging(logging =>
            {
                logging.ClearProviders();
                logging.SetMinimumLevel(logLevel);
                logging.AddSimpleConsole(options =>
                {
                    options.TimestampFormat = "yyyy-MM-dd HH:mm:ss.fff ";
                    options.SingleLine = true;
                });
                logging.AddProvider(new FileLoggerProvider(appConfig.Logging.LogDirectory, logLevel));
            })
            .ConfigureServices(services =>
            {
                services.AddSingleton(appConfig);
                services.AddSingleton(appConfig.Retry);
                services.AddSingleton<IFileReadinessChecker, FileReadinessChecker>();
                services.AddSingleton<IUploadBatchQueue, UploadBatchQueue>();

                services.AddHttpClient<IImmichAssetClient, ImmichAssetClient>((serviceProvider, client) =>
                {
                    var config = serviceProvider.GetRequiredService<AppConfig>();
                    var normalizedApiUrl = AppConfigValidator.EnsureTrailingSlash(config.Immich.ServerApiUrl);

                    client.BaseAddress = new Uri(normalizedApiUrl, UriKind.Absolute);
                    client.Timeout = TimeSpan.FromMinutes(2);
                    client.DefaultRequestHeaders.Add("x-api-key", config.Immich.ApiKey);
                    client.DefaultRequestHeaders.UserAgent.ParseAdd($"immich-folder-watch/{ProductVersion}");
                });

                services.AddHostedService<FolderWatchWorker>();
            })
            .Build();

        var startupLogger = host.Services
            .GetRequiredService<ILoggerFactory>()
            .CreateLogger("Startup");

        startupLogger.LogInformation("Performing startup connectivity check against {ApiUrl}.", appConfig.Immich.ServerApiUrl);

        try
        {
            var immichClient = host.Services.GetRequiredService<IImmichAssetClient>();
            await immichClient.PingAsync(CancellationToken.None);
        }
        catch (Exception ex)
        {
            startupLogger.LogCritical(ex, "Startup failed because Immich is not reachable.");
            return 1;
        }

        startupLogger.LogInformation("Startup validation completed successfully.");

        await host.RunAsync();
        return 0;
    }

    private static string GetProductVersion()
    {
        var informationalVersion = typeof(Bootstrapper)
            .Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
            ?.InformationalVersion;

        if (!string.IsNullOrWhiteSpace(informationalVersion))
        {
            var plusIndex = informationalVersion.IndexOf('+');
            return plusIndex >= 0
                ? informationalVersion[..plusIndex]
                : informationalVersion;
        }

        return "1.2.3";
    }
}
