# RW-02 stack decision

**Keep egui/eframe with wgpu as the preferred candidate. RW-02 remains open.** At `6084b23` both Ubuntu hosts and Windows ARM64 met all eleven native resource limits in the selected profiles. Both retained Windows x64 Mailbox depths exceeded the same-host WPF limits for idle close, scan close and scan reopen. Both Windows targets passed the full ordinary filename and reopened editor checks. A second normal launch gave the original window keyboard focus on x64. ARM64 kept it in the background. Interactive Shell activation, notification presentation, mixed DPI and RDP still require native evidence. RW-03 depends on RW-02 acceptance. [Scan measurements](rw02-windows-window.md#native-results-at-6084b23) · [Reopened filenames](rw02-windows-text.md#captured-ordinary-and-reopened-filenames-at-1904be7) · [Project contract](../project.md#m-rust-implementation-20261114) · [Stage gates](../rust-rewrite-plan.md#staged-implementation-proposal) · [Acceptance record](acceptance.md)

At `e796d30` both Ubuntu desktops again met all eleven X11 budgets. The
Windows jobs ended before a complete comparison. The x64 scan that did
finish exceeded both window-response limits. The Windows contrast adapter
has since been corrected. On native x64, the Linux GUI also followed high
contrast on a stock Noble GTK portal through its GNOME setting.
[Windows process exits](rw02-windows-window.md#native-process-exits-at-a1011bf-and-e796d30)
· [Ubuntu and Fedora contrast](rw02-appearance.md#high-contrast-on-older-ubuntu-settings-portals).

## What the gate requires

RW-01 is accepted. RW-02 requires a minimal native Rust GUI, filesystem, legacy codec and realtime spikes, four native target results, an exact licensed feature/font graph, a stack choice and an effort estimate. The GUI must demonstrate hidden startup, close/reopen with the engine alive, tray or launcher activation, clean Quit/restart, idle repaint behavior, both Linux window systems, Windows focus/COM, parented portals, tray absence/restart and notifications. It also requires scaling and multiple monitors, keyboard-only operation, screen-reader labels/focus, masking, German text, real IME composition, Unicode paste and graphics initialization/loss/fallback. The same-machine .NET reference sets explicit startup, CPU, memory, repaint and 100,000-file scan response budgets. [GUI gate](../rust-rewrite-plan.md#gui-acceptance-before-full-commitment) · [Native architecture and validation](../rust-desktop-standard.md#rds-08-build-and-validation-contract)

## Native evidence

All four archived subjects at `8b071ab` rebuilt the reviewed graph. Subsequent rows use completed workflow steps at `8a8adaa` and separate Fedora runs where stated. The Linux comparisons ran three 100,000-file trials and compared each metric against that host’s preselected .NET limits. All four follow-up archives matched the digest published by Actions and passed ZIP integrity checks. [Archive identifiers and findings](rw02-native-gui.md#native-follow-up-at-8a8adaa). [Archived run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452) · [Follow-up run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642)

| Target | Demonstrated | Outstanding for the decision |
| --- | --- | --- |
| Linux x64 | X11 and Wayland lifecycle, native Orca, XIM/GNOME composition, monitor moves, mixed-direction editing and parented Flatpak grants. The repeated X11 measurements passed all eleven limits. Actual private Plasma panel clicks and system appearance changes passed on x64. | On an offline Noble VM the installed private backport enforced the read lease and the original package was restored successfully. The user deferred distribution approval. [Installed comparison](rw02-portal-noble.md#installed-patch-and-rollback-on-the-same-native-guest). [Portal](rw02-portal-noble.md) · [Plasma](rw02-plasma.md) · [Appearance](rw02-appearance.md) |
| Linux ARM64 | Native Orca speech and masking on both backends, Mozc commit, mixed scaling, installed Flatpak grants and Vulkan loss. At `1b95ba0` all eleven X11 limits passed and two Plasma panel clicks reopened the same window. | The stock Documents portal refused the required lock. Its private Noble backport passed. The stock Settings portal did not export contrast. [Plasma evidence](rw02-plasma.md#native-ubuntu-arm64-panel-at-6af7100) · [Installed grants](rw02-portal-dialog.md) |
| Windows x64 | DX12 lifecycle and recovery, ordinary field editing, fonts, Japanese IME, NVDA, clipboard and Startup readback passed. At `1b95ba0` both retained frame depths met eleven limits. Each reopened the same HWND, kept the focused filename and drew the edit. | At `6084b23` idle close, scan close and scan reopen exceeded the WPF limits. The Shell show callback passed. Pointer activation and independent notification presentation remain open. Mixed DPI and RDP require a suitable display. [Launcher](rw02-instance.md#private-launcher-cleanup-at-8566f81) · [Timing](rw02-windows-window.md#native-results-at-6084b23) · [Shell](rw02-windows-services.md) |
| Windows ARM64 | DX12 lifecycle and recovery, ordinary field editing, fonts, Japanese IME, NVDA, clipboard and Startup readback passed. At `1b95ba0` both retained frame depths met all eleven limits and drew the edited filename after reopening. | Both ordinary launchers reopened a visible window on Default, where Windows denied foreground. Explorer refused registration. Interactive activation, notification presentation and mixed DPI/RDP remain open. [Launcher](rw02-instance.md#private-launcher-cleanup-at-8566f81) · [Display](rw02-windows-display.md) · [Timing](rw02-windows-window.md#native-results-at-6084b23) |

Fedora additionally exercised a real Intel Iris Xe render node. At `68795a2`, three independent trials on a private Mutter virtual output recovered to llvmpipe, preserved the worker and accepted the next edit. Six 15-second idle intervals had zero application buffer commits. This establishes hardware-backed rendering on that virtual output. The plan also calls for assessment under RDP and on lower-end GPUs. It prescribes neither a physical GPU reset nor every possible GPU/monitor pairing. A focused iced comparison is the contingency for a failed essential capability, alongside a documented eframe fix. Glow is optional. [Intel results](rw02-wayland-recovery.md) · [Renderer decision](../rust-rewrite-plan.md#gui-decision)

## Inputs and remaining work

The filesystem feasibility result includes both real outcomes on both Ubuntu
architectures. The stock Documents portal refuses the upload read lease,
and the private backport enforces it across the grant and its backing file.
The RW-02 gate requires disclosing the filesystem limitation. The Linux
candidate still needs an available host implementation that preserves this
authorization and file lock. The outstanding Windows GUI gates independently
keep the stack selection open. [Stage exit criteria](../rust-rewrite-plan.md#staged-implementation-proposal)
· [Distribution availability](rw02-portal-upstream.md#additional-distribution-sources-checked-on-2026-11-22).

- **Desktop.** Rust 1.100.0, egui/eframe 0.37.0, winit 0.30.13 and wgpu 30.0.0 are pinned. The four verified normal/build profiles contain 235 packages per Linux target and 135 per Windows target, with AccessKit, clipboard, Vulkan on Linux and DX12 on Windows. The desktop spikes use zbus 5.19.0 on Linux and windows 0.62.2 for Windows Shell/COM. The maintained egui/epaint change uses unicode-bidi 0.3.18. Five unmodified OFL-1.1 Noto assets supply Sans, Mono, Symbols 2, Arabic and CJK JP. Default fonts, optional emoji and inspection are excluded. Retain the source/notice and Wayland relink obligations in the combined candidate. [Manifest](../../tools/rust-qa/gui/Cargo.toml) · [Exact sources, features and fonts](rw02-gui-dependencies.md)
- **Filesystem and state.** Four hosts passed handle-bound primitives, 5,844 scalar comparisons per casing mode at `93ecc35`, two live-WAL backups and 40 C# storage readbacks each. At `8566f81` each passed 162 YAML byte comparisons, 259 semantic comparisons and 140 C# readbacks using serde-saphyr 2.2.0. Storage uses rusqlite 0.43.0 with SQLite 3.54.1. Windows also passed encrypted loopback SMB. On tested distro Documents portals the required cooperating upload lock returned `ENOSYS`. The private backport enforced it on both architectures. Native x64 also passed an actual package upgrade and rollback with the installed Flatpak. Distribution and package maintenance remain open. The candidate guard passed on both Windows architectures across two sessions of one elevated account. The standard-user trial and old/new installed handover remain open under RI-AC05/08. [Filesystem](rw02-filesystem.md) · [YAML](rw02-yaml.md) · [Storage](rw02-storage-inputs.md) · [Portal control](rw02-portal-upstream.md) · [Writer ownership](rw02-cross-session.md)
- **Transport and watch events.** All four targets passed sixteen loopback scenarios at `8091469`, including real TLS endpoint-name rejection. Windows ARM64 also ran the transport with its reconstructed import library. Each Ubuntu target passed fifteen watch scenarios and each Windows target passed fourteen. Both Windows hosts observed actual kernel notification loss, replaced the registration and recovered all 514 files. [Transport](rw02-realtime-transport.md#tls-endpoint-identity) · [ARM64 relink](rw02-windows-imports.md) · [Watch events](rw02-watch-events.md)
- **Native logging and combined inputs.** The Windows Event Log passed on both targets. Both Ubuntu journals returned six records at the expected priorities. The combined development profile resolves 351 active external inputs across the four architectures, including three reconstructed sources. Both Ubuntu hosts built offline and relinked a modified Wayland binding. Both Windows hosts passed the combined native smoke. All eleven canonical graph and inventory files matched across the four targets. The packaged candidate inventories, notices and SBOM remain open. [Platform logs](rw02-platform-logs.md) · [Combined graph and reconstruction](rw02-combined-profile.md) · [Dependency rules](../rust-desktop-standard.md#rds-07-dependencies-and-licensing)

At `72fff40`, all four new archives matched their published digests. Both
Ubuntu hosts again met all eleven paired X11 limits. On both Windows hosts,
the source of the missing scan data was the ETW recorder's SDK compile
error. The retained-window candidate will be measured against the same
WPF controls. Both Windows hosts installed and removed the official Japanese
Basic Typing package. The second composition trial stopped at account
language selection. In a separate native x64 test, the stock Noble portal
and pristine package rebuild refused a file lease. The private backport
passed 42 grant/backing lock operations. [Native follow-up](rw02-native-gui.md#native-follow-up-at-72fff40)
· [Noble portal](rw02-portal-noble.md) · [Japanese input](rw02-windows-ime.md).

## Effort to reach a freeze

These are active engineering estimates assuming access to disposable input-capable Windows desktops, the system IME, a real reader, and representative graphics sessions. VM provisioning and upstream portal release time are additional. Parallel work can shorten elapsed time.

| Work | Estimated engineer-days |
| --- | ---: |
| Qualify Windows focus, tray/COM, reader, IME and mixed-DPI behavior on both architectures, then rerun the ordinary GUI | 4–8 |
| Finish native graphics coverage and compare paired .NET/Rust resource receipts, including verified scan work and threshold regressions | 3–6 |
| Resolve the supported Documents-portal path and consolidate the selected inputs, native receipts and notices | 2–4 |

Retest a reproducible eframe regression on an input-owning desktop first. An unresolved essential failure calls for a bounded implementation fix or the plan's focused iced comparison before freezing the stack. [Desktop standard](../rust-desktop-standard.md#rds-06-gui-policy)

The source comparison with iced 0.14.0 found the same underlying Win32
visibility implementation in its pinned version of winit. Its tiny-skia
renderer presents through GDI, making the cost of visible drawing a distinct
path to measure. Its native accessibility support and the rights for an
embedded icon font need qualification before adoption.
[Windows source and renderer comparison](rw02-windows-window.md#renderer-comparison-with-iced-0140).

At `549066f` and `ba02f8b`, the first-party GDI surface met the four
same-host WPF window-response limits on Windows x64. Both full egui runs
exceeded the scan close and reopen limits. On ARM64 the egui window met
all eleven resource limits twice. Both small GDI trials stopped at the
first independent screen observation. The results support testing bounded
frame queue depth on the qualified DX12 software adapter with the complete
egui view and its existing accessibility implementation.
[Two native comparisons](rw02-windows-window.md#visible-gdi-and-retained-egui-under-the-same-inventory).

At `1b95ba0` the Ubuntu x64 and ARM64 X11 guests both passed the eleven
same-host limits and the Plasma panel reopened the retained GUI twice on
each. The standard Noble Documents daemon continued to refuse the upload
lock. [Pinned native rehearsals](rw02-native-gui.md#ubuntu-native-results-at-1b95ba0).
