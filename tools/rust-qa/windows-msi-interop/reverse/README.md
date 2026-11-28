# Rust secondary with the installed WPF primary

This fixture uses a disposable native Windows system. ARM64 runs on the hosted
runner and x64 uses the [local test VM](../../windows-local/README.md).
Give each direction its own complete MSI transaction,
KnownFolder profile, scratch directory and evidence directory.

The compiled Rust executable first runs while the shipping election is absent.
It must return an error as the sole process in its job. The second launch uses
the same executable without arguments. The installed WPF primary has started
its in-process folder watcher and hidden its original root window. The
supervisor holds its process handle and publishes its PID and creation time in
the private Rust fixture. Rust opens the existing product mutex, verifies the
PID on its connected pipe, holds the live server process, and sends the
ordinary eight-byte `SHOW_GUI` message. WPF reads to EOF and shows its original
window. The observer saves the WinEvent sequence, the cursor measured before
releasing the suspended secondary, both process identities, the Rust log and
the empty secondary job in `before-quit.json` and its associated logs.

On the original ARM64 Default input desktop, the observer samples the WPF
root and the foreground window's root at the first visible WPF window,
after Rust reactivates it and before the Quit helper starts. Each sample
records the window class, executable basename, session, desktop and bounds
from `GetWindowRect` in the observer's screen coordinates. The held WPF
process, desktop membership and foreground are checked around the reads.
The receipt distinguishes the WPF root, another root, a missing foreground
and a window that changed during sampling. An unavailable native query is
recorded as such. The installed worker backup captures startup and pre-Quit
for each WPF lifetime in `upload-observation.json`. Its `--live-only` reader
includes the pre-Quit sample when the first worker reached it. These passive
samples issue no input. The menu helper verifies the actual cursor target.

