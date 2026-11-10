using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class SecureWatchRootTests : IDisposable
{
    private readonly string _test = Path.Combine(Path.GetTempPath(), "ifw-root-" + Guid.NewGuid().ToString("N"));
    private readonly List<string> _directoryLinks = [];
    private string Source => Path.Combine(_test, "source");
    private string Outside => Path.Combine(_test, "outside");

    public SecureWatchRootTests()
    {
        Directory.CreateDirectory(Source);
        Directory.CreateDirectory(Outside);
        File.WriteAllText(Path.Combine(Outside, "photo.jpg"), "outside-secret");
    }

    [Fact]
    public void OpenRead_RespectsExclusiveWriterLock()
    {
        var path = Path.Combine(Source, "writing.jpg");
        File.WriteAllText(path, "unfinished");
        using var root = SecureWatchRoot.Open(Source);
        using (var writer = new FileStream(path, FileMode.Open, FileAccess.Write, FileShare.None))
            Assert.ThrowsAny<IOException>(() => root.OpenRead("writing.jpg"));
        using var file = root.OpenRead("writing.jpg");
        Assert.Equal(10, file.Length);
    }

    [Fact]
    public void RootSymlinkWithTrailingSeparator_IsRejected()
    {
        var link = Path.Combine(_test, "linked-root");
        CreateDirectoryLink(link, Outside);
        Assert.ThrowsAny<IOException>(() => SecureWatchRoot.Open(link + Path.DirectorySeparatorChar));
    }

    [Fact]
    public void TransactionCache_BoundsContainersAndCreatesFreshContainerAfterEviction()
    {
        var counts = new List<int>();
        var hooks = new SecureWatchTestHooks { TransactionContainerCountChanged = counts.Add };
        using var root = SecureWatchRoot.Open(Source, hooks);
        for (var i = 0; i <= SecureTransactionPool.Capacity; i++)
        {
            var directory = "album-" + i;
            root.EnsureDirectory(directory);
            root.CheckWritable(directory);
        }
        root.CheckWritable("album-0");
        if (OperatingSystem.IsLinux())
        {
            Assert.Equal(SecureTransactionPool.Capacity, counts.Max());
            Assert.All(counts, count => Assert.InRange(count, 1, SecureTransactionPool.Capacity));
            Assert.Equal(2, Directory.GetDirectories(Path.Combine(Source, "album-0"), ".ifw-internal-*").Length);
        }
        else Assert.Empty(counts);
        Assert.Empty(root.EnumerateFiles(recursive: true));
    }

    [Fact]
    public void TransactionCache_EvictionKeepsActiveDownloadLeaseUsable()
    {
        using var root = SecureWatchRoot.Open(Source);
        root.EnsureDirectory("active");
        using var download = root.CreateDownload(Path.Combine("active", "photo.jpg"));
        download.Stream.Write(Encoding.UTF8.GetBytes("authorized"));
        for (var i = 0; i < SecureTransactionPool.Capacity; i++)
        {
            var directory = "album-" + i;
            root.EnsureDirectory(directory);
            root.CheckWritable(directory);
        }
        download.CompleteNoReplace();
        download.Dispose();
        Assert.Equal("authorized", File.ReadAllText(Path.Combine(Source, "active", "photo.jpg")));
        Assert.Equal(new[] { Path.Combine("active", "photo.jpg") }, root.EnumerateFiles(recursive: true));
    }

    [Fact]
    public void RepeatedTransactions_ReuseOnePrivateContainerPerParent()
    {
        using var root = SecureWatchRoot.Open(Source);
        for (var i = 0; i < 20; i++) root.CheckWritable("");
        var directories = Directory.GetDirectories(Source, ".ifw-internal-*");
        if (OperatingSystem.IsWindows()) Assert.Empty(directories);
        else Assert.Single(directories);
        AssertNoPayloadFiles(Source);
        Assert.Empty(root.EnumerateFiles(recursive: true));
    }

    [Fact]
    public void DirectoryReplacement_AfterAuthorizationNeverMovesReplacementAsOriginal()
    {
        var old = Path.Combine(Source, "old");
        var original = Path.Combine(Source, "original");
        Directory.CreateDirectory(old);
        File.WriteAllText(Path.Combine(old, "photo.jpg"), "authorized");
        var replaced = false;
        var hooks = new SecureWatchTestHooks
        {
            DirectoryAuthorizedBeforeMove = () =>
            {
                try { Directory.Move(old, original); }
                catch (IOException) when (OperatingSystem.IsWindows()) { return; }
                Directory.CreateDirectory(old);
                File.WriteAllText(Path.Combine(old, "photo.jpg"), "replacement");
                replaced = true;
            },
        };
        using var root = SecureWatchRoot.Open(Source, hooks);
        var error = Record.Exception(() => root.RenameDirectory("old", "new"));
        if (replaced)
        {
            Assert.IsAssignableFrom<IOException>(error);
            Assert.Equal("replacement", File.ReadAllText(Path.Combine(old, "photo.jpg")));
            Assert.Equal("authorized", File.ReadAllText(Path.Combine(original, "photo.jpg")));
            Assert.False(Directory.Exists(Path.Combine(Source, "new")));
        }
        else
        {
            Assert.Null(error);
            Assert.Equal("authorized", File.ReadAllText(Path.Combine(Source, "new", "photo.jpg")));
        }
    }

    [Fact]
    public void RenamedTransactionContainer_NeverCleansOrUsesReplacementName()
    {
        var moved = Path.Combine(_test, "moved-container");
        string? replacement = null;
        var hooks = new SecureWatchTestHooks
        {
            TransactionContainerCreated = name =>
            {
                replacement = Path.Combine(Source, name);
                Directory.Move(replacement, moved);
                Directory.CreateDirectory(replacement);
                File.WriteAllText(Path.Combine(replacement, "keep.jpg"), "replacement");
            },
        };
        using var root = SecureWatchRoot.Open(Source, hooks);
        using (var download = root.CreateDownload("photo.jpg"))
        {
            download.Stream.Write(Encoding.UTF8.GetBytes("authorized"));
            download.CompleteNoReplace();
        }
        root.CheckWritable("");
        Assert.Equal("authorized", File.ReadAllText(Path.Combine(Source, "photo.jpg")));
        if (replacement is not null)
        {
            Assert.Equal("replacement", File.ReadAllText(Path.Combine(replacement, "keep.jpg")));
            Assert.Empty(Directory.EnumerateFileSystemEntries(moved));
        }
        else Assert.True(OperatingSystem.IsWindows()); // Windows removes private dirs by held handle.
    }

    [Fact]
    public void RootReplacement_CannotRedirectReadsDownloadsEnumerationOrDeletion()
    {
        File.WriteAllText(Path.Combine(Source, "photo.jpg"), "authorized");
        using var root = SecureWatchRoot.Open(Source);
        var moved = Path.Combine(_test, "original-root");
        var replaced = TryReplaceDirectory(Source, moved, Outside);
        var authorizedLocation = replaced ? moved : Source;

        using (var file = root.OpenRead("photo.jpg")) Assert.Equal("authorized", Read(file.Stream));
        Assert.Equal(new[] { "photo.jpg" }, root.EnumerateFiles(recursive: true));
        root.EnsureDirectory("new");
        using (var download = root.CreateDownload(Path.Combine("new", "download.jpg")))
        {
            download.Stream.Write(Encoding.UTF8.GetBytes("download"));
            Assert.True(download.GetAvailableFreeSpace() > 0);
            download.CompleteNoReplace();
        }
        root.DeleteFile("photo.jpg");

        Assert.False(File.Exists(Path.Combine(authorizedLocation, "photo.jpg")));
        Assert.Equal("download", File.ReadAllText(Path.Combine(authorizedLocation, "new", "download.jpg")));
        Assert.Equal("outside-secret", File.ReadAllText(Path.Combine(Outside, "photo.jpg")));
        Assert.False(Directory.Exists(Path.Combine(Outside, "new")));
    }

    [Fact]
    public void ParentReplacement_AfterReadLeaseKeepsStreamMetadataAndDeletionOnOriginalIdentity()
    {
        var parent = Path.Combine(Source, "album");
        Directory.CreateDirectory(parent);
        File.WriteAllText(Path.Combine(parent, "photo.jpg"), "authorized");
        using var root = SecureWatchRoot.Open(Source);
        using var file = root.OpenRead(Path.Combine("album", "photo.jpg"), writableMetadata: true);
        var moved = Path.Combine(Source, "original-album");
        var replaced = TryReplaceDirectory(parent, moved, Outside);
        var originalTime = File.GetLastWriteTimeUtc(Path.Combine(Outside, "photo.jpg"));

        Assert.Equal("authorized", Read(file.Stream));
        file.SetTimestamps(DateTime.UtcNow.AddDays(-3), DateTime.UtcNow.AddDays(-2));
        file.Delete();
        file.Dispose();

        Assert.False(File.Exists(Path.Combine(replaced ? moved : parent, "photo.jpg")));
        Assert.Equal("outside-secret", File.ReadAllText(Path.Combine(Outside, "photo.jpg")));
        Assert.Equal(originalTime, File.GetLastWriteTimeUtc(Path.Combine(Outside, "photo.jpg")));
    }

    [Fact]
    public void ParentReplacement_BeforeOpenFailsClosedAndMarksEnumerationIncomplete()
    {
        var parent = Path.Combine(Source, "album");
        Directory.CreateDirectory(parent);
        using var root = SecureWatchRoot.Open(Source);
        Directory.Move(parent, Path.Combine(Source, "old-album"));
        CreateDirectoryLink(parent, Outside);

        Assert.ThrowsAny<IOException>(() => root.OpenRead(Path.Combine("album", "photo.jpg")));
        Assert.ThrowsAny<IOException>(() => root.DeleteFile(Path.Combine("album", "photo.jpg")));
        Assert.ThrowsAny<IOException>(() => root.CreateDownload(Path.Combine("album", "download.jpg")));
        Assert.ThrowsAny<IOException>(() => root.EnumerateFiles(recursive: true).ToArray());
        Assert.Equal("outside-secret", File.ReadAllText(Path.Combine(Outside, "photo.jpg")));
        Assert.False(File.Exists(Path.Combine(Outside, "download.jpg")));
    }

    [Fact]
    public void LeafReplacement_DoesNotReadOrDeleteReplacement()
    {
        var path = Path.Combine(Source, "photo.jpg");
        var renamed = Path.Combine(Source, "renamed.jpg");
        File.WriteAllText(path, "authorized");
        using var root = SecureWatchRoot.Open(Source);
        using var file = root.OpenRead("photo.jpg");
        File.Move(path, renamed);
        File.WriteAllText(path, "replacement");

        Assert.False(file.IsCurrentEntry());
        Assert.Equal("authorized", Read(file.Stream));
        if (OperatingSystem.IsWindows()) file.Delete();
        else Assert.ThrowsAny<IOException>(file.Delete);
        file.Dispose();

        Assert.Equal("replacement", File.ReadAllText(path));
        Assert.Equal("outside-secret", File.ReadAllText(Path.Combine(Outside, "photo.jpg")));
        if (!OperatingSystem.IsWindows()) Assert.Equal("authorized", File.ReadAllText(renamed));
    }

    [Fact]
    public void DownloadPublication_UsesPinnedParentAfterSwapAndNeverOverwritesDestination()
    {
        var parent = Path.Combine(Source, "album");
        Directory.CreateDirectory(parent);
        using var root = SecureWatchRoot.Open(Source);
        using var download = root.CreateDownload(Path.Combine("album", "photo.jpg"));
        download.Stream.Write(Encoding.UTF8.GetBytes("download"));
        var moved = Path.Combine(Source, "original-album");
        var replaced = TryReplaceDirectory(parent, moved, Outside);
        var target = Path.Combine(replaced ? moved : parent, "photo.jpg");
        File.WriteAllText(target, "concurrent-local-file");

        Assert.ThrowsAny<IOException>(download.CompleteNoReplace);
        download.Dispose();

        Assert.Equal("concurrent-local-file", File.ReadAllText(target));
        Assert.Equal("outside-secret", File.ReadAllText(Path.Combine(Outside, "photo.jpg")));
        AssertNoPayloadFiles(replaced ? moved : parent);
    }

    [Fact]
    public void DownloadCancellation_CleansPinnedTransactionWithoutTouchingReplacementDirectory()
    {
        var parent = Path.Combine(Source, "album");
        Directory.CreateDirectory(parent);
        using var root = SecureWatchRoot.Open(Source);
        var download = root.CreateDownload(Path.Combine("album", "photo.jpg"));
        download.Stream.Write(Encoding.UTF8.GetBytes("partial"));
        var moved = Path.Combine(Source, "original-album");
        var replaced = TryReplaceDirectory(parent, moved, Outside);

        download.Dispose();

        Assert.Equal("outside-secret", File.ReadAllText(Path.Combine(Outside, "photo.jpg")));
        AssertNoPayloadFiles(replaced ? moved : parent);
    }

    [Fact]
    public void DownloadCompleted_ExposesSameMetadataAndCreatesNoReplacement()
    {
        using var root = SecureWatchRoot.Open(Source);
        using var download = root.CreateDownload("download.jpg");
        download.Stream.Write(Encoding.UTF8.GetBytes("download"));
        var modified = new DateTime(2020, 2, 3, 4, 5, 6, DateTimeKind.Utc);
        download.SetTimestamps(modified, modified);
        download.CompleteNoReplace();
        Assert.Equal(8, download.Length);
        Assert.Equal(modified, download.LastWriteTimeUtc);
        download.Dispose();
        Assert.Equal("download", File.ReadAllText(Path.Combine(Source, "download.jpg")));
        AssertNoPayloadFiles(Source);
    }

    [Fact]
    public void DirectoryRename_IsAnchoredAndPreservesExistingDestination()
    {
        Directory.CreateDirectory(Path.Combine(Source, "old"));
        File.WriteAllText(Path.Combine(Source, "old", "photo.jpg"), "authorized");
        using var root = SecureWatchRoot.Open(Source);
        root.RenameDirectory("old", "new");
        Assert.Equal("authorized", File.ReadAllText(Path.Combine(Source, "new", "photo.jpg")));
        Directory.CreateDirectory(Path.Combine(Source, "occupied"));
        File.WriteAllText(Path.Combine(Source, "occupied", "photo.jpg"), "keep");
        Assert.ThrowsAny<IOException>(() => root.RenameDirectory("new", "occupied"));
        Assert.Equal("authorized", File.ReadAllText(Path.Combine(Source, "new", "photo.jpg")));
        Assert.Equal("keep", File.ReadAllText(Path.Combine(Source, "occupied", "photo.jpg")));
    }

    [Fact]
    public void RootDisposal_DoesNotInvalidateExistingLease()
    {
        File.WriteAllText(Path.Combine(Source, "photo.jpg"), "authorized");
        var root = SecureWatchRoot.Open(Source);
        using var file = root.OpenRead("photo.jpg");
        root.Dispose();
        Assert.Equal("authorized", Read(file.Stream));
        file.Delete();
    }

    [Fact]
    public void TimestampRepair_RejectsHardLinkedFile()
    {
        var outside = Path.Combine(Outside, "photo.jpg");
        var link = Path.Combine(Source, "linked.jpg");
        if (OperatingSystem.IsWindows()) Assert.True(CreateHardLink(link, outside, IntPtr.Zero));
        else Assert.Equal(0, Link(outside, link));
        var before = File.GetLastWriteTimeUtc(outside);
        using var root = SecureWatchRoot.Open(Source);
        using var file = root.OpenRead("linked.jpg", writableMetadata: true);
        Assert.ThrowsAny<IOException>(() => file.SetTimestamps(DateTime.UtcNow, DateTime.UtcNow));
        Assert.Equal(before, File.GetLastWriteTimeUtc(outside));
    }

    [Theory]
    [InlineData("../outside/photo.jpg")]
    [InlineData(".ifw-internal-fake/payload")]
    [InlineData("a/../photo.jpg")]
    public void InvalidRelativePaths_AreRejected(string relative)
    {
        using var root = SecureWatchRoot.Open(Source);
        Assert.ThrowsAny<IOException>(() => root.OpenRead(relative.Replace('/', Path.DirectorySeparatorChar)));
    }

    private static string Read(FileStream stream)
    {
        using var reader = new StreamReader(stream, Encoding.UTF8, leaveOpen: true);
        return reader.ReadToEnd();
    }

    private bool TryReplaceDirectory(string path, string moved, string outside)
    {
        try
        {
            Directory.Move(path, moved);
        }
        catch (IOException) when (OperatingSystem.IsWindows())
        {
            Assert.True(Directory.Exists(path));
            Assert.False(Directory.Exists(moved));
            return false; // Windows pins directories by denying delete/rename sharing.
        }
        CreateDirectoryLink(path, outside);
        return true;
    }

    private void CreateDirectoryLink(string path, string target)
    {
        if (!OperatingSystem.IsWindows())
        {
            Directory.CreateSymbolicLink(path, target);
            _directoryLinks.Add(path);
            return;
        }
        // Junctions exercise Windows reparse rejection without requiring symlink privileges.
        var start = new ProcessStartInfo("cmd.exe") { UseShellExecute = false, RedirectStandardError = true, RedirectStandardOutput = true };
        // cmd.exe parses its command string itself; ArgumentList would apply CRT escaping
        // to the embedded quotes and pass backslashes into mklink's filesystem paths.
        start.Arguments = $"/d /c mklink /J \"{path}\" \"{target}\"";
        using var process = Process.Start(start)!;
        process.WaitForExit();
        Assert.True(process.ExitCode == 0, process.StandardError.ReadToEnd() + process.StandardOutput.ReadToEnd());
        _directoryLinks.Add(path);
    }

    private static void AssertNoPayloadFiles(string directory)
    {
        foreach (var internalDirectory in Directory.EnumerateDirectories(directory, ".ifw-internal-*"))
            Assert.Empty(Directory.EnumerateFileSystemEntries(internalDirectory));
    }

    public void Dispose()
    {
        // Remove the link entries themselves before recursive fixture cleanup. In particular,
        // Windows junctions must never be recursively traversed to clean their targets.
        foreach (var link in _directoryLinks.AsEnumerable().Reverse())
            Directory.Delete(link, recursive: false);
        if (Directory.Exists(_test)) Directory.Delete(_test, recursive: true);
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateHardLinkW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CreateHardLink(string name, string existing, IntPtr security);
    [DllImport("libc", EntryPoint = "link", SetLastError = true)] private static extern int Link(string existing, string name);
}
