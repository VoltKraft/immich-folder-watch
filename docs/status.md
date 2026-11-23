# Project Status

## One- and two-frame Windows measurements (2026-11-23)

At `1b95ba0` the retained egui window passed all eleven same-host WPF
limits at both DX12 frame depths on Windows x64 and ARM64. All twelve
timed trials completed two 100,000-file inventories. The original PNGs
showed 209 changed filename pixels on x64 and 177 on ARM64 after
reopening. Keep the existing one-frame configuration for the retained
GUI. Both Ubuntu hosts also passed all eleven X11 limits. The two
Windows desktop jobs finished with failures in independent steps.
[Timing and raw archives](rust/rw02-windows-window.md#native-results-at-1b95ba0) · [Ubuntu](rust/rw02-native-gui.md#ubuntu-native-results-at-1b95ba0).

Both native Windows text observers completed all three edits and failed
the caret-free screenshot at the shared focus guard. The fix at `e2ec5e9`
requires the exact owned password control to hold focus while capturing
the verified filename rectangle. Its native rerun remains pending. The
x64 Shell sent a show callback, and the visible title and body remained
unobserved. ARM64 refused icon registration. The separate WinRT history
run at `653f255` has started. RW-02 still requires interactive Windows
activation and display evidence.
[Text observer](rust/rw02-windows-text.md#focus-when-capturing-the-caret-free-field) · [Notification evidence](rust/rw02-windows-services.md#windows-notification-history) · [Active native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514).

## Windows glyph capture and fixed-revision worker restore (2026-11-23)

The Fedora x64 run at `e728e86` exercised all four shipping worker
restarts through Rust's SQLite backup API. Detached replay verified 364
indexed files, 158 exact Git sources, the Rust executable, the C# test
assembly and all four consumed database hashes. The readback SHA-256 is
`0aa46b58ac93a6a911de7580ddec3c16cb5d85947fb1db10df25ae5e589c2cff`.
[Worker restore contract](rust/rw01-storage-contract.md#external-state-after-deletion-and-timestamp-repair).

The Windows glyph observer now verifies the intentionally focused control
and the exact geometry of the filename it captures. Independent review
identified a possible one-pixel shift and verified that the corrected
guard detects it. The seven portable text tests and PowerShell checks
passed locally. The working change still requires a native repeat on
both Windows desktops.
[Caret-free capture](rust/rw02-windows-text.md#focus-when-capturing-the-caret-free-field).

## Rust backups after propagated deletion and pending repair (2026-11-23)

On Fedora x64 four shipping workers restarted after download, upload,
deletion or interrupted repair from the bytes returned by Rust. Independent
review matched the eight changed sources, the four xUnit executions and
the before/after SQLite tables. The deletion peer retained the same nine
bytes. Restart completed the pending repair and preserved account history.
Two review findings were resolved. A failed case now retains its original
evidence while the independent cases continue. Executable regression
tests reject donors from different worker profiles and a journal that
contradicts its original entry. The four-target rerun from a clean source
revision and rollback after the installed Rust candidate's own activity
remain open. [Inputs, controls and replay](rust/rw01-storage-contract.md#external-state-after-deletion-and-timestamp-repair).

## Native repair and deletion references (2026-11-23)

At `e558b42` both new C# worker cases passed on all four native targets
and on Fedora x64. After restoring the pending backup, each worker
completed its timestamp repair with the original transfer and account
history. After restoring the latest deletion backup, the peer retained
the same nine bytes in trash and received zero additional writes.
Detached replay matched all eight reports from their SQLite backups,
media and xUnit results and verified the three compiled DLL hashes
on each target. The full Ubuntu suites passed
571 cases per host. Both Windows suites passed 562 with nine Linux-only
skips. The tooling suite ran 181 tests with five platform skips using a
temporary GPG test keyring. The installed Rust candidate's own activity
and rollback remain pending.
[Native originals and four-host readback](rust/rw01-storage-contract.md#external-state-after-deletion-and-timestamp-repair).

The same revision passed the four native feasibility jobs, CI and CodeQL.
Ubuntu passed 37 workspace tests and 15 watch scenarios per architecture.
Windows passed 34 and 14, and separately passed 208 C# recovery assertions
per architecture. Detached replay matched all eight Rust backup exchanges
for uploads and downloads. Its SHA-256 is
`90c72fdcac81b3bd74bfc85d1a6e2fc214f61138fa707839789783d60729e43f`.
[Native results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220170042) · [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220184362) · [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220184524).

Both Noble desktops at `1b95ba0` completed the pinned package rebuild,
reopened the Rust GUI from two Plasma panel clicks and met all eleven
native X11 resource limits. The stock Documents portal still refused
the required lock on both hosts. On Windows the ordinary-user launch
exited with no diagnostic bytes on either architecture. The elevated
control again completed its eight ownership events. Interactive Windows
evidence and the two frame-depth measurements remain under review.
[Ubuntu desktops](rust/rw02-native-gui.md#ubuntu-native-results-at-1b95ba0) · [Windows writer](rust/rw02-cross-session.md#native-writer-and-scheduler-cleanup-at-1e58541).

## Eight native worker restores and two external side effects (2026-11-23)

All four targets at `653f255` passed the shipping worker upload and
download through Rust's SQLite backup API. Independent replay matched
all eight reports, all 1,270 indexed files and the 154 original source
files in each archive. The detached readback SHA-256 is
`6099697c7aa98840aeab7bef95ac2ffc48728e998b29c32cf62243e6b4a75709`.
All four reference suites also passed. Ubuntu ran 569 cases on each
architecture. Windows passed 560 and skipped nine Linux-only cases per
host. [Native results](rust/rw01-storage-contract.md#peer-content-after-a-synthetic-upload).

Two separate working-tree references ran on Fedora x64. After an
interrupted timestamp correction, the C# worker reopened a standalone
backup with the repair still pending. The corrected file time survived
both database restores and the worker completed the journal. Three
negative trials detected an incorrect donor, an incorrect file time
and altered file content. In the deletion trial the shipping HTTP client
trashed one exact asset. Its synthetic peer retained the original bytes
and observed zero additional trash requests after restart. The original
grouped timestamp suite passed nine of ten locally. A separate inotify
watch on an empty test directory returned `ENOSPC` immediately before
the repeat, and the existing cancellation test timed out on its file event.
Both new tests passed in their focused runs. The next check uses the
same revision and original first-party DLLs on the four native targets.
[Side effects and replay](rust/rw01-storage-contract.md#external-state-after-deletion-and-timestamp-repair).

## Worker backup replay and Windows notification history (2026-11-23)

At `c4b876c`, the offline Fedora x64 storage trial restored both a download
and an upload through Rust's SQLite backup API. Each restarted C# worker
reconciled the same file and album without another transfer. Replay matched
both original reports byte-for-byte, all 318 indexed files and 154 archived
sources from Git. The peer retained the eight uploaded bytes and the same
asset ID. The readback SHA-256 is
`a9f0a6c8f030a4a9daf3a4662d5593106c26343588b4a46573205eca24b09565`.
[Activity evidence](rust/rw01-storage-contract.md#peer-content-after-a-synthetic-upload).

The new Windows trial observes normal and suppressed notifications through a
test shortcut's own WinRT history. It verifies each entry's content and
removal in separate processes. Both MSVC targets passed cross-Clippy and
the service tests passed 51 portable checks. The independent review
verified that detached replay requires the original PE import table,
native build report and input desktop. Native delivery, banner visibility
and user activation still require Windows observations. RW-02 remains open.
[Windows trial](rust/rw02-windows-services.md#windows-notification-history).

## Released installer behavior on the four hosted targets (2026-11-23)

At `1b95ba0`, both original Windows MSI files installed and uninstalled
successfully during cleanup. The test stopped before repair because it
expected a migration action absent from the compiled MSI tables. Both Noble
jobs imported the original OSTree commit and failed to reach a system bus at
deployment. The revised Linux fixture completed the entire offline installation,
repair and removal in Noble and Fedora x64 userspace on the local Fedora kernel.
The Windows fixture now checks the actual compiled actions and sole desktop
shortcut. At `0f29659`, all four jobs then completed actual install, repair
and uninstall. Both native Linux payloads matched all 785 entries. Windows
x64 verified 439 files and ARM64 verified 438. Direct replay of the four
original archives recovered the complete SQL fixture and original YAML
after uninstall. The four-host readback SHA-256 is
`ccf92ed76a89e2ce5aeafaeec38b2fa0c0ce48c2e8ea94095b93d03ad17b31d9`.
[Original run and receipts](rust/rw01-installed-packages.md#first-native-package-run).

The Fedora x64 upload exchange returned a Rust-generated SQLite backup to
the shipping worker. The peer retained all eight uploaded bytes through the
second reconciliation. The reference formerly missed some album mutation
methods. Independent review verified the corrected peer covers all 17 asset
client signatures and rejects unexpected writes even if the caller catches
the error. Ten native negative trials failed at the intended check. The
working-tree receipt has SHA-256
`85dfb12e8cae044794260191290fd62857a27ebd681709622435f8179ba12af0`.
The subsequent clean Fedora result is recorded above.
[Reference and replay](rust/rw01-storage-contract.md#peer-content-after-a-synthetic-upload).

## Four native upload references and package migration baseline (2026-11-23)

At `9efe6f4` all four shipping upload references passed. Ubuntu passed
568 tests on each architecture. Windows passed 559 and skipped nine
Linux-only tests per host. All four independent feasibility jobs passed,
including 37 workspace tests and 15 watch cases on each Linux host and
34 and 14 on each Windows host. Both Windows targets completed 208 C#
recovery assertions. [Upload reference](rust/rw01-storage-contract.md#peer-content-after-a-synthetic-upload) · [Native feasibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45175252054).

The original 3.0.4 Flatpak completed a clean, private Fedora x64 install,
repair and uninstall. The 785-entry payload and both retained synthetic
profile files matched. The two original Windows cabinets supplied the
expected hashes for 877 files. Independent review verified the original
cabinet contents and the full Fedora result, including all 16 evidence
hashes. The four native hosted package jobs are the next check.
[Installed package reference](rust/rw01-installed-packages.md).

The Fedora rehearsal repeated at `285101b` from clean fixture sources.
Direct SQL replay again recovered the full synthetic corpus. The eight
portable Python tests, PowerShell controls and both workflow syntax checks
passed locally. The repository tooling suite completed 178 tests with
five platform skips using a temporary GPG keyring and the reviewed
PowerShell 7.7.0 executable.

At `549066f` and `ba02f8b` the x64 GDI control met all four WPF response
limits. Full egui exceeded the scan close and reopen limits on x64 and
met all eleven limits on ARM64. The ARM64 GDI control stopped at its first
screen observation. The dated Ubuntu snapshots reproduced all six
authenticated release indexes and the four original portal source files.
The local Noble guest rebuilt from all 696 x64 packages and the
Noble-linked GUI reopened after two Plasma panel clicks.
RW-02 remains active. Next, test the full egui software renderer with the
second frame-queue setting on the two Windows targets and repeat the
Ubuntu desktop trials with these pinned inputs.
[Windows controls](rust/rw02-windows-window.md#visible-gdi-and-retained-egui-under-the-same-inventory) · [Ubuntu sources](rust/rw02-plasma.md#reproduction).

The two-frame software-adapter trial at `a44848d` passed both Windows
cross-Clippy configurations, native Fedora release compilation and local
offline reconstruction. Thirty-seven portable window, text and display
tests passed. A native Windows bitmap test remains for the hosted run.
Independent review replayed twelve original scan trials and rejected
missing or corrupt raw traces. The portable editor controls rejected
cursor-only changes. [Frame queue comparison](rust/rw02-windows-window.md#one-or-two-queued-frames-on-the-windows-software-adapter).

On both recent Windows runs, independent replay confirmed the x64 Shell's
show callback without observing the notification title and body. On ARM64
the Shell refused registration before the send. All 16 launcher profiles
were removed. Two separate retained-tray profiles at `ba02f8b` completed
removal on the same handles after Windows error 145. Foreground keyboard
handover on ARM64 remains open. [Notification results](rust/rw02-windows-services.md#sampling-across-the-shell-request) · [Launcher results](rust/rw02-instance.md#launcher-cleanup-and-foreground-at-549066f-and-ba02f8b).

## Worker download reference and Ubuntu desktop checks (2026-11-23)

The shipping worker downloaded a six-byte synthetic photo on Fedora x64.
The before backup contained no mapping or account history. The after backup
contained the downloaded asset and its account Last Sync. Restart from that
backup reconciled the same album and watch root with zero additional
transfers. Independent review added a positive album-list observation on
both runs and bound the two loaded assemblies and the original evidence
to their xUnit result. At `cf38f1a`, all four native reference jobs passed.
Each Ubuntu target passed 567 tests. Each Windows target passed 558 with
nine Linux-specific skips. Independent readback verified all eight original
backups and all four media files. The local focused case passed from the
same commit. An earlier local repeat of the full persistence class passed
34 of 66 tests. Six cases explicitly reported the shared inotify limit,
and a single native descriptor also failed at that time. The other failures
were timing, transfer and ordering assertions. The earlier local full-class
run passed 66 of 66. Both full hosted Ubuntu runs passed with the new case.
[Download activity reference](rust/rw01-storage-contract.md#download-activity-and-the-latest-backup).

The Rust backup example at `2353424` ran eleven cases on Fedora x64 with
the pinned compiler and bundled SQLite. The two complete donors passed,
including one with a different fixture label. Nine controls refused their
inputs. The stale refusal carries the actual request token and database SHA.
The C# exchange at `738e1d6` refused an oversized response before restarting
the worker. At `ba02f8b` the combined offline run passed on Fedora x64.
The real second C# worker opened the Rust backup and retained the original
mapping, history, six-byte photo and native file times after reconciling
the same album. Independent replay reproduced all 1,278 readback bytes and
matched all 153 archived project sources. The same trial then passed on
Windows and Ubuntu x64 and ARM64. The four original worker reports
reproduced byte-for-byte. On each host Rust refused the pre-download
backup and the restarted C# worker made zero transfers from the newer
one. Each of the four separate C#-only reference jobs also passed.
[Native backup procedure](../tools/rust-qa/storage/README.md#restore-after-a-synthetic-download) · [Four-host worker run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804585) · [C# reference](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804686).

The shipping upload reference at `c0abae3` also passed on Fedora x64.
The peer received the opened stream once and retained its bytes after
the worker restarted from SQLite. Independent review identified unobserved
trash and album mutation requests. Two test-only mutations then confirmed
the corrected assertions fail on either request.
[Upload reference and limits](rust/rw01-storage-contract.md#peer-content-after-a-synthetic-upload).

At `8566f81`, the original Linux archives verified all eleven X11 budgets
and the SQLite and realtime results on both architectures. ARM64 observed
two real Plasma panel clicks. Both x64 fixture downloads lost their HTTP
connection before response headers. Commit `549066f` passed seven
downloader tests and a private HTTP replay. Its hosted desktop run also
exercises the Windows GDI, tray, notification and profile-cleanup changes.
RW-02 remains open.
[Ubuntu results](rust/rw02-native-gui.md#ubuntu-native-results-at-8566f81) · [Native run at 549066f](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45167710471).

Independent readback of the completed Windows archives at `8566f81` found
that the retained Mailbox window met eleven of eleven limits on ARM64 and
eight on x64. Windows x64 exceeded the limits for idle close, scan close
and scan reopen. The independent observer found no matching notification title and body
on either host. All four native archives passed the
detached YAML and SQLite checks, and their development notices and SPDX
documents reproduced byte-for-byte. [Windows timings](rust/rw02-windows-window.md#retained-window-at-8566f81) · [Shell observations](rust/rw02-windows-services.md#original-desktop-at-8566f81) · [YAML checks](rust/rw02-yaml.md#reading-the-original-yaml-file-bytes) · [Storage matrix](rust/acceptance.md#native-evidence-matrix).

## Four-target checks and the Windows renderer comparison (2026-11-23)

At `8566f81`, the raw YAML round trip passed its native step on Windows
and Ubuntu, on both x64 and ARM64. All four native feasibility jobs also
passed. Independent readback of their ten archives verified 37 workspace
tests and 15 file-watch cases per Linux target, 34 and 14 per Windows
target, and 208 C# recovery assertions per Windows target. The readback
SHA-256 is `3a5a827726dea94d3e3f7fabdb63cccd25e777b0ee374562facc0e8b3ba92b54`.
The draft PR CI passed. Both hosted Rust CodeQL configurations again ran
40 queries on the recorded foundation tree and reported zero alerts.
[Native feasibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516267) · [Desktop and YAML run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037) · [Draft PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159526233) · [Rust CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159525936).

The GDI diagnostic at `763048a` passed six portable tests, Rustfmt and
strict Clippy for both Windows targets. Independent review verified that
the idle timings use the WPF warm-up sequence, and that qualifying scan
samples bind the visible pixels, frame and HWND to real file activity.
Commit `89883ea` also reads the shipping WPF tray icon after each idle
trial. Its lookup passed the independent receiver and error-path review.
Both comparisons await native Windows results. RW-02 remains open.
[Renderer procedure](../tools/rust-qa/windows-gdi-control/README.md) · [Shipping tray control](rust/rw02-windows-services.md#shipping-wpf-tray-lookup).

Commit `effae21` closes the earlier gap between the UIA observer's baseline
and the return of the Windows notification request. Independent review
replayed four timing edge cases. All 41 Python checks, the PowerShell
pixel and timing controls and the 178 repository tooling tests passed.
The native measurements still need to establish
whether the real desktop presents the unique title and body.
[Notification timing](rust/rw02-windows-services.md#sampling-across-the-shell-request).

The original Windows launcher at `8566f81` reopened on both architectures.
x64 obtained foreground immediately. ARM64 stayed in the background for
40 samples over 2,005 ms. Its separate private restart drained, then profile
cleanup received error 145. Commit `579fbcc` preserves the error and limits
retries to the same verified directory handle. Independent review passed.
[Native launcher results and cleanup test](rust/rw02-instance.md#private-launcher-cleanup-at-8566f81).

## Legacy YAML byte compatibility (2026-11-23)

At `a7a62fa`, a clean Fedora x64 build passed all 13 offline assessment
steps. Rust read 54 archived original files. The shipping C# loader reopened
70 Rust-written files and passed 140 comparisons. Ten damaged files were
readable with the same replacement characters in both languages and retained
their original bytes. Independent review verified the relocated archive and
22 rejection controls. [Raw file evidence](rust/rw02-yaml.md#reading-the-original-yaml-file-bytes).

## Rust foundation CodeQL (2026-11-23)

The extended CodeQL suite analyzed the five-crate foundation locally with
both target configurations. It ran 40 queries, including 20 security rules,
and reported zero alerts and zero extraction errors on each. The source
archive matched all 19 Rust files in Git. The Linux configuration activated
17 files and the Windows configuration activated 18. Their combined
coverage includes the platform-specific filesystem and logging modules.
The Rust tree was `51b7bff74a760b6f888b6c06b551303dc0a50be7`.
Commit `3b08278` adds the read-only draft-PR workflow. Native runtime and
the standalone GUI have separate assessments. [Reproduction and scope](development.md#rust-foundation-codeql).

The first hosted run on `267c217` passed both configurations. The downloaded
SARIF documents and coverage tables matched the Git sources and independent
local analyses. They report 2,914 Linux and 2,906 Windows lines of user code,
with zero alerts, extraction errors or warning-level diagnostics per target.
[Linux report](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45152719796/artifacts/14807885505) · [Windows report](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45152719796/artifacts/14806698523).

## Native candidate assessment at 6af7100 (2026-11-23)

All four native feasibility jobs passed at `6af7100`. Readback of the ten
Actions archives confirmed 37 Rust workspace tests and 15 watch-event cases
on each Linux target, and 34 tests and 14 cases on each Windows target.
All four matched 5,844 requests in each casing profile. Both Windows hosts
observed encrypted SMB 3.1.1, and their eight storage recovery cases each
passed a total of 208 C# assertions. The independent four-host readback
SHA-256 is `af82995f54e10d8bb266808535aa56f2dcb9338ad33a73ad7f75b57528655784`.
The local repository suite passed all 178 tests. Draft PR CI passed.
GitHub's default CodeQL jobs analyzed Actions, C#, JavaScript/TypeScript
and Python. The four native desktop jobs run separately.
[Native feasibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662890) · [PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144674806) · [Desktop assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858).

Both Ubuntu desktops passed all eleven same-host budgets and two pointer
activations through the running Plasma panel. Their offline compiler
receipts, notices and SPDX reports reproduced exactly. The retained Windows
x64 launcher obtained keyboard focus. The ARM64 HWND remained in the
background for 41 samples despite a successful handoff grant.
[Desktop measurements and archives](rust/rw02-native-gui.md#native-follow-up-at-6af7100) · [Windows visibility](rust/rw02-windows-window.md#testing-visibility-changes-without-resetting-the-window-frame).

Both Windows desktop jobs finished with failures. ARM64 met all eleven
retained-window resource limits. On x64 the p95 values for idle close,
scan close and scan reopen were 26.561, 35.398 and 35.614 ms against
14.571, 30.582 and 22.003 ms. The original x64 Shell accepted a late
notification and returned a show callback. Independent title/body
presentation is still unconfirmed on either host. All four compiler
receipts, notice archives and SPDX documents reproduced offline.
[Windows timings](rust/rw02-windows-window.md#native-retained-window-results-at-6af7100) · [Four-target notices](rust/rw02-combined-notices.md#native-notices-at-6af7100).

The canonical Windows launcher reopened on both original desktops. x64
obtained foreground immediately. On ARM64, Windows declined the granted
handoff and the window remained visible in the background for 2,044 ms.
Both private restart and cleanup cases passed. The original x64 Explorer
registered the integrated icon, but none of the four button queries found
an overflow provider. ARM64 Explorer rejected the initial add and both
retries. Both hosts again excluded an elevated writer across two sessions.
Standard-user exclusion still requires two eligible sessions.
[Ordinary launches](rust/rw02-instance.md#native-windows-launcher-at-6af7100)
· [Explorer observations](rust/rw02-windows-services.md#original-and-private-explorer-at-6af7100)
· [Cross-session writer evidence](rust/rw02-cross-session.md#native-writer-and-scheduler-cleanup-at-1e58541).

## Windows activation and resource results (2026-11-23)

The retained Windows candidate at `4975c45` changes only visibility on a
normal owned HWND when both native style words match its cached state.
Commit `9de3ded` checks the actual hide and reopen paths separately.
Independent review reproduced the 217-file winit tree, the paired source
archive and the native Fedora compiler outputs. Four Rust controls and 18
portable fixture tests passed, as did cross-Clippy for Windows x64 and
ARM64. Both native Windows performance runs are required to evaluate
the change. [Candidate and evidence requirements](rust/rw02-windows-window.md#testing-visibility-changes-without-resetting-the-window-frame).

The Linux ARM64 Plasma panel fixture at `725f1cd` has its own signed Ubuntu package
inventory. Its 691 archives include 598 ARM64 builds and 93
architecture-independent packages. Their payload and copyright hashes were
verified. The previously observed physical panel activations were on x64.
The ARM64 panel requires its own native run. [KDE panel fixture](rust/rw02-plasma.md).

At `1e58541` both Ubuntu desktop jobs, all four native feasibility jobs,
the draft PR's CI and CodeQL passed. Both Windows desktop jobs failed.
The original x64 Desktop confirmed ordinary second-launch foreground and
retained keyboard focus. On ARM64 the retained window reopened with its
worker. Windows refused its foreground request. The canonical ARM64 private
restart drained, then cleanup received Win32 error 32 before the independent
Default-desktop test. Commit `68f68c0` preserves the original-desktop result
first and identifies any busy entry during cleanup.
[Launcher evidence](rust/rw02-instance.md#native-windows-launcher-at-1e58541)
· [Native assessments](rust/rw02-native-gui.md#native-follow-up-at-1e58541)
· [PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124503587).

ARM64 again met all eleven retained-window limits. The x64 candidate
exceeded three. Every over-budget x64 close in the regular dispatch trial
waited through visible redraw. On 78 of 81 slow reopens the native show
call overlapped at least half of the response time. The original x64 Shell
registered the integrated icon but no provider activation was observed.
The ARM64 Shell refused all nine adds. Both late notification trials
stopped before sending a notification. Commit `5321181` fixes the
fixture-directory mismatch and its portable regression passes.
[Window measurements](rust/rw02-windows-window.md#retained-measurements-with-explicit-foreground-requests-at-1e58541)
· [Notifications](rust/rw02-windows-services.md#late-notification-on-the-original-desktop).

The native writer guard again performed eight ordered ownership operations
in two elevated sessions of the same account per Windows host. Both
scheduled-task cleanups returned zero. Neither standard-user launcher reached
its writer. On November 23 the repository reported no registered self-hosted
runners. Existing standard-user sessions and an actual mixed-DPI/RDP desktop
remain necessary for those trials. RW-01 is accepted and RW-02 remains open.
[Writer results and scheduler cleanup](rust/rw02-cross-session.md#native-writer-and-scheduler-cleanup-at-1e58541)
· [Display requirements](rust/rw02-windows-display.md)
· [Full acceptance matrix](rust/acceptance.md#native-evidence-matrix).

## Four-host storage and the Windows desktop rerun (2026-11-23)

RW-01 is accepted and RW-02 is active under the original RW-01–07 goal.
At `93ecc35` all four targets passed the storage build and native tests.
Direct SQL readback covered 32 databases, eight live-WAL backups, 120
stored-key lookups and eight untouched version-99 controls. All eight
database files per operating system were byte-identical between x64 and
ARM64. The native compiler inputs, notice archives and SPDX documents
for the combined development executable also reproduced on all four hosts.
[Storage readback](rust/rw02-legacy.md#native-desktop-storage-at-93ecc35)
· [Four notice and SPDX receipts](rust/rw02-combined-notices.md#native-notices-at-93ecc35).

Both Ubuntu desktop jobs passed. Windows ARM64 met all eleven retained
window performance limits. Windows x64 met eight. Its idle close took
46.72 ms at p95, its scan close 37.55 ms and its scan reopen 39.10 ms.
The x64 limits were 14.26, 31.58 and 22.79 ms respectively. Root repaint
produced zero DXGI presentations in all 547 verified hidden x64 intervals.
Earlier x64 results at `0a2b5ca` met all eleven limits. Windows interactive
tray activation, ordinary-user writer exclusion and the mixed-DPI/RDP
observations remain open. [Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235)
· [Retained-window measurements](rust/rw02-windows-window.md).

The candidate at `1e58541` preserves an explicit Windows Open until the
new or retained window is visible. Its original-Explorer check preserves the
identity of the popup and handles an invocation that already took effect
when COM returned an error. Both changes received independent source and
regression review. The same native Linux build passed all four lifecycle
cases, keyboard input, clipboard and password masking on private Fedora
X11 and Wayland desktops. The corrected Windows paths and the comparison
with the original WPF budgets are in the new native run.
[Explicit activation](rust/rw02-instance.md#explicit-windows-foreground-requests)
· [Fedora results](rust/rw02-native-gui.md#fedora-input-and-lifecycle-after-the-focus-change)
· [Four native desktop jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494708)
· [Native filesystem and compatibility jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494628)
· [Draft PR 46](https://github.com/VoltKraft/immich-folder-watch/pull/46).

## Windows ordinary launch, Shell registration and writer authority (2026-11-23)

At `93ecc35` a second launch on each original Windows desktop reopened the
canonical GUI, retained its worker and exited as the only member of its job.
The x64 window was foreground immediately. The ARM64 window was visible
throughout 41 samples over 2,042 ms and stayed in the background. On both
private desktops native enumeration found the titled visible GUI and its
hidden witness. The additional name query failed with Win32 error 5 before
the private restart. On the original x64 desktop the first physical icon
pixel differed from the requested marker. ARM64 refused the initial add.
Readback verified six archives and 31 Git source files per architecture.
[Original console and private desktop](rust/rw02-instance.md#ordinary-second-launch-and-private-desktop-at-93ecc35)
· [Shell observations](rust/rw02-windows-services.md#original-explorer-and-the-primary-gui-at-93ecc35).

The cross-session writer guard excluded each competing writer in two
elevated sessions of the same account on both Windows architectures. Both
hosts identified the ordinary-user trust level on a private console. The
subsequent launch exited before a standard-user writer could be measured.
The x64 scheduler had already stopped an instance during cleanup. Commit
`c4ba904` checks that race against a fresh empty instance collection.
[Writer results and original archives](rust/rw02-cross-session.md#hosted-private-console-and-lock-results-at-93ecc35).

Local integration now schedules the retained-window launcher, real Explorer
activation and late notification assessment on both Windows targets. The
native compiler evidence binds the GUI binary to its Cargo executable
target. The retained observer requires a native ordering witness for
same-tick visibility events. The notification observer requires separate
physical hits for title and body and corroborates the original Explorer
throughout the attempt. Commit `974bf45` checks process liveness on the
open handle. Both MSVC cross-Clippy runs, 34 service controls and all
178 repository tests passed locally. Commit `7fd8706` verifies private
window membership directly on the held desktop. The corrected observers
and retained activation still require their native runs. RW-02 remains
open under the original seven-package goal.
[Windows measurement](rust/rw02-windows-window.md)
· [Late notification](rust/rw02-windows-services.md#late-notification-on-the-original-desktop)
· [Stack decision](rust/rw02-stack-decision.md).

Both Ubuntu jobs at `93ecc35` subsequently passed. All eleven X11 limits
held, including scan reopen p95 of 1.08 ms on x64 and 0.92 ms on ARM64.
Both original compiler and notice ZIPs reproduced on each architecture.
The direct SQL replay checked all nine rows of both WAL backups, all 30
stored-key lookups and the ten controls per host. The four-host storage
readback above includes the completed Windows jobs.
[Ubuntu desktop, transport and notices](rust/rw02-native-gui.md#native-follow-up-at-93ecc35)
· [Storage and SQL](rust/rw02-legacy.md#native-desktop-storage-at-93ecc35).

## Four native compatibility runs at 93ecc35 (2026-11-23)

RW-01 is accepted and RW-02 is active. All four targets passed the complete
native feasibility run at `93ecc35`. Both scalar modes passed 5,844 requests
per target. Each Windows target passed encrypted SMB and all eight recovery
cases, including 208 C# assertions. The native and C# reference archives
were independently replayed. The two readback SHA-256 values are
`0b479754d9b3f1e49ceef572dde4163994b6c5c66f63b4f71e1f575c7852753d`
and `db19d34284b8ba1c51ffc6db5f8f327f32250486a687ff761eaf854cb76f2d9f`.
The desktop and installer criteria have separate evidence gates.
[Native casing receipts](rust/rw02-legacy.md#managed-globalization-invariant-casing-in-net-10012)
· [Filesystem and recovery](rust/rw02-filesystem.md#four-native-hosts)
· [Acceptance matrix](rust/acceptance.md#native-evidence-matrix).

The completed desktop run at `0a2b5ca` qualified all eleven retained Mailbox
limits on both Windows hosts. During a 100,000-file scan, reopening took
11.343 ms at p95 on x64 and 4.261 ms on ARM64. The x64 regular root-wake
trace had zero hidden presentations in 303 intervals. Each target's
original notice ZIP and development SPDX document reproduced byte-for-byte.
Both native Windows logs confirm the SQLite example warning corrected at
`dff8cb0`. Native activation of the integrated window and Shell remains
open. [Windows performance evidence](rust/rw02-windows-window.md#native-retained-window-results-at-0a2b5ca)
· [Four-target notice and SPDX readback](rust/rw02-combined-notices.md#native-notices-at-0a2b5ca).

## Ubuntu desktop, storage and native notices (2026-11-23)

Both Ubuntu desktop jobs passed at `0a2b5ca`. Replaying the three
100,000-file trials per target reproduced all eleven X11 response and
resource checks. Direct SQL on the archived C# databases matched all
30 stored-key answers per target. The two published development notice
ZIPs and SPDX inventories reproduced byte-for-byte from their native
compiler receipts. [Native results](rust/rw02-native-gui.md#native-follow-up-at-0a2b5ca)
· [Original notices](rust/rw02-combined-notices.md#native-notices-at-0a2b5ca).

Commit `8e32c84` requires evidence that the original Windows Shell process
actually exited before accepting a missing tray icon during shutdown.
The retained and canonical GUI source checks at `ccf42f1` matched on all
four target graphs. Commit `dff8cb0` corrected the Windows build of the
private SQLite study directory. Its normal Fedora storage run passed all
16 steps. Commit `17b3199` added ordered Shell registration and removal
observations. Independent review confirmed the remaining two observer
fixes at `a4d951d` against 35 tests and 77 reachable operation sequences.
The corrected launcher, tray and storage trials still require native runs.
Both hosted writer fixtures also returned empty pipes on their trust-level
queries. The next native run can repeat that query on its own private console.
[GUI dependency verification](rust/rw02-gui-dependencies.md#windows-notification-area-bindings)
· [Storage example](rust/rw02-legacy.md#windows-storage-example-compilation).
[Windows Shell review](rust/rw02-windows-services.md#primary-gui-and-shell-callback)
· [Standard-user query](rust/rw02-cross-session.md#trust-level-query-on-the-hosted-machines).

## Runtime selection and Windows launcher evidence (2026-11-22)

RW-01 is accepted. RW-02 remains active. At `0a2b5ca` all four hosted
C# references matched 29 files and 215 assertions. The four native Rust
jobs passed the ordinary comparison and rejected the hosted CoreLib patch
before the managed comparison. The clean Fedora repeat of `c1fd776` built
the oracle once and passed all fourteen steps with both children using the
selected .NET 10.0.12 runtime. The original feasibility and reference
readbacks have SHA-256
`1ba52ce8f5ae6f63acfaaa7ef00141974a79c0603b1329c9352aacc6a045aec0`
and `b0cd60e4e9535305a4a6b197a6c9c464ab77ab9bbda4ee1fd1079ecf3927e6c6`.
[Casing results](rust/rw02-legacy.md#managed-globalization-invariant-casing-in-net-10012)
· [Acceptance matrix](rust/acceptance.md#native-evidence-matrix).

Both Windows hosts reopened the elected GUI through a normal second launch
on the original desktop, retaining the same primary and worker. Both private
launches created their visible window on the wrong desktop. Each secondary
job recorded a second, unidentified process. The launcher results are failed.
At `706cb94` the primary GUI gained its own native Shell receiver. At
`76650d4` the four revised GUI dependency graphs and the retained eframe
source were verified. The Fedora combined offline build and Wayland relink
passed, including the 74 source hashes checked against that commit.
The next Windows runs must observe the corrected private launch, actual Shell
callback, secondary process count and same-worker cleanup on both architectures.
Commit `3dbc123` selects the named desktop at process creation.
Commit `8beb432` requires a visible on-screen window, an exact Shell item
and a callback ordered after its provider invocation. Thirty launcher tests
passed. At `9282426` the receiver retries registration if a new Shell first
refuses the icon. Nine GUI tests passed on Fedora and both Windows MSVC
targets passed cross-Clippy. The local repository suite passed all 178 tests.
[Ordinary launcher](rust/rw02-instance.md#native-desktop-selection-and-ordinary-reopening-at-0a2b5ca)
· [Primary GUI tray](rust/rw02-windows-services.md#primary-gui-and-shell-callback)
· [Combined native qualification](rust/rw02-combined-profile.md#native-qualification).

## Native rewrite assessments and independent storage review (2026-11-22)

RW-01 is accepted. RW-02 remains the active package of
[M-RUST-IMPLEMENTATION-20261114](project.md#m-rust-implementation-20261114).
Both Ubuntu desktop jobs passed at `7517e3b`. Both Windows targets passed
all three ordinary filename edits, all four standalone font cases and seven
ordered NVDA speech cues. At both `8b64330` and `7517e3b` the Japanese IME
showed preedit, committed あ, restored the language settings and removed the
temporary profile on each architecture. The hosted Windows desktops each
reported one 96-DPI console monitor. The Linux GUI built from the later
`f4d5b3a` sources also passed private Fedora X11 lifecycle, clipboard, Orca
and Japanese input checks, plus Wayland Japanese input and four transitions
between two outputs. [Four native desktop archives](rust/rw02-native-gui.md#native-follow-up-at-7517e3b)
· [IME receipts](rust/rw02-windows-ime.md) · [Font observations](rust/rw02-font-coverage.md).

At `8091469` both Ubuntu desktop jobs again passed. Recomputing their three
100,000-file trials reproduced all eleven same-host performance checks per
architecture. Ubuntu x64 and ARM64 reopened in 0.89 and 0.90 ms at scan p95
and each passed all sixteen loopback transport cases. [Ubuntu native receipts](rust/rw02-native-gui.md#native-follow-up-at-8091469)
· [TLS identity observations](rust/rw02-realtime-transport.md#tls-endpoint-identity).
Both Windows private Shells refused two registration attempts on the same
taskbar. The x64 original Shell accepted the icon and reported its balloon.
Neither host delivered a tray activation. The guard excluded writers in two
elevated sessions on both hosts. The ordinary-user fixture again stopped
before either writer ran. Source inspection across Fedora, Ubuntu, Debian,
Arch and openSUSE found the released Documents-portal read lock unavailable
in the examined packages. [Portal package sources](rust/rw02-portal-upstream.md#additional-distribution-sources-checked-on-2026-11-22).

The two official Unicode data inputs reproduce the distinct .NET invariant
uppercase tables observed on Fedora and on all four hosted targets. The
Fedora Rust probe passed 5,844 requests with each independently generated
table, and the strict comparison rejected a third synthetic mapping. The
four native jobs at `8091469` each qualified the 15.1.0 table. The shipping
C# store on Fedora produced two distinct insensitive keys with ICU 74.2 and
one with ICU 78. Changing either reader's library hid the existing entries
and repairs while leaving both accounts' transfer history readable. The
Rust read-only probe passed 56 lookups on the original C# backups and
eighteen controls on copies across the two environments, including
native source normalization and the complete same-process writer table.
The same .NET version in globalization-invariant mode produced identical
fixture databases to ICU 78 but a different 1,475-row casing table. Both
reference readers refused the unfamiliar writer. Independent replay at
`b77fc12` matched all 56 lookup answers, 299 evidence hashes and 137
source files. It also identified a whitespace-only account that the C#
store rejects. The correction passed 60 lookups and twenty controls across
the two genuine writers. At `727d052` the full Fedora storage entry point
passed all 16 steps. Its 302 evidence files and 137 Git source hashes matched.
The production new-key
policy and installed migration remain open.
[Casing qualification](rust/rw02-legacy.md#independently-reproduced-casing-profiles)
· [Stored-key experiment](rust/rw02-legacy.md#stored-sqlite-identities-across-two-casing-profiles).

The tagged .NET source and Unicode 16.0 independently reproduce the third
profile. With the same twelve input filenames the legacy C# store retained
eleven, ten or eight distinct insensitive entries under the three profiles.
The native Fedora scalar probe passed 5,844 comparisons each using the ICU
and managed tables at clean revision `da448ed`. All twelve native steps
passed. The comparison matched both oracle assemblies and CoreLib files.
The additional hosted comparison is selected in the normal feasibility
entry point. [Managed casing evidence](rust/rw02-legacy.md#managed-globalization-invariant-casing-in-net-10012).
At `733194b` all 318 Rust lookups on the three original writer profiles
matched the independent SQL projection. Fourteen controls passed. The separate
two-profile qualifier still refused the managed writer.
Independent review reproduced all 36 archived C# outputs, matched 5,400
additional Rust queries to SQLite and confirmed 25 additional refusals.
[Stored-key observations](rust/rw02-legacy.md#read-only-lookup-across-three-historical-writers).

Commit `66d9fd6` produced four SPDX inventories from the verified native
builds at `a66e045`. Each passed the pinned SPDX 2.3.1 schema and reproduced
byte-for-byte. The independent review checked source licenses, font assets
and all 74 indexed build outputs. The documents cover 337 and 336 compiled
Cargo packages on Linux x64 and ARM64, and 250 and 249 on Windows x64 and
ARM64. The packaged product inventory remains open under RI-AC09.
At `7517e3b` the assessment workflow generated all four inventories on the
native hosts. Local replay from the authenticated archives reproduced each
uploaded document byte-for-byte and passed the official schema and native
inventory controls.
Independent review of the four locally reconstructed development notice
ZIPs at `577843b` found three omissions. The two Linux inventories omit
the core Wayland protocol XML and five Plasma protocol license texts.
All four initial bundles omitted applicable per-file ring copyright and
permission notices. Independent review of `9f68c58` closed all three findings
for the development builds. Across the four corrected ZIPs, 2,356 complete
original files and 9,714 byte-range references matched their sources. All
four corrected SPDX documents passed the schema. The native workflow now
selects notice generation using its uploaded compiler receipt as input.
The native Fedora build at `9f68c58` produced the corrected inventory,
402 build units, 1,799 notice ZIP members and an SPDX document with 446
packages. Its relinked executable reported the edited Wayland interface.
Offline replay reconstructed that receipt twice from each of the four
`7517e3b` archives. All 1,798 indexed files in the resulting Linux x64
notice ZIP matched the independently reviewed ZIP. The manifest identified
the new receipt archive by its own SHA-256.
[Four build inventories and digests](rust/rw02-combined-sbom.md)
· [Development notice reconstruction](rust/rw02-combined-notices.md).

At `8091469` retained Mailbox met all eleven WPF limits on ARM64 for a
fourth native run. Windows x64 met eight. Reopening during a scan took
119.95 ms at p95 against 21.987 ms. In two dispatch traces x64 drew twice
inside each of 439 confirmed hidden intervals. ARM64 drew zero times in
all 402 intervals. The application and eframe change at `88fb4ba` keeps
processing input while the root HWND is hidden and requests a frame on show.
The two platform archives reproduce every original dispatch result. The
new behavior and the same-host response budgets still need a native run.
[Measured response and source change](rust/rw02-windows-window.md#presentations-while-the-root-hwnd-was-hidden).

The launcher trial timed out before its first visible window on both
Windows targets. The x64 cleanup error obscured the original timeout in
the JSON report. The new fixture records the initial window and cleanup
separately and also exercises an ordinary first launch on the disposable
input desktop. Native ordinary activation remains open. Both Windows hosts
passed the Japanese IME with profile cleanup a third time and passed all
sixteen realtime transport cases. Each still had one 96-DPI console output.
[Complete native archives](rust/rw02-native-gui.md#native-follow-up-at-8091469)
· [Launcher procedure](rust/rw02-instance.md#ordinary-second-launch-of-the-windows-gui).

The Rust study at `b7190ea` updated one known physical row on each of six
finalized copies from three genuine legacy writers. Independent review
reproduced all twelve before/after files and confirmed all 36 shipping C#
readbacks. It found a stale-value reporting error, permissive direct scratch
file modes, and a C# readback that ignored a live WAL. The correction at
`5d4ce2d` passed all thirteen Fedora checks, including a committed WAL and
direct output with umask 000. Independent re-review closed all three fixture
findings. Twelve new directories and 24 files had the required permissions,
both readers refused a separate live WAL, and all 144 lookup/list observations
matched raw SQL.
[Known-row update and independent findings](rust/rw02-legacy.md#updating-a-known-row-on-finalized-copies).
At `3b4854d` both Windows architectures passed all thirteen notification
scenarios. Their nonrecursive watch reported the direct child directory's
metadata and the direct file's creation and change. Both Ubuntu targets
passed all fifteen scenarios. On each Windows host the candidate guard
again excluded the other writer across two sessions of the same elevated
account. The fixture started and restored Secondary Logon. Its standard-user
probe stopped during the trust-level query before either writer ran.
Installed old/new handover and ordinary-user exclusion remain open.
[Four-platform run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099706),
[Window comparison](rust/rw02-windows-window.md) and [watch delivery](rust/rw02-watch-events.md).

The Windows watch fixture now exercises the ordinary 32 KiB notification
buffer with a bounded batch of 512 synthetic files. An independent review
checked request lifetimes, full replacement inventories and cleanup. Its
timeout finding was addressed by running the compiled test as the Python
parent's direct child. A local run of the pinned Cargo compiler exposed its
test-program layout under `debug/build`. The runner now validates the program
from Cargo's compiler message on every host. Eight portable controls and
Clippy on both Windows targets passed. At clean revision `21e07c4` Fedora
ran the same entry point and passed all fifteen watch scenarios. At
`7517e3b` both Windows hosts observed real notification loss, registered
a new watch and recovered all 514 files. Each passed fourteen scenarios.
All four targets also passed the new offline Cargo dependency boundary
checks. [Four native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460118).
[Notification loss trial](rust/rw02-watch-events.md#windows-notification-loss-and-recovery-trial).

The .NET reference, PR CI, CodeQL and dependency submission completed
successfully at the same commit. Both Windows archives at `3b4854d` reached
six recovery cases and 144 C# checks each. Inside each test VHD, Windows
reported disk-full error 112, SQLite reported code 13 and the supervisor
measured zero available bytes. The Rust worker then declined a CRLF-terminated
release command. Both VHDs detached. Revision `d708301` sends the exact LF
acknowledgement. A private Linux tmpfs reproduced the original failure and
recovered with the corrected sender. The complete Fedora trial passed all
eight cases and 208 C# assertions. At `7517e3b` Windows x64 and ARM64 each
completed all eight cases and 208 C# assertions. Both path comparison modes
recovered after zero free bytes and detached their VHD. All 465 indexed
files and 150 retained sources per Windows archive matched their hashes.
The native feasibility workflow now runs this Windows trial independently of
the desktop performance measurements and retains its entire evidence directory.
[Compatibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099738)
· [Desktop and storage](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730).

The standard native Linux x64 entry point at clean revision `c47d9b1`
passed all ten steps, including 36 Rust tests and 5,844 comparisons to the
C# oracle. The new offline Cargo graph check verified the roles of all five
workspace crates. Eight regression cases cover actual Cargo resolution,
development-only features and target-specific renamed or build dependencies.
[Architecture check](../tools/rust-qa/workspace-boundaries/check.py).

Revision `26ed5dd` compares two non-tearing DX12 presentation modes and
records their actual timing during scans. Revision `27ade4b` records
guarded keyboard submission and refreshes both Windows text interfaces
after Delete. Revision `e575bb3` accepts the observed token flag and
Japanese language representations in the respective native fixtures.
The [strict display checks](rust/rw02-windows-display.md) at `6a88744`
require a real mixed-DPI or RDP session when that qualification is selected.
The [filesystem adapter](rust/rw02-filesystem.md) at `f538828` declines
missing file identifiers. All eighteen Linux filesystem checks and Clippy
for Linux x64 and both Windows targets passed. Both Windows targets then
passed the native NTFS and encrypted SMB tests at `a66e045`. Revision
`88fd180` also checks the current identity of the held file. An independent
review and native tests on all four hosts passed. Linux ran 19 filesystem
checks per host. Windows ran 16 per host on local storage and again over
encrypted SMB. Both NTFS hosts observed a distinct short alias. The ARM64
SMB share also provided one. Both Windows storage VHDs returned FAT legacy
file identifiers across one rename. An independent review of `16781c2`
closed five findings in the opt-in adapter fixture. A Fedora repeat passed
eight recovery cases and all 208 C# assertions, with 476 evidence hashes
verified. At `8091469` both Windows hosts completed all eight cases and then
read and renamed a 45-byte file on the private FAT volume through the Rust
adapter. The held handle and the new name returned the same bytes. The
independent GUID readback confirmed the renamed file and the mount was removed.
[FAT16 adapter result](rust/rw02-filesystem.md#ordinary-fat16-adapter-on-native-windows-2026-11-22)
· [Independent recovery review](rust/rw02-storage-faults.md#native-windows-fat16-follow-up-at-8091469-2026-11-22)
· [Four native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343481).

The appearance-enabled desktop at `a66e045` passed all eleven fixed
Fedora X11 budgets over three 100,000-file runs. Median startup was
194.18 ms. Scan p95 was 5.60 ms to close and 1.95 ms to reopen.
[Paired .NET and Rust measurements](rust/rw02-performance.md#system-appearance-on-fedora-x64).

At `966b861` the Linux x64 storage fixture passed four real process kills,
two SQLite page limits and two 8 MiB tmpfs exhaustion cases. An independent
reviewer replayed all eight recoveries and 208 C# assertions, rejected 16
altered snapshots in both languages and verified all 453 evidence hashes.
The two previous review findings are closed for this experiment.
Ubuntu x64 and ARM64 each repeated all eight cases and 208 C# assertions
in the native run at `a66e045`. All 453 files in each evidence inventory
matched the archive. The later Windows recovery results are recorded above.
Production migration and installed rollback remain open.
[Storage sources and evidence](rust/rw02-storage-faults.md).

At `3b4854d` both Ubuntu jobs repeated all eight recoveries. Each archive
contained 465 of 466 indexed evidence files. The omitted 78-byte Git
attributes file matched the original commit when verified separately. At
`93d424a` the source snapshot preserves its logical path and bytes under a
visible artifact name. Fedora passed all eight recoveries again, and all
469 evidence files and 150 sources survived the local ZIP round trip.

The combined dependency assessment at `f22015a` built the native
Linux x64 executable offline and relinked a changed Wayland binding. A real
Plasma panel at `26b7aac` reopened the hidden application twice. At `6f55f36`
the visible panel followed system light, dark and high-contrast settings
and recovered after a portal service restart. Both Ubuntu hosts repeated the combined offline relink, the native
Noble portal comparison and light/dark changes at `a66e045`. Ubuntu x64
repeated two actual Plasma panel clicks. Both Windows combined smoke tests
passed. The earlier scan trials rejected a stale filesystem input digest.
The four subsequent archives at `3b4854d` contain the capacity, tray
and scan-time results above. Mixed-DPI and RDP require an appropriate
Windows session.
Released distro portals on the tested Linux hosts still refuse the required
cooperative file lock. [Combined build](rust/rw02-combined-profile.md),
[Plasma](rust/rw02-plasma.md), [appearance](rust/rw02-appearance.md) and
[acceptance matrix](rust/acceptance.md).

At `1efe254` the private Noble x64 trial distinguished a host without
file-lock support from an ordinary busy file on the same retained grant.
The packaged and pristine services reported `UnsupportedFileLock` on three
attempts each. With the existing backport, the reader acquired the file,
reported `FileBusy` while an independent writer held its lease, and acquired
the same file again after release. An independent reviewer verified the
reader and descriptor identities, the source hashes and all three native
service receipts. [Native portal evidence](rust/rw02-portal-noble.md).

The [current native desktop assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730)
uses `c5606ec` for the scan workload,
`c19a88e` for tray input ownership, `048cc27` for the disposable writer
service and `0ed4dc4` for the locked Windows WAL-index capture. The tray
review closed all three findings. The separate VHD review closed its
parameter-layout finding at `2a49051`. At `daf7d85` Fedora repeated all
eight storage cases, including six portable cases before the volume
trials. The 14 workflow security checks passed. Cargo version-update
configuration is prepared on the rewrite branch at `54fac8b`.

At `8b64330` and `7517e3b` native Windows x64 rebuilt the published import
library byte-for-byte with MSVC. The independently reconstructed LLVM
library and the published library both ran the actual winit event loop with
the same 105 imports from eleven DLLs. All four linker responses and four
symbol maps matched their receipts. Both maps per run attributed the two
executed bindings to the selected library. [Native import evidence](rust/rw02-windows-imports.md#native-windows-x64-reconstruction).

## Windows directory identity at cd1d7d7 (2026-11-21)

Both Windows runners traced the failed subscription to `ReOpenFile`.
Opening the same volume and 128-bit file ID succeeded on both. The revised
watch adapter uses this identity and checks the second handle before
starting asynchronous reads. It passed Clippy for both MSVC targets.
The same diagnostic revision again passed all fifteen scenarios on each
Ubuntu target. Windows event delivery and cancellation await a native
run of the revised adapter. [Native receipts](rust/rw02-watch-events.md#distribution-inputs-and-integration).

## Native watch registration at 45dc03b (2026-11-21)

Ubuntu x64 and ARM64 each passed eight unit tests and fifteen real watch
scenarios, including a 16,384-event kernel overflow and renewed coverage
after a directory was replaced. Both Windows targets passed seven unit tests
and returned Windows error 5 before the first native subscription was ready.
The next run records the failing operation and checks independent handles
to the same synthetic directory. The native Windows watch remains open.
[Four verified watch archives](rust/rw02-watch-events.md#distribution-inputs-and-integration).

## Native watch hints, platform logging and Windows desktop follow-up (2026-11-21)

Three Fedora x64 runs of the reviewed watch adapter passed eight unit checks
and fifteen native scenarios each. A real inotify queue overflowed at the
unchanged 16,384-event limit. Cancelling an inventory kept the previous
baseline pending. A second identity check detected a directory replaced
during watch registration, and the renewed subscription observed its next
edit. The completed runs used the same ELF binary. Both MSVC targets passed Clippy.
The four-target native feasibility workflow now includes this adapter.
[Detailed observations and hashes](rust/rw02-watch-events.md).

The Windows x64 and ARM64 platform log steps at `72fff40` passed. Both
Ubuntu jobs failed their logging step. A native Ubuntu 24.04 userspace
reproduced systemd 255.4's missing cgroup root. It delivered all six records
after a read-only mapping of the current test process’s cgroup. The writer
had zero effective capabilities. [Windows jobs and local Ubuntu receipt](rust/rw02-platform-logs.md).

The next GUI assessment compares retained Windows handles and smaller
DX12 allocations with the existing reference budgets. Independently reported
writer trials exercise ordinary inherited authority and verified standard
users across two sessions. Native results for those changes are pending.
Both private-desktop input steps at `72fff40` passed. Replaying the earlier
desktop reports selected the original desktop on x64 and the fixture desktop
on ARM64. [Retained GUI](rust/rw02-windows-window.md),
[writer authority](rust/rw02-cross-session.md) and
[desktop selection](rust/rw02-windows-desktop.md).

Both Ubuntu jobs at `72fff40` met all eleven same-host resource limits.
The downloaded archives confirmed the same systemd failure on both native
architectures. Windows x64 passed ordinary mixed-direction editing and
replacement-window input. The independent compatibility, native feasibility
and PR CI workflows passed. [Hosted measurements](rust/rw02-native-gui.md#native-follow-up-at-72fff40).

All four archives at that revision matched the Actions SHA-256 sums and
passed their CRC checks. Both Windows hosts met six of nine measured WPF
limits. The ETW recorder's SDK compilation error prevented all scan timing
comparisons. Windows x64 NVDA read all seven cues and the password masks.
Both text interfaces still returned 18 characters after Delete. Both hosts
installed and removed Japanese Basic Typing without reaching a composition trial.
The Ubuntu Noble package and its unmodified rebuild refused read leases.
The private backport passed 42 lock operations. Three native x64 builds
reproduced the same executable hashes. [Windows receipts](rust/rw02-native-gui.md#native-follow-up-at-72fff40)
and [Noble comparison](rust/rw02-portal-noble.md).

Orca's four ordered field and role announcements, three password masks and
non-silent private audio passed on both X11 and Wayland in Ubuntu Noble and
Fedora x64. The hosted Ubuntu ARM64 speech result is pending. The Windows
display recorder now checks the actual WTS transport and window DPI on each
available monitor. Both older Windows desktops had a single 96-DPI screen.
[Linux speech evidence](rust/rw02-ubuntu-reader.md) and
[Windows display evidence](rust/rw02-windows-display.md).

## Four hosted desktop results and Windows follow-up (2026-11-21)

Both Ubuntu jobs passed every step at `8a8adaa`. Each met all 11 paired
.NET limits with three 100,000-file trials. Both also passed actual renderer
replacement, Mozc, GNOME monitor changes and installed Flatpak grant/revocation.
On Windows x64 NVDA produced the seven expected announcements. The subsequent
clipboard clear failed. Windows ARM64 produced the first label. A full-screen
WWAHost window covered the test field on its active console. The private
desktop was restored on both architectures after its initial window enumeration
failed. Each Windows host exceeded three of nine limits, for visible working
set, idle close and idle reopen. All four ZIP digests and CRCs were verified.
[Archive inventory](rust/rw02-native-gui.md#native-follow-up-at-8a8adaa) and
[stack decision and remaining work](rust/rw02-stack-decision.md).

Commit `e80c205` added a real native Windows 100,000-file worker and independent
NTFS completion checks to the paired WPF and Rust trials. The local fixture
suite passed 23 tests with one Windows-only case. The next native jobs also
exercise the revised selection/foreground observers, the ordinary mixed-text
field, the native Japanese IME and the platform log readbacks. RW-02 remains
open. [Windows performance](rust/rw02-windows-performance.md),
[Windows text](rust/rw02-windows-text.md), [input method](rust/rw02-windows-ime.md)
and [native logging](rust/rw02-platform-logs.md).

## Intel Wayland presentation and idle checks (2026-11-21)

Three independent Fedora x64 sessions recovered from loss of the Intel
render device and resumed on llvmpipe. Both real adapters offered Mailbox on
their Wayland surfaces. In each run the regular filename field retained
text and focus, accepted the next key, and drew the change. The original
worker processed a new synthetic file. Six 15-second visible or hidden
idle intervals recorded zero application buffer commits. The output was a
private Mutter virtual monitor driven by an Intel render node. [Native
observations and source hashes](rust/rw02-wayland-recovery.md).

## Native log adapter and hosted desktop results (2026-11-21)

The new Rust logging crate passed the native Fedora x64 file and journal
comparison against the shipping .NET provider. Twelve file records survived
reopening. An isolated systemd journal preserved six distinct messages and
their priorities. Its writer reported zero effective capabilities. The
Windows implementation passed Clippy checks against each pinned MSVC target.
Windows native Event Log readback and Ubuntu native journal readback remain
open. [Receipts and reproduction](rust/rw02-platform-logs.md).

At `8a8adaa`, both hosted Ubuntu architectures passed native Mozc composition,
GNOME output scaling and installed Flatpak access and revocation under X11 and
Wayland. Windows x64 passed the complete DX12 replacement-window edit,
including restored focus and changed pixels. The same-account cross-session
test failed on both Windows hosts. [Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642).

## Native desktop follow-up and Windows writer ownership (2026-11-21)

The integrated Linux x64 GUI recovered and accepted a real edit on both X11
and Wayland after an application-owned device was destroyed during painting.
The separate Vulkan fixture now waits for its submitted queue work to finish
before returning a controlled device-loss result. A repeat of the Linux .NET
reference with 20,000 synthetic files reached every measurement phase after
resolving the exact .NET 10 targeting pack from the SDK. The established
100,000-file budgets remain the acceptance reference.
[Graphics observations](rust/rw02-graphics.md) and [resource evidence](rust/rw02-performance.md).

An isolated Ubuntu 24.04 x64 userspace reproduced the installed Flatpak
launcher's missing system-bus socket. With an isolated empty bus and the five
empty device directories required by Flatpak 1.14, the installed app passed
parented folder selection, grant readback, revocation and notification on both
X11 and Wayland. The next hosted run repeats the checks on both architectures.
[Ubuntu component hashes and native results](rust/rw02-portal-dialog.md).

Five tests for the cross-session driver passed locally, including file-lock
exclusion and reacquisition in two real POSIX sessions. Two distinct native
Windows sessions still need to pass. Six portable-reader parser and cleanup
tests and the window-targeted pointer sequence passed locally. The native
desktop jobs exercise those changes on both Windows architectures.
[Cross-session checks](rust/rw02-cross-session.md) and [Windows screen reader](rust/rw02-windows-reader.md).

## Native GUI checks at the integrated revision (2026-11-21)

At `8b071ab` the four native GUI builds reproduced their reviewed package
and feature inventories. Ubuntu x64 and ARM64 passed all three filename
editing cases and eight glyph controls in the integrated UI, and both
passed X11 and Wayland lifecycle, accessibility and host folder chooser
checks. All four compatibility jobs, all four Rust feasibility jobs and
all eight PR checks passed. The separate desktop assessment still has
failures. The Ubuntu jobs stopped before the paired performance measurements
and installed Flatpak selection. Windows x64 received the device-loss
callback and created a replacement WARP device, then exposed two HWNDs
during teardown. ARM64 still refused foreground input. NVDA initialized
with OneCore on both hosts but did not reach the application's speech checks.
The new Windows fixtures measure desktop availability and same-host WPF
budgets. Their native results are pending.
[Assessment run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452),
[Windows desktop fixture](rust/rw02-windows-desktop.md)
and [resource measurements](rust/rw02-windows-performance.md).

## Four-host IPC, native ARM64 relink and desktop checks (2026-11-21)

All four native hosts passed six old/new activation and profile-lock
observations at `5895c0b`. The ARM64 Microsoft toolchain reproduced the
published Windows import library byte-for-byte. Three independently linked
test images agreed with 64 processor feature results, and the rebuilt
transport passed all 15 loopback cases. The four compatibility jobs, four
Rust feasibility jobs and eight pull-request checks passed. Desktop assessment
still had failures. Windows ARM64 could not obtain foreground input, both
Windows font observers stopped at a Windows-1252 console write, and Ubuntu
did not supply the requested Anthy package.
[Old/new results](rust/rw02-instance.md#native-results-on-all-four-targets),
[ARM64 source reconstruction](rust/rw02-windows-imports.md),
[desktop run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264)
and [pull-request checks](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831858586).

## Integrated native GUI text and rendering (2026-11-21)

The same Linux x64 GUI executable, SHA-256
`80898c73bf97c9d6622ef837cd5361810b041e5d007a1fe742d32ad7921c1002`,
passed mixed-direction selection and editing in the ordinary filename field,
eight rendered glyph controls, and restoration of input after a controlled
graphics loss. On GNOME Wayland it also committed Japanese text without a
presentation override. The source review covers the exact features and inputs
of all 235 packages on each Linux target and 135 on each Windows
target. Native execution of this revision on the three other targets is
pending. [Text and source receipts](rust/rw02-gui-dependencies.md) and
[graphics observations](rust/rw02-graphics.md).

## Older portal hosts and signed Flatpak test runtimes (2026-11-21)

On Fedora x64, seven control runs covered both GTK chooser backends, the
registered and unregistered host paths, real installed Flatpak grants and
revocation, and GNOME notification and autostart. All 54 indexed files matched.
The signed public freedesktop 26.08 metadata supplied the pinned runtime
commits for both Linux architectures. The hosted jobs now test host selection
separately from attributed Flatpak actions. Ubuntu 24.04 lacks `ibus-anthy`.
Its failed package setup at `5895c0b` led to separate provisioning for GNOME
and its available Mozc engine. Its independent IPC tests passed on both native
Ubuntu hosts. [Portal evidence](rust/rw02-portal-dialog.md) and
[hosted runs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264).

## Windows screen reader fixture (2026-11-20)

The new disposable Windows scenario pairs UI Automation with NVDA 2026.3.1
speech records. Three local regression tests passed for ordered labels,
protected utterances and partial log writes. The native x64 and ARM64 runs
must still demonstrate actual reader output.
[Inputs, isolated profile and evidence requirements](rust/rw02-windows-reader.md).

## GNOME Wayland composition and mixed monitor scaling (2026-11-20)

Fedora x64 completed real IBus Anthy composition in the Rust filename field
with Mesa Mailbox. A single window moved between monitors and produced the
expected 100%, 200%, 125% and 100% buffers. The default presentation case
lost the composition after preedit. All four GNOME indexes and both existing
Orca regression receipts matched the retained files. The Ubuntu jobs now
exercise the combined scenario on both native architectures.
[Wayland observations and open compositor limits](rust/rw02-wayland-input.md).

## Native Linux graphics loss and recovery (2026-11-20)

Fourteen X11/Wayland cases on Fedora x64 exercised initial adapter failure,
device destruction, a software-driver `VK_ERROR_DEVICE_LOST`, repeat failure
and an unrelated application panic. The isolated recovery variant retained the
worker, draft and focus across an Intel-to-llvmpipe switch. New input produced
observable frames. All 71 indexed artifacts matched their hashes. Integration
in the shared build and Windows DX12 recovery remain open.
[Adapters, controls and native evidence](rust/rw02-graphics.md).

## Bidirectional filename editing (2026-11-20)

The released egui 0.37 selected the wrong logical character in mixed Arabic
filenames. With the upstream caret correction, Linux x64 passed the same four
native text cases, including Japanese glyphs, mixed digits, pointer deletion
and left/right movement. The selected candidate adds one runtime dependency,
`unicode-bidi` 0.3.18. Its Unicode table was reconstructed from upstream data.
The four-host workflow now runs the corrected fixture. Integration in the
shared GUI and repeat measurements remain open. [Native comparison, original
fonts and exact source review](rust/rw02-font-coverage.md).

## Hosted Windows input and Ubuntu portal results (2026-11-20)

At `2e7ed89`, Windows x64 passed the entire keyboard, password and Unicode
clipboard scenario. On ARM64, UI Automation returned the expected names and
protection, while the observer could not acquire the foreground. It sent no
keys. Native ARM64 reconstructed the same LLVM import archive twice, then
stopped before MSVC setup. Both Ubuntu architectures passed the tray and
real FUSE tests and encountered a missing host Registry in the separate chooser
case. All four standard Rust jobs and eight general PR jobs passed. The desktop
workflow recorded one passing and three failing jobs. The follow-up initializes
the ARM64 build shell per step and retries foreground only on the owned window.
[Desktop results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828363871),
[standard Rust checks](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828363958)
and [PR checks](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828375760).

## Native old/new activation and file guard (2026-11-20)

Two Fedora x64 runs passed six process-level observations. The shipping .NET
coordinator and Rust fixture activated each other, a second Rust writer was
refused, and orderly and abrupt exit both released the native file lock. The
shipping program could still start while the Rust file guard was held. The
four-host assessment now includes the same fixture. Windows cross-session
handover remains open. [Source and run receipt](rust/rw02-instance.md).

## Installed Flatpak dialogs, notifications and autostart (2026-11-20)

Five Fedora x64 runs exercised the real GTK portal and a temporary installed
Flatpak. X11 and Wayland both verified the parent window, cancellation and
selection. A fresh process lost access to the selected grant after revocation.
GNOME Shell displayed and withdrew the notification. Its Background portal
created and removed the app's autostart file and respected explicit denial.
All 25 indexed evidence files matched their hashes. The next native Ubuntu
runs cover the registered host application's folder picker on both architectures.
[Reproduction, images and source evidence](rust/rw02-portal-dialog.md).

## Four native YAML runs and Windows input (2026-11-20)

At `11e4e6f` all four native YAML runs passed with identical filtered sources
and independently checked evidence. Both Windows hosts passed WScript
readback of the private and known Startup shortcuts. Both observed German
UI Automation names and password protection. The x64 input test encountered
a sharing violation while reading a live log. The ARM64 observer could not
foreground the owned window, so it sent no keys. The follow-up reads the active
log with read/write sharing and checks the input desktop as well as the HWND
and PID. [YAML evidence](rust/rw02-yaml.md) and [Windows input and Shell results](rust/rw02-native-gui.md#reproduction).

## Native Ubuntu tray results and clean reference build (2026-11-20)

At `11e4e6f` both Ubuntu architectures passed the eight-step tray-owner
test and the full 183/116-assertion YAML comparison. All 204 files in each
YAML evidence index matched their hashes. The Documents oracle failed before
launch because bubblewrap could not create a mount point under read-only
Core sources on a clean checkout. Binding only tracked source files fixed
the build locally and preserved both reference DLL digests. Semantic FUSE
results for Ubuntu still require the rerun.
[CI run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44825008977)
and [Linux service evidence](rust/rw02-linux-services.md).

## Windows ARM64 import reconstruction (2026-11-20)

All 20,551 symbols in Microsoft's original ARM64 import library matched the
three WinMD sources and 371 C baselines. Two LLVM rebuilds produced identical
libraries. The actual Rust binding used by ring produced the same ARM64 PE
bytes with the original and reconstructed library. The offline source replay
checked all 152 registry archive pins in the transport graph. Its next
Windows ARM64 assessment runs the native observer, MSVC generator and all
15 loopback cases with the reconstructed library.
[Reconstruction receipts and source archive](rust/rw02-windows-imports.md).

## X11 composition and native Orca output (2026-11-20)

At the GUI source in `6c953e3`, the private Fedora X11 test received
a nonempty preedit and committed `あ` from IBus Anthy. Independent AT-SPI
read the committed text. Both X11 and Wayland runs passed the keyboard and
language scenarios with Orca speaking the expected labels and protected
input. Both produced real eSpeak samples on a private ALSA file device.
Wayland composition, broader font coverage and accessibility on the other
native targets remain open. [Desktop input evidence](rust/rw02-native-gui.md#native-composition-and-screen-reader-output).

## Native X11 resource comparison (2026-11-20)

Under three 100,000-file scans, the Rust GUI and synthetic inventory worker
met all 11 precommitted reference bounds on Fedora x64/X11. Median startup
was 176.99 ms. Visible and hidden RSS were 125.617 MiB. The median of the
three close p95s was 10.51 ms, with one individual p95 at 15.76 ms against
a 15.61 ms bound. Reopen was 1.44 ms. Native presentation and XDamage
counters both stayed at zero during idle and rose after reopen. The hidden
worker found a newly created file after 4.82 seconds and drained at Quit.
The exact executable passed all four lifecycle cases and keyboard checks on
X11 and Wayland. The other native environments and graphics recovery remain
open. [Paired runs, rule and artifact hashes](rust/rw02-performance.md#paired-x11-measurements).

## Real portal grants, SMB and desktop input (2026-11-20)

Three Fedora grant runs added an in-grant symlink to a readable control. The
adapter's own policy refused both existing symlinks. Independent review closed
the earlier ambiguous refusal and verified the private daemon builds, source
bindings and YAML archive. The [service evidence index](../tools/rust-qa/linux-services/evidence.sha256)
binds the strengthened runs on the stock, pristine and patched daemons.

The native Ubuntu assessment now includes the same tray ownership and FUSE
grant tests, with a separate read-only offline .NET reference build. The
Fedora reference build completed with zero compiler warnings or errors.
Hosted observations for these two new steps remain pending.

On Windows x64, both independent shortcut readbacks passed. The shell accepted
the icon, reported the notification shown, and accepted re-registration.
The native Windows ARM64 shortcut readbacks and cleanup passed, while the
independent PowerShell readers timed out and Explorer refused the icon.
The next candidate run tests the scripting hosts for each capability before
launching the native probe. Both Windows targets passed the updated cross-target
Clippy check, and five host-selection and cleanup regressions passed locally.
[Windows Shell evidence](rust/rw02-windows-services.md#native-observations-on-both-windows-architectures).

On Fedora x64 both the shipping .NET reader and Rust encountered `ENOSYS`
when requesting their shared upload lock through a real Documents grant.
Both acquired it on a private build of 1.22.1 with the upstream flock fix.
Cross-view cooperating writers received `EAGAIN` while the reader held its
lock and could write after release. The independent tests also verified
write refusal, publication, cancellation and revocation through the portal.
The native tray service recovered from watcher replacement and ignored a
late acknowledgement from the prior owner. [Linux service and portal evidence](rust/rw02-linux-services.md).

Both native Windows targets passed 13 filesystem tests over encrypted SMB
3.1.1 at `4961746`. Both Ubuntu architectures passed four native GUI lifecycle
cases and the complete AT-SPI keyboard, language, protected-field and
clipboard scenario under X11 and Wayland. [Filesystem evidence](rust/rw02-filesystem.md#four-native-hosts)
and [native desktop evidence](rust/rw02-native-gui.md).

## Cross-platform source archive identity (2026-11-20)

At `4961746` the Ubuntu YAML jobs correctly refused the compressed bundle
digest from Fedora. Both archives contained the same 19,486,720-byte tar as
the local reference. The source inventory now binds this canonical tar to
`f4caf0051b7bfd73f366bf3918721ddc6f0ebd35dd526fed1ddbd1335a8cab05`.
All package checksums, filtered files, licenses and target features matched
the previous inventory. The new local run passed all 13 steps and verified
all 204 indexed evidence files. Four native reruns are required for YAML.
[Source evidence](rust/rw02-yaml.md#reviewed-inputs-and-corresponding-sources).

## Native Linux lifecycle and SMB fixture follow-up (2026-11-20)

Both Ubuntu targets passed all four native GUI lifecycle cases on X11 and
Wayland at `06298d9`. The input observer then timed out on an empty AT-SPI
desktop. The revised fixture uses an in-memory settings backend on its
private bus and checks the application's accessibility tree by process ID.
Local X11 and Wayland both passed the full input case with the change.
[Native assessment](rust/rw02-native-gui.md).

On both Windows targets the temporary SMB share passed the ACL, encryption
configuration and UNC marker checks. The connection query then supplied a
parameter that the runner's cmdlet does not support. Filtering the returned
connections by the fixture's exact share name preserves the negotiated
dialect and encryption checks. Native Rust operations over SMB still need
the follow-up run. [SMB job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44818255768)
and [cmdlet reference](https://learn.microsoft.com/en-us/powershell/module/smbshare/get-smbconnection).

## YAML round-trip and filtered build inputs (2026-11-20)

The [YAML feasibility fixture](rust/rw02-yaml.md) passed 183 Rust differential
checks across 38 synthetic cases and 116 assertions reading the Rust-written
files through the production .NET reader on Linux x64. Cases include repeated
keys, aliases, explicit nulls, absent fields, unknown keys and integer
spellings. The offline release build used a fresh Cargo home and a filtered
source bundle with SHA-256
`b453c3cb5bc96839ae7766d40beae9b7dc97bea3ec1860150babb5b981d15714`.
The bundle retained 1,571 source files and 68 original notices. The source
filter, Rust parser budgets, formatter and Clippy passed. All 203 indexed
evidence files matched their hashes. Only the fresh run output is included in
the hosted artifact. Results for the remaining native hosts and migration
verification are pending.

## Windows desktop lifecycle and native service probes (2026-11-20)

Windows x64 and ARM64 each passed all four native DX12 lifecycle cases at
`167a03d`. A separate Windows observer confirmed zero show events on a
never-activated background start. The four downloaded assessment archives
matched the Actions digests and the nested SQLite and network evidence
hashes. All four hosts backed up both live WALs, passed 40 C# readback
assertions, and completed 15 isolated TLS/polling/WebSocket cases.
[Per-host results and archive digests](rust/rw02-native-gui.md#four-native-assessment-archives).

The [Windows services fixture](rust/rw02-windows-services.md) adds real Shell
icon/notification requests, a private-desktop fallback and per-user COM
shortcuts with independent WScript and UI Automation observations. Both
target ABIs passed cross-Clippy and the three recovery cases passed locally.
Native service results come from its dedicated Windows job steps.

## First hosted desktop and storage assessment (2026-11-20)

At `167a03d` the SQLite and network steps passed on Windows and Linux x64 and
ARM64. The GUI on the two Ubuntu runners reached Clippy and then Bubblewrap
was denied the operation to set up the private loopback interface. The GUI
executable did not run there. The job now probes the distribution launcher
and, on restricted disposable Ubuntu hosts, provisions an owner-controlled
copy of the launcher with Ubuntu's per-executable user-namespace permission.
It verifies the caller UID, runs the existing isolated fixture, and removes
the temporary profile and executable at job end. The rerun is the evidence
for this provisioning change. [Assessment run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44816389612)
and [Ubuntu user-namespace policy](https://discourse.ubuntu.com/t/ubuntu-24-04-lts-noble-numbat-release-notes/39890/1).

The [general PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44815614962)
passed all eight jobs at `7ba7056`. Its hidden=false smoke check exercised the
retry against the exact uploaded ID. All eight passed again at `167a03d`,
alongside all four [compatibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44816389013)
and [filesystem/codec](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44816389480) jobs.

## Native GUI, storage and transport assessments (2026-11-20)

The development fixtures now exercise three RW-02 paths on a native Linux x64
host. The [GUI](rust/rw02-native-gui.md) with its lazy window lifecycle opened,
closed and reopened on X11 and Wayland. The Linux release build using the
reviewed 232 external packages for that target and two Noto fonts has SHA-256
`06abf418bfefa3a0b21011663e2ba9d234767c6ebc21d87c84f27f52c1bbd4d9`.
The [storage assessment](rust/rw02-storage-inputs.md) verified 31 original source
archives and exercised two live 24,752-byte WALs. The shipping C# readers made
40 successful assertions across the originals and backups. The same WAL
initializer refused future schema 99 before changing either synthetic database.
The [transport](rust/rw02-realtime-transport.md) completed 15 controlled sessions
including scoped TLS, redirects, authentication, limits and inventory recovery.

The next hosted assessment exercises those probes natively with separate
observations on Windows/Linux x64/ARM64. RW-02 also needs the remaining
native desktop services, portal/filesystem coverage, YAML handling and
performance evidence before stack selection.

## First four native Rust feasibility results (2026-11-20)

All four archives from [the clean `4dcccb7` run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44811901356)
matched their published ZIP digests. Each Windows host passed 27 Rust tests,
including distinct NTFS short-name denial. Each Linux host passed 30 tests.
All four passed five window-policy traces and 5,844 C#/Rust scalar comparisons.
Their .NET 10.0.15 reference casing maps are byte-identical. The Fedora map
differs at 55 scalars. [Per-host counts and hashes](rust/rw02-filesystem.md#four-native-hosts).

RW-02 continues with native window, storage, transport and desktop-service
probes. Linux x64 observed the eframe startup flash independently on X11.
Delaying window creation until activation passed hidden start, close, reopen,
missing-tray startup and orderly quit on both X11 and Wayland. Broader native
integration, accessibility, graphics fallback and the Rust resource comparison
remain open.

The general PR CI twice failed to download newly finalized synthetic Pages
artifacts at `4dcccb7`. The logs show the upload IDs and an index response
within one second that omitted them. The API subsequently returned those IDs
and their digests. Retrying an entire job generated new IDs and reproduced
the failure. The nonpublishing smoke check now retries the same ID once after
30 seconds and still requires the tar contents to verify. Its next hosted
run must confirm the result. [Affected PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44811912153).

## RW-02 filesystem review and hosted follow-up (2026-11-20)

The independent [filesystem re-review](rust/rw02-filesystem.md#independent-review-of-the-feasibility-boundary)
closed the staging-acknowledgement and short-name coverage findings in source.
The corrected implementation passed 16 Linux filesystem tests on tmpfs and
Btrfs, including a real rename followed by an injected lost acknowledgement.
The native Windows workflow now requires a distinct working alias and the
protected API's denial. The first follow-up Windows run installed the pinned
compiler and reached Clippy, which requested typed two-byte UTF-16 chunks.
The implementation now uses that form. [Windows follow-up](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44810590778).

Both Linux artifacts of the original hosted feasibility run matched their
published ZIP digests and recorded clean `2ff9880` sources. Their uppercase
maps are byte-identical. Direct comparison to Fedora found 55 differing scalar
mappings. U+019B stays U+019B on the hosted references and maps to U+A7DC on
the local reference. The existing stored key is authoritative during migration.

## First hosted Rust results (2026-11-20)

At `2ff988095045739b6eeb0735750f5ec9aa9baca6` both Linux hosts passed all 27
Rust tests, five window-policy traces and 5,844 scalar comparisons. The two
Ubuntu references each produced 1,449 non-identity Unicode scalar mappings.
The Fedora reference produced 1,504. Each probe used its native reference map.
Migration must preserve stored keys and qualify conversion across legacy
environments before choosing a production normalizer.
[Native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44808944620).

The first Windows runs stopped during toolchain installation. Native Python's
CRLF output appended a carriage return to the checksum field read by Bash.
The installer now emits a binary ASCII record, exercised with simulated
Windows newlines. Subsequent Windows jobs must supply the native results.
Independent source review requested explicit reconciliation after an
unacknowledged rename and observable coverage of distinct NTFS short names.

## RW-02 first Rust native probes (2026-11-20)

The four native Rust distributions are pinned to 1.100.0, compiler
`0ef1bc386059596dada8fb65b50425aab2ea637a`. The verified Linux x64 distribution
ran the workspace locally. Rustfmt, Clippy with warnings denied, 27 tests,
release probe builds, five C# window trace comparisons and 5,844 native scalar
comparisons passed. The workspace lock contains four unpublished first-party
crates. The accepted .NET resource reference is checkpoint `4245831`.

The [filesystem tests](rust/rw02-filesystem.md) ran on tmpfs and Btrfs. The
[legacy scalar probe](rust/rw02-legacy.md) tested both SQLite casing modes and
1,335 reference timestamps. The [realtime assessment](rust/rw02-realtime.md)
identified transport settings that rule out unmodified rust_socketio 0.6.0.
The [GUI review](rust/rw02-gui-dependencies.md) identifies exact source and
notice inputs. Native desktop, network-session, database/YAML and manual
accessibility evidence remain open. The new four-host workflow records Rust
results and regenerated oracle comparisons at the source SHA. Verify its
first run, review the filesystem boundary independently and continue the GUI
and transport assessments.

## RW-02 Linux performance reference measured (2026-11-20)

The Linux x64 .NET reference completed three isolated 100,000-file scans with
35 close and 37 activation responses during traversal. Median startup was
906.63 ms and median hidden RSS was 233.262 MiB. The instrumented compositor
observed zero render passes in the 15-second idle windows and observed a render
after each reopening. The [measurement and budgets](rust/rw02-performance.md)
give the exact build, workload, driver, environment and raw evidence digest.
The Rust comparison on this host and the other native desktop environments
are pending.

At `27f5b02848a51bcdb63b4cf930bc5154c74bbd82`, all four native reference
jobs passed the checked-in golden comparison and all eight PR CI jobs passed.
[Golden rerun](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44803987836)
and [PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44803996983).

## RW-01 accepted and RW-02 started (2026-11-20)

The user resumed `M-RUST-IMPLEMENTATION-20261114` in its original Goal run.
The active chat, branch and open [draft PR #46](https://github.com/VoltKraft/immich-folder-watch/pull/46)
were verified at source `3ca5b0a89d266e61e219239f84d896dc71528ba0`.

The [native reference run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43634286661)
passed on all four targets. Both Windows architectures produced identical golden
files, as did both Linux architectures. The four downloaded archives matched
GitHub's digests. The [native evidence](rust/rw01-native-reference.md) records
the platform path/encoding differences and the nine Linux-specific tests skipped
on Windows. All nine passed on both Linux architectures. The existing
[PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43634333824)
also passed. Every PAR row and security rule has a reference or an explicit
stronger candidate requirement in the [parity mapping](rust/rw01-parity.md).

RW-02 is active. Its first work covers the GUI feature and font audit, the
native filesystem and legacy codecs, and an isolated .NET desktop resource
baseline for side-by-side measurement. The [acceptance record](rust/acceptance.md)
tracks the remaining native gates.

## RW-01 local compatibility baseline verified (2026-11-14)

- Goal remains active under `M-RUST-IMPLEMENTATION-20261114`; selection checkpoint
  `8d517342b0ebc9d0a6379be67ac32272269abded`. RW-01 remains in progress until native
  platform outputs are collected/reviewed. RW-02 dependency research is independent
  preparation; no later gate is declared passed.
- Added the [storage oracle](rust/rw01-storage-contract.md): 29 generated Linux
  files and 215 assertions, with hashes of 10 C#/oracle sources and 28 payloads.
  Added [63 behavior cases](rust/rw01-behavior-contract.md) and five real-view
  [window lifecycle traces](rust/rw01-parity.md). All inputs are synthetic; production
  application code, configuration, state and package dependencies are unchanged.
- Local native Linux x64 checks with SDK 10.0.401/runtime 10.0.12: existing portable
  suite 503/503; existing Linux headless/protocol suite 60/60; new behavior corpus
  63/63; new lifecycle corpus 5/5. Storage export and independent verification pass;
  an intentional ARM64 assertion on x64 fails before fixture generation. Reduced
  Avalonia provenance verification passes. Existing obsolete D-Bus/Bitmap API
  warnings remain; oracle restore reported NU1900 when advisory retrieval was
  unavailable. No skipped application tests in these four executed suites.
- Raw TRX/log evidence is in ignored `artifacts/rust/baseline-results/`,
  `artifacts/rust/behavior/results/` and `artifacts/rust/`. Commands and fixture
  limits are in [development](development.md#rust-rewrite-reference-corpus).
- Independent read-only review checked oracle/test isolation, native architecture
  assertion, source/payload hashes and candidate workflow. No open blocking finding.
  Renamed a success-only journal observation so it does not claim failure atomicity.
  [Security mapping](rust/rw01-security-contract.md) explicitly retains legacy
  future-schema WAL mutation, Windows cross-session writer and config durability,
  IPC deadline and parser-bound gaps as stronger Rust acceptance requirements.
- Prepared `Rust compatibility reference` workflow: four native OS/architecture
  lanes, read-only permissions, exact action/SDK pins, source-SHA artifact names,
  branch/job restriction to `rewrite/rust`, no signing/publication path. New and
  existing workflow security checks: seven passed; four PowerShell-only cases
  skipped locally and retained for Windows CI. Workflow preparation is not execution.
- Next action: commit/push this reference checkpoint, create the authorized single
  draft PR, collect native C# reference evidence including Windows golden output,
  review platform differences, and close RW-01 only after its evidence is sufficient.

## Rust implementation Goal selected (2026-11-14)

- Active milestone: `M-RUST-IMPLEMENTATION-20261114`; fixed RI-AC01 through RI-AC10
  in the [brief](project.md#m-rust-implementation-20261114), RW-01 through RW-07 as
  one assignment. The user's full implementation request supersedes the historical
  analysis-only scope. RW-08/publication remains excluded.
- Actual Goal control returned `active`; run/chat reference
  `01a1db8f-b8ef-7903-8dfc-932f9b39c743`, created 2026-11-14. No token budget was
  requested. This record does not activate or transfer a goal in another chat.
- Verified before changes: `rewrite/rust`, clean tree, HEAD
  `009246552cb4c0091196bab9a58cd64d44e5b629`. Local and live GitHub `main` remain
  `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`; no existing rewrite PR was found.
- Persisted goal boundaries and [acceptance matrix](rust/acceptance.md). RW-01
  synthetic storage/config oracle, behavior fixtures and independent security/
  workflow-trigger audit are assigned with disjoint ownership. No Rust capability
  or native acceptance is claimed at selection.
- Environment: .NET/Rust tools are absent from PATH; `/home/jan/.dotnet` supplies
  only SDK 10.0.203, which correctly refuses the pinned 10.0.401 project. Verified
  `artifacts/flatpak-local-2.11.2/sdk/dotnet --info`: SDK 10.0.401, runtime 10.0.12,
  Linux x64. Baseline tests use this existing SDK and isolated outputs; `global.json`
  is unchanged. The sandbox refused MSBuild's local IPC sockets; an authorized
  execution outside that restriction is running, without application/profile startup.
- Independent static workflow audit: existing `rewrite/rust` pushes trigger no
  shipping CI; PR CI is read-only. Release requires successful same-repository
  push CI on `main` (or explicit dispatch on `main`); downstream publication has
  separate release/manual triggers. No publication workflow is dispatched.
  Local workflow-security suite: six passed, four PowerShell-only cases skipped.
- Next action: finish and run RW-01 fixtures against the C# reference, map every
  parity/security rule, independently review the evidence and then begin RW-02.
  Audit publication triggers before the first authorized branch push/draft PR.
- Template cleanup was already completed on 2026-10-16; no reinitialization.

## Rust rewrite branch established (2026-11-14)

- User selected a dedicated branch for the existing rewrite changes and all
  subsequent rewrite work. Created and checked out `rewrite/rust`, preserving
  planning commit `c123ce9d253d72c928ac83892984a30f2748a576` unchanged.
- Moved local `main` back to its preceding commit
  `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc` with an expected-old-value ref update,
  after securing the planning commit on the new branch. No working files were
  reset and no commit was lost. Local `main` equals the existing `origin/main`
  tracking ref; no fetch or remote update occurred.
- Recorded the branch in AGENTS.md and the brief. Branch/ref checks confirm that
  the seven-file planning change is on `rewrite/rust` and absent from `main`.
  This follow-up changes only branch guidance/status; runtime files, the detailed
  rewrite plan and desktop standard are unchanged. No application tests are
  required for branch organization and documentation.
- Next action: continue review and subsequently selected implementation work on
  `rewrite/rust`. RW-01 through RW-08 remain unstarted. No push, merge, release or
  implementation is performed by this branch migration.

## Rust rewrite analysis and standard proposal (2026-11-14)

- Selected milestone: `M-RUST-ANALYSIS-20261114` / RW-00; completed for analysis
  and planning only, `RUST-AC01` through `RUST-AC06` met. User explicitly defers
  implementation and confirms that all first-party application/GUI code must be
  Rust while native libraries and SQLite are allowed.
  No Goal was requested or started.
- Baseline inspected: clean local `main` at
  `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`, product 3.0.4 and SDK 10.0.401 with
  roll-forward disabled. No fetch; historical CI/catalog evidence is not renewed.
- Prepared [rewrite assessment and migration plan](rust-rewrite-plan.md) and
  [Rust Desktop Standard proposal](rust-desktop-standard.md), with current source
  evidence for egui/eframe, alternatives and native integration. Preferred egui
  selection remains conditional on actual lifecycle/accessibility/GPU/native
  tests, full dependency/license inventory and independently reviewed fonts.
- Recorded exact YAML/SQLite identity/codec contracts, startup authority revocation,
  retained-handle filesystem invariants, single-instance interoperability,
  backup/cutover/rollback rules, four-target packaging and phased acceptance.
  The Windows Event Log message-resource dependency and incomplete notification
  parity are explicitly included. No existing residual risk is marked repaired.
- Updated project/entry/README links and the Unreleased documentation entry;
  corrected the brief's stale SDK description against `global.json`. Product
  sources, build files, dependency pins, versions, release history and runtime
  user data remain unchanged. No Rust scaffold, build, test execution, installation,
  live Immich request, push or publication occurred.
- Validation: independent security/compatibility and GUI/license/reuse reviews
  completed. Incorporated cross-session Windows writer-exclusion and exact startup
  ordering gates; corrected native-toolkit language eligibility and kept locales
  product-configurable. The security reviewer verified the corrections. Local
  Markdown target/anchor checks, code-fence balance, documentation-only scope and
  `git diff --check` pass. Product tests are intentionally not run for this
  documentation-only assignment; no native spike or resolved-graph license
  certification is implied. Keep the final local checkpoint hash in the chat
  handoff; no push is selected.
- Next action: user review/selection of the proposed plan. After explicit
  implementation selection, start RW-01. RW-01 through RW-08 are proposed and
  unstarted; do not infer implementation authorization from these documents or a generic
  continuation prompt.

## Release 3.0.4 published and WinGet submitted (2026-11-13)

- Published [v3.0.4](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.4)
  at 2026-11-13 21:16:48 UTC. The immutable tag points to release commit
  `4149763b7f322603a012aebad5f8a252450eb08b`, which includes the previously local
  completion record `2726821`. Four assets are present: x64/ARM64 Windows MSIs
  and x64/ARM64 Linux Flatpak bundles. No existing release or tag was replaced.
- Exact-revision [CI 43507280827](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43507280827),
  CodeQL `43507279726`, dependency submission `43507280481` and
  [Release 43508333926](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43508333926)
  pass. The installed x64 test was repeated with product version 3.0.4: safe
  refusal preserved all 439 baseline files, normal tray Quit allowed a successful
  retry, all 439 candidate payload hashes matched, and the app started with its
  bundled runtime. Synthetic user data survived and no app file operations were
  deferred. This is safe refusal plus retry, not automatic MSI shutdown.
- Independently inspected the release-build MSIs and matched their full SHA-256
  hashes to GitHub's published asset digests and WinGet entries. x64 has 439 file
  rows, ARM64 438; both contain unconditional BINDIR entries for the EXE,
  runtimeconfig, hostfxr.dll, hostpolicy.dll and coreclr.dll. Both compiled
  sequences are close 1398, guard 1399, InstallValidate 1400, InstallInitialize
  1500, RemoveExistingProducts 1501, RemoveFiles 3500. Native platform and MSI
  ProductVersion 3.0.4 match. The direct CDN transfer was slow; identical complete
  Actions artifacts were inspected after digest verification instead.
- Published MSI SHA-256 values:
  - x64: `419938C3FEC0C113BF0F33DBF1A9BD4A6748DF1E7930ACB20FEC5FC3F265A187`.
  - ARM64: `7669E1DFA319FA012E01DD7D728456716B1A1040478429B4137C7BA7FBFD11DA`.
- [WinGet workflow 43509275890](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43509275890)
  passes and created [microsoft/winget-pkgs#479776](https://github.com/microsoft/winget-pkgs/pull/479776).
  Reviewed all three manifest files: both asset URLs, hashes and distinct MSI
  ProductCodes match; no restricted Icons are authored. At this check the PR is
  open: CLA, PR, manifest, URL, domain, policy and catalog-content checks pass;
  installer scan, installation/metadata validation and completion remain pending.
  Submission is not yet WinGet catalog publication.
- Signed [Flatpak repository deployment 43509273256](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43509273256)
  passes. Flathub follow-up `43509274963` passes preparation and both native
  validation builds; updating an accepted Flathub app is skipped by the existing
  submission configuration. This is not a claim of Flathub catalog publication.
- Release publication and the requested submission/status verification are
  complete; Microsoft validation/merge remain external. Before updating Windows,
  choose Quit in the tray menu and retry any guarded update. ARM64 installation,
  automatic MSI shutdown and post-reboot behavior remain outside the executed
  validation. Final release evidence is recorded in a documentation-only
  checkpoint; released tag and package bytes remain immutable.

## Release 3.0.4 selected (2026-11-13)

- User authorizes publication of 3.0.4, pushing the final MSI validation record
  (2726821), and verification of release CI and WinGet submission.
- Refreshed origin/main: outstanding local commit is only that documentation
  checkpoint; no remote divergence or existing 3.0.4 release was found.
- Preparing a compatible packaging patch with existing dependency/runtime pins.
  Release publication and WinGet acceptance remain pending. Keep main fixed
  during the four-artifact build so its commit-pinned Flatpak guard remains valid.
- Prepared product 3.0.4 and assembly/file 3.0.4.0, dated changelog with tray Quit
  guidance, and generated AppStream metadata. Official SemVer 2.0.0 and Keep a
  Changelog 1.1.0 were checked. No dependency or runtime pin changed.
- Local checks: 12 WinGet generator tests, 18 MSI identity/sequence/refusal tests,
  version/XML consistency and diff whitespace pass. Independent release-path
  review found no blocker. No existing v3.0.4 tag, release or WinGet PR was found.

## Windows MSI correction pushed and exercised (2026-11-13)

- Scoped correction and test harness are pushed on main through
  `6c62d70cefd7b8f686f27534cde180037654ace5`.
  [CI 43491173118](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43491173118)
  passes all eight jobs on that exact revision, including Windows job
  `132112450161`, both compiled MSI architecture/identity/sequence gates and
  the installed-upgrade test. CodeQL `43491174454` and NuGet dependency
  submission `43491172697` also pass.
- Downloaded and reviewed
  [windows-upgrade-evidence](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43491173118/artifacts/14069093498)
  (seven-day retention). Public 3.0.3 ran as PID 5444 in session 2 with its
  app-local runtime loaded. Attempting the candidate upgrade returned 1603 at
  the explicit pre-removal guard; all 439 baseline files, registration and
  synthetic user data remained intact, with no pending application file operations.
- The test selected actual tray Quit command ID 3 using a checked native mouse
  click and required normal exit code 0. Retrying the same MSI returned 0,
  replaced the product registration, and matched SHA-256 for all 439 candidate
  payload files, including hostfxr.dll, hostpolicy.dll and coreclr.dll. Candidate
  PID 9880 started with a responsive WPF window and app-local runtime modules.
  User data preservation, empty deferred-file queue and final uninstall pass.
- Candidate MSI SHA-256:
  `CEC2431D2316CA9F0E82BD556CA2CC0F646B60761E9CE88D9515CA5C25783171`.
  Candidate MSI version 3.0.4 is test-only; Directory.Build.props and published
  release remain 3.0.3. No new release or WinGet submission was created.
- Evidence boundary: this proves safe refusal with a running app plus successful
  upgrade after normal tray closure. It does not prove automatic MSI shutdown,
  ARM64 installed execution, another user's desktop or post-reboot behavior.
  No reboot was requested or performed. Original incident causality remains
  unproven without its original update log. Close the tray application before
  retrying an update that reports the running-process guard.
- The requested push/Windows verification work is complete within these limits.
  Next action is a separately selected release; preserve the guard and this CI
  regression. Additional automatic-shutdown support would be separate work.
  This final evidence update is a local documentation checkpoint after the
  tested push, not another implementation revision or publication.

## Hosted tray input limitation (2026-11-13)

- `2f604e0` / CI `43489599940` again verifies the safe refusal and intact 439-file
  baseline, but posted keyboard messages do not select the verified Quit entry.
  The test fails before retrying; no successful upgrade is claimed.
- Use actual mouse input on the disposable runner, only after checking the exact
  Quit command's rectangle, popup ownership, cursor position and highlighted/
  enabled state. Require normal application exit code 0 and retain all evidence.
  This is test-driver work; the MSI protection remains unchanged. No release.

## Native tray test-driver correction (2026-11-13)

- `5efa9ee` / CI `43487846302` again passes both compiled MSI checks and the
  actual safe refusal with all 439 baseline files preserved. The native test
  helper finds the correct tray receiver and verifies popup command IDs 1/2/3.
- UI Automation does not expose the expected Quit item in this hosted popup;
  the test fails rather than claiming an upgrade. Replace that unsupported
  provider path with native menu keyboard messages, verifying that command ID 3
  is highlighted and enabled before Enter, then require actual process exit.
  No installer guard weakening, forced application termination or release.
- Five focused tests, native-helper compilation, PowerShell parsing and diff
  whitespace checks pass locally. Windows execution remains pending.

## Running baseline preservation verified (2026-11-13)

- Pushed `1af8d80`; CI `43485903150` confirms both freshly built MSI platforms
  and versions pass compiled validation. All other CI jobs pass.
- Real x64 test proves the running 3.0.3 process (session 2, app-local runtime
  modules loaded) causes the explicit guard refusal before removal. All 439
  baseline files, product registration and synthetic user data remain intact;
  no application file operations are deferred. The original incident mechanism
  remains unproven.
- The subsequent test-controlled session-message shutdown did not exit 3.0.3,
  so the overall Windows job correctly failed before retrying the upgrade.
  Replace that test helper with normal tray-menu Quit automation, then rerun.
  Do not present safe refusal as automatic upgrade completion. No release.
- Replacement test helper locates the exact PID-owned tray receiver and menu,
  verifies Quit command ID 3, then invokes that entry with Windows UI Automation
  in a bounded STA helper. Five regression cases and both PowerShell parsers
  pass; compiled native helper checks pass. Actual Windows execution is pending.

## Running-application acceptance findings (2026-11-13)

- Pushed `fe73b4c`; Windows run `43483904049` compiled both MSI candidates and
  passed the compiled sequence gate. Its actual installed upgrade started public
  3.0.3 with its app-local runtime loaded, then failed with MSI 1603 because
  `EnsureAppClosed` detected the remaining process. No product removal began.
  Evidence artifact: `windows-upgrade-evidence`, including verbose MSI logs.
- The CI failure is not a successful automatic upgrade. Preserve the guard:
  do not kill a worker or continue uninstalling loaded files. The service-hosted
  close action could not close this desktop's process; desktop isolation is a
  plausible explanation, not a proven diagnosis of the user's incident.
- Extend the installed test to distinguish automatic completion from explicit
  safe refusal. Refusal must preserve every baseline file, registration and user
  data with no deferred file operations. After owner-desktop graceful shutdown,
  retry the same candidate and require full payload/startup verification. Any
  other error remains a test failure. These execution results are pending.
- Review also identified shared WiX incremental state between architectures;
  isolate/reset intermediate outputs and validate the compiled MSI platform and
  version against requested values so a cached x64 package cannot pass as ARM64.
  No new product version or release is selected.
- Local validation: 31 focused installer/workflow tests pass, including five
  executed refusal-evidence/native-helper test cases; diff whitespace passes.
  Independent review found no blocking issue; HWND ownership is rechecked before
  each native message. Windows COM and actual installation execution remain
  pending on the next exact revision.

## Windows hosted compilation correction (2026-11-13)

- Initial Windows build `43483088598` passed application and focused installer
  tests but WiX compilation rejected the rescheduled virtual action (WIX7009).
  Added the required `override` access modifier to the authored sequence action;
  source regression now requires it. This is why source-only checks did not
  establish compiled-MSI acceptance. No failed build was released.
- Upgrade harness is pushed at `119aff3`; its subsequent run is superseded by
  this compilation correction. Recheck the next exact commit before acceptance.

## Windows upgrade execution selected (2026-11-13)

- User explicitly authorized pushing the MSI correction, checking Windows CI and
  executing a real upgrade with the application running before any new release.
- Pushed `a485e15ed889bb5f6eadbe063330dda657d2d78e` and its diagnosis history;
  initial CI `43483088598` is running. No product version or release changes.
- Preparing an isolated github-hosted Windows acceptance harness: install the
  immutable verified 3.0.3 x64 MSI, start its actual WPF process, upgrade to a
  test-only 3.0.4 MSI built from current sources, compare installed payload and
  configuration, then start the upgraded process. Collect logs and JSON evidence
  and uninstall the disposable test product. No credentials/media/server access.
- The temporary MSI version enables a real major upgrade without changing
  Directory.Build.props or publishing candidate assets to release channels.
  Actual execution and acceptance remain pending.

## Windows upgrade process-order correction prepared (2026-11-13)

- User confirms repair restored startup and selects investigation/prevention.
  Previous installed version is unknown; original upgrade log is unavailable.
  `M-WINDOWS-UPGRADE-RUNTIME-20261113` owns this local implementation scope.
- Parsed released 3.0.3 x64 MSI: InstallValidate 1400, RemoveExistingProducts
  1401, InstallInitialize 1500, RemoveFiles 3500, explicit application close
  3999, InstallFiles 4000. Closing after old-product removal exposes loaded
  runtime files to in-use/deferred-delete behavior. This ordering is verified;
  its role in this user's exact deletion sequence remains a hypothesis.
- Corrected authoring: synchronous close/end-session request with 15-second
  timeout before InstallValidate; Type19 abort if IFW_APP_RUNNING remains set.
  No early deferred termination/elevated action. Removal after InstallInitialize
  permits rollback of old-product removal. Actions live in linked Package scope.
- Verified semantics against WiX 6.0.2 CloseApps.cpp and UtilCompiler.cs: flags
  9 avoid deferred actions, detection property follows the wait, and timeout is
  stored in milliseconds. Sources:
  [CloseApps.cpp](https://github.com/wixtoolset/wix/blob/v6.0.2/src/ext/Util/ca/CloseApps.cpp),
  [compiler](https://github.com/wixtoolset/wix/blob/v6.0.2/src/ext/Util/wixext/UtilCompiler.cs),
  [rollback scheduling](https://docs.firegiant.com/wix/schema/wxs/majorupgrade/).
- Added compiled-MSI read-only COM validation of sequence, guard and close flags,
  called by build-msi before final delivery. Windows CI now builds both MSI
  architectures and runs checker tests. Existing installer payload and user-data
  handling are preserved; no version bump, new dependencies, push or release.
- Validation: 3 source-contract tests, 7 executed PowerShell checker tests
  and 10 workflow-security tests pass. CI YAML parses;
  diff whitespace check passes. PowerShell 7.7.0 was temporarily downloaded from
  the official MIT-licensed project and checked against its published SHA-256.
  Initial PowerShell setup failed on the read-only home cache; isolated XDG dirs
  resolved it. Negative tests now require an explicit validator rejection marker
  and exit code, so a host crash cannot count as a passing rejection test.
- Independent review caught a close-condition allowlist mismatch; it was fixed
  to accept the exact authored OS condition and the fixtures pass afterward.
- Windows limitation: attempted local WiX compilation reports Windows-only
  support and exits unsuccessfully. COM artifact validation and real upgrades
  with a running tray process (including post-reboot file/startup verification)
  remain unexecuted. Local tests do not establish installed-upgrade acceptance.
- Next action: publish the scoped correction with authorization, run Windows CI,
  then execute the running-app upgrade/reboot scenario before a new release.
  Retain the original upgrade log if available to prove the historical mechanism.

## Windows 3.0.3 launch failure investigation (2026-11-13)

- Follow-up user output confirms the installed EXE (200192 bytes) and runtimeconfig
  (529 bytes) exist, but hostfxr.dll, hostpolicy.dll and coreclr.dll are absent
  from `C:\Program Files\Immich Folder Watch\bin`. Direct EXE launch also fails.
  This establishes missing installed runtime files as the immediate startup
  failure, not why they went missing. The published MSI contains all three.
  Next step: repair from the verified 3.0.3 x64 MSI with forced file replacement
  and verbose logging, then recheck files and launch. Repair not yet executed.

- User reports a missing .NET Desktop Runtime dialog after updating to 3.0.3
  through UniGetUI; screenshot identifies x64 apphost 10.0.12. Installed state
  and the actual launched executable path remain unverified.
- Downloaded current public x64 MSI; SHA-256 matches release evidence
  `e2559768224568eaae67db9b19b82d8390720ffb9692cfe6248f69f08042cc6c`.
  Read MSI tables and extracted cabinet without executing Windows code.
  EXE, hostfxr.dll, hostpolicy.dll, coreclr.dll and runtimeconfig all map to BINDIR
  without component conditions. All four PE binaries are x64. Runtimeconfig
  includes NETCore and WindowsDesktop 10.0.12, confirming self-contained output.
- The published payload contains the boot files; this does not establish correct
  installation or upgrade behavior. Existing CI did not exercise an installed
  Windows upgrade/start. No specific installer defect is established yet.
- Requested installed-file presence and direct-path launch checks. The first
  user command was altered during copying and failed as PowerShell syntax;
  no installed-file evidence resulted. Next action: a literal-path file listing,
  then compare installed hashes/launch path and collect host trace if necessary.
- No application, installer, release or system configuration changes performed.

## WinGet policy correction published and verified (2026-11-11)

- Completed `M-WINGET-ICON-ROLLBACK-20261111`. Correction pushed to main at
  `80d0f0cbcb3280466ef787b81cf7baa78815c0fd`; manual `Icons` are no longer emitted
  or required. Legacy icon-bearing input cannot reintroduce them.
- [CI 43107681875](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43107681875)
  passes all eight jobs on that exact revision: Windows/Linux build and tests,
  packaging/tooling validation, both Pages artifact round trips, candidate
  preparation and both native Flatpak architectures. No rerun or workflow change
  was needed. [CodeQL 43107681491](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43107681491)
  passes all four analyses; NuGet submission `43107681388` also succeeds.
- Local evidence: 12 focused tests pass; all three corrected manifests pass the
  official 1.12.0 schemas and are byte-identical to pre-icon generator output.
- [WinGet PR #477862](https://github.com/microsoft/winget-pkgs/pull/477862) is
  confirmed CLOSED without merge. Existing published installers and version 3.0.3
  remain unchanged. No UniGetUI contribution or new release was performed.
- Final verification documentation is committed locally after the checked/pushed
  revision; no further main push is needed for the implementation. The requested
  correction is complete. UniGetUI artwork remains a separate optional follow-up.

## WinGet icon policy correction prepared; rejected PR closed (2026-11-11)

- Selected `M-WINGET-ICON-ROLLBACK-20261111` under explicit correction, PR closure,
  push and CI-verification authorization. Removed the generator's icon requirement
  and emission and the metadata object; updated the changelog/operator guidance.
  Embedded Windows branding, installer fields, versions and release assets remain
  unchanged. No UniGetUI database contribution is selected.
- All 12 focused regression tests pass, including no authored `Icons` and legacy
  icon input suppression. Generated all three manifests for 3.0.3: each passes
  its official 1.12.0 schema and is byte-identical to the pre-icon generator output
  at `169f788`. `git diff --check` passes.
- [WinGet PR #477862](https://github.com/microsoft/winget-pkgs/pull/477862) is
  confirmed CLOSED with `mergedAt: null`. The connector was denied; the existing
  authenticated CLI completed the explicitly authorized closure. Branch retained.
- Rechecked previous CI `43103171839`: attempt 2 has now completed successfully,
  resolving the queued Pages retry without source changes. Previous CodeQL/NuGet
  passed as recorded below. The current correction still needs its own pushed
  revision's CI; previous checks are not reused as that evidence.
- Remote main was refreshed at `6d05b17`; it is an ancestor of local HEAD.
  Push will preserve the prior local evidence commit `cfaccd7` and this correction.

## Generator pushed; WinGet publisher-policy blocker confirmed (2026-11-11)

- Pushed implementation `af7bb8e` and its documentation history to project main
  at `6d05b17907ad8a603fa01ffeeb7463ce7e10d70f` under explicit authorization.
- Exact-head CI [43103171839](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43103171839)
  attempt 1 completed with seven successful jobs: Windows/Linux build/tests,
  packaging lint, Flatpak preparation, both native Flatpak builds and the
  hidden=true Pages round trip. The hidden=false Pages job uploaded artifact
  `13892548202`, then failed because the immediate download did not find that ID.
  This suggests transient artifact visibility, not a proven root cause.
- Requested a targeted rerun of job `130799588814` after attempt 1 finished.
  Attempt 2 remains queued after repeated checks; no passing rerun is claimed.
  The original failure and outstanding runner scheduling prevent an all-green
  CI conclusion. No workflow changes or disabled checks were used.
- NuGet submission and all four CodeQL analyses in
  [43103172344](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43103172344)
  pass. Automatic Release follow-up `43104262729` is skipped; no release created.
- WinGet PR #477862 is OPEN but its hosted Manifest Validation fails with
  `FieldRequireVerifiedPublisher: Field usage requires verified publishers. (Icons)`.
  Verified in check `130798904294` on PR head `c50ef9e`; subsequent validation
  stages were skipped. The initial PR validation and CLA pass. The overall
  "Validation Completed" check does not mean that manifest validation passed.
- Correction to the initial diagnosis/remediation: the JSON schema accepts the
  fields, but a separate publisher-policy prerequisite prevents this package
  from using them. The generator is implemented and pushed, but its icon-bearing
  output is not currently acceptable to WinGet. Existing published 3.0.3 and its
  installers are unchanged; no upstream merge or actual client rendering.
- The [official WinGet policy](https://github.com/microsoft/winget-pkgs/blob/master/doc/manifest/schema/1.28.0/defaultLocale.md#icons---the-icons-for-the-package)
  says icons are populated during validation and must not be authored in PRs.
  Therefore absence in the source manifest alone did not prove absence in the
  served catalog; the initial diagnosis overstated this evidence. A maintainer
  [explains icon extraction](https://github.com/microsoft/winget-pkgs/issues/360963#issuecomment-4254042938)
  from Settings > Apps. No public publisher-verification onboarding was established.
- Final verification records are local only after the published `6d05b17`;
  remote main contains the requested implementation. Next CI action: inspect
  attempt 2 after runner scheduling.
- Recommended follow-up: revise/gate generator icon emission before another
  release submission and contribute to UniGetUI's separate icon database.
  No publisher claim, policy bypass, PR closure or additional external
  contribution was performed.

## WinGet generator publication selected (2026-11-11)

- Selected `M-WINGET-ICON-PUBLISH-20261111` under explicit push authorization.
- Clean working tree at implementation `af7bb8e`; refreshed remote main is
  `e0d1c40` and is an ancestor. Outgoing history includes the implementation,
  its diagnosis and the preceding v3.0.3 release-evidence record. Changes remain
  packaging/tooling/tests/documentation only; no version or workflow changes.
- WinGet PR #477862 remains open and mergeable at `c50ef9e`; upstream acceptance
  is not claimed. Push and exact-revision hosted checks are pending.

## WinGet icon correction implemented and submitted (2026-11-11)

- Completed `M-WINGET-ICON-20261111`: the generator requires and validates an
  immutable PNG URL, SHA-256, file type, resolution and theme, and emits `Icons`
  only in the default-locale manifest. Metadata and operator documentation updated;
  no dependency, application version, installer or release asset changes.
- Downloaded the public PNG pinned to `e0d1c403f261b9c906cc3853a1b7477518b64bf6`:
  512 x 512, byte-identical to the existing tracked asset, SHA-256
  `0A9877DB22201A4D3A133511DBE58AD667BE399F585D402E956474FFE28C3ED6`.
  Schema 1.12.0 requires `custom` for this resolution; theme is `default`.
- Validation: all 13 focused generator tests pass, including 17 invalid-icon
  variants and preservation of existing output on failure. All three generated
  manifests and all three submission manifests pass the official Microsoft
  1.12.0 JSON schemas with the installed YAML/JSON-schema validators. Parsed
  before/after comparison confirms only `Icons` changes; `git diff --check` passes.
- Submitted [WinGet PR #477862](https://github.com/microsoft/winget-pkgs/pull/477862)
  at `c50ef9e958f5c5654c8ef1890bb85468092a10d6`, based on upstream
  `258762d8d44056e7008a315f67b8415b6d079582`. Verified OPEN, non-draft and mergeable;
  remote diff contains exactly six additions in the existing 3.0.3 default-locale
  file. The installer and version manifests are untouched.
- The connector could write the fork but was denied upstream PR creation; the
  existing authenticated GitHub CLI successfully submitted the authorized PR.
  No upstream merge, project main push, product release or installed-app test.
- Local schema validation does not replace WinGet's hosted validation. External
  checks/acceptance and actual UniGetUI rendering remain pending. No Windows
  installer execution was necessary for this metadata-only change. Generator
  changes are locally committed; next actions are upstream acceptance/client
  refresh and separately authorized publication of the project changes.

## UniGetUI missing-icon investigation (2026-11-11)

- User reports no icon for Immich Folder Watch in UniGetUI. Read-only inspection
  confirms the published WinGet 3.0.3 default-locale manifest has no `Icons`;
  the repository manifest generator likewise emits no icon metadata.
- Windows installer source already declares its icon and `ARPPRODUCTICON`.
  UniGetUI's current native WinGet icon resolver reads catalog `Icons` URLs and
  hashes. Its current supplementary database contains no key matching `immich`
  or `voltkraft`. This explains missing catalog artwork, but the user's exact
  UniGetUI version, cache and installed Windows UI were not inspected.
- Sources: [published manifest](https://github.com/microsoft/winget-pkgs/blob/master/manifests/v/VoltKraft/ImmichFolderWatch/3.0.3/VoltKraft.ImmichFolderWatch.locale.en-US.yaml),
  [native icon resolver](https://github.com/Devolutions/UniGetUI/blob/main/src/UniGetUI.PackageEngine.Managers.WinGet/ClientHelpers/WinGetIconsHelper.cs),
  [supplementary database](https://github.com/Devolutions/UniGetUI/blob/main/WebBasedData/screenshot-database-v2.json).
- Next action: add immutable public PNG icon metadata to the WinGet generator,
  validate generated manifests, then submit a separately authorized metadata
  update upstream. Consider the UniGetUI database route for versions that do not
  use native catalog icons. No application release is inherently needed for a
  catalog metadata correction; no external write or application change occurred.
- This live check also confirms 3.0.3 now exists in the WinGet default branch,
  superseding the earlier pending-acceptance observation below.

## PR #32 merged and v3.0.3 published and verified (2026-11-11)

- Completed `M-RELEASE-303-20261111`: #32 merged as `3740ce0`; stable v3.0.3
  published from `e0d1c403f261b9c906cc3853a1b7477518b64bf6` with all main changes.
- Main and exact-release CI pass eight jobs each; final CodeQL passes all four
  analyses and NuGet succeeds. The release passes all nine jobs and publishes
  both Windows MSIs and both Linux Flatpaks. All four public hashes/sizes verify.
- Corrected a release-blocking test harness race without changing production
  code: 19 focused tests, 503 Core tests and 3,000 stress scenarios pass; all
  original assertions remain. Final hosted Windows/Linux tests also pass.
- Both released Linux bundles pass 240-assembly component audits plus exact
  reduced DLL/provenance/notices checks. Independent Windows inspection verifies
  version/architecture and no Avalonia in 415 managed assemblies per MSI.
- Signed Pages deployment and isolated signature-verified pulls confirm 3.0.3
  on both architectures with the existing key. WinGet #477698 is submitted and
  awaits external acceptance. Flathub preparation/native builds pass; submission
  remains disabled. Open CodeQL and Dependabot alert counts are zero.
- Auto-merge stays disabled. Prior v3.0.2 tag/assets are unchanged. No installed
  app or live Immich test was performed. Final evidence is saved locally after
  the immutable tag, without another main push; remote main/tag remain `e0d1c40`.
- Release scope is complete. External WinGet acceptance and optional Flathub
  onboarding are separate follow-ups. [Final evidence](release-3.0.3.md).

## PR #32 merge and v3.0.3 release selected (2026-11-11)

- Selected `M-RELEASE-303-20261111` under explicit merge/release authorization.
- Reverified #32 at `ce0b711`: OPEN/CLEAN, all 14 checks successful, no auto-merge.
  Latest release is v3.0.2; v3.0.3 is the next compatible patch release.
- Merged #32 with the expected-head guard as `3740ce0`. Local documentation
  history is preserved; only the newer brief/status summaries resolve conflicts.
  Main CI 43066118171 passes all eight jobs, CodeQL 43066119121 passes four
  analyses and NuGet succeeds. Existing-version release follow-up skips publication.
- Prepared v3.0.3 / 3.0.3.0 and regenerated AppStream. Version/history checks,
  AppStream and focused release tests pass; independent preparation review has
  no findings. First release candidate `6c60d55` passes CodeQL/NuGet, but Windows
  exposed an existing autostart test harness race outside the documented UI-thread
  contract. The test-only single-thread harness correction passes 19 focused
  tests, all 503 Core tests and 3,000 repeated ordering/cancellation scenarios.
  Independent review confirms all original assertions remain; no production
  changes. Fresh hosted checks/publication are pending.
  [Release evidence](release-3.0.3.md).

## PR #32 reduced Avalonia prepared and verified (2026-11-11)

- Completed `M-PR32-REDUCED-AVALONIA-20261111` for preparation/validation. Pushed
  only #32 through `ce0b711d33f6fa07c364445b96fb2bbc831b9354`; no merge or main push.
- Shipped-component audit confirms the existing issue in both v3.0.2 Linux
  bundles. Reduced 12.1.6.1 removes the identified implementations/resources and
  retains attribution; D-Bus 0.94.1 resolves the restore conflict.
- All eight CI jobs, four CodeQL analyses, aggregate CodeQL and NuGet submission
  succeed: 14 current PR checks green. Both downloaded native candidates pass
  exact DLL/provenance/license checks and a 240-assembly exclusion audit each.
- Linux passes 501 Core and 60 Linux tests; hosted packaging passes all 147 tooling
  tests. Windows passes with its documented platform skips. One unchanged Windows
  rerun passed after the existing short file-lock test timed out; a stalled Linux
  package-download attempt was replaced. Detailed outcomes are retained.
- Independent review verified package provenance and the extracted-cache tamper
  fix. Future Avalonia upgrades require coordinated source review/reconstruction.
- #32 is OPEN/CLEAN, auto-merge request null and repository auto-merge false.
  Remote main remains `df48398`; published v3.0.2 assets are unchanged. No new
  release, deployment, installed desktop test or live Immich connection occurred.
- PR description contains final hosted evidence. This closing record is local
  documentation only, preserving previous unpublished records. Next action:
  explicit merge authorization, followed separately by a release decision.
  [Final verification and artifact hashes](dependabot-pr32-20261111.md).

## Avalonia baseline license reassessment (2026-11-11)

- Read-only follow-up on #32 confirms the unchanged open head `51898a8`, failed
  build/restore checks and neutral aggregate CodeQL. No dependency edit, merge,
  workflow rerun or remote publication was performed.
- Correction to the earlier upgrade-only framing: the official source commit for
  installed Avalonia 12.0.3, `21e816874efa142bf9903b51fd323d1f35e56ab3`, already
  contains MS-PL headers in [Calendar.cs](https://github.com/AvaloniaUI/Avalonia/blob/21e816874efa142bf9903b51fd323d1f35e56ab3/src/Avalonia.Controls/Calendar/Calendar.cs)
  and [Fluent Calendar.xaml](https://github.com/AvaloniaUI/Avalonia/blob/21e816874efa142bf9903b51fd323d1f35e56ab3/src/Avalonia.Themes.Fluent/Controls/Calendar.xaml).
  The same headers were freshly verified at proposed 12.1.6 commit `cf8e564`.
  Source revisions come from the corresponding NuGet nuspec repository metadata.
- Staying on 12.0.3 does not resolve this source-license concern. v3.0.2 retains
  that dependency; its successful tests/publication do not establish component
  license compatibility. A complete released-binary inclusion audit was not
  performed in this follow-up, so no new definitive distribution finding is claimed.
- Options: reproducible source reduction/replacement with package and GUI audits;
  applicable permission from rights holders; or an explicitly reviewed licensing
  change with all necessary rights. Deferral alone is only temporary containment.
  Recommended next decision: a scoped baseline/component audit and reduced-build
  feasibility assessment. No remediation option is selected yet; #32 stays blocked
  and automatic merging remains disabled.

## Release v3.0.2 published and verified (2026-11-11)

- Completed `M-RELEASE-302-20261111`: v3.0.2 is published from main/release
  commit `df4839852bb84efef35a83cc429d51ce55b9ed1e`, including all new main changes.
- CI passes eight jobs; CodeQL passes all four languages; NuGet submission passes.
  Release passes all nine jobs, with both Windows MSIs and both Linux Flatpaks.
- Downloaded all four public assets and verified exact sizes/SHA-256 hashes;
  tag, versions and release notes match the selected commit/changelog.
- Signed Pages deployment passes. Isolated signature-verified OSTree pulls return
  3.0.2 for x86_64 and aarch64 using the unchanged persistent signing identity.
- WinGet #477568 is submitted and awaits external acceptance. Flathub preparation
  and both native builds pass; submission is correctly skipped while disabled.
- #32 remains open/license-blocked at 51898a8, auto-merge disabled, and open
  CodeQL/Dependabot alert counts zero. No application installation or live Immich
  connection was performed. Existing v3.0.1 is unchanged.
- Final evidence is saved locally after the immutable tag; no extra main push.
  Release scope is complete; external distributor acceptance is separate.
  [Release evidence, hashes and run links](release-3.0.2.md).

## Verification documentation published and checked (2026-11-11)

- Completed `M-DOC-PUBLISH-20261111`. Published the final report and related
  maintenance evidence as `ef6f394693353b9103ecf92c811051e69b04d35b`; the net
  change from application main `efeda2f` consists only of nine Markdown files.
- Explicit CI 43025624807 passes all eight jobs, including Windows/Linux and
  both native Flatpak architectures. CodeQL 43025461040 passes all four language
  analyses; NuGet 43025461060 succeeds. Manual dispatch was needed because the
  normal CI push path filter excludes Markdown/docs changes.
- The final record adds these verified results without changing any product or
  workflow file. This documentation-only closing update uses the same tested
  code; another full application build is not required for the record itself.
- Release follow-up 43026470636 is correctly skipped for the manually dispatched
  CI. Published v3.0.1 remains unchanged. A compatible v3.0.2 maintenance release
  is recommended for the YAML value-preservation fix and reviewed updates; no
  version change, new tag or publication is selected.
- #32 remains open/license-blocked at 51898a8, automatic merging disabled.
  [Published evidence and run links](dependabot-remaining-merges-20261111.md#documentation-publication-follow-up).

## Selected dependency PRs merged and main verified (2026-11-11)

- Completed `M-REMAINING-MERGE-20261111`: #38/#39/#40/#42/#43/#44/#45 merged
  through guarded requests after successful exact-head checks. Final main
  `efeda2ffb6ec975188d2b1454c39dd718c00e540` exactly matches the reviewed integration.
- Additive conflict resolutions preserve all reviewed changes and license data.
  Combined 501 portable tests pass; independent review confirms the exact source
  edit union, 24 license hashes and 109 version mappings. GitHub's stale conflicting
  state was resolved by a tree-identical normal merge and 14 fresh successful checks.
- Final main CI 43021602143 passes all eight jobs; CodeQL 43021602894 passes all
  four languages; NuGet 43021602079 succeeds. All 13 validation checks are green.
  Open Dependabot and code-scanning alert counts are zero after analysis.
- Release follow-up 43022515575 succeeds, detects existing v3.0.1 and skips all
  builds/publication/downstream updates. Published tag 1ab0748 and four assets
  remain unchanged; no new release or deployment occurred.
- Only #32 remains open at unchanged 51898a8, still license-blocked. Repository
  auto-merge is false. No live Immich test was performed.
- Local main incorporates remote main while preserving unpublished documentation;
  production files match exactly and only docs remain ahead. No extra main push.
- Scope complete; no further merge or release selected. [Full merge and validation
  evidence](dependabot-remaining-merges-20261111.md).

## Remaining dependency PRs prepared and verified (2026-11-11)

- Completed `M-REMAINING-PRS-20261111`: #38/#39/#40/#42/#43/#44/#45 are pushed,
  OPEN/CLEAN and pass all current checks. #38/#40 have 15 successful checks;
  the other five have 14. Every set includes Windows/Linux, both native Flatpak
  architectures, all four CodeQL analyses, aggregate CodeQL and NuGet submission.
- Exact-source license/compatibility reviews and fixes are complete. Key repairs:
  SocketIO 4 hardened adapters and independently reviewed shutdown/reconnect
  lifetime fix; complete 89-package offline notice coverage; Svg build-tool
  notices/runtime isolation; YAML notices and ambiguous-string round trips.
- #39's historical queued Dependabot app check belongs to its previous head.
  Its final changelog commit passes all current checks; no requirement was
  disabled or bypassed. The old service check is not claimed successful.
- Final live checks: zero open Dependabot/code-scanning alerts, repository
  auto-merge false and every PR auto-merge request null. #32 remains open and
  license-blocked at unchanged `51898a8`. Remote main remains `a82216d`.
- No PR merged, main pushed, release/deployment performed or live Immich server
  contacted. Root evidence/changelog is committed locally; branch-specific
  reports and updated PR bodies are remote. Prior unpublished records preserved.
- Next action: separate user merge decision for the seven prepared PRs, then
  integration/main verification. [Exact heads, runs and evidence](dependabot-remaining-prs-20261111.md).

## Remaining PR preparation selected (2026-11-11)

- Selected `M-REMAINING-PRS-20261111`: #38/#39/#40/#42/#43/#44/#45, excluding #32.
  Current remote main is `a82216d`; local unpublished evidence is preserved.
- Separate worktrees isolate Actions, SocketIO, branding, Hosting and YAML work.
  Root brief/status and final cross-cutting evidence remain primary-owned.
- Initial evidence: #42 application/Flatpak CI succeeds but CodeQL is neutral;
  #44/#45 fail native Flatpak packaging; #43 has major transport API changes.
  Exact-source license reviews and fixes are in progress. No merge is selected.

## Dependabot xUnit correction verified; separate warnings retained (2026-11-11)

- Completed scoped correction/verification `M-DEPENDABOT-IGNORE-20261111`. Replaced the interval with
  `>= 4.0.0` on isolated branch `fix/dependabot-xunit-ignore`; scope retains
  absolute version/security exclusion and changes no package versions.
- [PR #41](https://github.com/VoltKraft/immich-folder-watch/pull/41) head
  `ed1a5f624970fd1e046a0584fc363d47c5372925` contains the fix and focused docs.
  YAML semantic comparison and all 14 PR CI/CodeQL checks passed. The actual
  upstream C# parser reproduced the old failure and passed all five version
  boundary cases for the correction.
- Automatic approval review rejected the direct main push and required a PR or
  explicit publication approval. The user then explicitly authorized merging #41;
  expected-head merge succeeded as `a82216d4251e6517b71236602ab09abfdb13f3e1`.
  Main CI, CodeQL, dependency submission and config validation passed; automatic
  release follow-up correctly skipped publication. #32 stays blocked; auto-merge off.
- Independent source review confirms the C# updater parser supports the comparator
  and retains explicit ignore versions for security updates. A controlled fresh
  NuGet run `43009535605` succeeded with the new effective rule, zero requirement
  errors and xunit.v3 still 3.2.2. Created #42-#45 for review only.
- Dependabot UI retains separate duplicate-PR creation warnings and initial
  automatic version/rebase unknown errors. No successful #32 rebase is claimed.
  Next maintenance action: investigate those service/PR-handling warnings while
  retaining #32's license block. [Detailed evidence](dependabot-ignore-20261111.md).
- Final evidence is saved locally; no additional main documentation push.

## PR #34 merged; main verified, separate updater issue found (2026-11-11)

- User authorized the merge and main verification. Rechecked all 14 successful
  PR-head checks and merged exact head `1a4722c` as
  `eeba23df3a62a6cf307684b3a1a6f4d607d7118b`, without bypass or auto-merge.
- Main CI `43003920977` passed all eight jobs; CodeQL `43003920330` passed
  all four analyses; NuGet submission `43003920444` succeeded. Open code-scanning
  alerts: zero. Dependabot configuration check `130466569912` also succeeded.
- Release follow-up `43004699915` succeeded and correctly skipped publication
  because v3.0.1 exists. No new release, Pages deployment or downstream submission.
- Separate automatic NuGet updater runs failed with `illformed_requirement` for
  the existing xunit.v3 ignore range `[4.0.0,)`. Merge/verification completed;
  updater maintenance remains open. [Detailed evidence](dependabot-pr34-20261111.md).
- Local documentation conflicts preserve the newer validation/release records;
  implementation changes match remote main. No extra main push is selected.
- #32 remains open/blocked at unchanged `51898a8`; #34 is closed/merged and
  auto-merge disabled. Next maintenance action: validate/correct the xUnit ignore
  requirement and rerun NuGet updater jobs while preserving compatibility blocks.
  No configuration fix or additional remote push was performed in this assignment.

## PR #34 ready for a separate merge decision (2026-11-11)

- Completed `M-PR34-20261111`; refreshed #34 from `f22797e` onto remote main
  `2a9a96d` and pushed `1a4722c` without force-push or merging.
- Branding builds, pixel/ICO comparison and runtime-isolation verification pass;
  renewed license review found no blocker. All eight CI jobs, all four CodeQL
  analyses, aggregate CodeQL and NuGet submission succeeded: 14 successful checks.
- GitHub reports `MERGEABLE` / `CLEAN`; zero open code-scanning alerts. PR body
  contains exact-head evidence. Next action requires a separate user merge decision.
- No Dependabot configuration suite has appeared on the new head; the old queued
  checks remain historical, not successfully rerun. See [renewed evidence](dependabot-pr34-20261111.md).
- #32 remains blocked, auto-merge disabled, remote main and release v3.0.1 unchanged.
  Final evidence is saved locally; only the #34 branch and its description were
  updated remotely. No main documentation push.

## PR #37 merged and main verified (2026-11-11)

- User authorized merging #37 and verifying main. All 14 PR-head checks passed
  at `d79d3f3`; expected-head merge succeeded as
  `2a9a96d18ead49682804cdbe61e444b8c5f99703`, without bypassing checks.
- [Main CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43000078507)
  passed all eight jobs, including Windows/Linux tests, both native Flatpak
  candidates and both actual Pages upload/download modes.
  [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43000084573)
  passed all four analyses; NuGet submission succeeded. Open code-scanning
  alert count remains zero.
- [Release follow-up](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43000811523)
  succeeded in preparation and correctly skipped builds/publication because the
  v3.0.1 tag already exists. No release, Pages deployment or downstream submission
  was performed by this merge; published v3.0.1 remains unchanged.
- Final readback: #37 merged/closed; #32/#34 open/unmerged with no auto-merge
  requests, repository auto-merge disabled. Requested merge/validation completed.
- Local main includes the merge and preserves local v3.0.1/PR verification records.
  Documentation-only conflicts were reconciled without implementation changes.
  Final evidence is committed locally; no additional main documentation push.


## PR #37 ready for a separate merge decision (2026-11-11)

- `M-PR37-20261111` completed. Updated [PR #37](https://github.com/VoltKraft/immich-folder-watch/pull/37)
  from `c8989d6` to `d79d3f30376f2993a185bfc62dd55e87865f943d`, integrating main
  `1ab0748` without force-push and adding focused Pages upload/download validation.
- All eight CI jobs, all four CodeQL analyses, aggregate CodeQL and NuGet submission
  passed: 14 successful checks. Actual upload/download passed with both hidden-file
  modes; no deployment rights, environment or signing secrets were used.
- License/compatibility review and independent review found no blocker. GitHub
  reports the PR clean and mergeable. Its description contains exact-head run links.
- #37 remains open/unmerged; #32/#34 are unchanged/open, repository auto-merge off.
  Main/release v3.0.1 are unchanged. A merge requires a later user decision.
- [Detailed PR evidence](dependabot-pr37-20261111.md) records action source/license
  links, test coverage, uploaded fixture IDs and remaining deployment limitation.
  Final evidence is a local documentation checkpoint; only PR #37 was pushed.


## v3.0.1 published and verified (2026-11-11)

- `M-RELEASE-301-20261111` completed. [v3.0.1](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.1)
  is the latest stable release, tagged at `1ab074841c76b2493dc3af5d972ce229e5746edb`.
  The release includes all previously merged main changes and the verified
  container-ownership fix discovered during release validation.
- R301-AC01/02: Unified versions/AppStream/changelog match; six CI jobs and all
  four CodeQL analyses passed; both Windows MSIs and both Linux Flatpaks built,
  published and independently downloaded with matching size/SHA-256.
- R301-AC03: Signed Pages repository deployed; live signature/version verification
  passed for both architectures. WinGet submission succeeded (external PR open).
  Flathub preparation/builds passed; disabled submission was correctly skipped.
- R301-AC04: #32/#34 remain open/unmerged, auto-merge disabled, no live Immich or
  personal installation changes. No further milestone is selected.
- [Detailed evidence](release-3.0.1.md) owns run links, checksums, signed refs and
  publication limits. This final documentation checkpoint follows the immutable
  release and is retained locally; published artifacts remain unchanged.


## PR #37 preparation (2026-11-11)

- User selected `M-PR37-20261111`, authorizing branch refresh, focused compatibility
  validation and successful CI/CodeQL without merging or deployment.
- Integrated remote main `1ab0748` into original PR head `c8989d6` in an isolated
  worktree. No force-push; the root checkout's local v3.0.1 evidence is preserved.
- Add an actual upload/download smoke check for the Pages action using synthetic
  files only, read-only repository permissions and no publishing job/secrets.
- #32/#34 and disabled automatic merging are outside the mutation scope.


## v3.0.1 container checkout correction (2026-11-11)

- Preparation commit `b475dda` passed all six [CI jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42922983220)
  and all four [CodeQL analyses](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42922982812).
- The first [release build](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42923750608)
  failed before either Flatpak build: Git rejected the guard's `rev-parse` with
  `dubious ownership`. Checkout's temporary HOME does not carry its safe-directory
  configuration into subsequent shell steps in the privileged build container.
  This was an ownership-check failure, not a different target SHA.
- Scope the guard's Git trust exception to `GITHUB_WORKSPACE` for that single
  command. Keep strict target equality and default-branch checkout; do not add a
  global/wildcard exception. Extend the deployed-guard regression with Git's
  different-owner simulation, checking that plain Git rejects the fixture while
  the scoped guard accepts only its exact HEAD and rejects all other inputs.
- No v3.0.1 tag or assets were published by the failed run. Rerun full exact-head
  CI and release builds after this focused correction; prior versions stay intact.


## v3.0.1 release preparation (2026-11-11)

- User authorized publishing v3.0.1 from current main `bb13a33`, including all
  merged maintenance/security changes; selected `M-RELEASE-301-20261111`.
- Remote v3.0.1 release/tag are unused. Local main matches origin/main and the
  working tree was clean before preparation. Existing v3.0.0 assets are preserved.
- Unified versions are prepared as 3.0.1 / 3.0.1.0; release notes retain every
  Unreleased item and summarize the merged dependencies/actions and maintenance
  records. Release date uses the user's Europe/Berlin date, 2026-11-11.
- Publication follows successful main CI through the existing release workflow;
  verify all four assets and downstream signed Flatpak repository before handoff.
  No publication/build success is claimed at this preparation checkpoint.
- Local preflight passed: version/XML/changelog consistency, AppStream validation,
  five manifest regressions and five workflow-security tests (four PowerShell
  cases require Windows CI), plus whitespace checks. Independent release review
  found no blocker in the five-file preparation diff.
- #32 and #34 remain excluded from main; auto-merge stays disabled.


## Release checkout fix verified on main (2026-11-10)

- Published security fix `ae9558c` and Windows regression-runner correction
  `f1d20c3f1f802d67194d8ae620acc792c796ab7c`; remote main is the latter revision.
- [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42916629585)
  completed successfully on `f1d20c3`: all six jobs passed, including Windows/Linux
  builds/tests, all nine workflow security cases on Windows, and native x86_64/ARM64
  Flatpak candidates. Selecting Git Bash resolved the initial Windows test failure.
- [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42916628594)
  completed successfully on the same revision for all four languages. NuGet
  dependency submission also passed. The open code-scanning alert list is empty.
- Alerts [#11](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/11)
  and [#12](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/12)
  are both `fixed`, automatically recorded at 22:38:28 UTC; neither was dismissed.
- Final remote readback: #32 and #34 remain open/unmerged, both have no auto-merge
  request, and repository automatic merging remains disabled.
- Requested publication and validation are complete. This final evidence-only
  status entry is a local documentation checkpoint after the verified remote
  revision; no further implementation work or release dispatch is selected.


## Release checkout fix published; Windows test runner correction (2026-11-10)

- User explicitly authorized publishing the fix and verifying CI, CodeQL and
  alert closure. Pushed `ae9558ce07b93183c11c878d96aab0940488c37d` to main.
- CodeQL automatically marked alerts #11 and #12 `fixed` at 22:38:28 UTC;
  no dismissal was performed. The Actions analysis passed on the pushed fix.
- Initial [CI run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42916337435)
  exposed a Windows-only test harness problem: the new Bash regression's valid
  commit case failed before application build; all four PowerShell cases passed.
  Select Git for Windows' Bash explicitly instead of the ambiguous PATH launcher,
  and include stdout in assertion diagnostics. Release behavior and assertions
  remain unchanged. Fresh exact-head CI is required for this correction.
- #32/#34 remain open at their original heads, with `auto_merge: null`;
  repository `allow_auto_merge` is false. No PR merge or release dispatch.


## Release checkout alerts hardened locally (2026-11-10)

- Live CodeQL alerts [#11](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/11)
  and [#12](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/12)
  remain open on remote main `85ec9e4c45547fd353c647bf2c641550178e172f`.
  Both report `actions/cache-poisoning/poisonable-step` after the same dynamic
  Flatpak checkout, for `workflow_dispatch`.
- Existing gates already restrict dispatch to main and automatic runs to successful
  same-repository push CI on main. There is no dispatch SHA input, so no arbitrary
  external-commit exploit was demonstrated. The
  [CodeQL query guidance](https://codeql.github.com/codeql-query-help/actions/actions-cache-poisoning-poisonable-step/)
  explains why read-only repository permissions alone do not remove cache risk.
- Changed only the Flatpak release checkout to the explicit default branch, with
  an inline exact-commit guard before any repository script. The target remains
  manifest data. If main advances, the job stops instead of mixing SDK, manifest
  or offline-feed inputs from different commits. Retry behavior is documented in
  [publication workflow trust](development.md#publication-workflow-trust).
- Validation: five workflow security tests passed, including real Git-history
  matching/mismatched commits and malformed/injection inputs; four unrelated
  PowerShell cases were skipped because PowerShell is unavailable locally.
  Five manifest regression tests passed. YAML parsing/step-order checks and
  `git diff --check` passed. Independent security review found no blocking
  security or correctness issue; hosted CodeQL and Windows execution remain unverified.
- This is a local correction; no push, release dispatch, remote alert dismissal
  or hosted rescan was performed. Remote alert closure remains unverified until
  the fix is published and CodeQL scans it. #32/#34 and auto-merge are unchanged.
- The preceding documentation publication is complete: main `85ec9e4` passed
  [all six CI jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42911044302)
  after an explicit CI dispatch (documentation-only pushes are filtered), plus
  [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42910956556)
  and NuGet submission. A successful analysis job does not mean zero open alerts.


## Documentation publication checkpoint (2026-11-10)

- User authorized publishing the accumulated dependency-maintenance documentation
  to main and checking the resulting CI. Earlier statements below that records
  are local/unpushed describe their historical checkpoints, not a continuing
  publication restriction.
- Prepared from local checkpoint `2849aec` on remote baseline `9a84eec`; the
  accumulated diff changes only this status, the project brief, the Dependabot
  review and the configuration-check diagnosis. `git diff --check` passed.
- The preceding main revision passed CI and CodeQL as recorded below. Validation
  of the documentation push must be read from the checks attached to its exact
  GitHub commit; earlier runs do not establish the new revision's result.
- #32 remains open/blocked and #34 open/deferred. Automatic merging stays disabled.
  No additional dependency update, PR merge or version bump is selected.

## Remaining Actions PR merges completed (2026-11-10)

- User explicitly deferred #34 and authorized merging the other reviewed Actions
  updates (#28/#29/#30/#31). Each exact PR head had 13 successful checks before its
  manual merge. Expected-head checks protected against concurrent branch changes;
  no checks or branch rules were bypassed.

| PR | Validated head | Merge commit |
| --- | --- | --- |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | `c66de1e` | `b661638d9d7535a2a92c1cbfa510dc532d7dce05` |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | `2b2bdc6` | `b5f4dc122ed8203c9a17fae9f1330b1c057bc222` |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | `d0062e7` | `5c80ddd5a12c02b3badc549a1f72f4e33c8ec404` |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | `5ed2076` | `9a84eec0a5da6f9a5e58d92c0e776bc22f707309` |

- Final remote main: `9a84eec0a5da6f9a5e58d92c0e776bc22f707309`.
  [Combined main CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42909012903)
  and [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42909013941)
  completed successfully on that exact final merge commit. All six CI jobs passed,
  including Windows/Linux tests and native x86_64/ARM64 Flatpak builds; all four
  CodeQL language analyses passed. NuGet dependency submission also succeeded.
- #32 remains open/blocked at unchanged `51898a8`. #34 remains open/deferred at
  `f22797e`; no further configuration-check recovery was attempted after the user
  deferred it. Repository auto-merge remains disabled, with no PR auto-merge request.
- Local main incorporates the remote merges without losing local documentation
  history. No main documentation push, version bump, manual release or deployment.
- Completed: four authorized PR merges and successful combined main validation.
  No further milestone is selected; #32 remains blocked and #34 is explicitly
  deferred until a later user request. Final local evidence is not pushed.

## Dependabot configuration-check recovery blocked externally (2026-11-10)

- User authorized recovery of #34's queued Dependabot check without merges.
  Investigation and permitted recovery attempts are recorded in
  [the diagnosis and support handoff](dependabot-config-check-20261110.md).
- No config defect was identified: the original blob matches successful #28/#31
  validation, schema validation passes, and a comment-only retrigger preserves
  parsed YAML exactly. The evidence points to stalled GitHub Dependabot service
  processing; internal logs/root cause are unavailable and remediation is not claimed.
- REST retry returned 404; GraphQL explicitly restricts suite retries to GitHub
  Apps. After the user signed in, the actual Dependabot check UI still offered no
  rerun action. These are GitHub capability limits, not automatic approval rejection.
- Pushed only explanatory-comment commit `f22797ed4d452e1940493bf09d44b25b931b2ee8`
  to #34. New check `130148023423` remains queued, as does the superseded original
  `130138962423`; neither supplies diagnostic output. No further speculative
  commits, config changes, forged statuses or protection bypasses were performed.
- The new head has [all six CI jobs successful](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42907159639),
  including Windows/Linux and x86_64/ARM64 Flatpak, plus [all four CodeQL analyses](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42907153860),
  the aggregate CodeQL check and NuGet submission successful. Twelve checks pass;
  the separate configuration check is the sole unfinished check.
- PR #34 remains open/unmerged; #32 remains unchanged/open/blocked at `51898a8`,
  and repository auto-merge stays disabled. No main push, release or deployment.
- Remaining prerequisite: the owning GitHub service must process/requeue the
  validator. The linked handoff contains exact run/suite IDs, timestamps and
  reproduction evidence for GitHub support. No support request was sent. Local
  documentation is committed separately from the pushed PR comment.

## Remaining Dependabot refresh completed (2026-11-10)

- Milestone `M-DEPENDABOT-REFRESH-20261110` completed. User authorized updating
  #28/#29/#30/#31/#34 with current main and obtaining successful CI/CodeQL; no PR merges.
- GitHub update-branch requests used each exact expected head. All five new heads
  contain remote main `13e93dac570a49ec9e8595713c5fc9aeb2a78524`; ancestry and
  full diff checks confirm only each original reviewed proposal remains above main.
  No force-push, extra package change or test/check weakening was necessary.

| PR | Updated head | CI | CodeQL workflow |
| --- | --- | --- | --- |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | `c66de1e58f0bd4d31b5e004348909abcb8665f32` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904525439) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904516733) |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | `2b2bdc6c767e19beb0ebb58ae0ff32a7b8711110` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904530008) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904521815) |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | `d0062e7cccda5ec8ec19d55c58d7cf5b88074f5f` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904535257) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904528780) |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | `5ed20761e5ee96ba1fa9b16f90173273393da8c0` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904541922) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904531775) |
| [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34) | `f4412966f9e3008fb286945abcaa65a417e83996` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904546447) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904538706) |

- DCR-AC01/02: All six CI jobs passed on every updated head, covering Windows/Linux
  tests and native x86_64/ARM64 Flatpak builds. All four CodeQL analyses (Actions,
  C#, JavaScript/TypeScript, Python) and each aggregate `CodeQL` check passed.
  NuGet dependency submission passed too. The earlier neutral CodeQL assessment
  is resolved by the fresh analyses; no CodeQL configuration changes were needed.
- Separate service check: #34's `.github/dependabot.yml` check (ID 130138962423,
  [service details](https://dependabot-api.githubapp.com)) remains queued at this
  snapshot. It is not one of the completed CI/CodeQL jobs; no failure is reported.
  #28/#29/#30/#31 have all 13 reported checks successful; #34 has 12 successful
  and this one queued service check. Do not describe every #34 check as complete.
- DCR-AC03: All five PRs remain open/unmerged. #32 remains unchanged/open/blocked
  at `51898a8`; repository `allow_auto_merge: false`, all inspected PRs
  `auto_merge: null`. Remote main remains `13e93da`. No merge into main, main push,
  release, deployment or live Immich access occurred.
- Local records preserve authorization and validation; they are not pushed.
  No implementation milestone remains active. Next action: separately authorized
  review/merge after checking current heads and the outstanding service check.

The review below records the earlier heads; the refresh evidence above supersedes
its pending integration-CI and neutral-CodeQL limitations. Publication-only paths
remain outside the validation performed here.

## Remaining Dependabot review completed (2026-11-10)

- Reviewed #28/#29/#30/#31/#34 without remote changes. Exact heads, CI links,
  compatibility findings and upstream license sources are retained in
  [the review record](dependabot-review-20261110.md).
- All five exact-head CI runs completed successfully with six passing jobs each;
  NuGet dependency submission passed. CodeQL is neutral on every PR with
  `4 configurations not found`, so a successful security scan is not claimed.
- No concrete compatibility or license blocker was identified. Actions retain
  MIT licenses; #34 changes only the branding tool's SkiaSharp packages, preserving
  application runtime versions and native third-party notice coverage.
- All five heads integrate conflict-free with main `13e93da` in local tree-only
  checks. Their hosted CI predates the recent main merges. Before a later merge,
  refresh integration CI and obtain a complete CodeQL assessment. Pages/OIDC and
  release-only publication paths were not exercised or triggered by this review.
- All five PRs remain open/unmerged. #32 remains unchanged at `51898a8`, open and
  blocked; repository `allow_auto_merge: false`, with `auto_merge: null` on every
  inspected PR. No PR rebase, push, merge, workflow rerun or publication occurred.
- Review complete; no implementation milestone selected. Findings and scope are
  saved in a local documentation checkpoint only. A later merge needs separate
  authorization and current validation.

## Selective Dependabot merges completed (2026-11-10)

- User explicitly authorized merging #27, #33, #35 and #36 only. All four were
  merged manually with expected-head checks after every current-head check passed.
  Repository auto-merge remains disabled (`allow_auto_merge: false`); every
  inspected PR has `auto_merge: null`.
- Integration preserved every reviewed package version, deletion-race fix,
  regression test, xUnit compatibility constraint and license notice. Resolved
  overlapping status/changelog records and adjacent package declarations;
  removed duplicated historical status blocks without discarding history.
  Independent read-only review of final cumulative head `9f73d91` found no issues.

| PR | Validated head | Merge commit | Successful CI |
| --- | --- | --- | --- |
| [#27](https://github.com/VoltKraft/immich-folder-watch/pull/27) | `ca35782` | `20cf55a` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42889338522) |
| [#33](https://github.com/VoltKraft/immich-folder-watch/pull/33) | `d5c5170` | `4f1ff08` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42894339727) |
| [#35](https://github.com/VoltKraft/immich-folder-watch/pull/35) | `176796a` | `c705988` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42894342541) |
| [#36](https://github.com/VoltKraft/immich-folder-watch/pull/36) | `9f73d91` | `13e93da` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42894348336) |

- Additional CodeQL and dependency-submission checks passed on all four heads.
  The cumulative CI covers Windows/Linux tests and native x86_64/ARM64 Flatpak
  builds. No guard, assertion or branch rule was bypassed.
- #32 remains open at unchanged head `51898a8`, blocked by the previously recorded
  technical and license issues. No Avalonia upgrade or reduced build was included.
- Follow-up live check: remote main remains `13e93da`. Its [post-merge CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42895589381)
  completed successfully (GitHub updated at 2026-11-10 20:35:07 UTC). All six jobs
  passed: Windows/Linux build and tests, packaging lint, candidate preparation,
  and native x86_64/ARM64 Flatpak builds. No version bump or manual release was performed.
- Follow-up settings readback: repository `allow_auto_merge: false`; #32 remains
  open/unmerged at unchanged `51898a8`, with `auto_merge: null` and unsuccessful
  checks (`mergeable_state: unstable`). Its technical/license blockers remain
  deferred. This inspection made no remote changes or workflow reruns.
- Local main incorporates the remote merges while preserving the earlier local
  documentation commits. This aggregate handoff remains local and is not pushed.
- Milestone `M-DEPENDABOT-CI-20261110` is complete for the selected four PRs, with
  #32 explicitly deferred. No further milestone is selected. Next action: a
  separately selected licensing resolution for #32 or review of other open PRs.

The following entries are historical snapshots; the merge record above supersedes
prior statements that the selected PRs were still open or awaiting authorization.

## Dependabot CI remediation (2026-11-10)

- Selected milestone: `M-DEPENDABOT-CI-20261110`. User authorized fixes on
  existing PR branches without merges; later explicitly deferred #32's Avalonia
  upgrade because of incompatible embedded component licensing.
- Isolated worktrees preserve each bot proposal and the original local main.
  Scoped corrections are pushed without force; no update PR is merged.

| PR | Cause and correction | Pushed correction | Validation |
| --- | --- | --- | --- |
| #27 | Concurrent watcher/poll deletion handlers read the same asset before tombstone persistence; per-path ownership and retained retry baseline prevent duplicate remote trash | `ca35782` (fix `05297b7`) | Two deterministic regressions fail against old source; 483 Core tests pass before review delta, five focused deletion cases pass after it; independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42889338522) |
| #33 | Missing reviewed supplemental notices for Microsoft.Extensions/System 11.0.0; verified exact source license and all package notices, added exact-version supplements | `c6ad2e9` | Both architecture restores and 87-archive combined feed verified; real notice installer and 15 guard regression tests pass; independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42888743407) |
| #35 | xUnit 4 changes parallelism API, test-runner defaults and Avalonia extension ABI; retain framework 3.2.2 and compatible v2/runner upgrades, exclude incompatible future v4 proposals | `a5cbed6` | 481 Core and 53 Linux GUI/protocol cases pass with no failures/skips; schema and independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42888754999) |
| #36 | Missing reviewed supplemental notices for Microsoft.Data.Sqlite/Core 11.0.0; verified MIT source and added exact-version supplements | `2b2b186` | Both architecture restores and 81-archive combined feed verified; real notice installer and 15 guard regression tests pass; independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42888749135) |

- No license guard or test assertion was disabled. SDKs: local application/tests
  10.0.203; exact Flatpak feed restores 10.0.401. PR corrections add no release bump.
- Completion: all six CI jobs pass on each of the four exact corrected heads,
  including Windows/Linux and native x86_64/aarch64 Flatpak builds. No unfinished
  or failed current-head check remains on #27/#33/#35/#36. All remain open with
  `auto_merge: null`; repository `allow_auto_merge: false` was read back again.
- Final #27 CI: Linux 483 Core + 53 GUI/protocol passed; Windows 474 Core + 36 WPF
  + 34 portable Linux-project tests passed, with 9/19 expected platform skips.
  Other corrected PRs: Linux 481 + 53; Windows 472 + 36 + 34 with the same skips.
  All application builds have zero warnings/errors. Both native license logs
  confirm 87 archives for #33 and 81 for #36.
- PR descriptions now explain the final fixes and link exact-head validation;
  #27/#35 titles reflect their final scope. #32 stays unchanged at `51898a8`.
- Next action: manual review of the four validated PRs and separate authorization
  before merging. Keep #32 open/blocked pending a separately selected licensing
  resolution. No further implementation milestone is selected. This aggregate
  handoff is a local documentation checkpoint; main was not pushed by this task.

### Deferred Avalonia PR #32

- Baseline: Dependabot head `51898a8`, Avalonia 12.1.6. Initial CI fails NU1605:
  Avalonia.FreeDesktop requires Tmds.DBus.Protocol >=0.94.1 while the app pins 0.92.0.
- A local diagnostic with app/test pins at 0.94.1 passed the Linux Release build
  (three obsolescence warnings, zero errors), 53 Linux GUI/protocol tests and 33
  portable Linux-specific tests using SDK 10.0.203. The pin edits were reverted
  after the user selected leaving this PR open and blocked; the bot proposal is
  preserved. These results do not describe the unchanged PR head.
- Exact Avalonia source `cf8e564674700348947e93ab19105f27afe859a9` retains
  [MS-PL Calendar code](https://github.com/AvaloniaUI/Avalonia/blob/cf8e564674700348947e93ab19105f27afe859a9/src/Avalonia.Controls/Calendar/Calendar.cs)
  and [MS-PL Fluent theme resources](https://github.com/AvaloniaUI/Avalonia/blob/cf8e564674700348947e93ab19105f27afe859a9/src/Avalonia.Themes.Fluent/Controls/Calendar.xaml),
  with default compile/resource inclusion. The exact source contains 19 marked
  controls C# files and seven marked Fluent XAML files (plus eight Simple themes).
  Its [NOTICE](https://github.com/AvaloniaUI/Avalonia/blob/cf8e564674700348947e93ab19105f27afe859a9/NOTICE.md)
  and top-level MIT license are byte-identical to the repository's retained files;
  preserving those notices does not establish AGPL compatibility. The
  [GNU license list](https://www.gnu.org/licenses/license-list.html#ms-pl) identifies
  MS-PL as GPL-incompatible. No reduced build or linking exception was found here.
- Status: leave #32 open and blocked. No dependency/catalog approval, license-guard
  bypass, merge or publication. A separately scoped reduced build/component review
  or applicable licensing permission is required before proceeding. Windows and
  native Flatpak success are not claimed. No live Immich access occurred.


## Dependabot completion check (2026-11-10, 20:39 Europe/Berlin)

- The first [NuGet updater](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487345)
  completed successfully and created five additional PRs (#32 through #36).
  All ten Dependabot PRs remain open and unmerged. All reported checks on their
  current heads have finished; five PRs have successful CI and five have failures.

| PR | Update | Head | CI result |
| --- | --- | --- | --- |
| [#27](https://github.com/VoltKraft/immich-folder-watch/pull/27) | download-artifact 7.0.0 to 8.0.2 | `27ab531` | Windows build/test job failed; remaining CI jobs passed |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | upload-artifact 6.0.0 to 7.0.2 | `339ee48` | All six CI jobs passed |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | deploy-pages 4.0.5 to 5.0.1 | `0c8975d` | All six CI jobs passed |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | configure-pages 5.0.0 to 6.0.0 | `383e170` | All six CI jobs passed |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | setup-node 6.5.0 to 7.1.0 | `9c6d43d` | All six CI jobs passed |
| [#32](https://github.com/VoltKraft/immich-folder-watch/pull/32) | Avalonia group, five updates | `51898a8` | Windows/Linux build/test and Flatpak preparation failed; native builds skipped; NuGet submission also failed |
| [#33](https://github.com/VoltKraft/immich-folder-watch/pull/33) | Microsoft.Extensions group, six updates | `7fb5e63` | Both native Flatpak builds failed; remaining CI jobs passed |
| [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34) | SkiaSharp group, two updates | `a92df09` | All six CI jobs passed |
| [#35](https://github.com/VoltKraft/immich-folder-watch/pull/35) | xUnit group, three updates | `820cc9f` | Windows/Linux build/test jobs failed; remaining CI jobs passed |
| [#36](https://github.com/VoltKraft/immich-folder-watch/pull/36) | Microsoft.Data.Sqlite 10.0.10 to 11.0.0 | `4a26baf` | Both native Flatpak builds failed; remaining CI jobs passed |

- CodeQL reports neutral on all ten PRs, not a successful security scan.
  Failure causes were not investigated in this status-only check.
- Verified repository auto-merge remains disabled and every PR has
  `auto_merge: null` and no merge timestamp. No remote mutation, rerun or merge.
- Next action: investigate failed jobs and review compatibility/licenses before
  any separately authorized merge. Evidence is saved in a local documentation commit.

## First Dependabot run check (2026-11-10, 19:24 Europe/Berlin)

- Read-only GitHub inspection requested; no update PR was modified or merged.
- [GitHub Actions updater](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487560)
  completed successfully. The first [NuGet updater](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487345)
  is still running; no NuGet update PR exists at this snapshot.
- Created five open PRs: [#27](https://github.com/VoltKraft/immich-folder-watch/pull/27)
  download-artifact 7.0.0 to 8.0.2;
  [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28)
  upload-artifact 6.0.0 to 7.0.2;
  [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29)
  deploy-pages 4.0.5 to 5.0.1;
  [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30)
  configure-pages 5.0.0 to 6.0.0;
  [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31)
  setup-node 6.5.0 to 7.1.0. All are major-version proposals requiring review.
- PR CI is queued/running for all five; no failed check is reported at this
  snapshot. Packaging lint passed for #27/#29/#30. The successful updater run
  does not establish upgrade compatibility or completed PR CI.
- Verified repository `allow_auto_merge: false`, with `auto_merge: null` and
  no merge timestamp on all five PRs. No remote mutation was performed.
- Next action: recheck NuGet completion and PR CI, then review compatibility and
  licensing before any separately authorized merge. This check is recorded locally.

## Dependabot PR #36 license correction (2026-11-10)

- Scope: fix the existing Microsoft.Data.Sqlite 11.0.0 update PR's Flatpak CI
  failure without merging, changing product versions or weakening license checks.
- Baseline: `4a26baf`; both native Flatpak jobs stopped at the exact-version
  supplemental notice guard for Microsoft.Data.Sqlite.
- Inspected Microsoft.Data.Sqlite and Microsoft.Data.Sqlite.Core 11.0.0 archives:
  both declare MIT at the same recorded `dotnet/dotnet` revision and omit license
  text. Added an immutable version-specific MIT source and exact catalog entries;
  updated the top-level third-party summary. Native SQLite dependencies remain
  unchanged. Provenance is recorded in
  [the license review](../packaging/flatpak/licenses/README.md#microsoftdatasqlite-1100-review-2026-11-10).
- Validation: exact Flatpak SDK 10.0.401 restored Linux x64 and ARM64 into isolated
  caches. The generator's official-source/SHA-512 checks passed for the combined
  81-archive feed; the real license installer passed, and both new supplemental
  outputs match the upstream SHA-256. All 15 notice-installer regression tests
  passed, including rejection of unknown versions and modified notices.
- No application code changed. The existing Windows/Linux application CI passed
  before this metadata correction; actual native Flatpak rerun is still required.
- Next action: commit/push this correction to PR #36 and verify both native jobs.
  No PR has been merged and no release or live Immich operation was performed.

## Dependabot PR #35 compatibility repair (2026-11-10)

- User requested investigation and correction of failed Dependabot CI without
  merging. This worktree repairs PR #35 from `820cc9f` and retains its compatible
  xUnit 2.9.3 and Visual Studio runner 4.0.1 updates.
- Root causes: xUnit v3 framework 4.0.3 rejects the old assembly parallelism
  property, enables MTP v2 incompatible with the current .NET 10 VSTest command,
  and changes the extension ABI used by Avalonia.Headless.XUnit 12.0.3.
  A diagnostic `mtp-off`/new-parallelism experiment compiled but failed discovery
  for all 15 Avalonia GUI cases (`MissingMethodException`); 38 other tests passed.
- Correction: retain GUI framework 3.2.2 and its serial assembly setup, defer
  Dependabot `xunit.v3` proposals >=4 until a compatible bridge and runner path
  are validated, and use the predicate overload of `Assert.Single` for the newer
  xUnit v2 analyzer. No test was disabled or removed; no application code changed.
- License evidence: official NuGet package metadata for xUnit 2.9.3 and Visual
  Studio runner 4.0.1 declares Apache-2.0 with immutable source commits documented
  in the Linux test README. These test-only packages are AGPL-3.0-only compatible
  and do not enter application distribution artifacts.
- Validation: Release Linux GUI/protocol suite passed all 53 tests and the portable
  Core suite passed all 481 tests, with no failures/skips, using SDK 10.0.203,
  isolated headless controls and local D-Bus. Builds reported no warnings/errors.
  Dependabot schema, local documentation links and diff whitespace checks passed.
- Next action: verify Windows/full CI on the corrected PR head. No merge or live
  Immich operation is authorized or performed.

## Dependabot PR #33 license correction (2026-11-10)

- Scope: fix the existing Microsoft.Extensions 11.0.0 update PR's Flatpak CI
  failure without merging, changing product versions or weakening license checks.
- Baseline: `7fb5e63`; both native Flatpak jobs stopped at the exact-version
  supplemental notice guard, beginning with Microsoft.Extensions.Configuration.
- Reviewed all 32 changed Microsoft.Extensions/System 11.0.0 archives in the
  resolved feed against their recorded `dotnet/dotnet` source revision. Added
  version-specific MIT provenance and exact catalog entries, including four new
  transitive System packages. All upstream third-party notices are retained.
  Detailed source/hash and license-delta evidence is in
  [the license review](../packaging/flatpak/licenses/README.md#microsoftextensions-1100-review-2026-11-10).
- Validation: exact Flatpak SDK 10.0.401 restored Linux x64 and ARM64 into isolated
  caches. The generator's official-source/SHA-512 checks passed for the combined
  87-archive feed; the real license installer passed and all 32 updated license
  and notice outputs matched reviewed SHA-256 values. All 15 notice-installer
  regression tests passed, including rejection of unknown versions/tampering.
- No application code changed. The existing Windows/Linux application CI passed
  before this metadata correction; actual native Flatpak rerun is still required.
- Next action: commit/push this correction to PR #33 and verify both native jobs.
  No PR has been merged and no release or live Immich operation was performed.

## Dependabot PR #27 CI correction (2026-11-10)

- User authorized investigating/fixing existing PR #27 without merging. Its
  Windows CI failed `Sync_IgnoresExcludedFileDeletionsButPropagatesMediaDeletion`
  because one asset appeared twice in the trash requests.
- Cause: watcher and polling handlers both read the mapping before asynchronous
  tombstone persistence removed it. A per-path in-progress claim now gives one
  handler ownership until completion, including exceptional exits. Polling keeps
  missing mappings while a deletion is active or failed, preserving retryability.
- Added deterministic concurrent watcher/poll tests with paused persistence and
  injected persistence failure. Both assertions failed against the original
  production code; the initial guard passed the full 483-test Core suite.
  After independent review identified the polling retry gap, the corrected delta
  passed all five focused deletion cases (including the original three cases).
- Independent source review found no remaining actionable issue; handle-bound
  absence checks and watcher shutdown draining remain unchanged. Initial restricted
  MSBuild attempts failed without compiler diagnostics; permitted local runs passed.
- The updated download-artifact SHA retains the upstream MIT license, verified
  at `9000827ccba6bdab643e8b6fd33ac0654aef8333`. No dependency is added by this fix.
- Next action: push this correction to the existing PR and verify Windows/Linux
  and native Flatpak CI on its exact head. No merge, release or live Immich access.

## Dependabot activation (2026-11-10)

- Selected milestone: `M-DEPENDABOT-20261110`, extended by explicit user request
  to activate security alerts/updates and push configuration while disabling auto-merge.
- Starting state: clean local `main` at `8c8bab8`; remote default branch `main`
  remains at `64a9892`. API readback: vulnerability alerts enabled (HTTP 204),
  automated security fixes disabled/unpaused, repository `allow_auto_merge: true`.
- DB-AC04: Complete. Pushed configuration commit `8c8bab8` to `main` without
  force; GitHub's branch SHA and decoded `.github/dependabot.yml` content match
  the local commit/file. Security alerts were already enabled and remain enabled
  (HTTP 204). Enabled automated security fixes and independently read back
  `enabled: true`, `paused: false`. Disabled repository auto-merge and independently
  verified `allow_auto_merge: false`.
- Hosted evidence: GitHub queued the first [NuGet update run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487345)
  and [GitHub Actions update run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487560)
  for `8c8bab8`. Automatic NuGet dependency submission started. No Dependabot PRs
  existed at the check; no package upgrade or merge was performed.
- Checks: Remote content comparison and settings readback passed. Configuration
  retains the prior schema/coverage/review evidence. Application sources, versions
  and workflows are unchanged; no additional local runtime tests were needed.
- Next action: Review generated dependency/security PRs with the existing license
  and platform CI requirements. The initial bot runs and push CI are queued/running;
  their completion is not claimed. Activation is complete; no further milestone selected.

## Dependabot implementation (2026-11-10)

The following records the local checkpoint before the authorized activation above.

- Selected milestone: `M-DEPENDABOT-20261110`; local implementation complete.
- Baseline: clean local `main` at `64a9892`, whose merge commit includes PR #26
  and version-preparation commit `f7fef40`. The older version checkpoint below
  predates that merge; this task does not recheck release publication.
- Scope: NuGet and GitHub Actions configuration and maintenance documentation;
  no package updates, push, repository-setting changes or publication.
- DB-AC01: `.github/dependabot.yml` covers all nine tracked C# project manifests
  and all six GitHub Actions workflows. Related NuGet packages have family groups;
  each ecosystem checks weekly with at most five open version-update PRs.
- DB-AC02: PyYAML parsing and validation against the downloaded SchemaStore
  Dependabot 2.0 JSON Schema passed. Manifest coverage, 59 local documentation link
  targets and `git diff --check` passed. Independent review found no actionable
  issue in configuration, existing read-only PR CI or publication boundaries.
- DB-AC03: Development guidance, project brief, AGENTS and Unreleased changelog
  updated. The local checkpoint hash is provided in the chat handoff.
- Validation limits: No hosted Dependabot run, package upgrade, application build
  or runtime test was performed; application sources and workflows are unchanged.
  Initial sandbox download failed DNS resolution; permitted schema download passed.
  An obsolete upstream NuGet fetcher URL returned 404; review used current upstream
  C# discovery source instead. No production operation was attempted.
- Next action: when publication is authorized, push the checkpoint to the default
  branch through the normal review process and inspect the first hosted Dependabot
  jobs/PRs. Security-update repository settings were not changed or verified.
  No further milestone or Goal was started.

## Version preparation checkpoint (2026-11-10)

- Active milestone: `M-VERSION-MERGE-20261110`; version metadata prepared and
  locally verified. CI and the authorized merge follow this checkpoint.
- User authorized updating the version and then merging existing PR #26, replacing
  the earlier no-merge instruction. The normal automatic release pipeline follows
  successful main CI; publication must be verified separately.
- Baseline: clean branch at `225ce88631f376dee34aebe6480607d0b8da48ea`, matching
  origin; main remains `26a0de519ee4f7eae2e556b8da7726539d578594`.
- Current-head CI `42760864837` is successful after rerunning only the lint job
  that exceeded six hours during Ubuntu package retrieval. All six jobs are green.
- Selected version: `3.0.0`, because HTTPS-by-default requires migration of existing
  HTTP configuration. GitHub's latest published release is `v2.11.3`; no `v3.*`
  tag exists in the refreshed repository.
- Validation: canonical product/assembly/file versions, changelog date and exact
  generated AppStream content agree; AppStream offline validation and diff checks
  pass. Linux application build/analyzers pass with 0 warnings/errors. Independent
  review found no version/packaging blocker; remote `v3.0.0` is absent.
- Next action: validate all six CI jobs on the version-preparation commit, mark
  PR #26 ready and merge the exact validated head. The authoritative external
  state is the [PR checks and merge record](https://github.com/VoltKraft/immich-folder-watch/pull/26)
  and [release workflow](https://github.com/VoltKraft/immich-folder-watch/actions/workflows/release.yaml);
  this source checkpoint does not claim later publication. No new Goal was started.

## Directory race follow-up (2026-11-10)

The following records the completed remediation handoff before merge authorization.

- Selected milestone: `M-WATCH-ROOT-ATOMICITY-20261110`; complete. All six CI jobs
  pass on `a188722`; this final handoff changes documentation only.
- Baseline: clean local and remote PR head `d922bfa86df14408185e811e230167705354dc7c`.
  PR #26 is open, draft, unmerged, targeting `main`; existing branch is reused.
- Implementation checkpoint: `b1d2eee` pushed to the existing PR; initial CI
  exposed Windows-specific native call and test-fixture issues, corrected below.
  `eaccd17` corrects native Windows calls; `a188722` completes junction fixtures.
- User scope: completely close the remaining watch-directory race, with subagents
  and regression tests in the same PR. No merge or release.
- Ownership: native filesystem abstraction and platform tests; worker/API integration;
  independent security review. Parent owns records, integration checks and commits.
- WR-AC01: Pinned native Linux/Windows filesystem primitives and worker/API
  integration cover enumeration, absence, reads, downloads, exact-file cleanup,
  timestamps and both ends of directory moves. Roots outlive callbacks/retries.
- WR-AC02: Linux local and CI validation and Windows x64 runtime CI pass.
  Capability checks fail closed. The [watch-root contract](watch-root-security.md)
  documents retained Linux containers, bounded cache and Windows sharing locks.
- WR-AC03: 33 added regression cases (20 native, 5 API, 8 worker), including
  deterministic root/parent/leaf changes, same-fingerprint replacement cleanup,
  legacy content IDs, journal recovery, remote cleanup and shutdown lifetime.
- WR-AC04: Independent review found no remaining actionable source issue after
  corrections for identity, bounded handle caching, stale cleanup/album authority,
  retries and lifecycle. Implementation and tests are pushed to the same PR.
  Documentation and PR evidence are updated. All six application/packaging jobs
  pass, including native x86_64 and aarch64 builds/validation.
- Next action: review PR #26 and arrange an exact-commit Security Cloud scan when
  supported. No further implementation milestone selected. PR remains draft and
  unmerged; no release or stable repository publication occurred.
- Goal controls: no new Goal requested or started; prior run remains historical.

### Directory race validation (2026-11-10)

| Check | Result | Limits |
| --- | --- | --- |
| Portable Core suite | 481 passed, 0 failed/skipped | Linux x86_64, SDK 10.0.203; final album-cache revocation delta then passed 10 targeted album/security cases |
| Native focused suite | 20 passed, including LRU eviction with active leases and exclusive writer locks | Windows cases also pass in current CI; Linux-only cases retain platform scope |
| Linux GUI/protocol suite | 53 passed, 0 failed/skipped | Headless/local sockets and D-Bus; no live Immich |
| Linux application build/analyzers | Passed, 0 warnings/errors | Debug; generated branding remains ignored |
| Independent source review | Passed with no remaining actionable finding | Windows/UNC and ARM64 runtime are separate evidence requirements |
| Diagnostic full run | 468 passed / 4 failed before corrections | Fixed Linux writer-lock handling, retained-container assertions and friendly write-permission errors; subsequent full run passed |
| [Initial follow-up CI 42758835923](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42758835923) | Linux application tests/build and packaging lint passed. Windows build passed, Core 434 passed / 38 failed / 9 skipped; WPF 36 passed and Linux-project tests 34 passed / 19 skipped | Corrected explicit SYNCHRONIZE access, native handle-relative rename, junction command quoting and portable test path. Independent delta review and 20 focused Linux cases pass; Windows rerun required |
| [Windows correction CI 42759557792](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42759557792) at `eaccd17` | Native production failures resolved; Core 470 passed / 2 failed / 9 skipped; WPF 36 passed and Linux-project tests 34 passed / 19 skipped | Two junction test bodies passed but their recursive fixture cleanup failed; explicit nonrecursive junction cleanup is required before the final rerun |
| [Final CI 42760114840](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42760114840) at `a188722` | All six jobs passed. Windows: Core 472 passed / 9 platform skips, WPF 36 passed, Linux-project 34 passed / 19 platform skips, PowerShell security 7 passed. Linux: Core 481 passed and GUI/protocol 53 passed. Both builds 0 warnings/errors; lint, candidate preparation and native x86_64/aarch64 builds/validation passed | Actual UNC/ARM64 app runtime remains untested; the final documentation-only checkpoint does not change the validated code/tests |
| Repository handoff | Diff whitespace checks and 102 local documentation links passed; reviewed staged files contain no generated outputs | All scoped changes remain in the existing PR; no merge |
| Security Cloud rescan | Not executed; exposed connector still has no branch/commit selector | No finding was marked closed in the service; exact-commit scan remains outstanding |

## Previous security remediation handoff (2026-11-09)

This section records the earlier partial handoff; the follow-up above supersedes
its filesystem disposition and next action.

- Milestone: `M-SECURITY-REMEDIATION-20261109`; remediation pass delivered in draft PR #26, with one explicitly open residual finding.
- Goal run: requested and executed in chat `01a1c1ee-b279-76d2-8529-eaf116140007`, created
  2026-11-09; criteria SEC-AC01 through SEC-AC05 fixed in the selected brief. The user later
  explicitly reaffirmed subagent use; focused implementation and independent reviews
  were used. Completion permits explicitly documented unresolved findings. The remediation
  assignment is delivered; the filesystem finding remains explicitly open and
  the PR is not ready to merge.
- Baseline: refreshed `origin/main`, `26a0de519ee4f7eae2e556b8da7726539d578594`;
  initially clean. Working branch: `security/remediate-all-findings`.
- Discovery: 14 new findings (11 medium, 3 low) from completed repository scan
  `wfr_1cb38532afa4dc13e4acdc43f5953f4ebd3b4308486bbadb640050a3194de7fb`,
  target `3d41ef56b524b7acfa11559859fc0c7dab0daa73`, completed 2026-10-03.
  Direct repository-filtered finding lists returned zero; querying the exact scan
  returned all 14 with no further cursor. Full details contain no proposed patches.
- Workstreams: CI/publication credentials, API/transfer bounds, local config/runtime
  security and HTTPS policy, watch-root and remote-album authorization.
- User approved HTTPS-by-default with explicit HTTP exception and `xhigh` rescan.
- Checkpoints: `a303e95` contains reviewed CI hardening; `6e1a781` contains
  application remediation; `cf290b6` corrects the Windows SQLite fixture cleanup. All are pushed to the single
  [draft PR #26](https://github.com/VoltKraft/immich-folder-watch/pull/26), targeting `main`.
  No merge or release was performed.
- Current disposition: 13 findings addressed in code; one partially addressed
  (`csf_77f3e84ec9b70e5aff765235`, concurrent watch-directory replacement).
  Full mapping, compatibility changes and residual risks are in
  [the remediation record](security-remediation-20261109.md).
- Independent reviewers checked CI trust, native Linux storage, REST/download
  bounds, realtime adapters and album authority. Review-driven corrections cover
  redirect/buffering in SocketIO and stale authority after failed/offline/rapid
  folder renames. No remaining actionable issue in those reviewed fixes; the
  acknowledged handle-bound filesystem gap remains open.
- Next action: review the single PR; retain draft status until the open filesystem
  race is resolved and exact-commit security validation can be arranged. All six CI jobs passed on `cf290b6`; this final handoff updates documentation only.
  No additional milestone was selected.

### Security validation (2026-11-09)

| Check | Result | Limits |
| --- | --- | --- |
| Portable Core tests | 448 passed on final combined rerun; 0 failed/skipped | .NET 10.0.203 selected by `global.json`; Linux x86_64 |
| Linux GUI/protocol tests | 53 passed | Isolated headless UI, local sockets and D-Bus; no live Immich |
| Linux app build/analyzers | Passed, 0 warnings/errors | Debug build; generated branding not committed |
| Tooling/packaging | 97 Python tests passed, including real PowerShell security scripts and isolated signed Flatpak repository tests | Synthetic keys/artifacts only; no publication |
| Workflow validation | actionlint 1.7.12 passed; YAML parsed; independent CI review passed | No release/WinGet/Flathub dispatch executed |
| Filesystem/album security | Linked entries, ownership scope/restart, exact-ID and stale-ID handling covered | Path checks are not race-proof; Windows reparse/runtime acceptance outstanding |
| Rescan | Not executed: exposed Cloud connector has no documented PR branch/commit selector; no UI available and PR security-review feature disabled | Unchanged-main scan would not validate this branch; arrange exact-commit scan when supported |
| GitHub CI `42693673854` at `6e1a781` | Linux build/tests and packaging lint passed. Windows build passed with 0 warnings/errors; test job exposed pooled SQLite handles in the new ownership test cleanup | Added the repository-standard pool clearing after awaited operations; rerun passed in `42694315680`; Windows-specific 36 tests also passed |
| [GitHub CI `42694315680`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42694315680) at `cf290b6` | All six jobs passed: Windows/Linux application checks, packaging lint, candidate preparation, and native x86_64/aarch64 packages. Windows: Core 439 passed / 9 platform skips; Windows-specific 36 passed; Linux-project tests 34 passed / 19 platform skips; full solution build 0 warnings/errors; 7 PowerShell security tests passed | Both native x86_64 and aarch64 candidate builds/validation and artifact uploads passed; actual ARM64/UNC app runtime not exercised |
| Superseded native run | Earlier x86_64 candidate could not fetch its replaced synthetic PR merge commit after a new push | No source/compiler failure; current run is authoritative |
| Native runtime limits | Actual ARM64/UNC runtime remains unavailable | Native ABI source inspection and package compilation do not establish runtime behavior |
| Worker follow-up | 54 passed, 1 existing test raced SQLite persistence; moved its database assertion after durable completion and worker stop; final combined rerun passed | No product behavior was changed to satisfy the timing assertion |
| Initial sandbox attempts | VSTest socket and GPG-agent startup were denied; approved isolated reruns passed | Environment failures were not counted as passing tests |
| Repository diff | `git diff --check` passed; 79 local documentation paths checked with no missing targets; final staged artifact review passed | Only task-owned sources/docs/tests are staged |

## Previous completed distribution handoff

- Template cleanup: Completed 2026-10-16. Initialized workflow records for the
  established project; preserved its README, implementation, product documents,
  and history. Do not repeat initialization cleanup.
- Last updated: 2026-11-07 (Europe/Berlin).
- State / scope: `M-FLATPAK-PAGES-20261107` complete. The signed repository is
  live at <https://voltkraft.github.io/immich-folder-watch/>.
- Implementation revision: `48e6be14ccf508385c4b1796842010c09e2d1fb4`, pushed to
  `main`; product version and published bundle inputs remain `2.11.3`.
- Latest verified result: [Pages workflow 42412670753](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42412670753)
  succeeded. Both live descriptors work, and isolated Flatpak clients downloaded
  both complete architecture refs with commit and summary verification enabled.
- Authorization / execution: The user explicitly approved the signing-key upload,
  push and Pages activation on 2026-11-07 after the initial automatic approval
  rejection. The secret and fingerprint variable are configured, Pages uses
  Actions with HTTPS, and its environment allows branch `main` and tags `v*`.
- Next concrete action: No remaining distribution setup. Future stable releases
  dispatch the repository workflow automatically. Preserve the signing-key backup;
  select any subsequent product milestone separately.
- Required input: None.

## Historical distribution Goal reference

- Goal requested for this assignment: No. No Goal was started.
- Actual Goal state in another chat: Not inspected; this document neither activates
  nor transfers a run. Query actual Goal controls if a continuation refers to one.
- Selected Goal milestone / criteria snapshot / budget: Not applicable.

## Progress and evidence

| Milestone / criteria | Status | Evidence / remaining work |
| --- | --- | --- |
| `M-TEMPLATE-MIGRATION-20261016`, `TM-AC01` through `TM-AC04` | Verified | Guarded apply and preservation/static checks passed; see historical validation record and local recovery bundle |
| `M-FLATPAK-PAGES-20261107`, `FP-AC01`/`02`/`03`/`05` | Verified | Implementation, real signed bundles, regression tests, review and docs complete |
| `M-FLATPAK-PAGES-20261107`, `FP-AC04` | Verified | Explicitly authorized setup and Pages deployment succeeded; live descriptors, both architecture downloads and signature verification passed |

## Flatpak distribution validation (2026-11-07)

| Check | Result / evidence | Limits |
| --- | --- | --- |
| Existing release inputs | GitHub API confirmed stable `v2.11.3`; x64 bundle 34,198,880 bytes, ARM64 bundle 30,983,120 bytes | Existing release assets were read/downloaded, not changed |
| Real repository generation | Both bundles imported and signed with fingerprint `4ED65AC1C14D559C721C7A8B44B33451708EAD7D`; complete site is about 87 MiB on disk at ignored `artifacts/flatpak-pages-preview/` | Local staging only; no Pages deployment |
| Real client discovery | Isolated `flatpak remote-add` with public key and `remote-info` resolved x86_64 commit `bdcfdb3e896ca6be8c9d0b93e5947884711e2c56da1da3a6cecbfcbe89200bcf` and aarch64 commit `86250534e754a0fa6c2d0ab1236bf87e862599416f0871d979e424ced402e30b` | No installation in the real user profile, runtime download or app execution |
| Python tooling tests | `python3 -m unittest discover -s tools/tests -p 'test_*.py' -v`: 90 passed, including seven new repository tests | Initial sandbox run failed because gpg-agent sockets were denied; rerun with approved isolated local execution passed |
| Repository integration regression checks | Signed multiarchitecture import, updates after complete repo replacement, unsigned-summary rejection, `.flatpakref` client consumption, malformed input/branch and size-limit rejection all passed | Synthetic fixture updates; real app update across published Pages versions not yet observed |
| Workflows and review | All workflow YAML parses; actionlint passed for all workflows; independent read-only review found no actionable defects; `git diff --check` passed | Pages workflow succeeded; environment permits `main` and release tags `v*` |
| New action licenses | Official upstream MIT licenses verified for configure-pages, upload-pages-artifact and deploy-pages | CI-only additions; no application dependencies changed |
| Remote activation | Completed after explicit consent: `FLATPAK_GPG_PRIVATE_KEY` Actions secret, matching `FLATPAK_GPG_KEY_ID` variable, Pages `build_type=workflow`, HTTPS enforced, environment branch `main` / tag `v*` | Private key never printed or committed; previous rejection is resolved |
| Pages publication | Build and deployment both succeeded in [run 42412670753](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42412670753) from `48e6be1` | Publishes existing `v2.11.3` assets; no product release or tag was created |
| Live HTTPS endpoints | HTTP 200 for index, `.flatpakrepo`, `.flatpakref`, public key, repo config, summary and summary signature | Evidence saved locally in ignored `artifacts/flatpak-pages-live-verification.json` |
| Live client verification | Fresh isolated `.flatpakrepo` client resolves both expected commits; a separate `.flatpakref` client downloads complete x86_64 and aarch64 apps from Pages, with `gpg-verify=true` and `gpg-verify-summary=true` | Used `--no-deps --no-related --no-deploy`; no real-user installation, runtime download or application execution; future-version update remains covered by the local integration regression test |
| GitHub packaging CI | `Lint Flatpak packaging` passed in [run 42412671037](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42412671037), including repository tests | Broader application tests and native candidate builds were still running at handoff; no application code changed |
| Local application/desktop/Immich tests | Not run | Distribution-only change; live distribution was verified without application execution |

## Historical migration validation record

| Check | Result / evidence | Limits |
| --- | --- | --- |
| Initial Git state | Clean at migration baseline `3d41ef56b524b7acfa11559859fc0c7dab0daa73`; inspected with `git --no-optional-locks -C <repository> status --porcelain=v2 --branch --untracked-files=all` and both working/staged diffs | Local refs only; no fetch |
| Old agent provenance | All 37 old `.codex` tracked files match template commit `fe6db7f7e7e65f076b5dc0706fc6d46eba6de14b` | Confirms no target-specific profile customizations |
| Applied Markdown links, TOML, scoped diff, content preservation | Passed: 11 Markdown files, 90 local links/anchors, 35 TOML files / 34 roles; 298 unaffected original files retain identical SHA-256 hashes. Reports: local `inspection-after.json` and `integrity.json` in the recovery bundle. | Static checks; ignored artifacts, nested checkouts, and runtime data are outside the content manifest |
| Application builds/tests, packaging, desktop checks, live Immich | Not run for this documentation/configuration-only assignment | No runtime, UI, sync, installer, or service validation implied |
| Existing QA reports | Retained as historical evidence at their original revisions | Migration does not renew their sign-offs or fill blank acceptance rows |

## Open questions and blockers

| ID | Question / missing prerequisite | Impact and next action |
| --- | --- | --- |
| IFW-Q01 | Resolved: GitHub Pages Flatpak distribution selected on 2026-11-07. | See `M-FLATPAK-PAGES-20261107`. |
| IFW-Q04 | Resolved: explicit user consent received; secret upload, push, Pages activation and live validation completed. | No remaining activation blocker. |
| IFW-Q02 | Older README/architecture summaries call Flatpak tray support disabled, while detailed architecture, parity notes, and later changelog describe restricted tray integration. Some QA labels also predate current modes. | Pre-existing documentation discrepancy, outside this migration. Reconcile against code and actual desktop evidence in a separately selected task; do not infer runtime behavior from either summary. |
| IFW-Q03 | Native desktop acceptance and actual Flathub publication are not established by the inspected historical preparation record. | Keep the existing QA boundaries; verify only when the corresponding task and environment are authorized. |

## Completion and next handoff

- Historical workflow migration is complete at `4afa9f4`; recovery evidence remains
  in [the migration record](template-migration.md).
- `FP-AC01` through `FP-AC05` are complete; local and live evidence is recorded above.
- Deliverables: Repository generator/tests, Pages workflow and release dispatch,
  public signing key, installation/migration/operations documentation and CI wiring.
- Private recovery key: ignored `artifacts/flatpak-signing/private-key.asc`, mode
  0600 inside a mode-0700 directory. Public key only is included in Git.
- Checkpoint: Implementation `48e6be1` is published; this completion record and
  installation-document updates are saved in a separate documentation checkpoint,
  whose hash is recorded in the chat handoff. No version/tag change.
