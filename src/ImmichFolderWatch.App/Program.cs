using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.Core.Installation;

namespace ImmichFolderWatch.App;

internal static class Program
{
    public const string MigrateLegacyUserArgument = "--migrate-legacy-user";

    internal static SingleInstanceCoordinator? SingleInstance { get; private set; }

    internal static bool StartHiddenForAutostart { get; private set; }

    [STAThread]
    public static int Main(string[] args)
    {
        if (args.Any(a => string.Equals(a, MigrateLegacyUserArgument, StringComparison.OrdinalIgnoreCase)))
        {
            return RunLegacyUserMigration();
        }

        StartHiddenForAutostart = args.Any(a =>
            string.Equals(a, AutostartManager.AutostartArgument, StringComparison.OrdinalIgnoreCase));

        var coordinator = SingleInstanceCoordinator.Create();
        if (!coordinator.IsPrimaryInstance)
        {
            coordinator.TrySignalShowGui(TimeSpan.FromSeconds(2));
            coordinator.Dispose();
            return 0;
        }

        SingleInstance = coordinator;

        try
        {
            var application = new App();
            application.InitializeComponent();
            return application.Run();
        }
        finally
        {
            coordinator.Dispose();
            SingleInstance = null;
        }
    }

    private static int RunLegacyUserMigration()
    {
        try
        {
            var legacyConfig = InstallationPaths.GetLegacyProgramDataConfigPath();
            var userConfig = InstallationPaths.GetConfigPath();

            if (File.Exists(legacyConfig) && !File.Exists(userConfig))
            {
                var userDir = Path.GetDirectoryName(userConfig);
                if (!string.IsNullOrWhiteSpace(userDir))
                {
                    Directory.CreateDirectory(userDir);
                }

                File.Copy(legacyConfig, userConfig);
            }

            try
            {
                new AutostartManager().Enable();
            }
            catch (Exception)
            {
            }

            return 0;
        }
        catch (Exception)
        {
            return 0;
        }
    }
}
