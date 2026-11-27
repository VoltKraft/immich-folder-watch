# RW-02 stack decision

**Keep egui/eframe with wgpu as the preferred candidate. RW-02 remains open.**
Both native Ubuntu desktops met all eleven same-host limits at `3d67a46`.
At `0bb39bf` the two retained Windows ARM64 Mailbox profiles met all
eleven WPF limits. On x64 both profiles exceeded the idle-close, scan-close
and scan-reopen limits across three trials per profile. Both Windows filename
editors passed. The ARM64 ordinary second launch reopened the window in
the background. Windows Shell activation, visible notifications, a
reversible contrast change, mixed DPI, RDP and ordinary-user cross-session
ownership remain open.
[Windows measurements](rw02-windows-window.md#windows-results-at-0bb39bf) ·
[Ubuntu results](rw02-native-gui.md#ubuntu-native-results-at-3d67a46) ·
[Stage gates](../rust-rewrite-plan.md#staged-implementation-proposal) · [Acceptance record](acceptance.md).

On Windows Server 2022 x64 at `47fe26d`, Explorer drew the registered
Rust tray icon and its changed color at the same point. The accessibility
lookup found no eligible item to invoke, and the GUI received no Shell
activation callback.
[Windows Server 2022 observation](rw02-windows-services.md#visible-background-start-icon-on-windows-server-2022-at-47fe26d).

On a Windows x64 WARP adapter, the private CPU renderer met all eleven
same-host WPF limits at `dddb21a`. All 421 file-qualified reopens showed
a full editor frame before the next close. Scan close/reopen p95 was
5.71/9.66 ms. The ordinary retained renderer met eight limits on the
same host. A second x64 host at `972adc6` also met all eleven limits,
with full frames in 171 of 172 eligible reopen intervals. This makes
the CPU path viable for the tested software adapter. At `3b488ca` automatic
selection passed all eleven limits and delivered a complete frame on all
246 eligible reopens. At `10ab0b8` automatic selection again met all
eleven limits. A real sampler change switched the example to wgpu while
preserving its partial texture update on the same visible window.
At `483f053` the timed GUI recreated its WARP device and window after
the first device was destroyed. Its visible draft and original worker
survived. All eleven limits and the separate sampler handoff passed.
On Fedora x64 six real editor frames at two scales matched
the egui-wgpu reference within two levels per color channel.
[Native measurements](rw02-windows-window.md#native-windows-x64-cpu-renderer-at-dddb21a) ·
[Independent second run](rw02-windows-window.md#native-windows-x64-cpu-repeat-at-972adc6) ·
[Automatic WARP selection](rw02-windows-window.md#automatic-warp-selection-on-windows-x64-at-3b488ca) ·
[Visible handoff](rw02-windows-window.md#visible-texture-handoff-on-windows-x64-at-10ab0b8) ·
[Device recovery](rw02-windows-window.md#warp-device-recovery-on-windows-x64-at-483f053) ·
[Source inventory and pixel comparison](rw02-windows-window.md#cpu-rendering-of-the-original-editor-meshes).

On Windows x64 at `de3eec4`, disabling DWM transitions on the retained
window changed scan close and reopen p95 by less than 0.1 ms on that host.
Both variants exceeded the WPF limits despite successful presentation and
visible edits. Keep the ordinary window policy.
[Native comparison and originals](../../tools/rust-qa/windows-warm-window/dwm-transitions.md#native-windows-x64-result-at-de3eec4).

The private build at `c52da2d` processed window input while waiting for
DXGI on x64. It met nine of eleven WPF limits. The median ordinary
scan-reopen p95 on this host was 33.06 ms. The private build took
45.88 ms against a limit of 21.70 ms. This renderer change does not
qualify for adoption.
[Frame timing, resource limits and editor pixels](rw02-windows-window.md#one-shot-frame-readiness-on-windows-x64-at-c52da2d).

The installed Noble backport completed the requested Ubuntu package
feasibility trial. The user left distribution and ongoing package
maintenance undecided. The stock portal's refusal to lock a file still
affects the operating requirements for a candidate on that system.
[Installed upgrade, contention and rollback](rw02-portal-noble.md#installed-patch-and-rollback-on-the-same-native-guest).

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
| Linux x64 | X11 and Wayland lifecycle, native Orca, XIM/GNOME composition, monitor moves, mixed-direction editing and parented Flatpak grants. The repeated X11 measurements passed all eleven limits. Private Plasma panel clicks and system appearance changes passed. On Fedora, the installed test Flatpak's notification appeared in GNOME Shell's message list and disappeared after withdrawal. | On an offline Noble VM the installed private backport enforced the read lease and the original package was restored successfully. The user deferred distribution approval. [Installed comparison](rw02-portal-noble.md#installed-patch-and-rollback-on-the-same-native-guest). [Portal](rw02-portal-noble.md) · [Plasma](rw02-plasma.md) · [Appearance](rw02-appearance.md) |
| Linux ARM64 | Native Orca speech and masking on both backends, Mozc commit, mixed scaling, installed Flatpak grants and Vulkan loss. At `1b95ba0` all eleven X11 limits passed and two Plasma panel clicks reopened the same window. At `21e794f` the GUI visibly followed GNOME’s contrast setting. At `1a62d5c` the installed test Flatpak posted and withdrew the same notification through GTK on Ubuntu 24.04. Three monitor captures showed its title and body only in the open GNOME message list before withdrawal. [Notification captures and bus trace](rw02-portal-dialog.md#visible-gnome-notifications-on-linux-arm64). | The stock Documents portal refused the required lock. The private Noble backport passed. Distribution remains undecided. [Native contrast](rw02-appearance.md#stock-ubuntu-x64-and-arm64-at-21e794f). [Plasma evidence](rw02-plasma.md#native-ubuntu-arm64-panel-at-6af7100) · [Installed grants](rw02-portal-dialog.md) |
| Windows x64 | At `f155b65` both Mailbox profiles met all eleven WPF limits. The CPU painter met all eleven in both explicit WARP trials and again with automatic selection at `3b488ca`. All 246 eligible reopens on that host received a full frame. NVDA, IME, clipboard, DX12 recovery, Startup and WinRT history passed. WPF and Rust gained focus after an ordinary second launch. At `de3eec4` an F24 launch from a foreground window on a private desktop focused the original Rust window and preserved its worker. [WARP measurements](rw02-windows-window.md#automatic-warp-selection-on-windows-x64-at-3b488ca) · [Keyboard launch](rw02-instance.md#ordering-a-fast-foreground-keyboard-launch). | The ordinary Mailbox profiles exceeded both scan-response limits at `ead9fb3`. Explorer accepted both registrations at `f155b65`, but neither rectangle showed its marker. Explorer activation, visible notifications, reversible system contrast, mixed DPI and RDP remain open. [Timings](rw02-windows-window.md#windows-results-at-ead9fb3) · [Tray and notifications](rw02-windows-services.md#native-icon-pixels-and-winrt-popup-at-f155b65) · [Display](rw02-windows-display.md#hosted-display-and-field-capture-at-f155b65) |
| Windows ARM64 | At `ead9fb3` both retained Mailbox profiles met all eleven limits across three trials per profile. Independent replay verified the native job CPU and working sets. NVDA, Japanese IME, WinRT history, clipboard and Startup passed. At `de3eec4` an F24 launch from a foreground window on a private desktop focused the original Rust window and preserved its inventory worker. [Keyboard launch](rw02-instance.md#ordering-a-fast-foreground-keyboard-launch). | Both WPF and Rust reopened in the background after an ordinary second launch. Explorer declined registration. Explorer activation, visible notifications, reversible system contrast, mixed DPI and RDP remain open. [Windows ARM64 measurements](rw02-windows-window.md#windows-results-at-ead9fb3) · [Second launches](rw02-instance.md#native-staged-image-readback-at-f155b65) · [Tray and notifications](rw02-windows-services.md#native-icon-pixels-and-winrt-popup-at-f155b65) · [Contrast](rw02-appearance.md#windows-contrast-baseline-and-restoration-at-f155b65) |

Fedora additionally exercised a real Intel Iris Xe render node. At `68795a2`, three independent trials on a private Mutter virtual output recovered to llvmpipe, preserved the worker and accepted the next edit. Six 15-second idle intervals had zero application buffer commits. This establishes hardware-backed rendering on that virtual output. The plan also calls for assessment under RDP and on lower-end GPUs. It prescribes neither a physical GPU reset nor every possible GPU/monitor pairing. A focused iced comparison is the contingency for a failed essential capability, alongside a documented eframe fix. Glow is optional. [Intel results](rw02-wayland-recovery.md) · [Renderer decision](../rust-rewrite-plan.md#gui-decision)

## Inputs and remaining work

Installed shipping workers have now consumed Rust's live SQLite backup
after a real upload on native Ubuntu and Windows, x64 and ARM64. The
Windows ARM64 result used a private input desktop in the original logon
session. The separate Default-desktop trial stopped before Quit. Installed
WPF secondary launches also reactivated the Rust inventory worker on both
architectures. The same-user, standard-user cross-session check and RW-07
candidate migration remain open.
[Ubuntu recovery](rw01-storage-contract.md#installed-ubuntu-worker-restart-at-3d67a46) ·
[Windows recovery](rw01-storage-contract.md#installed-windows-worker-restart-at-c4d05b6) ·
[Installed Windows activation](rw02-instance.md#installed-windows-activation-at-d7c084c).

The filesystem feasibility result includes both real outcomes on both Ubuntu
architectures. The stock Documents portal refuses the upload read lease,
and the private backport enforces it across the grant and its backing file.
The RW-02 gate requires disclosing the filesystem limitation. The Linux
candidate still needs an available host implementation that preserves this
authorization and file lock. The outstanding Windows GUI gates independently
keep the stack selection open. [Stage exit criteria](../rust-rewrite-plan.md#staged-implementation-proposal)
· [Distribution availability](rw02-portal-upstream.md#additional-distribution-sources-checked-on-2026-11-22).

- **Desktop.** Rust 1.100.0, egui/eframe 0.37.0, winit 0.30.13 and wgpu 30.0.0 are pinned. The four verified normal/build profiles contain 235 packages per Linux target and 135 per Windows target, with AccessKit, clipboard, Vulkan on Linux and DX12 on Windows. The desktop spikes use zbus 5.19.0 on Linux and windows 0.62.2 for Windows Shell/COM. The maintained egui/epaint change uses unicode-bidi 0.3.18. Five unmodified OFL-1.1 Noto assets supply Sans, Mono, Symbols 2, Arabic and CJK JP. Default fonts, optional emoji and inspection are excluded. Retain the source/notice and Wayland relink obligations in the combined candidate. [Manifest](../../tools/rust-qa/gui/Cargo.toml) · [Exact sources, features and fonts](rw02-gui-dependencies.md)
- **Filesystem and state.** Four hosts passed handle-bound primitives, 5,844 scalar comparisons per casing mode at `93ecc35`, two live-WAL backups and 40 C# storage readbacks each. At `0bb39bf` each passed 246 YAML byte comparisons, 392 semantic comparisons and 224 C# readbacks using serde-saphyr 2.2.0. On each host the C# worker restarted from Rust’s returned backup after four synthetic activities. Storage uses rusqlite 0.43.0 with SQLite 3.54.1. Windows also passed encrypted loopback SMB. On tested distro Documents portals the required cooperating upload lock returned `ENOSYS`. The private backport enforced it on both architectures. Native x64 also passed an actual package upgrade and rollback with the installed Flatpak. Distribution and package maintenance remain open. The candidate guard passed on both Windows architectures across two sessions of one elevated account. The standard-user cross-session trial and installed handover with the complete candidate remain open under RI-AC05/08. [Filesystem](rw02-filesystem.md) · [YAML](rw02-yaml.md#four-native-anchor-and-compact-mapping-exchanges-at-0bb39bf) · [Worker restarts](rw01-storage-contract.md#native-worker-recovery-at-0bb39bf) · [Storage](rw02-storage-inputs.md) · [Portal control](rw02-portal-upstream.md) · [Writer ownership](rw02-cross-session.md)
- **Transport and watch events.** All four targets passed twenty loopback scenarios at `e2f161b`, including TLS endpoint-name rejection, delayed namespace acknowledgement, continued polling during a stalled WebSocket probe and peer-observed shutdown. Windows ARM64 also ran the transport with its reconstructed import library. Each Ubuntu target passed fifteen watch scenarios and each Windows target passed fourteen. Both Windows hosts observed actual kernel notification loss, replaced the registration and recovered all 514 files. [Transport](rw02-realtime-transport.md#tls-endpoint-identity) · [ARM64 relink](rw02-windows-imports.md) · [Watch events](rw02-watch-events.md)
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
