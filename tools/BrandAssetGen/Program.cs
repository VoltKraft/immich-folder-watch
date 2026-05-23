using System.Reflection;
using SkiaSharp;
using Svg.Skia;

const string FlatpakAppId = "io.github.voltkraft.immich-folder-watch";
ReadOnlySpan<int> iconSizes = [16, 24, 32, 48, 64, 128, 256];

var options = Options.Parse(args);
var projectRoot = Path.GetFullPath(options.ProjectRoot ?? Directory.GetCurrentDirectory());
var logoPath = Path.GetFullPath(options.LogoPath ?? Path.Combine(projectRoot, "assets", "branding", "logo.svg"));
var outputRoot = Path.GetFullPath(options.OutputRoot ?? Path.Combine(projectRoot, "artifacts", "branding"));

if (!File.Exists(logoPath))
{
    throw new FileNotFoundException("Brand logo source was not found.", logoPath);
}

Directory.CreateDirectory(outputRoot);

var windowsOutputRoot = Path.Combine(outputRoot, "windows");
var guiOutputRoot = Path.Combine(outputRoot, "gui");
var flatpakOutputRoot = Path.Combine(outputRoot, "flatpak");

Directory.CreateDirectory(windowsOutputRoot);
Directory.CreateDirectory(guiOutputRoot);
Directory.CreateDirectory(flatpakOutputRoot);

using var svg = new SKSvg();
using var picture = svg.Load(logoPath) ?? throw new InvalidOperationException($"Could not load SVG from '{logoPath}'.");

if (picture.CullRect.Width <= 0 || picture.CullRect.Height <= 0)
{
    throw new InvalidOperationException("The SVG logo does not define a usable size.");
}

var iconFrames = new List<(int Size, byte[] Bytes)>(iconSizes.Length);
foreach (var size in iconSizes)
{
    iconFrames.Add((size, RenderPng(picture, size)));
}

WriteIco(Path.Combine(windowsOutputRoot, "app.ico"), iconFrames);
WriteIfChanged(Path.Combine(guiOutputRoot, "header-logo.png"), RenderPng(picture, 160));
WriteIfChanged(Path.Combine(flatpakOutputRoot, $"{FlatpakAppId}.png"), RenderPng(picture, 512));
CopyIfChanged(logoPath, Path.Combine(flatpakOutputRoot, $"{FlatpakAppId}.svg"));

Console.WriteLine($"Generated branding assets at {outputRoot}");

return;

static byte[] RenderPng(SKPicture picture, int size)
{
    var info = new SKImageInfo(size, size, SKColorType.Rgba8888, SKAlphaType.Premul);
    using var surface = SKSurface.Create(info) ?? throw new InvalidOperationException("Could not create a Skia surface.");
    var canvas = surface.Canvas;
    canvas.Clear(SKColors.Transparent);

    var bounds = picture.CullRect;
    var scale = Math.Min(size / bounds.Width, size / bounds.Height);
    var translateX = ((size - (bounds.Width * scale)) / 2f) - (bounds.Left * scale);
    var translateY = ((size - (bounds.Height * scale)) / 2f) - (bounds.Top * scale);

    canvas.Translate(translateX, translateY);
    canvas.Scale(scale);
    canvas.DrawPicture(picture);
    canvas.Flush();

    using var image = surface.Snapshot();
    using var data = image.Encode(SKEncodedImageFormat.Png, 100);
    if (data is null)
    {
        throw new InvalidOperationException($"Could not encode a {size}px PNG.");
    }

    return data.ToArray();
}

static void WriteIco(string outputPath, IReadOnlyList<(int Size, byte[] Bytes)> frames)
{
    using var memory = new MemoryStream();
    using var writer = new BinaryWriter(memory);

    writer.Write((ushort)0);
    writer.Write((ushort)1);
    writer.Write((ushort)frames.Count);

    var imageOffset = 6 + (16 * frames.Count);
    foreach (var (size, bytes) in frames)
    {
        writer.Write((byte)(size >= 256 ? 0 : size));
        writer.Write((byte)(size >= 256 ? 0 : size));
        writer.Write((byte)0);
        writer.Write((byte)0);
        writer.Write((ushort)1);
        writer.Write((ushort)32);
        writer.Write(bytes.Length);
        writer.Write(imageOffset);
        imageOffset += bytes.Length;
    }

    foreach (var (_, bytes) in frames)
    {
        writer.Write(bytes);
    }

    WriteIfChanged(outputPath, memory.ToArray());
}

static void CopyIfChanged(string sourcePath, string destinationPath)
{
    var sourceBytes = File.ReadAllBytes(sourcePath);
    WriteIfChanged(destinationPath, sourceBytes);
}

static void WriteIfChanged(string outputPath, byte[] bytes)
{
    var directory = Path.GetDirectoryName(outputPath);
    if (!string.IsNullOrWhiteSpace(directory))
    {
        Directory.CreateDirectory(directory);
    }

    if (File.Exists(outputPath))
    {
        var existingBytes = File.ReadAllBytes(outputPath);
        if (existingBytes.AsSpan().SequenceEqual(bytes))
        {
            return;
        }
    }

    File.WriteAllBytes(outputPath, bytes);
}

sealed record Options(string? ProjectRoot, string? LogoPath, string? OutputRoot)
{
    public static Options Parse(string[] args)
    {
        string? projectRoot = null;
        string? logoPath = null;
        string? outputRoot = null;

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--help":
                case "-h":
                    PrintUsage();
                    Environment.Exit(0);
                    break;
                case "--project-root":
                    projectRoot = ReadValue(args, ref i, "--project-root");
                    break;
                case "--logo":
                    logoPath = ReadValue(args, ref i, "--logo");
                    break;
                case "--output-root":
                    outputRoot = ReadValue(args, ref i, "--output-root");
                    break;
                default:
                    throw new ArgumentException($"Unknown argument '{args[i]}'.");
            }
        }

        return new Options(projectRoot, logoPath, outputRoot);
    }

    private static string ReadValue(string[] args, ref int index, string argumentName)
    {
        index++;
        if (index >= args.Length)
        {
            throw new ArgumentException($"Missing value for '{argumentName}'.");
        }

        return args[index];
    }

    private static void PrintUsage()
    {
        var executableName = Path.GetFileNameWithoutExtension(Environment.ProcessPath) ?? Assembly.GetExecutingAssembly().GetName().Name ?? "BrandAssetGen";
        Console.WriteLine($"Usage: {executableName} [--project-root <path>] [--logo <path>] [--output-root <path>]");
    }
}
