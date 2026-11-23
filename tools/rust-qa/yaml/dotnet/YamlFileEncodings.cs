using System.Text;

namespace ImmichFolderWatch.YamlAssessment;

internal static class YamlFileEncodings
{
    internal sealed record Sample(string Name, byte[] Bytes, int CodePage, bool HasDecodingErrors = false);

    private const string Source = "watch:\n  sources:\n    - path: media\n      albumName: ";
    private const string Album = "Grüße 日本語 😀 e\u0301 \uFFFD\n";

    internal static IEnumerable<Sample> Samples()
    {
        var plainUtf8 = new UTF8Encoding(false);
        var utf8 = new UTF8Encoding(true);
        var utf16Le = new UnicodeEncoding(false, true);
        var utf16Be = new UnicodeEncoding(true, true);
        var utf32Le = new UTF32Encoding(false, true);
        var utf32Be = new UTF32Encoding(true, true);

        foreach (var (name, encoding) in new (string, Encoding)[]
        {
            ("utf8", plainUtf8), ("utf8-bom", utf8), ("utf16le", utf16Le),
            ("utf16be", utf16Be), ("utf32le", utf32Le), ("utf32be", utf32Be),
        })
        {
            yield return new Sample("encoding-" + name, Encode(encoding, Source + Album), encoding.CodePage);
        }

        // Keep the invalid units inside an ordinary album value so that the shipping loader observes them.
        yield return Damaged("utf8-short", plainUtf8, [0xe2, 0x82]);
        yield return Damaged("utf8-continuation", utf8, [0x80]);
        yield return Damaged("utf16le-high", utf16Le, [0x00, 0xd8]);
        yield return Damaged("utf16be-low", utf16Be, [0xdc, 0x00]);
        yield return Damaged("utf16le-odd", utf16Le, [0x61]);
        yield return Damaged("utf16be-high-odd", utf16Be, [0xd8, 0x00, 0x61]);
        yield return Damaged("utf32le-invalid", utf32Le, [0x00, 0x00, 0x11, 0x00]);
        yield return Damaged("utf32be-surrogate", utf32Be, [0x00, 0x00, 0xd8, 0x00]);
        yield return Damaged("utf32le-short", utf32Le, [0x61, 0x00, 0x00]);
        yield return Damaged("utf32be-short", utf32Be, [0x00, 0x00]);
    }

    private static byte[] Encode(Encoding encoding, string text) =>
        [.. encoding.GetPreamble(), .. encoding.GetBytes(text)];

    private static Sample Damaged(string name, Encoding encoding, byte[] suffix) =>
        new("encoding-" + name, [.. Encode(encoding, Source + "Archive"), .. suffix], encoding.CodePage, true);

    internal static (string Text, int CodePage, bool HadDecodingErrors) Observe(string path, byte[] source)
    {
        using var reader = new StreamReader(path, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        var text = reader.ReadToEnd();
        if (text != File.ReadAllText(path))
            throw new InvalidDataException("StreamReader and the shipping file reader decoded different text.");
        var codePage = reader.CurrentEncoding.CodePage;
        var strict = Encoding.GetEncoding(codePage, EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback);
        try
        {
            strict.GetCharCount(source);
            return (text, codePage, false);
        }
        catch (DecoderFallbackException)
        {
            return (text, codePage, true);
        }
    }
}
