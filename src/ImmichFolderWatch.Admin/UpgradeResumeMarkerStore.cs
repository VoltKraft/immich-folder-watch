using Microsoft.Win32;

internal sealed class UpgradeResumeMarkerStore
{
    private const string RegistryKeyPath = @"Software\ImmichFolderWatch";
    private const string ResumeValueName = "ResumeServiceAfterUpgrade";

    public bool ConsumeWasRunningBeforeUpgrade()
    {
        var wasRunningBeforeUpgrade = WasRunningBeforeUpgrade();
        Clear();
        return wasRunningBeforeUpgrade;
    }

    private static bool WasRunningBeforeUpgrade()
    {
        using var key = Registry.LocalMachine.OpenSubKey(RegistryKeyPath, writable: false);
        var value = key?.GetValue(ResumeValueName);
        return value is not null && Convert.ToInt32(value) == 1;
    }

    private static void Clear()
    {
        using var key = Registry.LocalMachine.OpenSubKey(RegistryKeyPath, writable: true);
        key?.DeleteValue(ResumeValueName, throwOnMissingValue: false);
    }
}
