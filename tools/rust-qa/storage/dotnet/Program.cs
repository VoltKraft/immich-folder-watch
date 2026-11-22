using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static class Program
{
    private static async Task Main(string[] args)
    {
        if (args is ["--casing-fixtures", var destination])
        {
            await CasingCases.WriteAsync(destination);
            return;
        }
        if (args.Length != 1)
        {
            throw new ArgumentException("Usage: StorageReadback <synthetic-assessment-output> or --casing-fixtures <new-output>");
        }
        var output = Path.GetFullPath(args[0]);
        var scope = Path.GetFullPath("artifacts/rust") + Path.DirectorySeparatorChar;
        if (!output.StartsWith(scope, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new ArgumentException("Readback is restricted to the isolated assessment tree.");
        }
        using var report = JsonDocument.Parse(File.ReadAllText(Path.Combine(output, "result.json")));
        if (report.RootElement.GetProperty("Format").GetString() != "ifw-rw02-sqlite-assessment-v1")
        {
            throw new InvalidDataException("Not a synthetic Rust storage result.");
        }
        var expectedArchitecture = Environment.GetEnvironmentVariable("IFW_ORACLE_EXPECT_ARCH");
        if (expectedArchitecture is not ("x64" or "arm64") ||
            !RuntimeInformation.ProcessArchitecture.ToString().Equals(expectedArchitecture, StringComparison.OrdinalIgnoreCase) ||
            !RuntimeInformation.OSArchitecture.ToString().Equals(expectedArchitecture, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Set IFW_ORACLE_EXPECT_ARCH to the matching native x64 or arm64 lane.");
        }
        var operatingSystem = OperatingSystem.IsWindows() ? "windows" : OperatingSystem.IsLinux() ? "linux" : "unsupported";
        if (report.RootElement.GetProperty("Os").GetString() != operatingSystem)
        {
            throw new InvalidDataException("Rust and C# native platforms differ.");
        }
        var checks = 0;
        void Check(bool value, string message)
        {
            if (!value)
            {
                throw new InvalidDataException(message);
            }
            checks++;
        }
        foreach (var mode in new[] { "sensitive", "insensitive" })
        {
            using var expectedDocument = JsonDocument.Parse(File.ReadAllText(Path.Combine(output, mode + ".expected.json")));
            var expected = expectedDocument.RootElement;
            var account = expected.GetProperty("Account").GetString()!;
            var other = expected.GetProperty("OtherAccount").GetString()!;
            var source = expected.GetProperty("Source").GetString()!;
            var entries = expected.GetProperty("Entries").Deserialize<List<SyncStateEntry>>()!;
            var repairs = expected.GetProperty("Repairs").Deserialize<List<SyncTimestampRepair>>()!;
            var history = expected.GetProperty("LastSuccessfulSyncUtc").GetDateTimeOffset();
            foreach (var suffix in new[] { ".db", ".backup.db" })
            {
                var database = Path.Combine(output, mode + suffix);
                var store = new SqliteSyncStateStore(database, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
                Check((await store.GetSourceEntriesAsync(account, source)).SequenceEqual(entries), "C# entry readback differs");
                Check((await store.GetTimestampRepairsAsync(account, source)).SequenceEqual(repairs), "C# repair readback differs");
                Check(await store.GetLastSuccessfulSyncAsync(account) == history, "C# history readback differs");
                Check(await store.GetOwnedAlbumAsync(account, source, "Straße", default) == "album-rust-roundtrip", "C# exact ownership differs");
                Check(await store.GetOwnedAlbumAsync(other, source, "Other", default) == "album-other", "Other account ownership changed");
                Check((await store.GetSourceEntriesAsync(other, source)).Count == 1, "Other account entry changed");
                var downloaded = (await store.GetAsync(account, source, "download.bin"))!;
                Check(downloaded.FileSize == 9_007_199_254_740_995L && downloaded.AssetId == "asset-rust-roundtrip", "Large integer was rounded");
                var repair = (await store.GetTimestampRepairsAsync(account, source)).Single();
                Check(repair.CreationTimeUtc == DateTimeOffset.ParseExact("1900-01-02T03:04:05.0000001+00:00", "O", CultureInfo.InvariantCulture), "Pre-Unix repair tick changed");
                Check(repair.ContentSha256 == Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes("RW02-SYNTHETIC-REPAIR-CONTENT"))), "Rust SHA-256 differs from C#");
                Check(entries.Single(entry => entry.Status == SyncEntryStatus.Tombstone).TombstoneExpiresAtUtc == (await store.GetAsync(account, source, "removed.jpg"))!.TombstoneExpiresAtUtc, "Tombstone expiry changed");
            }
        }
        await using var engine = new SqliteConnection("Data Source=:memory:");
        await engine.OpenAsync();
        await using var engineVersionCommand = engine.CreateCommand();
        engineVersionCommand.CommandText = "SELECT sqlite_version();";
        var engineVersion = (string)(await engineVersionCommand.ExecuteScalarAsync())!;
        SqliteConnection.ClearAllPools();
        Console.WriteLine($"C# readback passed: {checks} assertions over Rust-written original and WAL backup databases; .NET {Environment.Version}, {RuntimeInformation.OSDescription}, {RuntimeInformation.ProcessArchitecture}, SQLite {engineVersion}.");
        File.WriteAllText(Path.Combine(output, "csharp-readback.json"), JsonSerializer.Serialize(new
        {
            Format = "ifw-rw02-csharp-readback-v1",
            Assertions = checks,
            Runtime = Environment.Version.ToString(),
            OperatingSystem = operatingSystem,
            Architecture = RuntimeInformation.ProcessArchitecture.ToString(),
            OSArchitecture = RuntimeInformation.OSArchitecture.ToString(),
            SQLiteVersion = engineVersion
        }));
    }
}
