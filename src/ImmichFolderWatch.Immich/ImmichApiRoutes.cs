namespace ImmichFolderWatch.Immich;

internal static class ImmichApiRoutes
{
    public const string ServerPing = "server/ping";

    public const string ServerInfoPing = "server-info/ping";

    public const string ServerInfo = "server-info";

    public const string AssetUpload = "assets";

    public const string Albums = "albums";

    public const string AlbumsAssets = "albums/assets";

    public static string AlbumAssets(string albumId)
    {
        return $"albums/{albumId}/assets";
    }
}
