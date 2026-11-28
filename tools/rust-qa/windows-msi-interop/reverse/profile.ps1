# Return the top-level profile entries that the verified WPF primary produced.
function Get-ReverseProfileEntries([string]$ProfilePath, [string]$Evidence, [switch]$Upload) {
    $observation = if ($Upload) { 'upload-observation.json' } else { 'reverse-activation.json' }
    $row = Get-Content -Raw -LiteralPath (Join-Path $Evidence $observation) | ConvertFrom-Json -AsHashtable
    $quit = if ($Upload) { $row.restored.quit } else { $row.quit }
    if ($row.status -cne 'observed' -or $quit.empty -ne $true -or -not $row.profileFiles.Contains('sync-state.db')) {
        throw 'Missing completed original WPF job or retained SQLite evidence.'
    }
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $observed = @{}
    foreach ($entry in (Get-ChildItem -Force -LiteralPath $ProfilePath)) {
        if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected link in the shipping profile.' }
        if ($entry.PSIsContainer) {
            if ($entry.Name -cnotin @('logs', 'engine-logs')) { throw 'Unexpected WPF profile directory.' }
            [void]$names.Add($entry.Name)
            foreach ($file in (Get-ChildItem -Force -LiteralPath $entry.FullName)) {
                if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                    $file.Name -cnotmatch '^immich-folder-watch-\d{8}\.log$' -or $file.Length -gt 2097152) {
                    throw 'Unexpected WPF log object.'
                }
                $observed.Add($entry.Name + '/' + $file.Name, (Get-FileDigest $file.FullName))
            }
        } elseif ($entry.Name -cin @('sync-state.db', 'sync-state.db-wal', 'sync-state.db-shm')) {
            if ($entry.Length -gt 16777216) { throw 'The synthetic SQLite output exceeds the budget.' }
            [void]$names.Add($entry.Name)
            $observed.Add($entry.Name, (Get-FileDigest $entry.FullName))
        }
    }
    if ($observed.Count -ne $row.profileFiles.Count) { throw 'Missing or additional original shipping output.' }
    foreach ($key in $observed.Keys) {
        if ($observed[$key] -cne $row.profileFiles[$key] -or $observed[$key] -cne
            (Get-FileDigest (Join-Path (Join-Path $Evidence 'wpf-profile') $key))) {
            throw 'The live WPF file, captured original and observer digest differ.'
        }
    }
    return $names
}