To request a regular exit, the observer verifies the original process,
creation time, UI thread and message-only tray receiver. PowerShell 7
compiles the checksum-pinned C# menu helper from the original
[3.0.4 upgrade test](../../../../packaging/windows/Test-InstalledUpgrade.ps1).
The helper opens the product's context menu, locates command 3 in the
owned popup, checks the cursor and highlighted item, and selects Quit
with a mouse click. WPF positions the menu at the cursor. The observer
opens its PowerShell observer without a console window. It samples up to
16 points inside the original WPF client and places the cursor at the first
point owned by the original window and UI thread. It verifies the
physical screen position and owning UI thread, and runs the helper in
the same per-monitor DPI context. The receipt retains the original
window and anchor, the helper's result and the popup handle. A refusal
also captures the observed foreground window and owned popup geometry.
The genuine interaction with the Explorer notification icon has its own
[Windows Shell test](../../../../docs/rust/rw02-windows-services.md#primary-gui-and-shell-callback).

The result records the exit method, worker shutdown signal and start of the
shutdown flush separately. The 3.0.4 worker emits its flush message before
awaiting the pending uploads. Completion of that flush remains unobserved.
If the native menu is unavailable, the observer preserves the activation and
records how it reaped its own process. Its full readback then reports an
incomplete WPF shutdown. The original SQLite database and
application logs from the empty synthetic source are retained after process
exit. The parent installer verifies their contents before uninstalling.

The native supervisor and full readback use these commands from a prepared
runner. Replace `TARGET` with `x86_64-pc-windows-msvc` or
`aarch64-pc-windows-msvc`. The partial readback works after WPF activation,
including when the later quit or cleanup evidence is incomplete.

```sh
python -B tools/rust-qa/windows-msi-interop/run.py TARGET --wpf-primary
python -B tools/rust-qa/windows-msi-interop/reverse/readback.py artifacts/rust/windows-msi-interop/reverse/TARGET
python -B tools/rust-qa/windows-msi-interop/reverse/readback.py artifacts/rust/windows-msi-interop/reverse/TARGET --before-quit
```

### WPF activation and Quit on one private ARM64 input desktop

A separate workflow job uses a fresh Windows ARM64 host. It sets
`TRIAL_VARIANT=arm64-private-input` and passes `--private-input-desktop`
to both commands below. The MSI still installs into the empty disposable
runner and the WPF starts without arguments. A supervisor holds the
original Default input desktop. It selects a newly created desktop in
that unlocked session, launches the observer there and restores the
original input desktop when the observer exits or fails.

The private desktop name contains the Rust launch profile's token. Both
argument-free Rust runs use that desktop explicitly. Before releasing the
real secondary, the observer verifies that the hidden original WPF root
still belongs to its UI thread on the private desktop. The Rust pipe
client validates the connected WPF process and reads its own native
input-desktop flag. The WPF root must reopen on that same desktop. The
original menu helper selects Quit on the same WPF process. The full reader
checks the worker shutdown evidence, both process jobs, MSI removal and
the return to the original console. The separate artifact is named
`rust-windows-msi-activation-arm64-private-input-WPF-primary-<commit>`.
Its scope covers cross-version activation and the application's normal
Quit. Explorer tray activation has a separate fixture.

```sh
python -B tools/rust-qa/windows-msi-interop/run.py aarch64-pc-windows-msvc --wpf-primary --private-input-desktop
python -B tools/rust-qa/windows-msi-interop/reverse/readback.py artifacts/rust/windows-msi-interop/reverse/aarch64-pc-windows-msvc --private-input-desktop
```

Add `--before-quit` to the private readback to check the completed
activation when the subsequent menu or worker shutdown fails. This mode
also requires evidence that the supervisor restored the original desktop.
The Default and private readers each require the matching desktop mode.

Run the portable checks from the repository root.

```sh
python -B -m unittest discover -s tools/rust-qa/windows-msi-interop/reverse
pwsh -NoProfile -NonInteractive -File tools/rust-qa/windows-msi-interop/reverse/test_profile.ps1
pwsh -NoProfile -NonInteractive -File tools/rust-qa/windows-msi-interop/reverse/test_quit_source.ps1
```


### Launcher source after enabling the local x64 tray trial

The ordinary GUI now supports the disposable x64 VM in addition to the
hosted rewrite runner. For these installed ARM64 comparisons, each private
patch reconstructs the exact launcher previously measured at `1910195`.
The Rust-primary source retains SHA-256
`58c04d0ea71fd89846499c79214572db3645eff933c0197e0f80034a1f526c01`.
The WPF-primary source retains
`7a7f5efbcddff0b17a77aed5d69ffe34cefdfda693ad020dc1a2f12154b20941`.
Both variants check the hosted environment before using the installed
endpoint name. The build checks all other compiled GUI files against the
ordinary retained build from the same revision.

### Native ARM64 activation at c0dd89c

The three jobs installed the 3.0.4 ARM64 MSI on separate hosts. All three
reached the native window interaction. The following results were replayed
from the original archives using the reader and installer log parser from
the same commit. [Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103605884).

| Primary and input desktop | Result | Original Actions ZIP SHA-256 |
| --- | --- | --- |
| Rust on Default | The installed secondary reopened Rust HWND 262778. The same worker completed both kernel-observed file queries. Normal Quit and job cleanup passed. | [`a0e8a62d423e6097dc4611f50490e2daabd5447ff4abd34941d654efdcf6c56d`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103605884/artifacts/15246892466) |
| WPF on private input | Rust reopened WPF HWND 262366 and exited zero. The shipping helper selected Quit. WPF logged shutdown and the start of flushing, then exited zero. The supervisor restored Default in session 2 and closed both desktop handles. | [`977088d6ca499c5c46a0a752abe55dcbc140e5119f7ffa441c807e30bb4f3079`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103605884/artifacts/15247141473) |
| WPF on Default | Rust reopened WPF HWND 131422 and exited zero. The partial readback passed. The observer could not reach the Quit menu, and the full readback failed. | [`ea6bd9bc7f7ee5f5d2960291fb555b7e67e646e25a2986d8769454408a5f02da`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103605884/artifacts/15247321285) |

On Default all 16 sampled client points returned the same foreign
foreground window (HWND 66052, PID 8368). The helper stopped before moving
the cursor or opening a popup. The three earlier passive samples identified
the WPF window but could not identify the foreground owner. The observer
terminated its own WPF process and drained its job. An ordinary Quit and
orderly worker shutdown on Default remain unobserved. On the private desktop
the shipping worker log ends its flush evidence at the start of flushing.

The six original transaction logs confirmed installation and removal on
all three hosts. Each final checkpoint had no registered product, installation
directory, pending application operations or running application process.
Each supervisor removed its synthetic profile and scratch directory.
The original archives and detached readback are in
`artifacts/rust/hosted-msi-interop/46103605884/`. Its `verified.json` has
SHA-256 `2c151feeb38e8bd1ba56983ca982e06ff42c17fcd4869f84531b7bddf97b1cfe`.
