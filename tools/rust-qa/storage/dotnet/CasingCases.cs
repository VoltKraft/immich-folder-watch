using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static partial class CasingCases
{
    private const string Baseline = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc";
    private const string Account = "ifw-casing-primary";
    private const string OtherAccount = "ifw-casing-other";
    private const string RelativePath = "Media-ƛ.jpg";
    private const string UpperRelativePath = "Media-Ƛ.jpg";
    private const string RepairRelativePath = "Repair-ƛ.mov";
    private const string TombstoneRelativePath = "Removed-ƛ.jpg";
    private const string AlbumDirectory = "Album-ƛ";
    private const string AlbumId = "Opaque-Id-ƛ";
    private const string OtherAlbumId = "Opaque-Id-Ƛ";
    private static readonly DateTimeOffset Seed = new DateTimeOffset(2024, 2, 29, 3, 4, 5, TimeSpan.Zero).AddTicks(1_234_567);
    private static string SourcePath => OperatingSystem.IsWindows() ? @"C:\IfwSynthetic\Case-ƛ" : "/IfwSynthetic/Case-ƛ";

    public static async Task WriteAsync(string destination)
    {
        var (os, arch) = NativeTarget();
        var sources = VerifyShippingSources();
        await WithFreshDirectoryAsync(destination, async staging =>
        {
            var casing = InvariantUppercaseProfile.Capture();
            casing.Write(staging);
            var cases = new Dictionary<string, object>();
            foreach (var mode in new[] { "sensitive", "insensitive" })
                cases.Add(mode, await SnapshotAsync(staging, mode));
            var manifest = new
            {
                format = "ifw-qualified-path-key-fixture-v1", baseline = Baseline, sources,
                seed = Seed, os, arch, target = RuntimeInformation.RuntimeIdentifier,
                runtime = Environment.Version.ToString(), nativeUpperOfDiscriminator = "ƛ".ToUpperInvariant(),
                casingProfile = casing.Manifest,
                coreAssemblySha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location),
                fixtureAssemblySha256 = HashFile(typeof(CasingCases).Assembly.Location),
                sourcePath = SourcePath, account = Account, otherAccount = OtherAccount,
                relativePath = RelativePath, upperRelativePath = UpperRelativePath,
                repairRelativePath = RepairRelativePath, tombstoneRelativePath = TombstoneRelativePath,
                albumDirectory = AlbumDirectory, albumId = AlbumId, otherAlbumId = OtherAlbumId, cases
            };
            await File.WriteAllTextAsync(Path.Combine(staging, "manifest.json"),
                JsonSerializer.Serialize(manifest, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        });
    }

    private static (string Os, string Arch) NativeTarget()
    {
        var arch = RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant();
        var os = OperatingSystem.IsWindows() ? "windows" : OperatingSystem.IsLinux() ? "linux" : "unsupported";
        var expectedArch = Environment.GetEnvironmentVariable("IFW_ORACLE_EXPECT_ARCH");
        if (os == "unsupported" || arch is not ("x64" or "arm64") ||
            RuntimeInformation.OSArchitecture != RuntimeInformation.ProcessArchitecture ||
            (expectedArch is not null && arch != expectedArch))
            throw new InvalidOperationException("A matching native Windows or Linux x64/arm64 runtime is required.");

        return (os, arch);
    }

    private static string ArtifactDirectory(string destination)
    {
        var root = Path.GetFullPath("artifacts/rust") + Path.DirectorySeparatorChar;
        var output = Path.TrimEndingDirectorySeparator(Path.GetFullPath(destination));
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (!Path.IsPathFullyQualified(destination) || !output.StartsWith(root, comparison))
            throw new IOException("Supply an absolute directory below the repository's artifacts/rust.");
        for (var directory = new DirectoryInfo(output); directory is not null &&
             !string.Equals(directory.FullName, Environment.CurrentDirectory, comparison); directory = directory.Parent)
            if (directory.LinkTarget is not null || (directory.Exists && directory.Attributes.HasFlag(FileAttributes.ReparsePoint)))
                throw new IOException("The synthetic fixture directory cannot traverse a link.");
        return output;
    }

    private static async Task WithFreshDirectoryAsync(string destination, Func<string, Task> write)
    {
        var output = ArtifactDirectory(destination);
        if (Path.Exists(output))
            throw new IOException("Supply a fresh absolute output directory below the repository's artifacts/rust.");
        var parent = Directory.GetParent(output)!;
        parent.Create();

        // Publish both closed snapshots and their manifest together, even when two
        // independent fixture invocations request the same output name.
        var temporary = Path.Combine(parent.FullName, ".ifw-casing-" + Guid.NewGuid().ToString("N"));
        var staging = OperatingSystem.IsWindows() ? Directory.CreateDirectory(temporary) :
            Directory.CreateDirectory(temporary, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        try
        {
            await write(staging.FullName);
            Directory.Move(staging.FullName, output);
        }
        finally
        {
            SqliteConnection.ClearAllPools();
            if (Directory.Exists(staging.FullName))
                staging.Delete(recursive: true);
        }
    }

    private static async Task<object> SnapshotAsync(string staging, string mode)
    {
        var sensitive = mode == "sensitive";
        var source = Path.Combine(staging, mode + ".writer.db");
        var snapshot = Path.Combine(staging, mode + ".db");
        var store = new SqliteSyncStateStore(source, NullLogger<SqliteSyncStateStore>.Instance, sensitive);
        var entry = new SyncStateEntry(Account, SourcePath, RelativePath, "asset-lower", AlbumDirectory,
            73, Seed, SyncTransferDirection.Download, SyncEntryStatus.Synchronized, Seed);
        await store.UpsertAsync(entry with { RelativePath = UpperRelativePath, AssetId = "asset-upper" });
        await store.UpsertAsync(entry);
        await store.UpsertAsync(entry with { RelativePath = TombstoneRelativePath, AssetId = null,
            Status = SyncEntryStatus.Tombstone, TombstoneExpiresAtUtc = Seed.AddDays(7) });
        await store.UpsertAsync(entry with { AccountScope = OtherAccount, AssetId = "asset-other" });
        var repair = new SyncTimestampRepair(entry, Seed.AddDays(-2), Seed.AddTicks(-1),
            Convert.ToHexString(SHA256.HashData("casing-fixture-content"u8)));
        await store.SaveTimestampRepairAsync(repair);
        await store.SaveTimestampRepairAsync(repair with { OriginalEntry = entry with { RelativePath = RepairRelativePath } });
        await store.SaveOwnedAlbumAsync(Account, SourcePath, AlbumDirectory, AlbumId, default);
        await store.SaveOwnedAlbumAsync(OtherAccount, SourcePath, AlbumDirectory, OtherAlbumId, default);
        await store.RecordSuccessfulSyncAsync(Account, Seed.AddMinutes(17));
        await store.RecordSuccessfulSyncAsync(OtherAccount, Seed.AddMinutes(18));

        // Normal legacy upserts collapse these names only when the actual host
        // equates them. The lower spelling was written last and must survive.
        var shared = !sensitive && RelativePath.ToUpperInvariant() == UpperRelativePath.ToUpperInvariant();
        if ((await store.GetAsync(Account, SourcePath, RelativePath))?.AssetId != "asset-lower" ||
            (await store.GetAsync(Account, SourcePath, UpperRelativePath))?.AssetId != (shared ? "asset-lower" : "asset-upper") ||
            (await store.GetSourceEntriesAsync(Account, SourcePath)).Count != (shared ? 2 : 3) ||
            await store.GetAsync(Account, SourcePath, RepairRelativePath) is not null ||
            (await store.GetTimestampRepairsAsync(Account, SourcePath)).Count != 2)
            throw new InvalidDataException("The legacy readers disagree with the synthetic writes.");

        JsonElement tables;
        string sqlite;
        using (var original = Open(source, SqliteOpenMode.ReadWrite))
        using (var backup = Open(snapshot, SqliteOpenMode.ReadWriteCreate))
        {
            if (new FileInfo(source + "-wal").Length <= 32)
                throw new InvalidDataException("Expected committed WAL frames from the shipping store.");
            original.BackupDatabase(backup);
            using var check = backup.CreateCommand();
            check.CommandText = "PRAGMA journal_mode=DELETE";
            if ((string?)check.ExecuteScalar() != "delete")
                throw new InvalidDataException("The standalone backup did not leave WAL mode.");
            check.CommandText = "PRAGMA user_version";
            if ((long?)check.ExecuteScalar() != 1)
                throw new InvalidDataException("Expected the shipping schema version.");
            check.CommandText = "PRAGMA integrity_check";
            if ((string?)check.ExecuteScalar() != "ok")
                throw new InvalidDataException("The standalone backup failed its integrity check.");
            sqlite = backup.ServerVersion;
            tables = ReadTables(backup);
            if (!JsonElement.DeepEquals(tables, ReadTables(original)))
                throw new InvalidDataException("The backup changed rows written by the shipping store.");
        }
        SqliteConnection.ClearAllPools();
        File.Delete(source);
        if (Directory.EnumerateFiles(staging, mode + ".*").Any(file => file != snapshot))
            throw new IOException("Database companions remain after closing the legacy writer and backup.");
        return new { sha256 = HashFile(snapshot), sqlite, tables };
    }

    private static JsonElement ReadTables(SqliteConnection database)
    {
        var tables = new Dictionary<string, List<Dictionary<string, object?>>>();
        foreach (var (table, ordering) in new[] {
                     ("sync_entries", "account_scope,source_key,relative_path_key"),
                     ("sync_timestamp_repairs", "account_scope,source_key,relative_path_key"),
                     ("owned_albums", "account_scope,source_key,directory_key"),
                     ("sync_account_status", "account_scope") })
        {
            using var command = database.CreateCommand();
            command.CommandText = $"SELECT * FROM {table} ORDER BY {ordering}";
            using var reader = command.ExecuteReader();
            var rows = new List<Dictionary<string, object?>>();
            while (reader.Read())
            {
                var row = new Dictionary<string, object?>();
                for (var i = 0; i < reader.FieldCount; i++)
                    row.Add(reader.GetName(i), reader.IsDBNull(i) ? null : reader.GetValue(i));
                rows.Add(row);
            }
            tables.Add(table, rows);
        }
        return JsonSerializer.SerializeToElement(tables);
    }

    private static SqliteConnection Open(string path, SqliteOpenMode mode)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
            { DataSource = path, Mode = mode, Pooling = false }.ToString());
        connection.Open();
        return connection;
    }

    private static Dictionary<string, string> VerifyShippingSources()
    {
        // The Linux baseline manifest records Git's LF content. Normalize only
        // checkout line endings so native Windows and Linux builds share its pins.
        using var baseline = JsonDocument.Parse(File.ReadAllBytes("rust/tests/fixtures/legacy/linux/manifest.json"));
        if (baseline.RootElement.GetProperty("BehavioralBaseline").GetString() != Baseline)
            throw new InvalidDataException("The reference store baseline changed.");
        var sources = new Dictionary<string, string>();
        foreach (var name in new[] { "Models/SyncStateEntry.cs", "Models/SyncTimestampRepair.cs",
                     "Services/SqliteSyncStateStore.cs", "Services/SqliteSyncStateStore.AlbumOwnership.cs" })
        {
            var path = "src/ImmichFolderWatch.Core/" + name;
            var bytes = Encoding.UTF8.GetBytes(File.ReadAllText(path).Replace("\r\n", "\n", StringComparison.Ordinal));
            var digest = Convert.ToHexStringLower(SHA256.HashData(bytes));
            if (digest != baseline.RootElement.GetProperty("SourceHashes").GetProperty(path).GetString())
                throw new InvalidDataException("A legacy storage input differs from its reference digest.");
            sources.Add(path, digest);
        }
        return sources;
    }

    private static string HashFile(string path)
    {
        using var file = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(file));
    }
}
