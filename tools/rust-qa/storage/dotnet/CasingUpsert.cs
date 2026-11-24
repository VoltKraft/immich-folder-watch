using System.Text.Json;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static partial class CasingCases
{
    public static async Task UpsertInsertedAsync(string directory)
    {
        var native = NativeTarget();
        var reader = InvariantUppercaseProfile.Capture();
        var fixture = LoadWrittenFixture(directory, "ƛ".ToUpperInvariant(), native, VerifyShippingSources(), null);
        if (!JsonElement.DeepEquals(fixture.Manifest.GetProperty("casingProfile"), JsonSerializer.SerializeToElement(reader.Manifest)) ||
            fixture.Manifest.GetProperty("fixtureAssemblySha256").GetString() != HashFile(typeof(CasingCases).Assembly.Location) ||
            fixture.Manifest.GetProperty("coreAssemblySha256").GetString() != HashFile(typeof(SqliteSyncStateStore).Assembly.Location))
            throw new InvalidDataException("The native reader differs from the qualified C# writer.");

        var parent = Directory.GetParent(fixture.Directory)!.FullName;
        await WithFreshDirectoryAsync(Path.Combine(parent, "native-insert-upserts"), async staging =>
        {
            var observations = new List<object>();
            foreach (var mode in new[] { "sensitive", "insensitive" })
            {
                var input = ArtifactDirectory(Path.Combine(parent, "native-insert-" + mode));
                var files = new DirectoryInfo(input).GetFileSystemInfos();
                if (!files.Select(f => f.Name).ToHashSet(StringComparer.Ordinal).SetEquals(["after.db", "receipt.json"]) ||
                    files.Any(f => f is not FileInfo || f.LinkTarget is not null || f.Attributes.HasFlag(FileAttributes.ReparsePoint)))
                    throw new IOException("Expected an original standalone Rust output and its receipt.");
                using var document = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(input, "receipt.json")));
                var receipt = document.RootElement;
                if (receipt.GetProperty("format").GetString() != "ifw-native-concordant-insert-v1" ||
                    receipt.GetProperty("mode").GetString() != mode || receipt.GetProperty("donor").GetString() != fixture.DatabaseHash(mode))
                    throw new InvalidDataException("The Rust receipt differs from the marked original C# backup.");
                var request = receipt.GetProperty("stable");
                var source = request.GetProperty("source").GetString()!;
                var relative = request.GetProperty("relative").GetString()!;
                var asset = request.GetProperty("asset").GetString()!;
                var from = Path.Combine(input, "after.db");
                var hash = receipt.GetProperty("after").GetString()!;
                for (var pass = 1; pass <= 2; pass++)
                {
                    var path = Path.Combine(staging, $"{mode}-{pass}.db");
                    File.Copy(from, path);
                    if (HashFile(path) != hash || request.GetProperty("account").GetString() != Account)
                        throw new InvalidDataException("The copy or account differs from the requested native insert.");
                    var store = new SqliteSyncStateStore(path, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
                    var entry = await store.GetAsync(Account, source, relative);
                    if (entry is null || entry.AssetId != asset || entry.FileSize != (pass == 1 ? 83 : 101) ||
                        entry.SourcePath != Path.TrimEndingDirectorySeparator(Path.GetFullPath(source)) ||
                        entry.RelativePath != relative.Replace('/', Path.DirectorySeparatorChar))
                        throw new InvalidDataException($"The shipping store could not read the expected normalized entry on {mode} pass {pass}.");
                    await store.UpsertAsync(entry with { SourcePath = source, RelativePath = relative, FileSize = 101 });
                    SqliteConnection.ClearAllPools();
                    using (var db = Open(path, SqliteOpenMode.ReadWrite))
                    using (var command = db.CreateCommand())
                    {
                        command.CommandText = "PRAGMA journal_mode=DELETE";
                        if ((string?)command.ExecuteScalar() != "delete")
                            throw new InvalidDataException("Expected a standalone schema-v1 output from the shipping store.");
                    }
                    from = path;
                    hash = HashFile(path);
                    observations.Add(new { mode, pass, source = entry.SourcePath, relative = entry.RelativePath, asset = entry.AssetId,
                        readSize = entry.FileSize, sha256 = hash });
                }
            }
            VerifyOriginal(fixture);
            await File.WriteAllTextAsync(Path.Combine(staging, "receipt.json"), JsonSerializer.Serialize(new {
                os = native.Os, arch = native.Arch, readerProfile = reader.Manifest, donorManifest = fixture.ManifestSha256, observations }));
        });
    }
}
