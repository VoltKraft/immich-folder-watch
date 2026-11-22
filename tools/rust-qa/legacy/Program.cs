using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ImmichFolderWatch.LegacyScalarOracle;

/// <summary>Development-only scalar reference. Never loads an app profile or media.</summary>
internal static class Program
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };

    private static int Main(string[] args)
    {
        if (args.Length != 2 || args[0] != "export")
        {
            Console.Error.WriteLine("Usage: LegacyScalarOracle export <isolated-output-directory>");
            return 2;
        }
        var expected = Environment.GetEnvironmentVariable("IFW_ORACLE_EXPECT_ARCH");
        if (expected is not null &&
            (expected is not ("x64" or "arm64") ||
             !RuntimeInformation.ProcessArchitecture.ToString().Equals(expected, StringComparison.OrdinalIgnoreCase) ||
             !RuntimeInformation.OSArchitecture.ToString().Equals(expected, StringComparison.OrdinalIgnoreCase)))
        {
            Console.Error.WriteLine("Native scalar-oracle architecture assertion failed.");
            return 2;
        }
        var output = Path.GetFullPath(args[1]);
        Directory.CreateDirectory(output);
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(output, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);

        var casing = InvariantUppercaseProfile.Capture();
        casing.Write(output);

        var ticks = new SortedSet<long> { 0, 1, 9_999_999, 10_000_000, DateTime.MaxValue.Ticks,
            DateTime.UnixEpoch.Ticks - 1, DateTime.UnixEpoch.Ticks, DateTime.UnixEpoch.Ticks + 1 };
        foreach (var year in new[] { 1, 4, 100, 400, 1600, 1900, 1969, 1970, 2000, 2024, 9999 })
        for (var month = 1; month <= 12; month++)
        foreach (var day in new[] { 1, DateTime.DaysInMonth(year, month) })
        {
            var date = new DateTime(year, month, day, 23, 59, 59, DateTimeKind.Utc);
            foreach (var fraction in new[] { 0L, 1L, 1_200_000L, 1_234_567L, 9_999_999L })
                ticks.Add(date.Ticks + fraction);
        }
        var platform = OperatingSystem.IsWindows() ? "windows" : "linux";
        var legacyDirectory = Path.Combine(Environment.CurrentDirectory, "rust", "tests", "fixtures", "legacy", platform, "sqlite");
        foreach (var name in new[] { "sensitive.expected.json", "insensitive.expected.json", "sensitive.wal-backup.json" })
        {
            using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(legacyDirectory, name)));
            CollectTimestampTicks(document.RootElement, ticks);
        }
        var timestamps = ticks.Select(value =>
        {
            var time = new DateTimeOffset(value, TimeSpan.Zero);
            return new
            {
                UtcTicks = value,
                Sql = time.ToString("O", CultureInfo.InvariantCulture),
                JsonScalar = JsonSerializer.Deserialize<string>(JsonSerializer.Serialize(time)),
                UnixSeconds = time.ToUnixTimeSeconds(),
                SubsecondNanoseconds = (value % TimeSpan.TicksPerSecond) * 100,
            };
        }).ToArray();
        WriteJson(output, "timestamps.json", timestamps);
        var strings = new[] { "straße", "iıİI", "σςΣ", "é", "e\u0301", "日本語", "𐐨", "ﬃ",
            "\ud800a\udc00", "\ud800", "\udc00", "a\ud800\ud801\udc28z" };
        WriteJson(output, "utf16-vectors.json", strings.Select(value => new
        {
            Input = ToUtf16Hex(value), Output = ToUtf16Hex(value.ToUpperInvariant()),
        }));
        var payloads = new[] { "invariant-uppercase.tsv", "timestamps.json", "utf16-vectors.json" };
        WriteJson(output, "manifest.json", new
        {
            Format = "ifw-rw02-scalar-reference-v1",
            Runtime = Environment.Version.ToString(),
            CoreLibBuild = typeof(string).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
            CoreLibSha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(typeof(string).Assembly.Location))),
            OracleAssemblySha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(typeof(Program).Assembly.Location))),
            GlobalizationInvariantRequested = Environment.GetEnvironmentVariable("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT") == "1",
            ProcessArchitecture = RuntimeInformation.ProcessArchitecture.ToString(),
            OSArchitecture = RuntimeInformation.OSArchitecture.ToString(),
            OS = OperatingSystem.IsWindows() ? "windows" : "linux",
            InvariantSortVersion = CultureInfo.InvariantCulture.CompareInfo.Version.FullVersion,
            ScannedScalars = casing.ScannedScalars, ChangedScalars = casing.ChangedScalars,
            ContextBatchEquivalenceChecked = true,
            TimestampVectors = timestamps.Length,
            Payloads = payloads.ToDictionary(name => name, name =>
                Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(Path.Combine(output, name))))),
            Scope = "Observed .NET output only; no shipping table or cross-platform equivalence certification.",
            GeneratorSources = new[] { "tools/rust-qa/legacy/Program.cs", "tools/rust-qa/legacy/InvariantUppercaseProfile.cs",
                    "tools/rust-qa/legacy/LegacyScalarOracle.csproj" }
                .ToDictionary(name => name, name => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(name)))),
        });
        Console.WriteLine($"Scalar reference exported: {casing.ScannedScalars} Unicode scalars, {casing.ChangedScalars} changed mappings, " +
            $"{timestamps.Length} timestamps; .NET {Environment.Version}, process {RuntimeInformation.ProcessArchitecture}, OS {RuntimeInformation.OSArchitecture}.");
        return 0;
    }

    private static void CollectTimestampTicks(JsonElement element, SortedSet<long> ticks)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in element.EnumerateObject()) CollectTimestampTicks(property.Value, ticks);
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var value in element.EnumerateArray()) CollectTimestampTicks(value, ticks);
        }
        else if (element.ValueKind == JsonValueKind.String)
        {
            var text = element.GetString()!;
            if (DateTimeOffset.TryParseExact(text, "O", CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var timestamp))
                ticks.Add(timestamp.UtcTicks);
            else if (text.StartsWith("{\"OriginalEntry\":", StringComparison.Ordinal))
            {
                using var nested = JsonDocument.Parse(text);
                CollectTimestampTicks(nested.RootElement, ticks);
            }
        }
    }

    private static string ToUtf16Hex(string value) =>
        string.Concat(value.Select(unit => ((int)unit).ToString("X4", CultureInfo.InvariantCulture)));

    private static void WriteJson(string directory, string name, object value) =>
        Write(directory, name, JsonSerializer.Serialize(value, Json) + "\n");

    private static void Write(string directory, string name, string value) =>
        File.WriteAllText(Path.Combine(directory, name), value, new UTF8Encoding(false));
}
