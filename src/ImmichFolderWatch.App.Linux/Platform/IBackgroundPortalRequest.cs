namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>The completed Background portal interaction, including the permissions actually granted.</summary>
public readonly record struct BackgroundPortalResponse(uint ResponseCode, bool Background, bool Autostart);

public interface IBackgroundPortalRequest
{
    /// <summary>
    /// Waits for Request.Response, rather than just the initial method reply.
    /// Throws on transport errors, caller cancellation, or a response timeout.
    /// </summary>
    Task<BackgroundPortalResponse> RequestAsync(bool autostart, CancellationToken cancellationToken = default);
}
