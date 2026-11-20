using System.ComponentModel;
using ImmichFolderWatch.Core.Services;

if (Environment.GetEnvironmentVariable("IFW_QA_ISOLATED") != "1" || args.Length != 2 ||
    args[0] is not ("read" or "hold") || !(args[1] == "/tmp/producer/source" ||
    args[1].StartsWith("/run/user/0/doc/by-app/org.example.IfwServices/", StringComparison.Ordinal)))
{
    Console.Error.WriteLine("Expected an isolated synthetic portal or backing read");
    return 2;
}

using var root = SecureWatchRoot.Open(args[1]);
try
{
    using var file = root.OpenRead("album/original.jpg");
    using var reader = new StreamReader(file.Stream);
    if (reader.ReadToEnd() != "Synthetic upload fixture\n")
    {
        throw new InvalidDataException("Unexpected fixture contents.");
    }
    Console.WriteLine($"ACQUIRED runtime={Environment.Version}");
    Console.Out.Flush();
    if (args[0] == "hold" && Console.ReadLine() != "release")
    {
        throw new InvalidOperationException("Missing release signal.");
    }
    return 0;
}
catch (IOException error) when (error.InnerException is Win32Exception native)
{
    Console.WriteLine($"REFUSED errno={native.NativeErrorCode} runtime={Environment.Version} operation={error.Message}");
    return 20;
}
