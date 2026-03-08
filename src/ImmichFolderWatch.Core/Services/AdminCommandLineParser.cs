using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public static class AdminCommandLineParser
{
    public const string Usage = """
Usage:
  ImmichFolderWatch.Admin status [--result-file <path>]
  ImmichFolderWatch.Admin apply-verified-config --source <path> [--result-file <path>]
""";

    public static bool TryParse(string[] args, out AdminCommand? command, out string message, out bool helpRequested)
    {
        command = null;
        helpRequested = false;

        if (args.Length == 1 && IsHelp(args[0]))
        {
            message = Usage;
            helpRequested = true;
            return false;
        }

        if (args.Length == 0)
        {
            message = $"Missing command.{Environment.NewLine}{Usage}";
            return false;
        }

        var commandName = args[0];
        if (args.Length == 2 && IsHelp(args[1]))
        {
            message = Usage;
            helpRequested = true;
            return false;
        }

        if (string.Equals(commandName, "status", StringComparison.OrdinalIgnoreCase))
        {
            return TryParseStatus(args[1..], out command, out message);
        }

        if (string.Equals(commandName, "apply-verified-config", StringComparison.OrdinalIgnoreCase))
        {
            return TryParseApplyVerifiedConfig(args[1..], out command, out message);
        }

        message = $"Unknown command '{commandName}'.{Environment.NewLine}{Usage}";
        return false;
    }

    private static bool TryParseStatus(string[] args, out AdminCommand? command, out string message)
    {
        command = null;
        message = string.Empty;

        if (!TryReadCommonOptions(args, requiresSource: false, out var sourcePath, out var resultFilePath, out message))
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(sourcePath))
        {
            message = $"The status command does not accept --source.{Environment.NewLine}{Usage}";
            return false;
        }

        command = new AdminCommand(AdminCommandKind.Status, null, resultFilePath);
        return true;
    }

    private static bool TryParseApplyVerifiedConfig(string[] args, out AdminCommand? command, out string message)
    {
        command = null;
        message = string.Empty;

        if (!TryReadCommonOptions(args, requiresSource: true, out var sourcePath, out var resultFilePath, out message))
        {
            return false;
        }

        command = new AdminCommand(AdminCommandKind.ApplyVerifiedConfig, sourcePath, resultFilePath);
        return true;
    }

    private static bool TryReadCommonOptions(
        string[] args,
        bool requiresSource,
        out string? sourcePath,
        out string? resultFilePath,
        out string message)
    {
        sourcePath = null;
        resultFilePath = null;
        message = string.Empty;

        for (var i = 0; i < args.Length; i++)
        {
            var argument = args[i];

            if (IsHelp(argument))
            {
                message = Usage;
                return false;
            }

            if (string.Equals(argument, "--source", StringComparison.OrdinalIgnoreCase))
            {
                if (!TryReadValue(args, ref i, "--source", out sourcePath, out message))
                {
                    return false;
                }

                continue;
            }

            if (string.Equals(argument, "--result-file", StringComparison.OrdinalIgnoreCase))
            {
                if (!TryReadValue(args, ref i, "--result-file", out resultFilePath, out message))
                {
                    return false;
                }

                continue;
            }

            message = $"Unknown option '{argument}'.{Environment.NewLine}{Usage}";
            return false;
        }

        if (requiresSource && string.IsNullOrWhiteSpace(sourcePath))
        {
            message = $"The apply-verified-config command requires --source <path>.{Environment.NewLine}{Usage}";
            return false;
        }

        return true;
    }

    private static bool TryReadValue(string[] args, ref int index, string optionName, out string? value, out string message)
    {
        value = null;
        message = string.Empty;

        if (index + 1 >= args.Length || string.IsNullOrWhiteSpace(args[index + 1]))
        {
            message = $"Missing value for {optionName}.{Environment.NewLine}{Usage}";
            return false;
        }

        index++;
        value = args[index].Trim();
        return true;
    }

    private static bool IsHelp(string value)
    {
        return string.Equals(value, "--help", StringComparison.OrdinalIgnoreCase)
            || string.Equals(value, "-h", StringComparison.OrdinalIgnoreCase);
    }
}
