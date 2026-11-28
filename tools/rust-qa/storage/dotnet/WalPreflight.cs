using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace ImmichFolderWatch.StorageAssessment;

internal static class WalPreflight
{
    internal static List<Observation> Check(string output, JsonElement records)
    {
        var observations = new List<Observation>();
        foreach (var (name, expected) in new[] { ("newer-with-index", 99), ("newer-without-index", 99), ("supported-without-index", 1) })
        {
            var record = records.EnumerateArray().Single(row => row.GetProperty("Case").GetString() == name);
            var source = Path.Combine(output, name);
            if (expected == 99)
            {
                var filenames = name == "newer-with-index"
                    ? new[] { "state.db", "state.db-shm", "state.db-wal" } : new[] { "state.db", "state.db-wal" };
                if (!Directory.GetFiles(source).Select(Path.GetFileName).Order(StringComparer.Ordinal).SequenceEqual(filenames))
                {
                    throw new InvalidDataException($"Unexpected files after refusal in {name}.");
                }
                foreach (var file in filenames)
                {
                    using var stream = File.OpenRead(Path.Combine(source, file));
                    var digest = Convert.ToHexStringLower(SHA256.HashData(stream));
                    if (digest != record.GetProperty("SourceBefore").GetProperty(file).GetString())
                    {
                        throw new InvalidDataException($"Different original bytes in {name}/{file}.");
                    }
                }
            }
            var scratch = Directory.CreateTempSubdirectory("ifw-wal-readback-");
            try
            {
                var main = Path.Combine(scratch.FullName, "state.db");
                File.Copy(Path.Combine(source, "state.db"), main);
                var originalWal = Path.Combine(source, "state.db-wal");
                if (expected == 99 || File.Exists(originalWal))
                {
                    File.Copy(originalWal, main + "-wal");
                }
                using var db = new SqliteConnection(new SqliteConnectionStringBuilder
                {
                    DataSource = main, Mode = SqliteOpenMode.ReadWrite, Pooling = false
                }.ToString());
                db.Open();
                using var query = db.CreateCommand();
                query.CommandText = "PRAGMA user_version;";
                var version = (long)query.ExecuteScalar()!;
                query.CommandText = "SELECT value FROM sample;";
                var value = (long)query.ExecuteScalar()!;
                if (version != expected || value != expected)
                {
                    throw new InvalidDataException($"Recovery of {name} returned version {version} and value {value}.");
                }
                observations.Add(new(name, version, value));
            }
            finally
            {
                scratch.Delete(recursive: true);
            }
        }
        return observations;
    }

    internal sealed record Observation(string Case, long Version, long Value);
}
