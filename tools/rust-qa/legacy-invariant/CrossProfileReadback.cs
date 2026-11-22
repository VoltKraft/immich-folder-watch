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
    private sealed record StudyProfile(string Name, string Hash, int Changes);
    private sealed record StudyWriter(StudyProfile Profile, string Directory, JsonElement Report, Dictionary<string, string> Files);
    private static readonly StudyProfile[] StudyProfiles =
    [
        new("icu15", "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f", 1449),
        new("managed16", "51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4", 1475),
        new("icu17", "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e", 1504)
    ];

    private static Dictionary<string, string> StudyFiles(string directory)
    {
        var members = new DirectoryInfo(directory).GetFileSystemInfos();
        var names = new[] { "result.json", InvariantUppercaseProfile.FileName, "sensitive.db", "insensitive.db" };
        if (members.Length != names.Length || members.Any(file => file is not FileInfo || file.LinkTarget is not null ||
                file.Attributes.HasFlag(FileAttributes.ReparsePoint) || !names.Contains(file.Name, StringComparer.Ordinal)))
            throw new IOException("Expected only the four regular files of a finalized synthetic capture.");
        return names.ToDictionary(name => name, name => HashFile(Path.Combine(directory, name)), StringComparer.Ordinal);
    }

    private static StudyWriter CheckStudyWriter(string path, StudyProfile profile, string os, string arch,
        string corelib, Dictionary<string, string> sources)
    {
        var directory = ArtifactDirectory(path);
        var hashes = StudyFiles(directory);
        using var document = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(directory, "result.json")));
        var report = document.RootElement;
        string? Field(string name) => report.GetProperty(name).GetString();
        if (Field("format") != "ifw-managed-invariant-store-differential-v1" || Field("baseline") != Baseline ||
            Field("account") != StudyAccount || Field("sourcePath") != StudySource || report.GetProperty("seed").GetDateTimeOffset() != Seed ||
            Field("os") != os || Field("arch") != arch || Field("target") != RuntimeInformation.RuntimeIdentifier ||
            Field("runtime") != "10.0.12" || Field("corelibSha256") != corelib ||
            !JsonElement.DeepEquals(report.GetProperty("sources"), JsonSerializer.SerializeToElement(sources)))
            throw new InvalidDataException("The writer is outside the native synthetic shipping-source study.");
        var casing = report.GetProperty("casingProfile");
        if (casing.GetProperty("tableSha256").GetString() != profile.Hash || hashes[InvariantUppercaseProfile.FileName] != profile.Hash ||
            casing.GetProperty("scannedScalars").GetInt32() != 0x110000 - 0x800 ||
            casing.GetProperty("changedScalars").GetInt32() != profile.Changes || !casing.GetProperty("contextBatchChecked").GetBoolean())
            throw new InvalidDataException("The supplied writer differs from the requested exhaustive table.");
        foreach (var mode in new[] { "sensitive", "insensitive" })
            if (hashes[mode + ".db"] != report.GetProperty("cases").GetProperty(mode).GetProperty("sha256").GetString())
                throw new InvalidDataException("The source database differs from the writer's finalized digest.");
        return new StudyWriter(profile, directory, report.Clone(), hashes);
    }

    private static async Task ReadIdentitiesAsync(string[] inputs, string destination)
    {
        var (os, arch) = NativeTarget();
        var sources = VerifyShippingSources();
        var corelib = typeof(string).Assembly;
        var corelibSha256 = HashFile(corelib.Location);
        var casing = InvariantUppercaseProfile.Capture();
        var reader = StudyProfiles.SingleOrDefault(profile => profile.Hash == casing.TableSha256 && profile.Changes == casing.ChangedScalars);
        if (Environment.Version.ToString() != "10.0.12" || reader is null || casing.ScannedScalars != 0x110000 - 0x800)
            throw new InvalidDataException("Use one of the three enumerated .NET 10.0.12 study environments.");
        var writers = inputs.Zip(StudyProfiles, (path, profile) => CheckStudyWriter(path, profile, os, arch, corelibSha256, sources)).ToArray();
        var output = ArtifactDirectory(destination);
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (writers.Any(writer => output.Equals(writer.Directory, comparison) ||
                output.StartsWith(writer.Directory + Path.DirectorySeparatorChar, comparison)))
            throw new IOException("The output must be separate from every source capture.");

        await WithFreshDirectoryAsync(output, async staging =>
        {
            casing.Write(staging);
            var observations = new Dictionary<string, object>();
            foreach (var writer in writers)
            {
                var directory = Directory.CreateDirectory(Path.Combine(staging, writer.Profile.Name)).FullName;
                var cases = new Dictionary<string, object>();
                foreach (var mode in new[] { "sensitive", "insensitive" })
                    cases.Add(mode, await ReadIdentitiesCopyAsync(writer, directory, mode));
                observations.Add(writer.Profile.Name, new { writerFilesSha256 = writer.Files, cases });
            }
            foreach (var writer in writers)
                if (StudyFiles(ArtifactDirectory(writer.Directory)).Any(file => writer.Files[file.Key] != file.Value))
                    throw new InvalidDataException("An original writer capture changed during readback.");
            var result = new
            {
                format = "ifw-managed-invariant-cross-readback-v1", baseline = Baseline, sources, os, arch,
                target = RuntimeInformation.RuntimeIdentifier, runtime = Environment.Version.ToString(),
                corelibBuild = corelib.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                corelibSha256, fixtureAssemblySha256 = HashFile(typeof(CasingCases).Assembly.Location),
                coreAssemblySha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location),
                reader = reader.Name, casingProfile = casing.Manifest, observations
            };
            await File.WriteAllTextAsync(Path.Combine(staging, "result.json"),
                JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        });
    }

    private static async Task<object> ReadIdentitiesCopyAsync(StudyWriter writer, string directory, string mode)
    {
        var filename = mode + ".db";
        var copy = Path.Combine(directory, filename);
        File.Copy(Path.Combine(writer.Directory, filename), copy);
        var beforeSha256 = HashFile(copy);
        if (beforeSha256 != writer.Files[filename])
            throw new InvalidDataException("The fresh copy differs from the original.");
        var tables = writer.Report.GetProperty("cases").GetProperty(mode).GetProperty("tables");
        string storedSource;
        using (var database = Open(copy, SqliteOpenMode.ReadOnly))
        using (var command = database.CreateCommand())
        {
            command.CommandText = "PRAGMA user_version";
            if ((long?)command.ExecuteScalar() != 1 || !JsonElement.DeepEquals(tables, ReadTables(database)))
                throw new InvalidDataException("The standalone schema-v1 copy differs from its original rows.");
            storedSource = tables.GetProperty("sync_entries")[0].GetProperty("source_key").GetString()!;
        }
        var store = new SqliteSyncStateStore(copy, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
        var display = await ObserveSourceAsync(store, StudySource);
        var stored = await ObserveSourceAsync(store, storedSource);
        var history = await store.GetLastSuccessfulSyncAsync(StudyAccount);
        SqliteConnection.ClearAllPools();
        using (var database = Open(copy, SqliteOpenMode.ReadWrite))
        using (var command = database.CreateCommand())
        {
            // The shipping read initializer enables WAL. Finalize this owned copy for immutable inspection.
            command.CommandText = "PRAGMA journal_mode=DELETE";
            if ((string?)command.ExecuteScalar() != "delete" || !JsonElement.DeepEquals(tables, ReadTables(database)))
                throw new InvalidDataException("The reader copy did not retain the finalized logical tables.");
        }
        if (Directory.EnumerateFiles(directory, mode + ".*").Any(file => file != copy))
            throw new IOException("A database companion remains on the reader copy.");
        return new { beforeSha256, afterSha256 = HashFile(copy), display, stored, history };
    }

    private static async Task<object> ObserveSourceAsync(SqliteSyncStateStore store, string source)
    {
        static object? Identity(SyncStateEntry? entry) => entry is null ? null :
            new { sourcePath = entry.SourcePath, relativePath = entry.RelativePath, assetId = entry.AssetId };
        var entries = (await store.GetSourceEntriesAsync(StudyAccount, source)).Select(Identity).ToArray();
        var lookups = new Dictionary<string, object?>();
        foreach (var (name, upper, lower) in Pairs)
            foreach (var spelling in new[] { upper, lower })
            {
                var path = $"{name}-{spelling}.jpg";
                lookups.Add(path, Identity(await store.GetAsync(StudyAccount, source, path)));
            }
        return new { source, entries, lookups };
    }
}
