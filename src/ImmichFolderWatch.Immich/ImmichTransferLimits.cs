namespace ImmichFolderWatch.Immich;

/// <summary>Resource ceilings for untrusted Immich responses. Exceeding a ceiling fails the operation.</summary>
public sealed record ImmichTransferLimits
{
    public int MaxMetadataBytes { get; init; } = 16 * 1024 * 1024;

    public int MaxDiagnosticBytes { get; init; } = 64 * 1024;

    public long MaxSearchBytes { get; init; } = 128L * 1024 * 1024;

    public int MaxSearchAssets { get; init; } = 125_000;

    public int MaxSearchPages { get; init; } = 500;

    public long MaxDownloadBytes { get; init; } = 100L * 1024 * 1024 * 1024;

    public long MinimumFreeSpaceBytes { get; init; } = 1024L * 1024 * 1024;

    public TimeSpan BodyInactivityTimeout { get; init; } = TimeSpan.FromSeconds(60);

    public TimeSpan DownloadTimeout { get; init; } = TimeSpan.FromHours(6);

    internal void Validate()
    {
        if (MaxMetadataBytes <= 0 || MaxDiagnosticBytes <= 0 || MaxSearchBytes <= 0
            || MaxSearchAssets <= 0 || MaxSearchPages <= 0 || MaxDownloadBytes <= 0
            || MinimumFreeSpaceBytes < 0 || BodyInactivityTimeout <= TimeSpan.Zero
            || DownloadTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(ImmichTransferLimits), "Transfer limits must be positive (the free-space reserve may be zero).");
        }
    }
}
