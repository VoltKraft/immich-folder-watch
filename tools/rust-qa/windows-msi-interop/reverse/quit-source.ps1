# Read the original upgrade-test helper as data without executing the installer harness.
# Requires PowerShell 7 for the native trial and for the portable compiler control.
function Get-InstalledUpgradeQuitSource {
    param([string]$Path = (Join-Path $PSScriptRoot '../../../../packaging/windows/Test-InstalledUpgrade.ps1'))

    $raw = [IO.File]::ReadAllBytes($Path)
    $scriptText = [Text.UTF8Encoding]::new($false, $true).GetString($raw).Replace("`r`n", "`n")
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($scriptText, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'Could not parse the installed upgrade reference.' }
    $functions = @($ast.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Close-TestApplicationGracefully'
    }, $true))
    if ($functions.Count -ne 1) { throw 'Expected the unique installed upgrade Quit function.' }
    $commands = @($functions[0].Body.FindAll({ param($node)
        $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -ceq 'Add-Type'
    }, $true))
    if ($commands.Count -ne 1) { throw 'Expected the unique Add-Type in the installed upgrade Quit function.' }
    $arguments = $commands[0].CommandElements
    if ($arguments.Count -ne 3 -or $arguments[1] -isnot [Management.Automation.Language.CommandParameterAst] -or
        $arguments[1].ParameterName -cne 'TypeDefinition' -or
        $arguments[2] -isnot [Management.Automation.Language.StringConstantExpressionAst] -or
        $arguments[2].StringConstantType -ne 'SingleQuotedHereString') {
        throw 'Expected a literal native helper source in the installed upgrade Quit function.'
    }
    $code = $arguments[2].Value
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($code))).Replace('-', '').ToLowerInvariant()
    } finally { $hash.Dispose() }
    # v3.0.4, commit 4149763b7f322603a012aebad5f8a252450eb08b, with checkout CRLF normalized to LF.
    if ($digest -cne 'f50baad6accfd09afc3e86beb9908027b8498525f6a787f35d217841c86c9e5c') {
        throw 'The installed 3.0.4 native Quit source digest differs.'
    }
    return [pscustomobject]@{ Code = $code; Sha256 = $digest }
}

function Add-InstalledQuitReceiverCheck {
    # These queries only bind the caller's original receiver to its process, UI thread and input desktop.
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class InstalledQuitReceiver
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern IntPtr FindWindowExW(IntPtr parent, IntPtr after, string className, string title);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
    [DllImport("user32.dll")] private static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern bool GetUserObjectInformationW(IntPtr handle, int index, out int value, int size, out int needed);

    private static bool IsInputDesktop(uint thread)
    {
        IntPtr desktop = GetThreadDesktop(thread);
        int receivesInput, needed;
        return desktop != IntPtr.Zero &&
            GetUserObjectInformationW(desktop, 6, out receivesInput, sizeof(int), out needed) && receivesInput != 0;
    }

    public static bool Matches(IntPtr receiver, uint expectedPid, uint expectedThread)
    {
        var messages = new IntPtr(-3);
        const string title = "ImmichFolderWatchTrayReceiver";
        uint pid;
        return receiver != IntPtr.Zero && FindWindowExW(messages, IntPtr.Zero, null, title) == receiver &&
            GetWindowThreadProcessId(receiver, out pid) == expectedThread && pid == expectedPid &&
            IsInputDesktop(expectedThread) && IsInputDesktop(GetCurrentThreadId());
    }
}
'@
}
