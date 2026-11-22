using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.StorageAssessment;

internal static partial class CasingCases
{
    private static readonly string[] SizeFiles = ["before.db", "after.db"];

    // Linux statx has a fixed ABI. The shipping SecureWatchRoot checks the opened
    // file type and rejects symlinks; this study also requires a single hard link.
    [StructLayout(LayoutKind.Explicit, Size = 256)]
    private struct SizeFileStat
    {
        [FieldOffset(0)] public uint Mask;
        [FieldOffset(16)] public uint Links;
    }

    [DllImport("libc", EntryPoint = "statx", SetLastError = true)]
    private static extern int SizeFileStatAt(SafeFileHandle fd, string path, int flags, uint mask, out SizeFileStat stat);

    private static void RequirePairMembers(string source)
    {
        var files = new DirectoryInfo(source).GetFileSystemInfos();
        if (files.Length != SizeFiles.Length || files.Any(f => f is not FileInfo || f.LinkTarget is not null ||
            f.Attributes.HasFlag(FileAttributes.ReparsePoint) || !SizeFiles.Contains(f.Name, StringComparer.Ordinal)))
            throw new InvalidDataException("Expected a finalized pair of regular before.db and after.db files.");
    }

    private static Dictionary<string, string> SizeInputPair(string source, string? copyTo = null)
    {
        RequirePairMembers(source);
        using var root = SecureWatchRoot.Open(source);
        var hashes = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var name in SizeFiles)
        {
            using var file = root.OpenRead(name);
            if (SizeFileStatAt(file.Stream.SafeFileHandle, "", 0x1000, 4, out var stat) != 0 ||
                (stat.Mask & 4) == 0 || stat.Links != 1)
                throw new InvalidDataException("Expected a single-link regular study file.");
            byte[] header = new byte[20];
            file.Stream.ReadExactly(header);
            if (!header.AsSpan(0, 16).SequenceEqual("SQLite format 3\0"u8) || header[18] != 1 || header[19] != 1)
                throw new InvalidDataException("Expected a finalized rollback-journal database header.");
            file.Stream.Position = 0;
            hashes.Add(name, Convert.ToHexStringLower(SHA256.HashData(file.Stream)));
            if (copyTo is not null)
            {
                file.Stream.Position = 0;
                var destination = Path.Combine(copyTo, name);
                using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    file.Stream.CopyTo(output);
                if (HashFile(destination) != hashes[name])
                    throw new IOException("The working copy differs from the opened study file.");
            }
            if (!file.IsCurrentEntry())
                throw new IOException("A study input was replaced during the read.");
        }
        RequirePairMembers(source);
        return hashes;
    }

    private static void CheckSizePair(string source, Dictionary<string, string> expected)
    {
        var actual = SizeInputPair(source);
        if (actual.Any(pair => expected[pair.Key] != pair.Value))
            throw new IOException("A finalized study pair changed during the read.");
    }

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
            var originals = new Dictionary<string, Dictionary<string, string>>();
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
                    var inputs = SizeInputPair(source, directory);
                    CheckSizePair(source, inputs);
                    originals.Add(source, inputs);
                    foreach (var phase in new[] { "before", "after" })
                    {
                        string key = $"{writer.Name}/{mode}/{phase}";
                        string filename = phase + ".db";
                        var copy = Path.Combine(directory, filename);
                        observations[key] = await ObserveSizeCopyAsync(copy, inputs[filename], relative, mode);
                    }
                    CheckSizePair(source, inputs);
                }
            }
            foreach (var (source, hashes) in originals)
                CheckSizePair(source, hashes);
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
