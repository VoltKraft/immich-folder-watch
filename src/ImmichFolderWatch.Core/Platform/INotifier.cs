namespace ImmichFolderWatch.Core.Platform;

public interface INotifier
{
    Task ShowAsync(
        string title,
        string body,
        NotificationKind kind = NotificationKind.Info,
        CancellationToken cancellationToken = default);
}

public enum NotificationKind
{
    Info,
    Warning,
    Error,
}
