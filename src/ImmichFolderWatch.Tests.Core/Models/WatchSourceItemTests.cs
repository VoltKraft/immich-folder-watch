using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Core.Models;

public sealed class WatchSourceItemTests
{
    [Fact]
    public void DeleteAfterUpload_IsVisibleOnlyForUploadModes_AndPreservesValue()
    {
        var item = new WatchSourceItem();

        Assert.False(item.DeleteAfterUpload);
        Assert.True(item.ShowDeleteAfterUpload);

        item.DeleteAfterUpload = true;
        item.SyncMode = WatchSourceSyncModes.UploadAll;

        Assert.True(item.ShowDeleteAfterUpload);
        Assert.True(item.DeleteAfterUpload);

        item.SyncMode = WatchSourceSyncModes.Sync;

        Assert.False(item.ShowDeleteAfterUpload);
        Assert.True(item.DeleteAfterUpload);

        item.SyncMode = WatchSourceSyncModes.UploadNew;

        Assert.True(item.ShowDeleteAfterUpload);
        Assert.True(item.DeleteAfterUpload);
    }

    [Fact]
    public void Path_PrefillsAlbumNameOnce_FromFolderName()
    {
        var item = new WatchSourceItem();

        item.Path = @"C:\Users\jan\Pictures\Screenshots";

        Assert.Equal("Screenshots", item.AlbumName);

        item.Path = @"C:\Users\jan\Pictures\Camera";

        Assert.Equal("Screenshots", item.AlbumName);
    }

    [Fact]
    public void AlbumName_StaysEmptyAfterUserClearsIt()
    {
        var item = new WatchSourceItem
        {
            Path = @"C:\Users\jan\Pictures\Screenshots",
        };

        item.AlbumName = string.Empty;
        item.Path = @"C:\Users\jan\Pictures\Camera";

        Assert.Equal(string.Empty, item.AlbumName);
    }

    [Fact]
    public void AlbumName_DoesNotAutofill_WhenUserSetCustomValueBeforePath()
    {
        var item = new WatchSourceItem
        {
            AlbumName = "Manual Album",
        };

        item.Path = @"C:\Users\jan\Pictures\Screenshots";

        Assert.Equal("Manual Album", item.AlbumName);
    }

    [Fact]
    public void LoadedEmptyAlbum_RemainsEmptyAndDoesNotAutofillLater()
    {
        var item = new WatchSourceItem
        {
            Path = @"C:\Users\jan\Pictures\Screenshots",
            AlbumName = string.Empty,
        };

        Assert.Equal(string.Empty, item.AlbumName);

        item.Path = @"C:\Users\jan\Pictures\Camera";

        Assert.Equal(string.Empty, item.AlbumName);
    }

    [Fact]
    public void DisplayPath_FallsBackToPath_WhenNotOverridden()
    {
        var item = new WatchSourceItem
        {
            Path = "/home/user/Pictures/Photos",
        };

        Assert.Equal("/home/user/Pictures/Photos", item.DisplayPath);
    }

    [Fact]
    public void DisplayPath_UserEditMirrorsBackIntoPath()
    {
        var item = new WatchSourceItem
        {
            Path = "/home/user/Pictures/Photos",
        };

        item.DisplayPath = "/home/user/Pictures/Vacation";

        Assert.Equal("/home/user/Pictures/Vacation", item.DisplayPath);
        Assert.Equal("/home/user/Pictures/Vacation", item.Path);
    }

    [Fact]
    public void SetPortalPath_KeepsMountInPath_AndShowsHostInDisplayPath()
    {
        var item = new WatchSourceItem();

        item.SetPortalPath(
            mountPath: "/run/user/1000/doc/abc123/Photos",
            hostPath: "/home/user/Pictures/Photos");

        Assert.Equal("/run/user/1000/doc/abc123/Photos", item.Path);
        Assert.Equal("/home/user/Pictures/Photos", item.DisplayPath);
    }

    [Fact]
    public void SetPortalPath_AlbumNameSuggestionUsesPath_LastSegmentMatchesHostPath()
    {
        var item = new WatchSourceItem();

        item.SetPortalPath(
            mountPath: "/run/user/1000/doc/abc123/Photos",
            hostPath: "/home/user/Pictures/Photos");

        // Album auto-fill reads Path; the mount's last segment ("Photos")
        // matches the host path's basename — same suggestion either way.
        Assert.Equal("Photos", item.AlbumName);
    }

    [Fact]
    public void DisplayPath_UserEditAfterPortalPick_ClobbersPathToHostPath()
    {
        var item = new WatchSourceItem();
        item.SetPortalPath(
            mountPath: "/run/user/1000/doc/abc123/Photos",
            hostPath: "/home/user/Pictures/Photos");

        item.DisplayPath = "/home/user/Pictures/Vacation";

        Assert.Equal("/home/user/Pictures/Vacation", item.Path);
        Assert.Equal("/home/user/Pictures/Vacation", item.DisplayPath);
    }
}
