using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static class RollbackStudy
{
    internal static Task Main(string[] args) => CasingCases.RollbackAsync(args);
}

internal static partial class CasingCases
{
    private const string DonorReceipt = "4cc86159873ef842dc8460e21f1f6dfe145b6c1d1cec231ddaec291aee5f58dd";
    private static readonly (string Source, string Path, string Id)[] RollbackEntries =
    [
        (Stable, "New/Stable.jpg", "Insert-Asset-A"),
        (Stable, "New/Only-ƛ.jpg", "Insert-Asset-B"),
        (SourcePath, "New/Source.jpg", "Insert-Asset-C")
    ];

    internal static async Task RollbackAsync(string[] args)
    {
        if (args is not [var action, var version] || action is not ("write" or "read") || !Profiles.Contains(version))
            throw new ArgumentException("Expected a fixed write or read phase and qualified profile.");
        var (os, arch) = NativeTarget();
        if (os != "linux" || arch != "x64" || Environment.Version.ToString() != "10.0.12")
            throw new InvalidDataException("Expected the native Linux x64 reference runtime.");
        var sources = VerifyShippingSources();
        var work = Path.GetFullPath("artifacts/rust/work");
        var basis = Path.GetFullPath("artifacts/rust/donors");
        var workMount = RequireTmpfs(work, "rw");
        var inputMount = RequireTmpfs(basis, "ro");
        using var historical = SecureWatchRoot.Open(basis);
        var evidence = OpenInput(historical, "result.json");
        if (Convert.ToHexStringLower(SHA256.HashData(evidence)) != DonorReceipt)
            throw new InvalidDataException("Wrong finalized Rust fixture receipt.");
        using var receipt = JsonDocument.Parse(evidence);
        var trials = receipt.RootElement.GetProperty("trials");
        var profile = InvariantUppercaseProfile.Capture();
        if (HashFile($"tools/rust-qa/legacy/casing/unicode-{version}.tsv") != profile.TableSha256)
            throw new InvalidDataException("Actual .NET process does not use the requested full casing table.");
        await WithFreshDirectoryAsync(Path.Combine(work, action + "-" + version), async output =>
        {
            profile.Write(output);
            var cases = new Dictionary<string, object>();
            foreach (var donor in Profiles)
            foreach (var mode in new[] { "sensitive", "insensitive" })
            foreach (var chosen in Profiles)
            {
                var name = $"{donor}-{mode}-{chosen}";
                if (action == "write")
                {
                    var bytes = OpenInput(historical, $"{name}/inserted.db");
                    if (Convert.ToHexStringLower(SHA256.HashData(bytes)) != trials.GetProperty(name).GetProperty("after").GetString())
                        throw new InvalidDataException("Rust input differs from its attested bytes.");
                    var path = Path.Combine(output, name + ".working.db");
                    await CreateCopyAsync(path, bytes);
                    var store = new SqliteSyncStateStore(path, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
                    var stages = new Dictionary<string, object> { ["before"] = await ObserveRollbackAsync(store) };
                    var hashes = new Dictionary<string, string>();
                    foreach (var phase in new[] { "first", "repeat" })
                    {
                        foreach (var (source, relative, id) in RollbackEntries)
                            await store.UpsertAsync(new SyncStateEntry(Account, source, relative, id, "Synthetic insert", 101,
                                Seed, SyncTransferDirection.Download, SyncEntryStatus.Synchronized, Seed));
                        stages.Add(phase, await ObserveRollbackAsync(store));
                        hashes[phase] = BackupWorking(path, Path.Combine(output, name + "." + phase + ".db"));
                    }
                    SqliteConnection.ClearAllPools();
                    File.Delete(path);
                    cases.Add(name, new { stages, hashes });
                }
                else
                {
                    foreach (var writer in Profiles)
                    {
                        var writerPath = Path.Combine(work, "write-" + writer);
                        _ = RequireTmpfs(writerPath, "ro");
                        using var snapshots = SecureWatchRoot.Open(writerPath);
                        var bytes = OpenInput(snapshots, name + ".repeat.db");
                        using var writerReport = JsonDocument.Parse(OpenInput(snapshots, "result.json"));
                        var digest = Convert.ToHexStringLower(SHA256.HashData(bytes));
                        if (writerReport.RootElement.GetProperty("cases").GetProperty(name).GetProperty("hashes")
                            .GetProperty("repeat").GetString() != digest)
                            throw new InvalidDataException("Finalized C# snapshot differs from the writer record.");
                        var path = Path.Combine(output, writer + "-" + name + ".working.db");
                        await CreateCopyAsync(path, bytes);
                        var store = new SqliteSyncStateStore(path, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
                        cases.Add(writer + "/" + name, new { digest, observation = await ObserveRollbackAsync(store) });
                        SqliteConnection.ClearAllPools();
                        File.Delete(path);
                    }
                }
            }
            if (Directory.EnumerateFiles(output).Any(f => f.EndsWith("-wal") || f.EndsWith("-shm") || f.EndsWith("-journal")))
                throw new IOException("A private working database left companions.");
            var core = typeof(string).Assembly;
            var report = new { format = "ifw-rollback-upsert-v1", action, version, baseline = Baseline, sources, os, arch,
                runtime = Environment.Version.ToString(), casingProfile = profile.Manifest, rootInputSha256 = DonorReceipt,
                corelibSha256 = HashFile(core.Location), corelibBuild = core.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                storeSha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location), probeSha256 = HashFile(typeof(RollbackStudy).Assembly.Location),
                workMount, inputMount, cases };
            await File.WriteAllTextAsync(Path.Combine(output, "result.json"), JsonSerializer.Serialize(report) + "\n");
        });
    }

    private static async Task CreateCopyAsync(string path, byte[] bytes)
    {
        await using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        await file.WriteAsync(bytes);
    }

    private static string BackupWorking(string source, string destination)
    {
        using (File.Open(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { }
        using (var live = Open(source, SqliteOpenMode.ReadOnly))
        using (var saved = Open(destination, SqliteOpenMode.ReadWrite))
        {
            live.BackupDatabase(saved);
            using var check = saved.CreateCommand();
            check.CommandText = "PRAGMA journal_mode=DELETE";
            if ((string?)check.ExecuteScalar() != "delete" || !JsonElement.DeepEquals(ReadTables(live), ReadTables(saved)))
                throw new InvalidDataException("Finalized backup differs from committed store contents.");
        }
        return HashFile(destination);
    }

    private static async Task<object> ObserveRollbackAsync(SqliteSyncStateStore store)
    {
        var lookups = new List<object?>();
        foreach (var (account, root, path) in new[] {
                     (Account, Stable, "New/Stable.jpg"), (Account, Stable, "New/Only-ƛ.jpg"), (Account, Stable, "New/Only-Ƛ.jpg"),
                     (Account, SourcePath, "New/Source.jpg"), (Account, SourcePath.Replace('ƛ','Ƛ'), "New/Source.jpg"),
                     (OtherAccount, Stable, "New/Stable.jpg") })
            lookups.Add(Identity(await store.GetAsync(account, root, path)));
        var lists = new List<object>();
        foreach (var (account, source) in new[] { (Account,Stable), (Account,SourcePath), (Account,SourcePath.Replace('ƛ','Ƛ')), (OtherAccount,Stable) })
            lists.Add((await store.GetSourceEntriesAsync(account, source)).Select(Identity).ToArray());
        return new { lookups, lists, history = await store.GetLastSuccessfulSyncAsync(Account),
            otherHistory = await store.GetLastSuccessfulSyncAsync(OtherAccount) };
    }
}
