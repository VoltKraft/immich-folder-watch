using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.LegacyScalarOracle;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.StorageAssessment;

internal static partial class CasingCases
{
    private sealed record WrittenFixture(string Directory, string Upper, JsonElement Manifest, string ManifestSha256,
        bool HasWriterTable)
    {
        public string DatabaseHash(string mode) =>
            Manifest.GetProperty("cases").GetProperty(mode).GetProperty("sha256").GetString()!;
    }

    // These two independent UnicodeData reconstructions are pinned by casing_profiles.py.
    private static (string Sha256, int Changed) KnownTable(string upper) => upper switch
    {
        "ƛ" => ("02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f", 1449),
        "Ƛ" => ("195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e", 1504),
        _ => throw new InvalidDataException("The discriminator differs from both qualified profiles.")
    };

    public static async Task<bool> CompareAsync(string oldFixture, string newFixture, string destination,
        string? archivedOldDigest = null, string? archivedNewDigest = null)
    {
        var native = NativeTarget();
        var sources = VerifyShippingSources();
        var readerUpper = "ƛ".ToUpperInvariant();
        var readerProfile = InvariantUppercaseProfile.Capture();
        var readerTableVerified = (readerUpper is "ƛ" or "Ƛ") && readerProfile.ScannedScalars == 0x110000 - 0x800 &&
            (readerProfile.TableSha256, readerProfile.ChangedScalars) == KnownTable(readerUpper);
        var fixtures = new[] { LoadWrittenFixture(oldFixture, "ƛ", native, sources, archivedOldDigest),
            LoadWrittenFixture(newFixture, "Ƛ", native, sources, archivedNewDigest) };
        var output = ArtifactDirectory(destination);
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (fixtures.Any(f => output.Equals(f.Directory, comparison) || output.StartsWith(f.Directory + Path.DirectorySeparatorChar, comparison)))
            throw new IOException("The readback output must be separate from both original fixtures.");

        var passed = readerTableVerified;
        await WithFreshDirectoryAsync(output, async staging =>
        {
            readerProfile.Write(staging);
            var observations = new List<object>();
            try
            {
                foreach (var fixture in readerTableVerified ? fixtures : Array.Empty<WrittenFixture>())
                {
                    var name = fixture.Upper == "ƛ" ? "writer-019b" : "writer-a7dc";
                    var copy = Directory.CreateDirectory(Path.Combine(staging, name)).FullName;
                    File.Copy(Path.Combine(fixture.Directory, "manifest.json"), Path.Combine(copy, "source-manifest.json"));
                    if (HashFile(Path.Combine(copy, "source-manifest.json")) != fixture.ManifestSha256)
                        throw new InvalidDataException("The copied writer manifest changed.");
                    if (fixture.HasWriterTable)
                    {
                        var filename = InvariantUppercaseProfile.FileName;
                        File.Copy(Path.Combine(fixture.Directory, filename), Path.Combine(copy, filename));
                        if (HashFile(Path.Combine(copy, filename)) != KnownTable(fixture.Upper).Sha256)
                            throw new InvalidDataException("The copied writer casing table changed.");
                    }
                    foreach (var mode in new[] { "sensitive", "insensitive" })
                    {
                        var (matches, evidence) = await ReadCopyAsync(fixture, mode, copy, readerUpper);
                        passed &= matches;
                        observations.Add(evidence);
                    }
                }
            }
            finally
            {
                foreach (var fixture in fixtures)
                    VerifyOriginal(fixture);
            }
            var report = new
            {
                format = "ifw-csharp-cross-profile-readback-v1", passed, baseline = Baseline, sources,
                os = native.Os, arch = native.Arch, target = RuntimeInformation.RuntimeIdentifier,
                runtime = Environment.Version.ToString(), readerUpper, casingProfile = readerProfile.Manifest,
                readerTableVerified, originalsVerified = true, writerTablesVerified = fixtures.All(fixture => fixture.HasWriterTable),
                error = readerTableVerified ? null : "The active reader's complete invariant casing differs from the qualified profiles.",
                coreAssemblySha256 = HashFile(typeof(SqliteSyncStateStore).Assembly.Location),
                fixtureAssemblySha256 = HashFile(typeof(CasingCases).Assembly.Location), observations
            };
            await File.WriteAllTextAsync(Path.Combine(staging, "result.json"),
                JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        });
        return passed;
    }

    private static WrittenFixture LoadWrittenFixture(string directory, string upper, (string Os, string Arch) native,
        Dictionary<string, string> sources, string? archivedDigest)
    {
        var input = ArtifactDirectory(directory);
        var hasTable = CheckFileSet(input);
        var bytes = File.ReadAllBytes(Path.Combine(input, "manifest.json"));
        using var document = JsonDocument.Parse(bytes);
        var manifest = document.RootElement;
        string? Field(string key) => manifest.GetProperty(key).GetString();
        if (Field("format") != "ifw-qualified-path-key-fixture-v1" || Field("baseline") != Baseline ||
            Field("os") != native.Os || Field("arch") != native.Arch || Field("target") != RuntimeInformation.RuntimeIdentifier ||
            Field("nativeUpperOfDiscriminator") != upper || !JsonElement.DeepEquals(manifest.GetProperty("sources"), JsonSerializer.SerializeToElement(sources)) ||
            manifest.GetProperty("seed").GetDateTimeOffset() != Seed || Field("sourcePath") != SourcePath ||
            Field("account") != Account || Field("otherAccount") != OtherAccount ||
            Field("relativePath") != RelativePath || Field("upperRelativePath") != UpperRelativePath ||
            Field("repairRelativePath") != RepairRelativePath || Field("tombstoneRelativePath") != TombstoneRelativePath ||
            Field("albumDirectory") != AlbumDirectory || Field("albumId") != AlbumId || Field("otherAlbumId") != OtherAlbumId)
            throw new InvalidDataException("Expected the marked synthetic writer fixture for this baseline, profile and native target.");
        var digest = Convert.ToHexStringLower(SHA256.HashData(bytes));
        if (archivedDigest is not null && archivedDigest != digest)
            throw new InvalidDataException("The original writer manifest differs from its supplied attestation.");
        if (manifest.TryGetProperty("casingProfile", out var profile) != hasTable)
            throw new InvalidDataException("The writer's profile and complete casing table must be present together.");
        if (hasTable)
        {
            var expected = KnownTable(upper);
            if (profile.GetProperty("tableSha256").GetString() != expected.Sha256 ||
                profile.GetProperty("scannedScalars").GetInt32() != 0x110000 - 0x800 ||
                profile.GetProperty("changedScalars").GetInt32() != expected.Changed ||
                !profile.GetProperty("contextBatchChecked").GetBoolean())
                throw new InvalidDataException("The writer's full casing profile differs from the qualified reference.");
        }
        else if (archivedDigest is null)
            throw new InvalidDataException("This historical writer requires its recorded external manifest digest for diagnostic readback.");
        var fixture = new WrittenFixture(input, upper, manifest.Clone(), digest, hasTable);
        VerifyOriginal(fixture);
        return fixture;
    }

    private static bool CheckFileSet(string directory)
    {
        var files = new DirectoryInfo(directory).EnumerateFileSystemInfos().ToArray();
        var names = files.Select(file => file.Name).ToHashSet(StringComparer.Ordinal);
        var hasTable = names.Remove(InvariantUppercaseProfile.FileName);
        if (!names.SetEquals(new[] { "insensitive.db", "manifest.json", "sensitive.db" }) ||
            files.Any(file => file is not FileInfo || file.LinkTarget is not null || file.Attributes.HasFlag(FileAttributes.ReparsePoint)))
            throw new IOException("The original fixture must contain its regular source files and standalone backups.");
        return hasTable;
    }

    private static void VerifyOriginal(WrittenFixture fixture)
    {
        if (CheckFileSet(ArtifactDirectory(fixture.Directory)) != fixture.HasWriterTable ||
            (fixture.HasWriterTable && HashFile(Path.Combine(fixture.Directory, InvariantUppercaseProfile.FileName)) != KnownTable(fixture.Upper).Sha256) ||
            HashFile(Path.Combine(fixture.Directory, "manifest.json")) != fixture.ManifestSha256 ||
            new[] { "sensitive", "insensitive" }.Any(mode => HashFile(Path.Combine(fixture.Directory, mode + ".db")) != fixture.DatabaseHash(mode)))
            throw new InvalidDataException("The original fixture bytes differ from the recorded writer output.");
    }

    private static async Task<(bool Matches, object Evidence)> ReadCopyAsync(WrittenFixture fixture, string mode,
        string directory, string readerUpper)
    {
        var filename = mode + ".db";
        var copy = Path.Combine(directory, filename);
        File.Copy(Path.Combine(fixture.Directory, filename), copy);
        var originalSha256 = fixture.DatabaseHash(mode);
        if (HashFile(copy) != originalSha256)
            throw new InvalidDataException("The fresh database copy differs from the writer's digest.");
        var writerTables = fixture.Manifest.GetProperty("cases").GetProperty(mode).GetProperty("tables");
        string sqlite;
        using (var database = Open(copy, SqliteOpenMode.ReadOnly))
        using (var check = database.CreateCommand())
        {
            sqlite = database.ServerVersion;
            check.CommandText = "PRAGMA user_version";
            if ((long?)check.ExecuteScalar() != 1)
                throw new InvalidDataException("The synthetic copy must use schema v1.");
            check.CommandText = "PRAGMA journal_mode";
            if ((string?)check.ExecuteScalar() != "delete" || !JsonElement.DeepEquals(writerTables, ReadTables(database)))
                throw new InvalidDataException("The standalone copy differs from the writer's logical inventory.");
        }

        // The shipping initializer enables WAL even for a lookup. Only hand it
        // the fresh copy, and check all four logical tables again after it exits.
        var store = new SqliteSyncStateStore(copy, NullLogger<SqliteSyncStateStore>.Instance, mode == "sensitive");
        var entries = await store.GetSourceEntriesAsync(Account, SourcePath);
        var lower = await store.GetAsync(Account, SourcePath, RelativePath);
        var upper = await store.GetAsync(Account, SourcePath, UpperRelativePath);
        var removed = await store.GetAsync(Account, SourcePath, TombstoneRelativePath);
        var other = await store.GetAsync(OtherAccount, SourcePath, RelativePath);
        var repairs = await store.GetTimestampRepairsAsync(Account, SourcePath);
        var observed = new
        {
            primaryEntries = entries.Count, lower = lower?.AssetId, upper = upper?.AssetId,
            tombstone = removed?.TombstoneExpiresAtUtc, other = other?.AssetId,
            journals = repairs.Select(repair => repair.OriginalEntry.RelativePath).Order(StringComparer.Ordinal).ToArray(),
            album = await store.GetOwnedAlbumAsync(Account, SourcePath, AlbumDirectory, default),
            otherAlbum = await store.GetOwnedAlbumAsync(OtherAccount, SourcePath, AlbumDirectory, default),
            history = await store.GetLastSuccessfulSyncAsync(Account), otherHistory = await store.GetLastSuccessfulSyncAsync(OtherAccount)
        };
        SqliteConnection.ClearAllPools();
        bool rowsPreserved;
        using (var database = Open(copy, SqliteOpenMode.ReadOnly))
            rowsPreserved = JsonElement.DeepEquals(writerTables, ReadTables(database));
        var visible = mode == "sensitive" || fixture.Upper == readerUpper;
        var collapsed = mode == "insensitive" && fixture.Upper == "Ƛ";
        var expectedCount = visible ? (collapsed ? 2 : 3) : 0;
        var matches = rowsPreserved && observed.primaryEntries == expectedCount &&
            observed.lower == (visible ? "asset-lower" : null) && observed.upper == (visible ? (collapsed ? "asset-lower" : "asset-upper") : null) &&
            observed.other == (visible ? "asset-other" : null) && observed.tombstone == (visible ? Seed.AddDays(7) : null) &&
            observed.journals.SequenceEqual(visible ? new[] { RelativePath, RepairRelativePath } : Array.Empty<string>()) &&
            observed.album == (visible ? AlbumId : null) && observed.otherAlbum == (visible ? OtherAlbumId : null) &&
            observed.history == Seed.AddMinutes(17) && observed.otherHistory == Seed.AddMinutes(18);
        return (matches, new
        {
            mode, writerUpper = fixture.Upper, readerUpper, sqlite, sourceManifestSha256 = fixture.ManifestSha256, originalSha256,
            writerTableVerified = fixture.HasWriterTable,
            writerCoreAssemblySha256 = fixture.Manifest.GetProperty("coreAssemblySha256").GetString(),
            writerFixtureAssemblySha256 = fixture.Manifest.GetProperty("fixtureAssemblySha256").GetString(),
            readerCopySha256 = HashFile(copy), rowsPreserved, expectedVisible = visible,
            expectedPrimaryEntries = expectedCount, observed, matches
        });
    }
}
