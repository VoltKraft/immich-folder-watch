using ImmichFolderWatch.Core.Logging;
using Microsoft.Extensions.Logging;

if (args.Length != 1 || args[0].Length != 32 || File.ReadAllText(".ifw-native-log").TrimEnd() != args[0])
{
    return 2;
}

using var reference = LoggerFactory.Create(builder =>
{
    builder.SetMinimumLevel(LogLevel.Trace);
    builder.AddProvider(new FileLoggerProvider("reference-files", LogLevel.Trace));
    builder.AddSystemdConsole(options =>
    {
        options.IncludeScopes = false;
        options.UseUtcTimestamp = true;
    });
});
var logger = reference.CreateLogger("Desktop.Fixture");
var levels = new[] { LogLevel.Trace, LogLevel.Debug, LogLevel.Information, LogLevel.Warning, LogLevel.Error, LogLevel.Critical };
for (var index = 0; index < levels.Length; index++)
{
    var message = $"Grüße 二 {args[0]} {index}\nFortsetzung";
    logger.Log(levels[index], new EventId(100 + index), message, null, (text, _) => text);
}
return 0;
