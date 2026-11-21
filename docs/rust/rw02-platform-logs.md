# Native platform log outputs

RW-02 exercises three configured destinations with `desktop-platform-log`.
It writes to an open file or journal stream and can open a pre-registered
Windows Event Log source. The caller supplies a category, event ID, level,
formatted message and file timestamp. The crate has no registry dependencies,
redistributable libraries, fonts, Immich imports or GUI types. Windows links
the operating system's Advapi32. Linux uses the existing console stream.
[Rust adapter](../../rust/crates/desktop-platform-log/src/lib.rs) and
[Windows implementation](../../rust/crates/desktop-platform-log/src/windows.rs).

| Destination | Native contract | Current evidence |
| --- | --- | --- |
| File | Append UTF-8 records with local timestamp and level, preserve multi-line text and report flush errors | Fedora x64 matched the shipping provider after normalizing timestamps. Twelve records survived two processes, twelve opens and an existing log entry. |
| Linux journal | Write one record with syslog priority, category, event ID and text. Prevent CR, LF and NUL from splitting the record. | A separate reader recovered six ordered records with the expected text and priorities. The six-record console stream matched the .NET formatter byte for byte. |
| Windows Event Log | Open an existing source under the expected log and submit correctly typed events with category and event ID. | The native x64 and ARM64 Actions steps passed at `72fff40`, including writing, readback, formatting, missing-source refusal and owned log cleanup. |

The reference builds the shipping `FileLoggerProvider.cs` from product 3.0.4
with .NET SDK 10.0.401 and an empty NuGet feed. Its normalized source
SHA-256 is `383b7e9cb608de608f6dca6c2d1cbf3a698363aafd30fb6396fe65df1954688a`.
The same reference uses the console formatter and settings from the Linux
host. The Windows fixture builds its own single-message resource DLL using
the native Windows SDK. It registers a new source in a unique custom log.
The Rust process uses a read-only registry check. A separate reader verifies
six insertion strings, levels, event IDs and formatted messages before the
fixture removes the private log. [Shipping file provider](../../src/ImmichFolderWatch.Core/Logging/FileLoggerProvider.cs),
[.NET systemd formatter](https://source.dot.net/Microsoft.Extensions.Logging.Console/SystemdConsoleFormatter.cs.html),
[Windows event submission](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-reporteventw)
and [Windows message resources](https://learn.microsoft.com/en-us/windows/win32/eventlog/message-text-files).

On Fedora x64 with systemd 262.1, the test launched a private journal in
separate mount, user, network, IPC and PID namespaces. The Rust writer
reported zero effective capabilities and `NoNewPrivs=1`. The reader
attributed all records to the synthetic machine and identifier, with stdout
transport and priorities 7, 7, 6, 4, 3 and 2. The Rust executable had SHA-256
`9694087b62d606be733c96bfce5f580571794c1eac8dea6c8f0ee8995fab7f0b`.
The receipt at `artifacts/rust/platform-logs/fedora-x64-reference-02/result.json`
had SHA-256 `0835607b2bae595ade573e42626a067c6b9b1a88074cae645a4e74ca8ce1b231`.
[Independent observer](../../tools/rust-qa/platform-logs/observe.py) and
[journal stream semantics](https://www.freedesktop.org/software/systemd/man/latest/systemd-cat.html).

At `72fff40`, Windows x64 and ARM64 passed the native Event Log step.
Both Ubuntu jobs failed during their log step. With the Ubuntu 24.04 userspace
on the x64 Fedora kernel, systemd 255.4 reproduced a refused stream connection
and reported a missing cgroup root. Its initialization resolves the cgroup of
PID 1. Mapping the caller's own cgroup read-only inside a new cgroup namespace
allowed the actual Ubuntu journal to receive all six messages in priority
order. The writer had zero effective capabilities and no-new-privileges set.
The Ubuntu archive's daemon hash was
`ca1c6fe707f574cc0261f87ba13395fe2687169b0e02aae107a3e299d016fe1a`.
The successful local receipt `noble-native-cgroup-01/result.json` had SHA-256
`12e26e018ff2969a60ca78a5bf43159ebc198257754e5e60ff17de7f50fbc35b`.
Use `--journal-system-root` to select an extracted distribution of the native
architecture. The hosted Ubuntu checks still need a repeat with this change.
[Hosted jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350)
and [systemd 255 journal initialization](https://github.com/systemd/systemd/blob/v255/src/journal/journald-server.c#L2455-L2457).

Install the pinned compiler in `artifacts/rust/toolchain`, put the selected
.NET SDK on `PATH`, and run from the checkout with a fresh output directory.

```sh
python3 tools/rust-qa/platform-logs/observe.py x86_64-unknown-linux-gnu --output artifacts/rust/platform-logs/local-01
```

On Windows the workflow enters the matching Visual Studio developer shell
and supplies the native target triple. Registration and cleanup belong to
the disposable test harness. Product target selection, file naming and
retention, redaction of actual application fields, Windows fallback warnings
and installation of the message resource remain integration work.
[Shipping Windows target selection](../../src/ImmichFolderWatch.App/Hosting/AppHost.cs)
and [desktop service contract](../rust-desktop-standard.md).
