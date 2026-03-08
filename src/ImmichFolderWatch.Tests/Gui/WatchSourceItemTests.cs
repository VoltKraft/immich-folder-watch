using ImmichFolderWatch.Gui.Models;

namespace ImmichFolderWatch.Tests.Gui;

public sealed class WatchSourceItemTests
{
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
}
