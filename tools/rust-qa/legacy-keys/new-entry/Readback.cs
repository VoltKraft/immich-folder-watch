using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static partial class CasingCases
{
    private const string Stable = "/IfwSynthetic/Insert-ASCII";
    private static readonly string[] Profiles = ["15.1.0", "17.0.0"];

    private static object? Identity(SyncStateEntry? entry) => entry is null ? null : new
        { entry.AccountScope, entry.SourcePath, entry.RelativePath, entry.AssetId, entry.FileSize };

    private static string RequireTmpfs(string path, string access)
    {
        var expected = path.Replace("\\", "\\134").Replace(" ", "\\040").Replace("\t", "\\011").Replace("\n", "\\012");
        foreach (var line in File.ReadLines("/proc/self/mountinfo"))
        {
            var halves = line.Split(" - ", 2, StringSplitOptions.None);
            var mount = halves[0].Split(' ');
            if (halves.Length == 2 && mount.Length > 5 && mount[4] == expected &&
                mount[5].Split(',')[0] == access && halves[1].StartsWith("tmpfs ", StringComparison.Ordinal))
                return line;
        }
        throw new IOException("Required private study mount is missing.");
    }

    private static byte[] OpenInput(SecureWatchRoot root, string relative)
    {
        using var file = root.OpenRead(relative);
        if (file.Stream.Length is <= 0 or > 1024 * 1024)
            throw new InvalidDataException("Expected a bounded regular synthetic input.");
        var bytes = new byte[checked((int)file.Stream.Length)];
        file.Stream.ReadExactly(bytes);
        if (file.Stream.ReadByte() != -1 || !file.IsCurrentEntry())
            throw new IOException("The opened study input changed.");
        return bytes;
    }

    internal static async Task Main(string[] args)
    {
        if (args is not [var corpus, var destination])
            throw new ArgumentException("Expected the synthetic Rust cases and a fresh reader directory.");
        var (os, arch) = NativeTarget();
        var sources = VerifyShippingSources();
        var run = Path.GetFullPath("artifacts/rust/work");
        if (os != "linux" || arch != "x64" || corpus != Path.Combine(run, "cases") ||
            !Profiles.Any(p => destination == Path.Combine(run, "reader-" + p)))
            throw new InvalidDataException("Expected the isolated Linux x64 study.");
        var privateWorkMount = RequireTmpfs(run, "rw");
        var readOnlyCasesMount = RequireTmpfs(corpus, "ro");
        using var work = SecureWatchRoot.Open(run);
        using var inputs = SecureWatchRoot.Open(corpus);
        if (!OpenInput(work, "new-entry-study.marker").AsSpan().SequenceEqual("ifw-rw02-new-entry-study-v1\n"u8))
            throw new InvalidDataException("Missing synthetic run marker.");
        await WithFreshDirectoryAsync(destination, async output =>
        {
            var profile = InvariantUppercaseProfile.Capture();
            profile.Write(output);
            var expected = Profiles.Single(version => Path.GetFileName(destination) == "reader-" + version);
            if (HashFile($"tools/rust-qa/legacy/casing/unicode-{expected}.tsv") != profile.TableSha256)
                throw new InvalidDataException("The active reader casing table is unqualified.");
            var cases = new Dictionary<string, object>();
            foreach (var donor in Profiles)
            foreach (var mode in new[] { "sensitive", "insensitive" })
            foreach (var chosen in Profiles)
            {
                var name = $"{donor}-{mode}-{chosen}";
                var directory = Path.Combine(corpus, name);
                if (!Directory.GetFileSystemEntries(directory).Select(Path.GetFileName).Order(StringComparer.Ordinal)
                        .SequenceEqual(new[] { "inserted.db", "receipt.json" }))
                    throw new InvalidDataException("Expected one finalized synthetic database and its receipt.");
                using var marker = JsonDocument.Parse(OpenInput(inputs, Path.Combine(name, "receipt.json")));
                var reference = marker.RootElement;
                var contents = OpenInput(inputs, Path.Combine(name, "inserted.db"));
                var digest = Convert.ToHexStringLower(SHA256.HashData(contents));
                if (reference.GetProperty("format").GetString() != "ifw-study-new-entries-v1" ||
                    reference.GetProperty("mode").GetString() != mode || reference.GetProperty("chosenProfile").GetString() != chosen ||
                    reference.GetProperty("after").GetString() != digest)
                    throw new InvalidDataException("Rust observation differs from the input copy.");
                var copy = Path.Combine(output, name + ".db");
                using (var created = new FileStream(copy, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    created.Write(contents);
                var store = new SqliteSyncStateStore(copy, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
                var lookups = new List<object?>();
                foreach (var (account, root, relative) in new[] {
                    (Account, Stable, "New/Stable.jpg"), (Account, Stable, "New/Only-ƛ.jpg"),
                    (Account, Stable, "New/Only-Ƛ.jpg"), (Account, SourcePath, "New/Source.jpg"),
                    (Account, SourcePath.Replace('ƛ', 'Ƛ'), "New/Source.jpg"), (OtherAccount, Stable, "New/Stable.jpg") })
                    lookups.Add(Identity(await store.GetAsync(account, root, relative)));
                var lists = new List<object>();
                foreach (var (account, root) in new[] { (Account, Stable), (Account, SourcePath),
                             (Account, SourcePath.Replace('ƛ', 'Ƛ')), (OtherAccount, Stable) })
                    lists.Add((await store.GetSourceEntriesAsync(account, root)).Select(Identity).ToArray());
                var history = await store.GetLastSuccessfulSyncAsync(Account);
                var otherHistory = await store.GetLastSuccessfulSyncAsync(OtherAccount);
                SqliteConnection.ClearAllPools();
                cases.Add(name, new { digest, readerCopySha256 = HashFile(copy), lookups, lists, history, otherHistory });
            }
            var corelib = typeof(string).Assembly;
            var report = new { format = "ifw-study-insert-readback-v1", baseline = Baseline, sources, os, arch, privateWorkMount, readOnlyCasesMount,
                runtime = Environment.Version.ToString(), corelibBuild = corelib.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                corelibSha256 = HashFile(corelib.Location), storeSha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location),
                readerSha256 = HashFile(typeof(CasingCases).Assembly.Location), casingProfile = profile.Manifest, cases };
            await File.WriteAllTextAsync(Path.Combine(output, "result.json"), JsonSerializer.Serialize(report) + "\n");
        });
    }
}
