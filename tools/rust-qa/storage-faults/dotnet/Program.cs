using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageFaults;

internal static class Program
{
    private static string AuthenticateSnapshot(string path, string expected)
    {
        if (expected.Length != 64 || expected.Any(character => !char.IsAsciiHexDigitLower(character)))
            throw new ArgumentException("Invalid producer SHA-256.");
        var actual = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));
        if (actual != expected)
            throw new InvalidDataException("SNAPSHOT_SHA256_MISMATCH: retained backup differs from producer");
        return actual;
    }

    private static async Task<int> Main(string[] args)
    {
        if (args.Length != 2)
        {
            throw new ArgumentException("Usage: FaultReadback <isolated-fault-case> <producer-sha256>");
        }
        var output = Path.GetFullPath(args[0]);
        var root = Path.GetFullPath("artifacts/rust/storage-faults") + Path.DirectorySeparatorChar;
        if (!output.StartsWith(root, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new ArgumentException("Readback is restricted to the synthetic storage-faults tree.");
        }
        var architecture = Environment.GetEnvironmentVariable("IFW_ORACLE_EXPECT_ARCH");
        if (architecture is not ("x64" or "arm64") ||
            !RuntimeInformation.ProcessArchitecture.ToString().Equals(architecture, StringComparison.OrdinalIgnoreCase) ||
            !RuntimeInformation.OSArchitecture.ToString().Equals(architecture, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Native process/OS architecture mismatch.");
        }
        var snapshotPath = Path.Combine(output, "snapshot.db");
        var producerSha256 = args[1];
        string beforeSha256;
        try
        {
            // Authenticate before any SQLite open or derived file. The supervisor
            // supplies the original producer digest, not a newly measured hash.
            beforeSha256 = AuthenticateSnapshot(snapshotPath, producerSha256);
        }
        catch (InvalidDataException error) when (error.Message.StartsWith("SNAPSHOT_SHA256_MISMATCH", StringComparison.Ordinal))
        {
            Console.Error.WriteLine(error.Message);
            return 42;
        }
        using var evidence = JsonDocument.Parse(File.ReadAllText(Path.Combine(output, "fault.json")));
        if (evidence.RootElement.GetProperty("format").GetString() != "ifw-storage-fault-v1")
        {
            throw new InvalidDataException("Not a synthetic fault case.");
        }
        if (evidence.RootElement.GetProperty("snapshot_sha256").GetString() != producerSha256)
            throw new InvalidDataException("Fault marker changed producer digest.");
        var sensitive = evidence.RootElement.GetProperty("mode").GetString() == "sensitive";
        var committedWithoutAcknowledgement = evidence.RootElement.GetProperty("fault").GetString() == "commit-before-ack";
        var checks = 0;
        void Check(bool condition, string message)
        {
            if (!condition) throw new InvalidDataException(message);
            checks++;
        }
        string? copySha256 = null;
        var databases = new List<string> { "state.db", "snapshot.db", "restored.db" };
        if (File.Exists(Path.Combine(output, "same-volume-restored.db"))) databases.Add("same-volume-restored.db");
        foreach (var databaseName in databases)
        {
            var expectedName = databaseName == "state.db" && committedWithoutAcknowledgement
                ? "unacknowledged.expected.json" : "confirmed.expected.json";
            using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(output, expectedName)));
            var expected = document.RootElement;
            var account = expected.GetProperty("Account").GetString()!;
            var other = expected.GetProperty("OtherAccount").GetString()!;
            var source = expected.GetProperty("Source").GetString()!;
            var entries = expected.GetProperty("Entries").Deserialize<List<SyncStateEntry>>()!;
            var repairs = expected.GetProperty("Repairs").Deserialize<List<SyncTimestampRepair>>()!;
            var databasePath = Path.Combine(output, databaseName);
            if (databaseName == "snapshot.db")
            {
                // The real legacy initializer can update header bookkeeping even
                // for reads. Preserve the retained backup and inspect a closed,
                // byte-identical copy, never a live database's main file alone.
                if (File.Exists(snapshotPath + "-wal") && new FileInfo(snapshotPath + "-wal").Length != 0)
                    throw new InvalidDataException("Snapshot still has live WAL data.");
                AuthenticateSnapshot(snapshotPath, producerSha256);
                databasePath = Path.Combine(output, "csharp-snapshot.db");
                File.Copy(snapshotPath, databasePath, overwrite: false);
                copySha256 = AuthenticateSnapshot(databasePath, producerSha256);
                AuthenticateSnapshot(snapshotPath, producerSha256);
            }
            var store = new SqliteSyncStateStore(databasePath, NullLogger<SqliteSyncStateStore>.Instance, sensitive);
            Check((await store.GetSourceEntriesAsync(account, source)).SequenceEqual(entries), "Recovered entries differ from the real C# reader");
            Check((await store.GetTimestampRepairsAsync(account, source)).SequenceEqual(repairs), "Recovered repair JSON differs");
            Check(await store.GetLastSuccessfulSyncAsync(account) == expected.GetProperty("LastSuccessfulSyncUtc").GetDateTimeOffset(), "Recovered history differs");
            Check(await store.GetOwnedAlbumAsync(account, source, "Straße", default) == expected.GetProperty("OwnedAlbumId").GetString(), "Recovered exact album provenance differs");
            Check(await store.GetOwnedAlbumAsync(other, source, "Other", default) == "album-other", "Other account ownership changed");
            Check((await store.GetSourceEntriesAsync(other, source)).Count == 1, "Other account entry changed");
            Check((await store.GetAsync(account, source, "download.bin"))!.FileSize == 9_007_199_254_740_995L, "64-bit file size was rounded");
            Check((await store.GetAsync(account, source, "removed.jpg"))!.TombstoneExpiresAtUtc == entries.Single(entry => entry.Status == SyncEntryStatus.Tombstone).TombstoneExpiresAtUtc, "Tombstone expiry changed");
        }
        await using var engine = new SqliteConnection("Data Source=:memory:");
        await engine.OpenAsync();
        await using var command = engine.CreateCommand();
        command.CommandText = "SELECT sqlite_version();";
        var sqliteVersion = (string)(await command.ExecuteScalarAsync())!;
        SqliteConnection.ClearAllPools();
        var afterSha256 = AuthenticateSnapshot(snapshotPath, producerSha256);
        File.WriteAllText(Path.Combine(output, "csharp-readback.json"), JsonSerializer.Serialize(new
        {
            Format = "ifw-storage-fault-csharp-v1",
            Assertions = checks,
            Runtime = Environment.Version.ToString(),
            Architecture = RuntimeInformation.ProcessArchitecture.ToString(),
            OSArchitecture = RuntimeInformation.OSArchitecture.ToString(),
            SQLiteVersion = sqliteVersion,
            RetainedSnapshotUnchanged = true,
            SnapshotSha256 = producerSha256,
            SnapshotBeforeSha256 = beforeSha256,
            SnapshotAfterSha256 = afterSha256,
            SnapshotCopySha256 = copySha256
        }));
        Console.WriteLine($"C# fault readback passed: {checks} assertions over recovered, snapshot and restored profiles.");
        return 0;
    }
}
