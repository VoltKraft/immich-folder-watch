using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.YamlAssessment;

internal static class Program
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true };
    private const string ChangedAlbum = "Rust – Grüße 日本語 😀: # null";

    private static void Main(string[] args)
    {
        var expectedArchitecture = Environment.GetEnvironmentVariable("IFW_ORACLE_EXPECT_ARCH");
        if (expectedArchitecture is not ("x64" or "arm64") ||
            !RuntimeInformation.ProcessArchitecture.ToString().Equals(expectedArchitecture, StringComparison.OrdinalIgnoreCase) ||
            !RuntimeInformation.OSArchitecture.ToString().Equals(expectedArchitecture, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("The oracle requires the requested native process and OS architecture.");
        }
        if (args.Length != 3 || args[0] is not ("export" or "verify"))
        {
            throw new ArgumentException("Usage: YamlOracle export <reviewed-corpus> <new-output> | verify <reference> <Rust-output>");
        }
        if (args[0] == "export")
        {
            Export(Path.GetFullPath(args[1]), Isolated(args[2]));
        }
        else
        {
            Verify(Isolated(args[1]), Isolated(args[2]));
        }
    }

    private static string Isolated(string value)
    {
        var path = Path.GetFullPath(value);
        var scope = Path.GetFullPath("artifacts/rust/yaml-assessment") + Path.DirectorySeparatorChar;
        if (!path.StartsWith(scope, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new ArgumentException("Only synthetic YAML assessment artifacts are allowed.");
        }
        return path;
    }

    private static void Export(string fixtures, string output)
    {
        var native = OperatingSystem.IsWindows() ? "windows" : "linux";
        var expectedFixtures = Path.GetFullPath(Path.Combine("rust", "tests", "fixtures", "legacy", native));
        if (!fixtures.Equals(expectedFixtures, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
            throw new ArgumentException("Only the reviewed native synthetic corpus is allowed.");
        if (Directory.Exists(output)) throw new IOException("Refusing an existing output directory.");
        Directory.CreateDirectory(output);
        var profile = Path.Combine(output, "profile");
        Directory.CreateDirectory(profile);
        var cases = new SortedDictionary<string, byte[]>(StringComparer.Ordinal);
        foreach (var file in Directory.GetFiles(Path.Combine(fixtures, "config"), "*.yaml"))
        {
            cases.Add(Path.GetFileNameWithoutExtension(file), File.ReadAllBytes(file));
        }
        var additional = new Dictionary<string, string>
        {
            ["duplicate-field"] = "retry:\n  maxAttempts: 1\n  maxAttempts: 9\n",
            ["duplicate-section"] = "retry: {maxAttempts: 1, baseDelayMilliseconds: 7}\nretry: {maxAttempts: 9}\n",
            ["duplicate-invalid-first"] = "retry:\n  maxAttempts: wrong\n  maxAttempts: 5\n",
            ["duplicate-invalid-last"] = "retry: {maxAttempts: 5, maxAttempts: wrong}\n",
            ["duplicate-invalid-section"] = "retry: wrong\nretry: {maxAttempts: 5}\n",
            ["duplicate-invalid-nested"] = "watch:\n  sources: [{path: Pictures, includeSubdirectories: wrong}]\n  sources: [{path: Photos}]\n",
            ["duplicate-nested-and-skipped"] = "watch:\n  sources:\n  - path: Pictures\n    extensions: [png]\n    extensions: [jpg]\n    future: {includeSubdirectories: wrong}\n    future: [one, two]\nretry: {maxAttempts: 5, maxAttempts: null}\n",
            ["merge-key"] = "base: &base {path: from-merge, albumName: merge}\nwatch:\n  sources:\n    - <<: *base\n      albumName: explicit\n",
            ["unknown-keys"] = "future: {nested: [one, two]}\nwatch:\n  sources: [{path: media, future: {nested: [a, b]}}]\n",
            ["null-values"] = "immich: {apiKey: null, serverApiUrl: null}\nlogging: {level: null, target: null, logDirectory: null}\nlocalization: {language: null}\nwatch: {sources: [null, {path: null, albumName: null, extensions: [null, jpg, ' ']}], extensions: null}\n",
            ["unicode-filters"] = "watch:\n  extensions: [JPG, .jpg, İMG, img, Straße, STRASSE, Σ, σ, ς]\n  sources:\n    - path: 'Média/日本語/😀'\n      excludeDirectories: [' Straße ', STRASSE, σ, ς, Σ, ı, I, i, İ]\n      excludeFileNames: ['Ä.TMP', 'ä.tmp', 'ſ', S, 'K', K]\nlocalization: {language: ' DE '}\n",
            ["unicode-trim"] = "immich: {apiKey: '\u00a0synthetic\u2003'}\nwatch: {sources: [{path: '\u2003 Fotos \u00a0', albumName: '\u2003Gruß\u00a0'}]}\n",
            ["boolean-legacy"] = "immich: {allowInsecureHttp: yes}\nwatch: {sources: [{includeSubdirectories: ON, deleteAfterUpload: off}]}\n",
            ["plain-string-scalars"] = "immich: {apiKey: 123, serverApiUrl: true}\nwatch: {sources: [{path: 001, albumName: false, extensions: [123, true]}]}\n",
            ["scalar-null-versus-quoted"] = "watch: {sources: [{path: '', albumName: null}, {path: '.', albumName: 'null'}]}\n",
            ["integer-extremes"] = "retry: {maxAttempts: -2147483648, baseDelayMilliseconds: 2147483647}\nwatch: {batchIntervalSeconds: 0, maxBatchSize: -1}\n",
            ["integer-overflow"] = "retry: {maxAttempts: 2147483648}\n",
            ["null-nonnullable"] = "immich: {allowInsecureHttp: null}\nretry: {maxAttempts: null, baseDelayMilliseconds: null}\nwatch: {batchIntervalSeconds: null, maxBatchSize: null, fileReadyTimeoutSeconds: null}\n",
            ["integer-spellings"] = "retry: {maxAttempts: 010, baseDelayMilliseconds: 0x20}\nwatch: {maxBatchSize: +7}\n",
            ["integer-underscore"] = "retry: {maxAttempts: 1_000}\n",
            ["integer-quoted"] = "retry: {maxAttempts: '009', baseDelayMilliseconds: '+10'}\n",
            ["legacy-intervals"] = "watch: {batchIntervalSeconds: 1:30, fileReadyTimeoutSeconds: '1:05', sources: [{albumName: 12:30}]}\nretry: {baseDelayMilliseconds: 1:00:05}\n",
            ["legacy-interval-invalid"] = "watch: {batchIntervalSeconds: 1:60}\n",
            ["legacy-tagged-string"] = "watch: {maxBatchSize: !!str '010', sources: [{includeSubdirectories: !!str true}]}\n",
            ["legacy-tagged-interval-string"] = "watch: {batchIntervalSeconds: !!str '1:30'}\n",
            ["boolean-padded"] = "watch: {sources: [{includeSubdirectories: ' yes '}]}\n",
            ["boolean-tagged-legacy-word"] = "watch: {sources: [{deleteAfterUpload: !!str 'no'}]}\n",
            ["typed-tag-properties"] = "watch: {batchIntervalSeconds: !!int 1:30, fileReadyTimeoutSeconds: !!float 9.0, sources: [{albumName: !!int 90}, {albumName: !!bool true}]}\n",
            ["typed-tag-rounding"] = "watch: {batchIntervalSeconds: !!float 9.5, fileReadyTimeoutSeconds: !!float 10.5, sources: [{albumName: !!float 1.25e-6}]}\n",
            ["typed-tag-alias"] = "watch:\n  batchIntervalSeconds: &duration !!int '1:30'\n  sources:\n  - albumName: *duration\n    includeSubdirectories: &enabled !!bool yes\n    excludeFileNames: [*enabled, 001]\n",
            ["typed-tag-text-alias-to-boolean"] = "watch:\n  sources:\n  - albumName: &name !!int 1:30\n    includeSubdirectories: *name\n",
            ["typed-tag-unicode-lines"] = "watch:\u2028  batchIntervalSeconds: !!int 1:30\u2028  sources: [{albumName: true}]\n",
            ["typed-tag-padded-boolean"] = "watch: {sources: [{includeSubdirectories: !!bool ' yes '}]}\n",
            ["typed-integer-octal-prefix"] = "watch: {batchIntervalSeconds: 0o25}\n",
            ["typed-scalar-control"] = "watch: {batchIntervalSeconds: 021, sources: [{albumName: 001, includeSubdirectories: yes}]}\n",
            ["boolean-invalid"] = "immich: {allowInsecureHttp: maybe}\n",
            ["unknown-alias"] = "watch: {sources: [*missing]}\n",
            ["anchor-shadow"] = "watch:\n  sources:\n  - path: &a Pictures\n    extra: &a Ghost\n    albumName: *a\n",
            ["anchor-skipped-only"] = "extra: {items: [{albumName: &a Ghost}]}\nwatch: {sources: [{albumName: *a}]}\n",
            ["anchor-on-key"] = "watch:\n  sources:\n  - &a path: Pictures\n    albumName: *a\n",
            ["alias-as-key"] = "watch:\n  sources:\n  - path: &key albumName\n    *key : Normal\n",
            ["alias-in-skipped-map"] = "watch:\n  sources:\n  - path: &a Pictures\n    extra: &a {*missing : *alsoMissing}\n    albumName: *a\n",
            ["anchor-known-reassigned"] = "watch:\n  sources:\n  - path: &a Pictures\n    albumName: *a\n    path: &a Neu\n    excludeDirectories: [*a]\n",
            ["anchor-separator-shadow"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: &a >-\n      Foto\u2028      Nord\n    extra: &a {child: *missing}\n    excludeDirectories: [*a]\n",
            ["flow-anchor-followed"] = "logging: {logDirectory: &dir logs, level: Information}\n",
            ["flow-anchor-tagged-followed"] = "logging: {logDirectory: !!str &dir 'logs', # next key\n level: Information}\n",
            ["flow-anchor-quoted-empty"] = "extra: {nested: {child: &a \"\", next: value}}\n",
            ["flow-anchor-final"] = "logging: {level: Information, logDirectory: &dir !!str logs,}\n",
            ["flow-anchor-implicit-empty"] = "extra: {child: &a , next: value}\n",
            ["flow-anchor-in-sequence"] = "watch: {extensions: &list [&a .jpg, .png], sources: [{path: Pictures, extensions: *list}]}\n",
            ["flow-anchor-on-key"] = "logging: {&key level: Information, logDirectory: !!str logs}\n",
            ["flow-anchor-implicit-pair"] = "extra: [child: &a value, next: other]\n",
            ["explicit-strings"] = "watch: {sources: [{path: !!str 001, albumName: !!str true}]}\n",
            ["include-tag"] = "immich: {apiKey: !include synthetic-never-read.yaml}\n",
            ["properties-literal"] = "immich: {apiKey: '${IFW_SYNTHETIC_NEVER_EXPAND}'}\n",
            ["multiple-documents"] = "{}\n---\nretry: {maxAttempts: 9}\n",
            ["empty-document"] = "\n",
            ["null-document"] = "null\n",
            ["nonmapping-document"] = "[a, b]\n",
            ["multiline"] = "immich:\n  apiKey: |\n    synthetic-first\n    synthetic-second\nlogging: {logDirectory: 'logs/../logs'}\n",
            ["trailing-path-separator"] = "watch: {sources: [{path: 'media/'}]}\nlogging: {logDirectory: 'logs/'}\n",
            ["unknown-property-casing"] = "Immich: {apiKey: ignored}\nimmich: {ApiKey: ignored-too}\n",
            ["format-mark-in-key"] = "retry:\n  maxAttempts: 7\n  \uFEFFmaxAttempts: 11\n",
            ["separator-folding"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: |-\n      A\n      \u2028      B\n",
            ["separator-alias"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: &name >2-\n      Foto\u2028        Nord\n  - path: More\n    albumName: *name\n",
            ["separator-escaped"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: \"Foto\\L      Nord\"\n",
            ["separator-controls"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: \"A\\x7fB\\x86C\u2028      Nord\"\n",
            ["separator-new-key"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: Foto\u2028    extra: one\n",
            ["separator-underindent"] = "watch:\n  sources:\n  - path: Pictures\n    albumName: >-\n      Foto\u2028    Nord\n",
        };
        foreach (var entry in additional) cases.Add(entry.Key, Encoding.UTF8.GetBytes(entry.Value));
        var encodingSamples = YamlFileEncodings.Samples().Concat(SavedFolderLists()).Concat(SavedUnicodeProfiles())
            .ToDictionary(sample => sample.Name, StringComparer.Ordinal);
        foreach (var sample in encodingSamples.Values) cases.Add(sample.Name, sample.Bytes);
        var loader = new AppConfigLoader();
        var rows = new List<object>();
        var corpusAssertions = 0;
        foreach (var (name, sourceBytes) in cases)
        {
            var path = Path.Combine(profile, name + ".yaml");
            File.WriteAllBytes(path, sourceBytes);
            var (yaml, sourceCodePage, sourceHadDecodingErrors) = YamlFileEncodings.Observe(path, sourceBytes);
            var sourceSha256 = Convert.ToHexStringLower(SHA256.HashData(sourceBytes));
            if (encodingSamples.TryGetValue(name, out var sample) &&
                (sample.CodePage != sourceCodePage || sample.HasDecodingErrors != sourceHadDecodingErrors))
                throw new InvalidDataException($"Unexpected native decoder selection or fallback: {name}.");
            try
            {
                var editable = loader.LoadForEditing(path);
                var runtime = loader.Load(path);
                if (name.EndsWith(".input", StringComparison.Ordinal))
                {
                    var expected = JsonNode.Parse(File.ReadAllText(Path.Combine(fixtures, "config", name.Replace(".input", ".expected", StringComparison.Ordinal) + ".json")))!;
                    if (!JsonNode.DeepEquals(JsonSerializer.SerializeToNode(editable), expected["Editable"]))
                        throw new InvalidOperationException("The accepted editable corpus changed.");
                    var tokenized = JsonNode.Parse(JsonSerializer.Serialize(runtime))!;
                    foreach (var source in tokenized["Watch"]!["Sources"]!.AsArray()) Tokenize(source!, "Path", profile);
                    Tokenize(tokenized["Logging"]!, "LogDirectory", profile);
                    if (!JsonNode.DeepEquals(tokenized, expected["Runtime"]))
                        throw new InvalidOperationException("The accepted native runtime corpus changed.");
                    corpusAssertions += 2;
                }
                rows.Add(new { Name = name, Yaml = yaml, SourceCodePage = sourceCodePage, SourceHadDecodingErrors = sourceHadDecodingErrors,
                    SourceSha256 = sourceSha256, Accepted = true, Editable = editable, Runtime = runtime,
                    Written = new AppConfigWriter().Serialize(editable) });
            }
            catch (Exception exception) when (exception is not InvalidOperationException || !exception.Message.StartsWith("The accepted", StringComparison.Ordinal))
            {
                if (name.EndsWith(".input", StringComparison.Ordinal) || name.EndsWith(".written", StringComparison.Ordinal)
                    || encodingSamples.ContainsKey(name)) throw;
                rows.Add(new { Name = name, Yaml = yaml, SourceCodePage = sourceCodePage, SourceHadDecodingErrors = sourceHadDecodingErrors,
                    SourceSha256 = sourceSha256, Accepted = false, ErrorType = exception.GetType().FullName });
            }
        }
        var casing = ExportCasing();
        Write(Path.Combine(output, "casing.json"), casing);
        Write(Path.Combine(output, "reference.json"), new
        {
            Format = "ifw-rw02-yaml-reference-v2", Platform = OperatingSystem.IsWindows() ? "windows" : "linux",
            Architecture = RuntimeInformation.ProcessArchitecture.ToString(), OSArchitecture = RuntimeInformation.OSArchitecture.ToString(),
            Runtime = Environment.Version.ToString(), Profile = profile, CorpusAssertions = corpusAssertions,
            CasingSha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(Path.Combine(output, "casing.json")))), Cases = rows
        });
        Console.WriteLine($"C# YAML reference exported: {rows.Count} cases, {corpusAssertions} accepted-corpus assertions, all Unicode scalars.");
    }

    private static IEnumerable<YamlFileEncodings.Sample> SavedUnicodeProfiles()
    {
        var config = new AppConfig
        {
            Immich = new ImmichSettings { ServerApiUrl = "https://example.invalid/api", ApiKey = "synthetic-example" },
        };
        config.Watch.Sources.Add(new WatchSourceSettings { Path = "Pictures", AlbumName = "\uFEFFFoto", Extensions = [".jpg"] });
        var writer = new AppConfigWriter();
        var saved = writer.Serialize(config);
        var encoding = new UTF8Encoding(true);
        yield return new("saved-album-format-mark", [.. encoding.GetPreamble(), .. encoding.GetBytes(saved)], encoding.CodePage);
        foreach (var (name, separator) in new[] { ("line", "\u2028"), ("paragraph", "\u2029") })
        {
            var source = config.Watch.Sources[0];
            source.Path = "Pictures" + separator + "Nord";
            source.AlbumName = "Foto" + separator + "Nord";
            source.ExcludeFileNames = ["Cover" + separator + "Nord.jpg"];
            yield return new($"saved-{name}-separator", Encoding.UTF8.GetBytes(writer.Serialize(config)), Encoding.UTF8.CodePage);
        }
    }

    private static IEnumerable<YamlFileEncodings.Sample> SavedFolderLists()
    {
        foreach (var count in new[] { 100, 300 })
        {
            var config = new AppConfig
            {
                Immich = new ImmichSettings { ServerApiUrl = "https://example.invalid/api", ApiKey = "synthetic-demo" },
            };
            for (var i = 1; i <= count; i++)
            {
                config.Watch.Sources.Add(new WatchSourceSettings
                {
                    Path = $"Albums/Archive-{i:D3}",
                    AlbumName = $"Archiv {i:D3} – 日本語",
                    IncludeSubdirectories = i % 2 == 0,
                    Extensions = [".jpg", ".jpeg", ".png"],
                    ExcludeDirectories = ["Thumbnails"],
                    ExcludeFileNames = ["cover.png"],
                    SyncMode = i % 3 == 0 ? WatchSourceSyncModes.Sync : WatchSourceSyncModes.UploadAll,
                });
            }
            var saved = new AppConfigWriter().Serialize(config);
            yield return new($"folders-{count}-utf8", Encoding.UTF8.GetBytes(saved), Encoding.UTF8.CodePage);
            if (count == 300)
                yield return new("folders-300-utf32", [.. Encoding.UTF32.GetPreamble(), .. Encoding.UTF32.GetBytes(saved)], Encoding.UTF32.CodePage);
        }
    }

    private static void Tokenize(JsonNode value, string property, string profile)
    {
        var path = value[property]!.GetValue<string>();
        if (path.StartsWith(profile + Path.DirectorySeparatorChar, StringComparison.Ordinal)) value[property] = "$PROFILE" + path[profile.Length..];
    }

    private static object ExportCasing()
    {
        var classes = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var lower = new List<int[]>();
        var ordinal = new List<int[]>();
        var whitespace = new List<int>();
        var count = 0;
        var batches = 0;
        var originalBatch = new StringBuilder();
        var lowerBatch = new StringBuilder();
        var ordinalBatch = new StringBuilder();
        for (var scalar = 0; scalar <= 0x10ffff; scalar++)
        {
            if (!Rune.IsValid(scalar)) continue;
            var original = char.ConvertFromUtf32(scalar);
            var lowered = original.ToLowerInvariant();
            var loweredScalar = Rune.GetRuneAt(lowered, 0);
            if (loweredScalar.Utf16SequenceLength != lowered.Length) throw new InvalidOperationException("Unexpected expanding lowercase.");
            if (lowered != original) lower.Add(new[] { scalar, loweredScalar.Value });
            if (!classes.TryGetValue(original, out var representative)) classes.Add(original, representative = scalar);
            if (representative != scalar) ordinal.Add(new[] { scalar, representative });
            if (original.Trim().Length == 0) whitespace.Add(scalar);
            originalBatch.Append(original);
            lowerBatch.Append(lowered);
            ordinalBatch.Append(char.ConvertFromUtf32(representative));
            count++;
            if (count % 4096 == 0 || scalar == 0x10ffff)
            {
                if (originalBatch.ToString().ToLowerInvariant() != lowerBatch.ToString() ||
                    !StringComparer.OrdinalIgnoreCase.Equals(originalBatch.ToString(), ordinalBatch.ToString()))
                    throw new InvalidOperationException("Context-dependent string behavior in generated casing.");
                batches++;
                originalBatch.Clear(); lowerBatch.Clear(); ordinalBatch.Clear();
            }
        }
        return new { Format = "ifw-rw02-yaml-casing-v1", Scalars = count, ContextBatches = batches,
            Lower = lower, Ordinal = ordinal, Whitespace = whitespace };
    }

    private static void Verify(string referenceDirectory, string output)
    {
        var reference = JsonNode.Parse(File.ReadAllText(Path.Combine(referenceDirectory, "reference.json")))!;
        var format = reference["format"]!.GetValue<string>();
        if (format is not ("ifw-rw02-yaml-reference-v1" or "ifw-rw02-yaml-reference-v2"))
            throw new InvalidDataException("Unknown synthetic reference format.");
        if (reference["platform"]!.GetValue<string>() != (OperatingSystem.IsWindows() ? "windows" : "linux") ||
            reference["architecture"]!.GetValue<string>() != RuntimeInformation.ProcessArchitecture.ToString() ||
            reference["osArchitecture"]!.GetValue<string>() != RuntimeInformation.OSArchitecture.ToString())
            throw new InvalidDataException("The reference requires its original native platform and architecture.");
        var verifyBytes = format == "ifw-rw02-yaml-reference-v2";
        var originals = verifyBytes ? YamlFiles(Path.Combine(referenceDirectory, "profile")) : null;
        var rustFiles = YamlFiles(output);
        var loader = new AppConfigLoader();
        var assertions = 0;
        var preservedInputs = 0;
        var readOnlyInputs = 0;
        foreach (var row in reference["cases"]!.AsArray())
        {
            var name = row!["name"]!.GetValue<string>();
            if (name.Length == 0 || name.Any(c => !char.IsAsciiLetterOrDigit(c) && c is not ('-' or '.')))
                throw new InvalidDataException("Invalid synthetic case name.");
            if (verifyBytes)
            {
                var bytes = File.ReadAllBytes(originals![name + ".yaml"]);
                if (Convert.ToHexStringLower(SHA256.HashData(bytes)) != row["sourceSha256"]!.GetValue<string>())
                    throw new InvalidDataException($"Original YAML bytes changed: {name}.");
                preservedInputs++;
                if (row["sourceHadDecodingErrors"]!.GetValue<bool>())
                {
                    if (rustFiles.ContainsKey(name + ".roundtrip.yaml") || rustFiles.ContainsKey(name + ".changed.yaml"))
                        throw new InvalidDataException($"A rewritten YAML exists for a lossy decode: {name}.");
                    readOnlyInputs++;
                    continue;
                }
            }
            if (!row["accepted"]!.GetValue<bool>()) continue;
            foreach (var mutation in new[] { false, true })
            {
                var expected = row["editable"]!.Deserialize<AppConfig>(Json)!;
                if (mutation)
                {
                    expected.Localization.Language = "de";
                    expected.Retry.MaxAttempts = 9;
                    expected.Watch.Sources.Add(new WatchSourceSettings { Path = "Neu/../Fotos 日本語", AlbumName = ChangedAlbum,
                        Extensions = new List<string> { ".heic" }, IncludeSubdirectories = true, SyncMode = "sync" });
                }
                var path = rustFiles[name + (mutation ? ".changed" : ".roundtrip") + ".yaml"];
                if (!JsonNode.DeepEquals(JsonSerializer.SerializeToNode(expected, Json), JsonSerializer.SerializeToNode(loader.LoadForEditing(path), Json)))
                    throw new InvalidOperationException($"Rust YAML editable readback differs: {name} ({mutation}).");
                assertions++;
                if (!JsonNode.DeepEquals(JsonSerializer.SerializeToNode(AppConfigLoader.NormalizeForRuntime(expected, output), Json),
                    JsonSerializer.SerializeToNode(loader.Load(path), Json)))
                    throw new InvalidOperationException($"Rust YAML runtime readback differs: {name} ({mutation}).");
                assertions++;
            }
        }
        var readback = JsonSerializer.SerializeToNode(new { Format = verifyBytes ? "ifw-rw02-yaml-readback-v2" : "ifw-rw02-yaml-readback-v1",
            Assertions = assertions, Runtime = Environment.Version.ToString(), Architecture = RuntimeInformation.ProcessArchitecture.ToString(),
            OSArchitecture = RuntimeInformation.OSArchitecture.ToString() }, Json)!.AsObject();
        if (verifyBytes)
        {
            readback["preservedInputs"] = preservedInputs;
            readback["readOnlyInputs"] = readOnlyInputs;
        }
        Write(Path.Combine(output, "csharp-readback.json"), readback);
        Console.WriteLine($"C# YAML readback passed: {assertions} editable/runtime assertions on original and changed Rust YAML.");
    }

    private static Dictionary<string, string> YamlFiles(string directory) =>
        Directory.EnumerateFiles(directory, "*.yaml").ToDictionary(path => Path.GetFileName(path), StringComparer.Ordinal);

    private static void Write(string path, object value) => File.WriteAllText(path, JsonSerializer.Serialize(value, Json) + "\n", new UTF8Encoding(false));
}
