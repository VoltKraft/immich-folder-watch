using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static partial class CasingCases
{
    private static async Task ReadUpdatedSizesAsync(string cases, string output)
    {
        var (os, arch) = NativeTarget();
        var sources = VerifyShippingSources();
        var input = ArtifactDirectory(cases);
        var result = ArtifactDirectory(output);
        var area = Path.GetFullPath("artifacts/rust/stored-key-mutations") + Path.DirectorySeparatorChar;
        if (os != "linux" || arch != "x64" || Environment.Version.ToString() != "10.0.12" ||
            !input.StartsWith(area, StringComparison.Ordinal) || !result.StartsWith(area, StringComparison.Ordinal) ||
            result.StartsWith(input + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            throw new IOException("Expected separate, private study inputs and output on native Linux x64.");
        var casing = InvariantUppercaseProfile.Capture();
        var profile = StudyProfiles.Single(p => p.Hash == casing.TableSha256 && p.Changes == casing.ChangedScalars);
        if (casing.ScannedScalars != 0x110000 - 0x800)
            throw new InvalidDataException("Incomplete same-process casing table.");
        await WithFreshDirectoryAsync(result, async staging =>
        {
            casing.Write(staging);
            var observations = new Dictionary<string, object>();
            foreach (var writer in StudyProfiles)
            {
                string relative = writer.Name switch
                {
                    "icu15" => "long-s-S.jpg",
                    "managed16" => "stroke-Ƛ.jpg",
                    "icu17" => "beria-\U00016EA0.jpg",
                    _ => throw new InvalidDataException("Unexpected writer.")
                };
                foreach (var mode in new[] { "sensitive", "insensitive" })
                {
                    var source = ArtifactDirectory(Path.Combine(input, writer.Name, mode));
                    var directory = Directory.CreateDirectory(Path.Combine(staging, writer.Name, mode)).FullName;
                    foreach (var phase in new[] { "before", "after" })
                    {
                        string key = $"{writer.Name}/{mode}/{phase}";
                        string filename = phase + ".db";
                        var original = new FileInfo(Path.Combine(source, filename));
                        if (!original.Exists || original.LinkTarget is not null || original.Attributes.HasFlag(FileAttributes.ReparsePoint))
                            throw new IOException("Expected an ordinary study copy.");
                        var sha = HashFile(original.FullName);
                        var copy = Path.Combine(directory, filename);
                        File.Copy(original.FullName, copy);
                        if (HashFile(copy) != sha)
                            throw new IOException("The working copy differs from the staged input.");
                        observations[key] = await ObserveSizeCopyAsync(copy, sha, relative, mode);
                        if (HashFile(original.FullName) != sha)
                            throw new IOException("Input changed during the shipping read.");
                    }
                }
            }
            var corelib = typeof(string).Assembly;
            var record = new { format = "ifw-study-file-size-csharp-v1", baseline = Baseline, sources, os, arch,
                target = RuntimeInformation.RuntimeIdentifier, runtime = Environment.Version.ToString(), reader = profile.Name,
                corelibBuild = corelib.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                corelibSha256 = HashFile(corelib.Location), fixtureAssemblySha256 = HashFile(typeof(CasingCases).Assembly.Location),
                coreAssemblySha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location), casingProfile = casing.Manifest, observations };
            await File.WriteAllTextAsync(Path.Combine(staging, "result.json"), JsonSerializer.Serialize(record) + "\n");
        });
    }

    private static async Task<object> ObserveSizeCopyAsync(string copy, string sha, string relative, string mode)
    {
        JsonElement tables;
        using (var database = Open(copy, SqliteOpenMode.ReadOnly))
            tables = ReadTables(database);
        var stored = tables.GetProperty("sync_entries")[0].GetProperty("source_key").GetString()!;
        var store = new SqliteSyncStateStore(copy, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
        static object? Entry(SyncStateEntry? row) => row is null ? null :
            new { account = row.AccountScope, source = row.SourcePath, relative = row.RelativePath, asset = row.AssetId, size = row.FileSize };
        async Task<object> Read(string source) => new { source, relative,
            get = Entry(await store.GetAsync(StudyAccount, source, relative)),
            list = (await store.GetSourceEntriesAsync(StudyAccount, source)).Select(Entry).ToArray() };
        var display = await Read(StudySource);
        var storedKey = await Read(stored);
        var history = await store.GetLastSuccessfulSyncAsync(StudyAccount);
        SqliteConnection.ClearAllPools();
        using (var database = Open(copy, SqliteOpenMode.ReadWrite))
        using (var command = database.CreateCommand())
        {
            command.CommandText = "PRAGMA journal_mode=DELETE";
            if ((string?)command.ExecuteScalar() != "delete" || !JsonElement.DeepEquals(tables, ReadTables(database)))
                throw new InvalidDataException("A shipping read changed the working tables.");
        }
        return new { inputSha256 = sha, display, storedKey, history };
    }
}
