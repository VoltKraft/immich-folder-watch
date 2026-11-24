using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static class ConcordantStore
{
    internal static Task Main(string[] args) => CasingCases.CheckConcordantAsync(args);
}

internal static partial class CasingCases
{
    internal static async Task CheckConcordantAsync(string[] args)
    {
        if (args is not [var profileName] || NativeTarget() != ("linux", "x64") || Environment.Version.ToString() != "10.0.12")
            throw new InvalidDataException("Expected the native Linux x64 .NET 10.0.12 test runner.");
        var tableFile = profileName switch
        {
            "older" => "legacy/casing/unicode-15.1.0.tsv",
            "managed" => "legacy-invariant/managed-invariant-10.0.12.tsv",
            "current" => "legacy/casing/unicode-17.0.0.tsv",
            _ => throw new InvalidDataException("Unknown rollback profile.")
        };
        var sources = VerifyShippingSources();
        var work = Path.GetFullPath("artifacts/rust/work");
        var cases = Path.Combine(work, "cases");
        _ = RequireTmpfs(work, "rw");
        _ = RequireTmpfs(cases, "ro");
        using var inputs = SecureWatchRoot.Open(cases);
        using var plan = JsonDocument.Parse(OpenInput(inputs, "accepted.json"));
        await WithFreshDirectoryAsync(Path.Combine(work, "csharp-" + profileName), async output =>
        {
            var casing = InvariantUppercaseProfile.Capture();
            casing.Write(output);
            if (casing.TableSha256 != HashFile(Path.Combine("tools/rust-qa", tableFile)))
                throw new InvalidDataException("The actual rollback writer has a different casing table.");
            var results = new Dictionary<string, object>();
            foreach (var writer in new[] { "older", "managed", "current" })
            foreach (var mode in new[] { "insensitive", "sensitive" })
            {
                var name = writer + "-" + mode;
                var bytes = OpenInput(inputs, name + "/after.db");
                var digest = Convert.ToHexStringLower(SHA256.HashData(bytes));
                using var receipt = JsonDocument.Parse(OpenInput(inputs, name + "/receipt.json"));
                if (receipt.RootElement.GetProperty("format").GetString() != "ifw-concordant-insert-v1" ||
                    receipt.RootElement.GetProperty("after").GetString() != digest)
                    throw new InvalidDataException("Unexpected finalized Rust input.");
                var copy = Path.Combine(output, name + ".working.db");
                await CreateCopyAsync(copy, bytes);
                var store = new SqliteSyncStateStore(copy, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
                var stages = new Dictionary<string, object>();
                foreach (var phase in new[] { "before", "first", "repeat" })
                {
                    var observations = new List<object>();
                    foreach (var entry in plan.RootElement.GetProperty(mode).EnumerateArray())
                    {
                        var scope = entry.GetProperty("account").GetString()!;
                        var source = entry.GetProperty("source").GetString()!;
                        var relative = entry.GetProperty("relative").GetString()!;
                        var previous = await store.GetAsync(scope, source, relative);
                        if (previous is null || previous.AssetId != entry.GetProperty("asset").GetString() ||
                            previous.SourcePath != Path.TrimEndingDirectorySeparator(Path.GetFullPath(source)) || previous.RelativePath != relative)
                            throw new InvalidDataException("Original spelling or opaque asset identity was lost.");
                        if (phase != "before")
                            await store.UpsertAsync(previous with { AccountScope = scope, SourcePath = source, RelativePath = relative, FileSize = 101 });
                        var current = await store.GetAsync(scope, source, relative);
                        if (current is null || current.FileSize != (phase == "before" ? 83 : 101))
                            throw new InvalidDataException("Unexpected committed shipping writer size.");
                        observations.Add(Identity(current)!);
                    }
                    var saved = phase == "before" ? digest : BackupWorking(copy, Path.Combine(output, name + "." + phase + ".db"));
                    stages.Add(phase, new { sha256 = saved, observations });
                }
                SqliteConnection.ClearAllPools();
                File.Delete(copy);
                results.Add(name, stages);
            }
            var core = typeof(string).Assembly;
            var report = new { format = "ifw-concordant-rollback-v1", profileName, sources, baseline = Baseline, cases = results,
                casingProfile = casing.Manifest, runtime = Environment.Version.ToString(), os = "linux", arch = "x64",
                corelibSha256 = HashFile(core.Location), corelibBuild = core.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                storeSha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location), probeSha256 = HashFile(typeof(ConcordantStore).Assembly.Location) };
            await File.WriteAllTextAsync(Path.Combine(output, "result.json"), JsonSerializer.Serialize(report) + "\n");
        });
    }
}
