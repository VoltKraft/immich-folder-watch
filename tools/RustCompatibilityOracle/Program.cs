using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.RustCompatibilityOracle;

/// <summary>
/// Executes the shipping C# configuration and storage APIs against synthetic data only.
/// Exported SQL is an interchange fixture, never a backup of an installed application.
/// </summary>
internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        if (args.Length != 2 || args[0] is not ("export" or "verify"))
        {
            Console.Error.WriteLine("Usage: RustCompatibilityOracle <export|verify> <fixture-directory>");
            return 2;
        }

        if (!OperatingSystem.IsWindows() && !OperatingSystem.IsLinux())
        {
            Console.Error.WriteLine("The oracle supports native Windows and Linux only.");
            return 2;
        }
        var expectedArchitecture = Environment.GetEnvironmentVariable("IFW_ORACLE_EXPECT_ARCH");
        if (expectedArchitecture is not null &&
            (expectedArchitecture is not ("x64" or "arm64") ||
             !string.Equals(RuntimeInformation.ProcessArchitecture.ToString(), expectedArchitecture, StringComparison.OrdinalIgnoreCase) ||
             !string.Equals(RuntimeInformation.OSArchitecture.ToString(), expectedArchitecture, StringComparison.OrdinalIgnoreCase)))
        {
            Console.Error.WriteLine($"Native architecture assertion failed: expected {expectedArchitecture}; " +
                $"process {RuntimeInformation.ProcessArchitecture}, OS {RuntimeInformation.OSArchitecture}.");
            return 2;
        }

        var destination = Path.GetFullPath(args[1]);
        var platform = OperatingSystem.IsWindows() ? "windows" : "linux";
        var repository = FindRepository();
        var scratch = Path.Combine(Path.GetTempPath(), $"ifw-rust-oracle-{Guid.NewGuid():N}");
        Directory.CreateDirectory(scratch);
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(scratch, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);

        try
        {
            var corpus = new Corpus(repository, scratch);
            var files = await corpus.GenerateAsync();
            var target = Path.Combine(destination, platform);
            foreach (var (name, content) in files)
            {
                var path = Path.Combine(target, name.Replace('/', Path.DirectorySeparatorChar));
                if (args[0] == "export")
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                    await File.WriteAllTextAsync(path, content, new UTF8Encoding(false));
                }
                else if (!File.Exists(path) || await File.ReadAllTextAsync(path) != content)
                {
                    throw new InvalidDataException($"Fixture differs: {platform}/{name}. Regenerate only after reviewing baseline drift.");
                }
            }

            var extra = Directory.EnumerateFiles(target, "*", SearchOption.AllDirectories)
                .Select(path => Path.GetRelativePath(target, path).Replace('\\', '/'))
                .Except(files.Keys, StringComparer.Ordinal).ToArray();
            if (extra.Length != 0)
                throw new InvalidDataException($"Unexpected fixture files: {string.Join(", ", extra)}");

            Console.WriteLine($"{args[0]} passed: {files.Count} {platform} fixtures, {corpus.CheckCount} assertions; " +
                $".NET {Environment.Version}, process {RuntimeInformation.ProcessArchitecture}, OS {RuntimeInformation.OSArchitecture}. " +
                "No app profile or network used by the oracle.");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Oracle failed: {exception.GetType().Name}: {exception.Message}");
            return 1;
        }
        finally
        {
            SqliteConnection.ClearAllPools();
            Directory.Delete(scratch, recursive: true);
        }
    }

    private static string FindRepository()
    {
        var directory = new DirectoryInfo(Environment.CurrentDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "global.json")) &&
                Directory.Exists(Path.Combine(directory.FullName, "src", "ImmichFolderWatch.Core")))
                return directory.FullName;
            directory = directory.Parent;
        }
        throw new InvalidOperationException("Run the oracle from within the repository.");
    }
}

internal sealed class Corpus(string repository, string scratch)
{
    private const string Baseline = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc";
    private const string Server = "https://immich.example.invalid/api/";
    private const string SyntheticKey = "RW01-SYNTHETIC-NOT-A-CREDENTIAL";
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    private static readonly DateTimeOffset Epoch = DateTimeOffset.ParseExact(
        "2024-02-29T03:04:05.1234567+00:00", "O", CultureInfo.InvariantCulture);
    private static readonly string Source = OperatingSystem.IsWindows()
        ? @"C:\ifw-synthetic\Média" : "/ifw-synthetic/Média";
    private readonly SortedDictionary<string, string> files = new(StringComparer.Ordinal);
    public int CheckCount { get; private set; }

