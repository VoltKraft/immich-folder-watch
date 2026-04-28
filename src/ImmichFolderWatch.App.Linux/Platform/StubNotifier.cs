using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class StubNotifier : INotifier
{
    private readonly ILogger<StubNotifier> _logger;

    public StubNotifier()
        : this(NullLogger<StubNotifier>.Instance)
    {
    }

    public StubNotifier(ILogger<StubNotifier> logger)
    {
        _logger = logger;
    }

    public Task ShowAsync(
        string title,
        string body,
        NotificationKind kind = NotificationKind.Info,
        CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Notification[{Kind}] {Title}: {Body}", kind, title, body);
        return Task.CompletedTask;
    }
}
