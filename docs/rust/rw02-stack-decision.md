# RW-02 stack decision

**Keep egui/eframe with wgpu as the preferred candidate. RW-02 remains open.**
Both native Ubuntu desktops and the retained Windows ARM64 Mailbox builds
met all eleven same-host performance limits. On a hosted Windows x64 WARP
adapter, the CPU-painted executable at `483f053` met all eleven WPF limits
and recovered its device. The local Server 2025 x64 guest then ran that
archived executable over RDP at 96 and 192 DPI. The x64 Mailbox builds
met all eleven limits at `f155b65` and exceeded the two scan-response
limits on the host at `ead9fb3`.
[Ubuntu limits](rw02-native-gui.md#ubuntu-native-results-at-3d67a46) ·
[Mailbox at f155b65](rw02-windows-window.md#native-results-at-f155b65) ·
[Mailbox at ead9fb3](rw02-windows-window.md#windows-results-at-ead9fb3) ·
[CPU renderer and WPF control](rw02-windows-window.md#warp-device-recovery-on-windows-x64-at-483f053) ·
[Local x64 display trials](rw02-windows-display.md#local-windows-server-2025-x64-display-trial).

Windows ARM64 still needs native Explorer activation, a visible ordinary
notification, reversible system contrast, mixed DPI and RDP. Cross-session
ownership with installed WPF also remains open. On x64, installed WPF could
upload while Rust held both its admission endpoint and writer guard in a
second session of the same account.
[ARM64 display observations](rw02-windows-display.md#arm64-source-monitor-focus-at-3d55500) ·
[Installed cross-session launches](rw02-cross-session.md#installed-304-worker-in-another-session) ·
[Stage gates](../rust-rewrite-plan.md#staged-implementation-proposal) · [Acceptance record](acceptance.md).

The native Ubuntu worker restart builds also passed all eleven paired
resource limits. On Fedora x64 the canonical GUI now restores focus and
backwards text selection when Mutter recreates the window. The newer
Windows ARM64 application-mode trial confirmed the ordinary send and
history cleanup. No visible Shell banner was verified. Two x64 console
trials preserved the normal editor's backwards selection and focus
across an ordinary second launch. On ARM64 both rebuilt variants showed
the edited filename on private 96-DPI desktops. The archived ordinary GUI
also restored the selection and accepted the next two keystrokes after an
ordinary second launch. The separate Default-desktop trials timed out
waiting for the original field.
[Windows x64 second launch](rw02-windows-text.md#backward-filename-selection-across-an-ordinary-x64-second-launch) ·
[ARM64 second launch](rw02-windows-text.md#arm64-filename-selection-on-the-private-console) ·
[ARM64 frames after the selection fix](rw02-windows-display.md#native-arm64-editor-frames-after-the-selection-fix).
[Ubuntu budget repeat](rw02-performance.md#retained-worker-budget-on-ubuntu-x64-and-arm64-at-9487dbe) ·
[Reopened editor](rw02-native-gui.md#filename-selection-after-a-normal-close-and-second-launch) ·
[ARM64 original sender](../../tools/rust-qa/windows-services/toast-history.md#ordinary-notification-in-app-state-after-quiet-time).

On Windows Server 2022 x64 at `47fe26d`, Explorer drew the registered
Rust tray icon and its changed color at the same point. The accessibility
lookup found no eligible item to invoke, and the GUI received no Shell
activation callback.
At `3c4d62c` the classic toolbar's default action opened the background-start
GUI with focus and the original inventory worker. At `29ce1c0` the same
action reopened the previously visible GUI after close. The GUI recorded
its original root still hidden when consuming the callback, then received
keyboard focus. Each positive case ran first on its own x64 test desktop.
Explorer exposed no usable rectangle for the second GUI in either order.
[First visible icon](rw02-windows-services.md#visible-background-start-icon-on-windows-server-2022-at-47fe26d) ·
[Verified background-start activation](rw02-windows-services.md#explorer-activation-after-a-hidden-start-at-3c4d62c) ·
[Verified visible-start activation](rw02-windows-services.md#explorer-reopened-the-original-closed-window-at-29ce1c0).

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
| Windows x64 | Hosted NVDA, clipboard, Startup and foreground keyboard launch passed. WPF and Rust also gained focus after an ordinary second launch. The measured CPU executable passed RDP, mixed DPI and both named-scheme contrast transitions on the local Server 2025 guest. The standard user's Japanese IME committed あ in the ordinary GUI. Explorer opened the retained background-start GUI and reopened the original closed window with focus and its worker. At `56b7ae8` the same local console passed all three physical menu selections, including restart with a new worker and clean Quit. The native sender showed the full WinRT title and body in a visible Shell banner. [Second launches](rw02-instance.md#native-staged-image-readback-at-f155b65) · [Display](rw02-windows-display.md#local-windows-server-2025-x64-display-trial) · [Contrast](rw02-appearance.md#reversible-windows-server-2025-x64-contrast-on-a-named-scheme) · [IME](rw02-windows-ime.md#standard-user-console-result-at-065ae57) · [Shell activation](rw02-windows-services.md#both-explorer-starts-on-windows-server-2025) · [Menu and replay](../../tools/rust-qa/windows-launcher/tray-menu.md#local-server-2025-result-at-56b7ae8) · [WinRT](rw02-windows-services.md#visible-winrt-banner-on-the-local-windows-server-2025-x64-console) | The installed 3.0.4 worker can still start across sessions when Rust owns the separate writer guard. [Installed worker](rw02-cross-session.md#installed-304-worker-in-another-session) |
| Windows ARM64 | The two retained Mailbox profiles met all eleven WPF limits across three trials each. NVDA, Japanese IME, clipboard and Startup passed. An ordinary second launch reopened the window in the background. A launch from a foreground keyboard action focused the original Rust window. At `c0dd89c` both installed launch orders reactivated their primary. The private input desktop also allowed WPF Quit and restored Default. [WPF limits](rw02-windows-window.md#windows-results-at-ead9fb3) · [IME](rw02-windows-ime.md) · [Keyboard launch](rw02-instance.md#ordering-a-fast-foreground-keyboard-launch) · [Installed activation by desktop](../../tools/rust-qa/windows-msi-interop/reverse/README.md#native-arm64-activation-at-c0dd89c) | Explorer refused the tray registration. At `ee0bcd2` WinRT history passed on two consoles, including one with Do not disturb off, but neither physical observer saw the banner. The single 96-DPI console and read-only contrast baseline leave mixed DPI, RDP and a reversible contrast change open. Standard-user writer exclusion across two interactive sessions remains unverified. [Explorer](rw02-windows-services.md#native-notification-observations-at-5efe1f1) · [WinRT](../../tools/rust-qa/windows-services/toast-history.md#first-notification-on-a-fresh-windows-arm64-console) · [Display](rw02-windows-display.md#arm64-source-monitor-focus-at-3d55500) · [Contrast](rw02-appearance.md#native-read-only-contrast-baseline-at-5efe1f1) |

Fedora additionally exercised a real Intel Iris Xe render node. At `68795a2`, three independent trials on a private Mutter virtual output recovered to llvmpipe, preserved the worker and accepted the next edit. Six 15-second idle intervals had zero application buffer commits. This establishes hardware-backed rendering on that virtual output. The plan also calls for assessment under RDP and on lower-end GPUs. It prescribes neither a physical GPU reset nor every possible GPU/monitor pairing. A focused iced comparison is the contingency for a failed essential capability, alongside a documented eframe fix. Glow is optional. [Intel results](rw02-wayland-recovery.md) · [Renderer decision](../rust-rewrite-plan.md#gui-decision)

## Inputs and remaining work

Installed shipping workers have now consumed Rust's live SQLite backup
after a real upload on native Ubuntu and Windows, x64 and ARM64. The
Windows ARM64 result used a private input desktop in the original logon
session. The separate Default-desktop trial stopped before Quit. Installed
WPF secondary launches also reactivated the Rust inventory worker on both
architectures.
[Ubuntu recovery](rw01-storage-contract.md#installed-ubuntu-worker-restart-at-3d67a46) ·
[Windows recovery](rw01-storage-contract.md#installed-windows-worker-restart-at-c4d05b6) ·
[Installed activation](rw02-instance.md#installed-windows-activation-at-d7c084c).

On Server 2025 x64, two Rust writers in the same standard user's console
and RDP sessions excluded each other in both orders. With installed WPF
already uploading, Rust identified its pipe server and refused admission.
When Rust started first, WPF uploaded the synthetic PNG, received HTTP 201
and committed its SQLite row while both Rust guards were held.
When the installed uploader ran first, a separate local x64 trial at
`bfd99b2` delivered its ordinary Quit in RDP after the upload committed.
Rust subsequently acquired the endpoint and writer guard in the console.
[Orderly WPF exit and Rust admission](../../tools/rust-qa/instance/cross-session/wpf-handover.md#local-server-2025-handover-at-bfd99b2).
[Two Rust writers](rw02-cross-session.md#standard-user-console-and-rdp-handover-on-windows-server-2025-x64) ·
[Both installed launch orders](rw02-cross-session.md#installed-304-worker-in-another-session).

Two native Windows ARM64 runs also excluded both Rust writers across
an interactive logon and a batch logon of one standard account, then
reacquired the same file. In the repeat, Windows still reported the
temporary profile loaded after 720 seconds. The five writer processes,
temporary account, task and case data were gone. An interactive ARM64
console/RDP pair remains outstanding.
[ARM64 observations](../../tools/rust-qa/instance/cross-session/hosted-arm64/README.md).

An exclusive handle on the existing configuration file caused the installed
WPF Save and Apply to report a sharing violation. After release the same
window saved the draft and started its worker. In a separate NTFS trial,
ordinary replacement of two open Rust-owned config files failed with
`ERROR_ACCESS_DENIED`. An independent reader recovered both original
identities and contents. Lossless saves during ownership and end-to-end
old/new writer exclusion remain unresolved for the candidate.
[WPF Save and Apply](rw02-cross-session.md#save-and-apply-on-the-installed-wpf-window-while-the-config-is-held) ·
[NTFS replacement](rw02-cross-session.md#ordinary-replacement-of-two-rust-owned-config-files-on-ntfs).

The filesystem feasibility result includes both real outcomes on both Ubuntu
architectures. The stock Documents portal refuses the upload read lease,
and the private backport enforces it across the grant and its backing file.
The RW-02 gate requires disclosing the filesystem limitation. The Linux
candidate still needs an available host implementation that preserves this
authorization and file lock. The outstanding Windows GUI gates independently
keep the stack selection open. [Stage exit criteria](../rust-rewrite-plan.md#staged-implementation-proposal)
· [Distribution availability](rw02-portal-upstream.md#additional-distribution-sources-checked-on-2026-11-22).

- **Desktop.** Rust 1.100.0, egui/eframe 0.37.0, winit 0.30.13 and wgpu 30.0.0 are pinned. The four verified normal/build profiles contain 235 packages per Linux target and 135 per Windows target, with AccessKit, clipboard, Vulkan on Linux and DX12 on Windows. The desktop spikes use zbus 5.19.0 on Linux and windows 0.62.2 for Windows Shell/COM. The maintained egui/epaint change uses unicode-bidi 0.3.18. Five unmodified OFL-1.1 Noto assets supply Sans, Mono, Symbols 2, Arabic and CJK JP. Default fonts, optional emoji and inspection are excluded. Retain the source/notice and Wayland relink obligations in the combined candidate. [Manifest](../../tools/rust-qa/gui/Cargo.toml) · [Exact sources, features and fonts](rw02-gui-dependencies.md)
- **Filesystem and state.** Four hosts passed handle-bound primitives, 5,844 scalar comparisons per casing mode at `93ecc35`, two live-WAL backups and 40 C# storage readbacks each. At `0bb39bf` each passed 246 YAML byte comparisons, 392 semantic comparisons and 224 C# readbacks using serde-saphyr 2.2.0. On each host the C# worker restarted from Rust’s returned backup after four synthetic activities. Storage uses rusqlite 0.43.0 with SQLite 3.54.1. Windows also passed encrypted loopback SMB. On tested distro Documents portals the required cooperating upload lock returned `ENOSYS`. The private backport enforced it on both architectures. Native x64 also passed an actual package upgrade and rollback with the installed Flatpak. Distribution and package maintenance remain open. The candidate guard passed on both Windows architectures across two sessions of one elevated account. The Rust guard passed across standard-user console and RDP sessions on x64. On ARM64 it passed the lock sequence across an interactive and a batch session of a standard user. Two interactive ARM64 sessions and installed legacy/candidate writer exclusion remain open under RI-AC05/08. [Filesystem](rw02-filesystem.md) · [YAML](rw02-yaml.md#four-native-anchor-and-compact-mapping-exchanges-at-0bb39bf) · [Worker restarts](rw01-storage-contract.md#native-worker-recovery-at-0bb39bf) · [Storage](rw02-storage-inputs.md) · [Portal control](rw02-portal-upstream.md) · [Writer ownership](rw02-cross-session.md)
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

The original estimates assumed access to disposable input-capable Windows desktops, the system IME, a real reader and representative graphics sessions. The native evidence above records which parts have since passed. VM provisioning and upstream portal release time are additional. Parallel work can shorten elapsed time.

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