    public async Task<SortedDictionary<string, string>> GenerateAsync()
    {
        await ConfigurationsAsync();
        Identities();
        await PathVectorsAsync();
        await DatabaseAsync(pathsCaseSensitive: true);
        await DatabaseAsync(pathsCaseSensitive: false);
        await FutureSchemaAsync();

        var sourceFiles = new[]
        {
            "src/ImmichFolderWatch.Core/Configuration/AppConfig.cs",
            "src/ImmichFolderWatch.Core/Configuration/AppConfigLoader.cs",
            "src/ImmichFolderWatch.Core/Configuration/AppConfigWriter.cs",
            "src/ImmichFolderWatch.Core/Models/SyncAccountScope.cs",
            "src/ImmichFolderWatch.Core/Models/SyncStateEntry.cs",
            "src/ImmichFolderWatch.Core/Models/SyncTimestampRepair.cs",
            "src/ImmichFolderWatch.Core/Services/SqliteSyncStateStore.cs",
            "src/ImmichFolderWatch.Core/Services/SqliteSyncStateStore.AlbumOwnership.cs",
            "tools/RustCompatibilityOracle/Program.cs",
            "tools/RustCompatibilityOracle/RustCompatibilityOracle.csproj",
        };
        AddJson("manifest.json", new
        {
            Format = "ifw-rw01-legacy-v1",
            BehavioralBaseline = Baseline,
            Platform = OperatingSystem.IsWindows() ? "windows" : "linux",
            SyntheticOnly = true,
            SourceHashes = sourceFiles.ToDictionary(path => path, path =>
                Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(Path.Combine(repository, path))))),
            Fixtures = files.ToDictionary(pair => pair.Key, pair =>
                Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(pair.Value)))),
            Assertions = CheckCount,
        });
        return files;
    }

    private async Task ConfigurationsAsync()
    {
        var cases = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["defaults"] = "{}\n",
            ["legacy"] = """
                immich:
                  serverApiUrl: "  https://immich.example.invalid/api/  "
                  apiKey: " RW01-SYNTHETIC-NOT-A-CREDENTIAL "
                watch:
                  extensions: [JPG, .jpg, png, " "]
                  transferOrder: " OLDESTFIRST "
                  sources:
                    - path: " media/../Média "
                      albumName: "  Legacy album  "
                      syncMode: " unknown-future-mode "
                      excludeDirectories: [" temp ", TEMP, " "]
                      excludeFileNames: ["*.tmp", "*.TMP"]
                    - path: "second"
                      extensions: [.HEIC]
                      syncMode: " UPLOADALL "
                localization:
                  language: " DE "
                logging:
                  target: " JOURNALD "
                  logDirectory: " logs/../logs "
                unknownFutureProperty: ignored
                """ + "\n",
            ["null-sections"] = "immich: null\nwatch: null\nretry: null\nlogging: null\nlocalization: null\n",
            ["scalars"] = """
                immich:
                  serverApiUrl: 'https://immich.example.invalid/api'
                  apiKey: 'RW01-SYNTHETIC-NOT-A-CREDENTIAL'
                  allowInsecureHttp: true
                watch:
                  sources:
                    - path: 'C:\Pictures\2024'
                      albumName: 'null'
                      includeSubdirectories: true
                      extensions: ['jpg', '.MOV']
                      syncMode: sync
                    - path: '001'
                      albumName: '123'
                      deleteAfterUpload: true
                      syncMode: uploadAll
                    - path: 'Média/日本語/😀'
                      albumName: 'true'
                    - path: 'colon: hash#'
                      albumName: 'a: b # c'
                retry:
                  maxAttempts: 7
                  baseDelayMilliseconds: 123
                logging:
                  target: file
                localization:
                  language: en
                """ + "\n",
            ["aliases"] = """
                watch:
                  sources:
                    - &source
                      path: media
                      albumName: 'on'
                    - *source
                """ + "\n",
        };

        var loader = new AppConfigLoader();
        foreach (var (name, yaml) in cases)
        {
            var configPath = Path.Combine(scratch, "config.yaml");
            await File.WriteAllTextAsync(configPath, yaml);
            var editable = loader.LoadForEditing(configPath);
            var runtime = loader.Load(configPath);
            var written = new AppConfigWriter().Serialize(editable).Replace("\r\n", "\n");
            await File.WriteAllTextAsync(configPath, written);
            var roundTrip = loader.LoadForEditing(configPath);
            Check(JsonSerializer.Serialize(editable) == JsonSerializer.Serialize(roundTrip), $"{name}: YAML writer/readback");
            Add($"config/{name}.input.yaml", yaml);
            Add($"config/{name}.written.yaml", written);
            AddJson($"config/{name}.expected.json", new
            {
                Editable = editable,
                Runtime = RuntimeView(runtime),
                RuntimePathToken = "$PROFILE",
            });
        }
    }

    private object RuntimeView(AppConfig config)
    {
        string Normalize(string path) => path.StartsWith(scratch + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            ? "$PROFILE" + path[scratch.Length..] : path;
        foreach (var source in config.Watch.Sources) source.Path = Normalize(source.Path);
        config.Logging.LogDirectory = Normalize(config.Logging.LogDirectory);
        return config;
    }

    private void Identities()
    {
        var inputs = new[]
        {
            (Server, SyntheticKey),
            ("  " + Server + "// ", SyntheticKey),
            ("https://IMMICH.example.invalid:443/api", SyntheticKey),
            (Server, " " + SyntheticKey + " "),
            (Server, "RW01-SYNTHETIC-ä-日本語"),
        };
        var identities = inputs.Select(value => new
        {
            ServerApiUrl = value.Item1,
            ApiKey = value.Item2,
            AccountScope = SyncAccountScope.Create(value.Item1, value.Item2),
        }).ToArray();
        Check(identities[0].AccountScope == identities[1].AccountScope, "account URL trim/trailing slashes");
        Check(identities[0].AccountScope != identities[2].AccountScope, "account URL case/port retained");
        Check(identities[0].AccountScope != identities[3].AccountScope, "direct account API does not trim key");
        AddJson("identities.json", new
        {
            Accounts = identities,
            InvariantUppercase = new[] { "straße", "ß", "iıİI", "σςΣ", "é", "e\u0301", "日本語", "𐐨", "ﬃ" }
                .Select(value => new { Input = value, Output = value.ToUpperInvariant() }),
        });
    }

    private async Task DatabaseAsync(bool pathsCaseSensitive)
    {
        var mode = pathsCaseSensitive ? "sensitive" : "insensitive";
        var database = Path.Combine(scratch, mode + ".db");
        var store = NewStore(database, pathsCaseSensitive);
        var account = SyncAccountScope.Create(Server, SyntheticKey);
        var otherAccount = SyncAccountScope.Create(Server, "RW01-SYNTHETIC-OTHER");
        var relative = "Straße/σς-𐐨.jpg".Replace('/', Path.DirectorySeparatorChar);
        var uploaded = new SyncStateEntry(account, Source + Path.DirectorySeparatorChar, relative,
            "asset-upload", "null", 9007199254740993L, Epoch, SyncTransferDirection.Upload,
            SyncEntryStatus.Synchronized, Epoch.AddHours(1));
        var downloaded = uploaded with
        {
            RelativePath = "download.bin", AssetId = "asset-download", AlbumName = "", FileSize = 0,
            Direction = SyncTransferDirection.Download, LastWriteTimeUtc = Epoch.ToOffset(TimeSpan.FromHours(5.5)),
            LastSynchronizedAtUtc = Epoch.AddHours(2),
        };
        var tombstone = uploaded with
        {
            RelativePath = "removed.jpg", AssetId = null, Status = SyncEntryStatus.Tombstone,
            LastSynchronizedAtUtc = Epoch.AddDays(2), TombstoneExpiresAtUtc = Epoch.AddSeconds(120),
        };
        var other = downloaded with { AccountScope = otherAccount, RelativePath = "other-account.jpg" };
        foreach (var entry in new[] { uploaded, downloaded, tombstone, other }) await store.UpsertAsync(entry);
        await store.RecordSuccessfulSyncAsync(account, Epoch.AddHours(3));
        await store.RecordSuccessfulSyncAsync(account, Epoch);
        await store.RecordSuccessfulSyncAsync(otherAccount, Epoch.AddHours(2));
        await store.SaveOwnedAlbumAsync(account, Source, "Straße", "album-exact-id", default);
        await store.SaveOwnedAlbumAsync(otherAccount, Source, "Other", "album-other", default);
        var repair = new SyncTimestampRepair(uploaded, Epoch.AddDays(-2), Epoch.AddTicks(1),
            Convert.ToHexStringLower(SHA256.HashData("synthetic-content"u8)));
        await store.SaveTimestampRepairAsync(repair);

        var storedEntries = await store.GetSourceEntriesAsync(account, Source);
        var storedRepairs = await store.GetTimestampRepairsAsync(account, Source);
        Check(storedEntries.Count == 3, $"{mode}: entries read");
        Check(storedEntries.Single(entry => entry.RelativePath == relative).FileSize == uploaded.FileSize, $"{mode}: int64 precision");
        Check(storedRepairs.Count == 1 && storedRepairs[0].ContentSha256 == repair.ContentSha256.ToUpperInvariant(), $"{mode}: repair codec");
        Check(await store.GetLastSuccessfulSyncAsync(account) == Epoch.AddHours(3), $"{mode}: monotonic history");
        Check(await store.GetOwnedAlbumAsync(account, Source, "Straße", default) == "album-exact-id", $"{mode}: exact ownership");

        var snapshot = await ReadSnapshotAsync(database);
        var sql = ToSql(snapshot);
        Add($"sqlite/{mode}.sql", sql);
        AddJson($"sqlite/{mode}.expected.json", new
        {
            PathsCaseSensitive = pathsCaseSensitive, Source, Account = account, OtherAccount = otherAccount,
            Entries = storedEntries, Repairs = storedRepairs,
            LastSuccessfulSyncUtc = await store.GetLastSuccessfulSyncAsync(account), Snapshot = snapshot,
        });
        await VerifyImportAsync(sql, pathsCaseSensitive, account, otherAccount, storedEntries, storedRepairs);
        await VerifyOptionalTablesAsync(sql, pathsCaseSensitive, account, mode);
        await VerifyBackupAsync(sql, pathsCaseSensitive, account, mode);

        var observations = new List<object>();
        var beforeExpiry = await store.DeleteExpiredTombstonesAsync(Epoch.AddSeconds(120).AddTicks(-1));
        var atExpiry = await store.DeleteExpiredTombstonesAsync(Epoch.AddSeconds(120));
        Check(beforeExpiry == 0 && atExpiry == 1, $"{mode}: tombstone inclusive expiry");
        observations.Add(new { Case = "tombstone-boundary", BeforeExpiry = beforeExpiry, AtExpiry = atExpiry });

        await store.SaveTimestampRepairAsync(repair);
        var differentRepairRejected = await ThrowsAsync<InvalidOperationException>(() =>
            store.SaveTimestampRepairAsync(repair with { CreationTimeUtc = Epoch }));
        Check(differentRepairRejected, $"{mode}: cannot replace pending repair");
        await store.UpsertAsync(uploaded with { AlbumName = "changed-after-intent" });
        var staleMappingRejected = await ThrowsAsync<InvalidOperationException>(() =>
            store.CompleteTimestampRepairAsync(repair, uploaded with { LastWriteTimeUtc = repair.LastWriteTimeUtc }));
        Check(staleMappingRejected && (await store.GetTimestampRepairsAsync(account, Source)).Count == 1,
            $"{mode}: failed CAS retains intent");
        await store.UpsertAsync(uploaded);
        await store.CompleteTimestampRepairAsync(repair, uploaded with { LastWriteTimeUtc = repair.LastWriteTimeUtc });
        Check((await store.GetTimestampRepairsAsync(account, Source)).Count == 0, $"{mode}: completed repair removes journal");
        Check((await store.GetAsync(account, Source, relative))!.LastWriteTimeUtc == repair.LastWriteTimeUtc,
            $"{mode}: completed repair updates mapping");
        Check(await store.GetLastSuccessfulSyncAsync(account) == Epoch.AddHours(3), $"{mode}: repair is not a transfer");
        observations.Add(new { Case = "repair-compare-and-swap", DifferentRepairRejected = differentRepairRejected,
            StaleMappingRejected = staleMappingRejected, JournalRetainedOnConflict = true,
            CompletionUpdatesMappingAndRemovesJournal = true });

        await store.RemoveOwnedAlbumAsync(account, Source, "Straße", "wrong-album-id", default);
        Check(await store.GetOwnedAlbumAsync(account, Source, "Straße", default) == "album-exact-id", $"{mode}: removal requires exact ID");
        await store.RevokeAlbumOwnershipAsync(account, default);
        Check(await store.GetOwnedAlbumAsync(account, Source, "Straße", default) is null, $"{mode}: active account revoked");
        Check(await store.GetOwnedAlbumAsync(otherAccount, Source, "Other", default) == "album-other", $"{mode}: unrelated account preserved");
        observations.Add(new { Case = "authority-revocation", ExactIdRequired = true, ActiveAccountRevoked = true, OtherAccountPreserved = true });
        AddJson($"sqlite/{mode}.operations.json", observations);
    }

    private async Task PathVectorsAsync()
    {
        var sources = OperatingSystem.IsWindows()
            ? new[] { @"C:\", @"C:\ifw-synthetic\", @"C:\ifw-synthetic\..\Média", @"c:/ifw-synthetic/Média/",
                @"\\server.invalid\share\", @"\\server.invalid\share\Straße\" }
            : new[] { "/", "/ifw-synthetic/", "/ifw-synthetic/../Média", "/ifw-synthetic//Média/",
                "/ifw-synthetic/straße", "/ifw-synthetic/e\u0301" };
        var relatives = new[] { "album/é.jpg", @"album\é.jpg", "./σς-𐐨.jpg" };
        var vectors = new List<object>();
        foreach (var sensitive in new[] { true, false })
        foreach (var source in sources)
        foreach (var relative in relatives)
        {
            var path = Path.Combine(scratch, $"path-{vectors.Count}.db");
            var store = NewStore(path, sensitive);
            var entry = new SyncStateEntry("synthetic-path-scope", source, relative, "asset-path", "", 1,
                Epoch, SyncTransferDirection.Upload, SyncEntryStatus.Synchronized, Epoch);
            await store.UpsertAsync(entry);
            var read = await store.GetAsync(entry.AccountScope, source, relative);
            Check(read is not null && read.AssetId == entry.AssetId, "native path/key readback");
            var row = (await ReadSnapshotAsync(path)).Tables.Single(table => table.Name == "sync_entries").Rows.Single();
            vectors.Add(new { SourceInput = source, RelativeInput = relative, PathsCaseSensitive = sensitive,
                SourcePath = row[1], SourceKey = row[2], RelativePath = row[3], RelativePathKey = row[4] });
        }
        AddJson("sqlite/path-vectors.json", new
        {
            NativePlatform = OperatingSystem.IsWindows() ? "windows" : "linux",
            Boundary = "String/key normalization only. These synthetic path strings are never opened as media; they confer no filesystem authorization.",
            Vectors = vectors,
        });
    }

    private async Task VerifyImportAsync(string sql, bool sensitive, string account, string otherAccount,
        IReadOnlyList<SyncStateEntry> entries, IReadOnlyList<SyncTimestampRepair> repairs)
    {
        var path = Path.Combine(scratch, Guid.NewGuid().ToString("N") + ".db");
        await ExecuteAsync(path, sql);
        var store = NewStore(path, sensitive);
        Check(JsonSerializer.Serialize(await store.GetSourceEntriesAsync(account, Source)) == JsonSerializer.Serialize(entries), "SQL import: C# entries reader");
        Check(JsonSerializer.Serialize(await store.GetTimestampRepairsAsync(account, Source)) == JsonSerializer.Serialize(repairs), "SQL import: C# repair reader");
        Check(await store.GetOwnedAlbumAsync(otherAccount, Source, "Other", default) == "album-other", "SQL import: C# ownership reader");
    }

    private async Task VerifyOptionalTablesAsync(string sql, bool sensitive, string account, string mode)
    {
        var observations = new List<object>();
        var optional = new[] { "owned_albums", "sync_timestamp_repairs", "sync_account_status" };
        for (var version = 0; version <= 1; version++)
        for (var mask = 0; mask < 8; mask++)
        {
            var name = $"v{version}-optional-{mask}";
            var path = Path.Combine(scratch, $"{mode}-{name}.db");
            var removed = optional.Where((_, index) => (mask & (1 << index)) != 0).ToArray();
            var inputSql = sql + string.Join("", removed.Select(table => $"DROP TABLE {table};\n")) + $"PRAGMA user_version = {version};\n";
            await ExecuteAsync(path, inputSql);
            var store = NewStore(path, sensitive);
            await store.InitializeAsync();
            var snapshot = await ReadSnapshotAsync(path);
            var expectedHistory = removed.Contains("sync_account_status") ? Epoch.AddHours(2) : Epoch.AddHours(3);
            Check(snapshot.UserVersion == 1 && snapshot.Tables.Count == 4, $"{mode}/{name}: schema restored");
            Check((await store.GetSourceEntriesAsync(account, Source)).Count == 3, $"{mode}/{name}: main rows retained");
            Check(await store.GetLastSuccessfulSyncAsync(account) == expectedHistory, $"{mode}/{name}: history backfill");
            var changed = (await store.GetAsync(account, Source, "download.bin"))! with { LastSynchronizedAtUtc = Epoch.AddYears(1) };
            await store.UpsertAsync(changed);
            await NewStore(path, sensitive).InitializeAsync();
            Check(await store.GetLastSuccessfulSyncAsync(account) == expectedHistory, $"{mode}/{name}: no repeated history backfill");
            observations.Add(new { Name = name, UserVersion = version, RemovedTables = removed,
                ExpectedAfterInitializationVersion = 1, ExpectedLastSuccessfulSyncUtc = expectedHistory,
                ReopeningDoesNotBackfillAgain = true });
        }
        AddJson($"sqlite/{mode}.legacy-schema-cases.json", observations);
    }

    private async Task VerifyBackupAsync(string sql, bool sensitive, string account, string mode)
    {
        var path = Path.Combine(scratch, mode + "-wal.db");
        var backup = Path.Combine(scratch, mode + "-backup.db");
        await ExecuteAsync(path, sql);
        await using var live = await OpenAsync(path);
        await using (var command = live.CreateCommand())
        {
            command.CommandText = "PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0;";
            await command.ExecuteNonQueryAsync();
        }
        await NewStore(path, sensitive).RecordSuccessfulSyncAsync(account, Epoch.AddDays(5));
        Check(File.Exists(path + "-wal") && new FileInfo(path + "-wal").Length > 0, $"{mode}: committed WAL exists");
        await using (var destination = await OpenAsync(backup)) live.BackupDatabase(destination);
        var copiedHistory = await NewStore(backup, sensitive).GetLastSuccessfulSyncAsync(account);
        Check(copiedHistory == Epoch.AddDays(5), $"{mode}: SQLite backup includes committed WAL");
        Check(await ScalarAsync(backup, "PRAGMA integrity_check;") as string == "ok", $"{mode}: backup integrity");
        AddJson($"sqlite/{mode}.wal-backup.json", new { CommittedWalPresent = true,
            BackupApi = "Microsoft.Data.Sqlite.SqliteConnection.BackupDatabase",
            ExpectedLastSuccessfulSyncUtc = copiedHistory, IntegrityCheck = "ok",
            Boundary = "Storage primitive only; no engine quiescence, process crash, disk-full or application rollback acceptance implied." });
    }

    private async Task FutureSchemaAsync()
    {
        var database = Path.Combine(scratch, "future.db");
        await ExecuteAsync(database, "CREATE TABLE future_sentinel(value TEXT); INSERT INTO future_sentinel VALUES ('preserve'); PRAGMA user_version=999; PRAGMA journal_mode=DELETE;");
        var before = SHA256.HashData(await File.ReadAllBytesAsync(database));
        var beforeMode = await ScalarAsync(database, "PRAGMA journal_mode;");
        var rejected = await ThrowsAsync<NotSupportedException>(() => NewStore(database, true).InitializeAsync());
        SqliteConnection.ClearAllPools();
        var after = SHA256.HashData(await File.ReadAllBytesAsync(database));
        var afterMode = await ScalarAsync(database, "PRAGMA journal_mode;");
        Check(rejected, "future schema rejected");
        Check(Convert.ToInt64(await ScalarAsync(database, "PRAGMA user_version;")) == 999, "future version retained");
        Check(await ScalarAsync(database, "SELECT value FROM future_sentinel;") as string == "preserve", "future payload retained");
        AddJson("sqlite/future-version.observed.json", new
        {
            Rejected = rejected, UserVersion = 999, Sentinel = "preserve", JournalModeBefore = beforeMode,
            JournalModeAfter = afterMode, DatabaseBytesUnchanged = before.SequenceEqual(after),
            BaselineGap = "The legacy store configures WAL before rejecting the version. Rust must inspect unsupported schemas read-only without this mutation.",
        });
    }

    private static SqliteSyncStateStore NewStore(string database, bool sensitive) =>
        new(database, NullLogger<SqliteSyncStateStore>.Instance, sensitive);

    private static async Task<SqliteConnection> OpenAsync(string path)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = path, Pooling = false, Mode = SqliteOpenMode.ReadWriteCreate,
        }.ToString());
        await connection.OpenAsync();
        return connection;
    }

    private static async Task ExecuteAsync(string path, string sql)
    {
        await using var connection = await OpenAsync(path);
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        await command.ExecuteNonQueryAsync();
    }

    private static async Task<object?> ScalarAsync(string path, string sql)
    {
        await using var connection = await OpenAsync(path);
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        return await command.ExecuteScalarAsync();
    }

    private static async Task<DatabaseSnapshot> ReadSnapshotAsync(string path)
    {
        await using var connection = await OpenAsync(path);
        var schema = new List<SchemaObject>();
        await using (var command = connection.CreateCommand())
        {
            command.CommandText = "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC,name;";
            await using var reader = await command.ExecuteReaderAsync();
            while (await reader.ReadAsync()) schema.Add(new(reader.GetString(0), reader.GetString(1), reader.GetString(2)));
        }
        var tables = new List<TableSnapshot>();
        foreach (var item in schema.Where(item => item.Type == "table"))
        {
            await using var command = connection.CreateCommand();
            command.CommandText = $"SELECT * FROM \"{item.Name.Replace("\"", "\"\"")}\" ORDER BY " +
                (item.Name == "sync_account_status" ? "1" : "1,2,3") + ";";
            await using var reader = await command.ExecuteReaderAsync();
            var columns = Enumerable.Range(0, reader.FieldCount).Select(reader.GetName).ToArray();
            var rows = new List<object?[]>();
            while (await reader.ReadAsync())
                rows.Add(Enumerable.Range(0, reader.FieldCount).Select(index => reader.IsDBNull(index) ? null : reader.GetValue(index)).ToArray());
            tables.Add(new(item.Name, columns, rows));
        }
        return new(Convert.ToInt32(await ScalarAsync(path, "PRAGMA user_version;")), schema, tables);
    }

    private static string ToSql(DatabaseSnapshot snapshot)
    {
        var sql = new StringBuilder("-- Generated synthetic C# compatibility fixture; never an installed profile.\nBEGIN TRANSACTION;\n");
        foreach (var item in snapshot.Schema) sql.Append(item.Sql).Append(";\n");
        foreach (var table in snapshot.Tables)
        foreach (var row in table.Rows)
            sql.Append("INSERT INTO \"").Append(table.Name).Append("\" VALUES (")
                .AppendJoin(',', row.Select(SqlValue)).Append(");\n");
        return sql.Append("PRAGMA user_version = ").Append(snapshot.UserVersion).Append(";\nCOMMIT;\n").ToString();
    }

    private static string SqlValue(object? value) => value switch
    {
        null => "NULL",
        string text => "'" + text.Replace("'", "''") + "'",
        long number => number.ToString(CultureInfo.InvariantCulture),
        _ => throw new InvalidDataException("Unexpected SQLite fixture value type."),
    };

    private static async Task<bool> ThrowsAsync<T>(Func<Task> action) where T : Exception
    {
        try { await action(); return false; }
        catch (T) { return true; }
    }

    private void Check(bool condition, string label)
    {
        if (!condition) throw new InvalidDataException($"Assertion failed: {label}");
        CheckCount++;
    }

    private void Add(string name, string content) => files.Add(name, content.Replace("\r\n", "\n"));
    private void AddJson(string name, object value) => Add(name, JsonSerializer.Serialize(value, Json) + "\n");
    private sealed record SchemaObject(string Type, string Name, string Sql);
    private sealed record TableSnapshot(string Name, string[] Columns, List<object?[]> Rows);
    private sealed record DatabaseSnapshot(int UserVersion, List<SchemaObject> Schema, List<TableSnapshot> Tables);
}
