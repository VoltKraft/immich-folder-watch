namespace ImmichFolderWatch.Core.Models;

/// <summary>
/// Describes a newer release and its trusted download page.
/// </summary>
/// <param name="Version">The newer stable release version.</param>
/// <param name="DownloadUri">The release-specific GitHub download page.</param>
public sealed record UpdateInfo(Version Version, Uri DownloadUri);
