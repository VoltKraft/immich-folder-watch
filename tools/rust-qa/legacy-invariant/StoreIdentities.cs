using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

// This separate developer executable reuses the reviewed store source pins,
// same-process scalar capture and private staging directory from StorageReadback.
internal static partial class CasingCases
{
    private const string StudyAccount = "ifw-managed-invariant-study";
    private static string StudySource => OperatingSystem.IsWindows() ? @"C:\IfwSynthetic\Archive-ſ-ƛ" : "/IfwSynthetic/Archive-ſ-ƛ";
    private static readonly (string Name, string Upper, string Lower)[] Pairs =
    [
        ("long-s", "S", "ſ"),
        ("stroke", "Ƛ", "ƛ"),
        ("dotless", "I", "ı"),
        ("sharp-s", "SS", "ß"),
        ("garay", "\U00010D50", "\U00010D70"),
        ("beria", "\U00016EA0", "\U00016EBB")
    ];

    private static async Task<int> Main(string[] args)
    {
        if (args is ["read-sizes", var copies, var result])
        {
            await ReadUpdatedSizesAsync(copies, result);
            return 0;
        }
        if (args is ["read", var older, var managed, var current, var output])
        {
            await ReadIdentitiesAsync([older, managed, current], output);
            return 0;
        }
        if (args is not ["capture", var destination])
        {
            Console.Error.WriteLine("Usage: StoreIdentities capture <new-output>, read <icu15-writer> <managed-writer> <icu17-writer> <new-output>, or read-sizes <six-copy-cases> <new-output>");
            return 2;
        }
        var (os, arch) = NativeTarget();
        var sources = VerifyShippingSources();
        await WithFreshDirectoryAsync(destination, async staging =>
        {
            var casing = InvariantUppercaseProfile.Capture();
            casing.Write(staging);
            var cases = new Dictionary<string, object>();
            foreach (var mode in new[] { "sensitive", "insensitive" })
                cases.Add(mode, await CaptureIdentitiesAsync(staging, mode));
            var corelib = typeof(string).Assembly;
            var report = new
            {
                format = "ifw-managed-invariant-store-differential-v1", baseline = Baseline, sources,
                os, arch, target = RuntimeInformation.RuntimeIdentifier, runtime = Environment.Version.ToString(),
                corelibBuild = corelib.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                corelibSha256 = HashFile(corelib.Location), fixtureAssemblySha256 = HashFile(typeof(CasingCases).Assembly.Location),
                coreAssemblySha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location),
                casingProfile = casing.Manifest, account = StudyAccount, sourcePath = StudySource, seed = Seed, cases
            };
            await File.WriteAllTextAsync(Path.Combine(staging, "result.json"),
                JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        });
        return 0;
    }

    private static async Task<object> CaptureIdentitiesAsync(string staging, string mode)
    {
        var path = Path.Combine(staging, mode + ".db");
        var store = new SqliteSyncStateStore(path, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
        var paths = new List<string>();
        foreach (var (name, upper, lower) in Pairs)
        {
            foreach (var (spelling, kind) in new[] { (upper, "upper"), (lower, "lower") })
            {
                var relative = $"{name}-{spelling}.jpg";
                await store.UpsertAsync(new SyncStateEntry(StudyAccount, StudySource, relative, $"{name}-{kind}",
                    "Synthetic study", 19, Seed, SyncTransferDirection.Download, SyncEntryStatus.Synchronized, Seed));
                paths.Add(relative);
            }
        }
        await store.RecordSuccessfulSyncAsync(StudyAccount, Seed);
        var history = await store.GetLastSuccessfulSyncAsync(StudyAccount);
        var lookups = new Dictionary<string, string?>();
        foreach (var relative in paths)
            lookups.Add(relative, (await store.GetAsync(StudyAccount, StudySource, relative))?.AssetId);

        // Only this invocation owns the new database. Closing its pooled handles
        // and selecting the rollback journal yields a standalone immutable input.
        SqliteConnection.ClearAllPools();
        JsonElement tables;
        string sqlite;
        using (var connection = Open(path, SqliteOpenMode.ReadWrite))
        {
            using var command = connection.CreateCommand();
            command.CommandText = "PRAGMA journal_mode=DELETE";
            if ((string?)command.ExecuteScalar() != "delete")
                throw new InvalidDataException("Could not finalize the standalone database.");
            command.CommandText = "PRAGMA user_version";
            if ((long?)command.ExecuteScalar() != 1)
                throw new InvalidDataException("Expected the shipping schema version.");
            command.CommandText = "PRAGMA integrity_check";
            if ((string?)command.ExecuteScalar() != "ok")
                throw new InvalidDataException("The synthetic database failed its integrity check.");
            tables = ReadTables(connection);
            sqlite = connection.ServerVersion;
        }
        if (Directory.EnumerateFiles(staging, mode + ".*").Any(file => file != path))
            throw new IOException("The finalized database still has companions.");
        return new { sha256 = HashFile(path), sqlite, lookups, history, tables };
    }
}
