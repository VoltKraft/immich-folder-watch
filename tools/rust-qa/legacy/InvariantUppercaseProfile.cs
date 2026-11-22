using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace ImmichFolderWatch.LegacyScalarOracle;

/// <summary>Capture the complete invariant casing used by the calling .NET process.</summary>
internal sealed class InvariantUppercaseProfile
{
    public const string FileName = "invariant-uppercase.tsv";
    private readonly byte[] table;
    public string TableSha256 { get; }
    public int ScannedScalars { get; }
    public int ChangedScalars { get; }

    private InvariantUppercaseProfile(byte[] table, int scanned, int changed)
    {
        this.table = table;
        TableSha256 = Convert.ToHexStringLower(SHA256.HashData(table));
        ScannedScalars = scanned;
        ChangedScalars = changed;
    }

    public object Manifest => new
    {
        tableSha256 = TableSha256, scannedScalars = ScannedScalars, changedScalars = ChangedScalars,
        contextBatchChecked = true
    };

    public static InvariantUppercaseProfile Capture()
    {
        var map = new StringBuilder("IFW-INVARIANT-UPPERCASE-V1\n");
        var changed = 0;
        var scalarCount = 0;
        var batchInput = new StringBuilder();
        var batchExpected = new StringBuilder();
        for (var scalar = 0; scalar <= 0x10ffff; scalar++)
        {
            if (scalar is >= 0xd800 and <= 0xdfff) continue;
            var input = char.ConvertFromUtf32(scalar);
            var upper = input.ToUpperInvariant();
            var runes = upper.EnumerateRunes().ToArray();
            if (runes.Length != 1 || input.Length != upper.Length)
                throw new InvalidDataException("Invariant casing unexpectedly expanded a scalar.");
            if (input != upper)
            {
                map.Append(scalar.ToString("X6", CultureInfo.InvariantCulture)).Append('\t')
                    .Append(runes[0].Value.ToString("X6", CultureInfo.InvariantCulture)).Append('\n');
                changed++;
            }
            batchInput.Append(input);
            batchExpected.Append(upper);
            scalarCount++;
            if (scalarCount % 4096 == 0)
                VerifyContextBatch(batchInput, batchExpected);
        }
        VerifyContextBatch(batchInput, batchExpected);
        return new InvariantUppercaseProfile(Encoding.UTF8.GetBytes(map.ToString()), scalarCount, changed);
    }

    public void Write(string directory) => File.WriteAllBytes(Path.Combine(directory, FileName), table);

    private static void VerifyContextBatch(StringBuilder input, StringBuilder expected)
    {
        if (input.ToString().ToUpperInvariant() != expected.ToString())
            throw new InvalidDataException("Invariant casing depends on scalar context in this runtime.");
        input.Clear();
        expected.Clear();
    }
}
