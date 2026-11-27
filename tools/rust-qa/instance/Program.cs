using System.Runtime.InteropServices;
#if IFW_WINDOWS
using System.Security.Principal;
using ImmichFolderWatch.App.Services;
[assembly: System.Runtime.Versioning.SupportedOSPlatform("windows")]
#else
using ImmichFolderWatch.App.Linux.Platform;
#endif

if (args.Length != 3 || !Path.IsPathFullyQualified(args[1]) ||
    File.ReadAllText(Path.Combine(args[1], ".ifw-instance-fixture")) != "synthetic-only\n" ||
    RuntimeInformation.ProcessArchitecture != RuntimeInformation.OSArchitecture ||
    !string.Equals(RuntimeInformation.ProcessArchitecture.ToString(), args[2], StringComparison.OrdinalIgnoreCase))
{
    throw new InvalidOperationException("A marked synthetic profile and the native architecture are required.");
}
#if IFW_WINDOWS
// The shipping implementation derives its names from the real SID. Only a disposable runner may use them.
bool isolatedIdentity = args[0] == "identity" && Environment.GetEnvironmentVariable("IFW_QA_EXISTING_SESSION") == "1";
bool hosted = Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT") == "github-hosted" &&
    Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true" &&
    Environment.GetEnvironmentVariable("GITHUB_REPOSITORY") == "VoltKraft/immich-folder-watch" &&
    Environment.GetEnvironmentVariable("GITHUB_REF") == "refs/heads/rewrite/rust";
if (!OperatingSystem.IsWindows() || (!isolatedIdentity && !hosted))
{
    throw new InvalidOperationException("The Windows oracle requires the rewrite branch's disposable runner.");
}
#else
if (!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException();
#endif
if (args[0] == "identity")
{
#if IFW_WINDOWS
    using var identity = WindowsIdentity.GetCurrent();
    Console.WriteLine(identity.User?.Value ?? throw new InvalidOperationException("Missing account SID."));
#else
    Console.WriteLine("unix");
#endif
    return 0;
}

// The parent knows this secondary's PID before allowing it to contact the native listener.
if (args[0] == "signal" && Console.ReadLine() != "GO") return 2;
#if IFW_WINDOWS
using var coordinator = SingleInstanceCoordinator.Create();
#else
using var coordinator = new UnixSingleInstanceCoordinator(Path.Combine(args[1], UnixSingleInstanceCoordinator.DefaultSocketName));
#endif
if (args[0] == "signal")
{
    if (coordinator.IsPrimaryInstance || !coordinator.TrySignalShowGui(TimeSpan.FromSeconds(5))) return 3;
    Console.WriteLine("SECONDARY_SIGNALLED");
    return 0;
}
if (args[0] != "listen" || !coordinator.IsPrimaryInstance) return 4;
using var shown = new ManualResetEventSlim(false);
coordinator.StartListening(shown.Set);
Console.WriteLine("PRIMARY_READY");
if (!shown.Wait(TimeSpan.FromSeconds(30))) return 5;
Console.WriteLine("SHOW_GUI");
return 0;
