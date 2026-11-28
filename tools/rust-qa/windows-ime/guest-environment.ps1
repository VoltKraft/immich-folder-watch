function Assert-IfwImeGuest {
    if ($env:OS -cne 'Windows_NT' -or $env:GITHUB_ACTIONS -or $env:COMPUTERNAME -ine 'IFW-QA25' -or
        $env:PROCESSOR_ARCHITECTURE -cne 'AMD64' -or -not [Environment]::Is64BitProcess -or
        -not (Get-CimInstance Win32_ComputerSystem).HypervisorPresent) {
        throw 'Use the disposable local Windows x64 VM.'
    }
}

function Get-IfwImeCapabilityRecord {
    return (Join-Path $env:ProgramFiles 'ImmichFolderWatchImeQa\capability.json')
}

function Test-IfwMissingGuestIme($Result, [int]$ExitCode, [string]$Revision) {
    return ($ExitCode -eq 1 -and $Result.status -ceq 'unavailable' -and (Test-IfwImeProfile $Result) -and
            $Result.hasActiveInputDesktop -is [bool] -and $Result.hasActiveInputDesktop -and
            $Result.source -ceq $Revision -and $Result.prerequisite -cin @(
                'no loaded Japanese input locale', 'no enabled Japanese TSF keyboard service or loaded IMM IME'))
}

function Get-IfwImeMedium($LanguageSource, $cabName, $cabHash) {
    if ($LanguageSource -inotmatch '^[A-Z]:\\LanguagesAndOptionalFeatures\\?$') {
        throw 'Expected the root feature directory on a local optical drive.'
    }
    $folder = Get-Item -LiteralPath $LanguageSource
    if (-not $folder.PSIsContainer -or $folder.FullName -inotmatch '^[A-Z]:\\LanguagesAndOptionalFeatures$' -or
        [IO.DriveInfo]::new($folder.Root.Name).DriveType -ne [IO.DriveType]::CDRom) {
        throw 'Mount the original Server 2025 x64 Languages and Optional Features DVD.'
    }
    $hash = (Get-FileHash -LiteralPath (Join-Path $folder.FullName $cabName) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne $cabHash) { throw 'The Japanese Basic Typing CAB differs from the staged Microsoft medium.' }
    return $folder
}
