# Rust implementation acceptance record

Goal: [M-RUST-IMPLEMENTATION-20261114](../project.md#m-rust-implementation-20261114).
The brief owns the fixed RI-AC01 through RI-AC10 criteria; the
[plan](../rust-rewrite-plan.md) owns PAR-01 through PAR-10 and stage prerequisites.
This record owns the evidence matrix. A planned test, compiled artifact or existing
C# test name does not establish a Rust/native pass. Only synthetic isolated data
is permitted. The C# oracle is development tooling, never a candidate runtime.

## Baseline and provenance

- Starting rewrite revision: `009246552cb4c0091196bab9a58cd64d44e5b629`, clean tree.
- Shipping/reference revision: `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`, product 3.0.4.
- Local and live GitHub `main` both inspected at that reference on 2026-11-14.
- SDK contract: .NET 10.0.401, unchanged `global.json`; exact executable availability
  and test executions must be recorded separately.
- Keep synthetic fixture inputs and generator sources in Git; put binary databases,
  test results, screenshots, packages and resource measurements in ignored
  `artifacts/rust/` or Actions artifacts with source revision and hashes.
- Refresh this corpus for any later shipping fix before candidate cutover.

## Work-package gates

The [RW-01 feature/lifecycle mapping](rw01-parity.md),
[storage contract](rw01-storage-contract.md),
[behavior contract](rw01-behavior-contract.md) and
[security mapping](rw01-security-contract.md) own individual reference cases.

| Package | State | Required evidence / next dependency |
| --- | --- | --- |
| RW-01 | Accepted 2026-11-20 | [Four native reference runs and reviewed corpora](rw01-native-reference.md), plus the feature, security and lifecycle cases above |
| RW-02 | In progress | [Four native filesystem, lifecycle-policy and scalar runs](rw02-filesystem.md#four-native-hosts), [legacy codecs](rw02-legacy.md), [storage and WAL](rw02-storage-inputs.md), [fault recovery](rw02-storage-faults.md), [combined graph and offline relink](rw02-combined-profile.md), [native Windows](rw02-windows-window.md#windows-results-at-ead9fb3), [native Ubuntu](rw02-native-gui.md#ubuntu-native-results-at-ead9fb3) and [realtime transport](rw02-realtime-transport.md). The [Documents grant trials](rw02-portal-noble.md#native-ubuntu-grant-replay-at-e796d30) completed all 110 operations per architecture. The [installed Ubuntu x64 comparison](rw02-portal-noble.md#installed-patch-and-rollback-on-the-same-native-guest) passed upgrade, contention and rollback. The [stack decision](rw02-stack-decision.md) records the remaining native requirements. |
| RW-03 | Not started | RW-02 accepted; two-way codecs, WAL backup/recovery, writer exclusion, independent safe-fs review and adversarial native tests |
| RW-04 | Not started | RW-03 accepted; all upload modes/order/filter/retry/history and differential protocol/crash evidence |
| RW-05 | Not started | RW-04 accepted; complete bidirectional reconciliation, repairs, tombstones, realtime and deletion gates |
| RW-06 | Not started | RW-03 interfaces and RW-05 acceptance; full GUI/DE/EN/accessibility/performance plus isolated second desktop consumer |
| RW-07 | Not started | RW-05/06 accepted; four packages, offline reconstruction, installed migration/rollback, notices/SBOM and independent final review |

RW-08 is outside this goal. Success at an earlier row does not complete the goal.

## Overall acceptance

Windows Server 2022 x64 at `47fe26d` showed the registered background-start
icon and its acknowledged color change at the same point. At `3c4d62c` the
same hosted image delivered the Shell callback, showed and focused the
background-start GUI, and preserved the worker. At `29ce1c0` a fresh x64
desktop passed reopening the original window after closing to the tray,
with focus, the same worker and clean Quit. Each second GUI lacked a
usable icon rectangle on its desktop. ARM64 activation remains open.
[Hidden start](rw02-windows-services.md#explorer-activation-after-a-hidden-start-at-3c4d62c) ·
[Reopen after close](rw02-windows-services.md#explorer-reopened-the-original-closed-window-at-29ce1c0).

At `20dfb10` the x64 Explorer left quiet time after 48 minutes. The
classic sender received a show callback, and WinRT history contained
the normal and suppressed entries with their exact text. None of the
96 classic or 93 WinRT screen samples showed the expected title and body.
Visible Windows notification presentation remains open.
[Original Windows notification archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46034955133/artifacts/15221500889).

On Fedora x64 the Rust realtime adapter kept one application session after
the server ended its namespace or closed the WebSocket. Authenticated
inventory continued. At `d97eb33` the root and named subscriptions also
recovered after abrupt loss against the server versions pinned by Immich
3.4.2. Refused initial upgrades admitted zero events. The Fedora x64
suite passed 35 wire cases and six unit tests. Hosted repeats are pending.
[Paired shipping-client and Rust trials](rw02-realtime-transport.md#server-closes-an-established-websocket) ·
[Initial admission and original server comparison](rw02-realtime-transport.md#pausing-polling-before-the-initial-websocket-upgrade).

On Fedora x64 at `12400d8` all 39 wire scenarios and six unit tests
passed. Rust and the signed shipping assemblies used either an isolated
Linux CA bundle or a hashed directory for authenticated inventory and a
WebSocket session. Both rejected a foreign issuer and an incorrect host
identity, including during the WebSocket upgrade after a valid polling join.
[Private CA and peer results](rw02-realtime-transport.md#linux-platform-trust-with-private-certificates).

On Fedora x64 the HTTPS proxy comparison qualified authenticated REST,
polling and the WebSocket upgrade. Rust and signed .NET 3.0.4 both honored
the configured proxy and the direct-host exception. The fixed relay saw
zero API headers on CONNECT. The Rust suite passed 44 wire scenarios and
nine unit tests. The plaintext WebSocket and Windows proxy paths remain open.
[Proxy requests and TLS controls](rw02-realtime-transport.md#linux-proxy-selection-for-rest-and-realtime).

At `6cd7757` all five C# multipart retry cases passed on Windows and Ubuntu,
x64 and ARM64. On those four targets and on Fedora x64 the combined Rust
executable independently reproduced every identifier and retry body from
the original open file after each synthetic name was replaced. The Rust
comparison reads the body locally. Installed candidate uploads and migration
remain open.
[C# and Rust comparison](rw02-legacy.md#legacy-upload-identities-from-the-held-file) ·
[Original native upload results](rw02-combined-profile.md#offline-reconstruction-with-the-legacy-upload-comparison).

At `9313f39` the x64 display observer ran the same PE that previously passed
the CPU timing and device-recovery tests. A 640 × 400 GDI frame accompanied
a visible edit on the 96-DPI console. RDP and mixed-DPI checks remain open.
[Display evidence](rw02-windows-display.md#display-checks-with-the-measured-x64-cpu-executable).

On Windows and Ubuntu, x64 and ARM64, the YAML comparison at `9313f39`
passed all 87 inputs and 228 C# readbacks per platform. Rust rejects invalid
earlier values in repeated properties. On Fedora x64 the previous 82 cases
also preserved all 112 output files byte for byte.
[Repeated properties and signed 3.0.4 comparison](rw02-yaml.md#repeated-properties-in-the-shipping-configuration).

At `1d9f94d` Rust omitted the API key and private endpoint from debug
output while preserving all 114 emitted YAML files byte for byte on
Fedora x64. All 228 C# readbacks passed. Thirty watch- and log-path
comparisons matched the signed release's editable and resolved values.
[Diagnostic and path checks](rw02-yaml.md#configuration-diagnostics-and-native-path-comparisons).

At `dddb21a` the private Windows x64 CPU renderer met all eleven WPF
limits. All 421 file-qualified reopens drew a complete editor frame
before the next close. The ordinary retained renderer met eight limits
on that host. A second native run at `972adc6` also met all eleven
limits with 171 full frames across 172 eligible reopen intervals.
Automatic WARP selection at `3b488ca` met all eleven limits on a third
host and drew a complete frame on each of 246 eligible reopens. The
separate sampler-handoff example stopped before the first visible sample
on that revision. At `10ab0b8` automatic selection again met all eleven
limits. The example switched from CPU painting to wgpu on the original
window. All three screen captures preserved the expected texture colors.
The separate device-loss trial stopped before requesting destruction.
At `483f053` the same measured executable passed a real WARP device
loss. Its new window showed the existing edit, accepted the next edit
and retained the original worker through another inventory and normal Quit.
[First native CPU trial](rw02-windows-window.md#native-windows-x64-cpu-renderer-at-dddb21a) ·
[Second native CPU trial](rw02-windows-window.md#native-windows-x64-cpu-repeat-at-972adc6) ·
[Automatic selection](rw02-windows-window.md#automatic-warp-selection-on-windows-x64-at-3b488ca) ·
[Visible texture handoff](rw02-windows-window.md#visible-texture-handoff-on-windows-x64-at-10ab0b8) ·
[WARP recovery](rw02-windows-window.md#warp-device-recovery-on-windows-x64-at-483f053).

The native foreground F24 checks at `de3eec4` restored focus on both Windows
architectures and preserved the original workers. The x64 observation
resolved equal resume and SHOW timestamps using the original HWND's
hidden state immediately after resume. Explorer activation remains open.
[Native keyboard observations](rw02-instance.md#ordering-a-fast-foreground-keyboard-launch).

At `c4d05b6` the installed 3.0.4 Windows worker consumed the Rust-returned
database on both architectures. On the x64 Default desktop and the ARM64
private input desktop, the second WPF process preserved ROWID 1 and
uploaded only the new PNG as ROWID 2. Both processes quit through the
shipping menu on each desktop. The ARM64 Default trial verified the
first upload and live backup, then stopped with another process covering
all 16 candidate points for Quit. All three MSIs were removed.
[Native runs and independent SQLite readbacks](rw01-storage-contract.md#installed-windows-worker-restart-at-c4d05b6).

At `d7c084c` the installed WPF secondary reopened the original Rust window
on both Windows architectures. Both Rust inventory workers completed the
two file queries. The opposite order passed on x64. On ARM64 the Rust
secondary reactivated WPF and exited normally, but the observer could
not select Quit on that Default desktop. Both Rust-primary runs passed
again at `69b3ddd`. All four x64 ETW snapshots and the completed trace
reported zero loss. Standard-user cross-session writer exclusion remains open.
[Both launch orders](rw02-instance.md#installed-windows-activation-at-d7c084c) ·
[Native trace evidence](../../tools/rust-qa/windows-msi-interop/file-trace.md).

At `0bb39bf` all sixteen native C# worker restarts used the expected
Rust-returned SQLite backup. Detached replay matched the four original
tables and the external state for each activity on each target.
[Native recovery and archived inputs](rw01-storage-contract.md#native-worker-recovery-at-0bb39bf).

Both native Ubuntu architectures reopened the same signed shipping window
after an ordinary secondary Flatpak launch at `5b6cebf`. All four original
3.0.4 packages also passed installation, repair, removal and retained-profile
readback. The paired Ubuntu Rust desktop measurements at `ead9fb3` met all
eleven resource limits on each architecture.
[Shipping packages](rw01-installed-packages.md#two-signed-launches-on-both-ubuntu-architectures-at-5b6cebf) ·
[Linux measurements](rw02-native-gui.md#ubuntu-native-results-at-ead9fb3).

On Fedora x64 and on both native Ubuntu architectures the installed
Flatpak trial exercised both launch orders. On Ubuntu at `3d67a46`
five observations followed each Rust inventory worker. The signed
3.0.4 worker reopened Rust’s backup after a real upload to the isolated
peer, kept the original row and uploaded only the new image. Independent
replay checked both request bodies, 16 WAL frames and final ROWIDs 1
and 2 on each host. Installed migration of the complete Rust sync engine
remains an RW-07 requirement.
[Native Ubuntu handover](rw01-storage-contract.md#installed-ubuntu-worker-restart-at-3d67a46) ·
[Fedora handover and earlier Ubuntu failure](rw01-storage-contract.md#native-linux-handover-and-backup-observer).

At `2dd5f93` the installed Windows x64 worker reopened its live
Rust backup after a real upload. Only the second PNG was uploaded at
restart. Native ARM64 confirmed the first upload and live backup before
its Quit observer stopped. Both original Windows MSIs were removed.
[Installed Windows recovery and source archives](rw01-storage-contract.md#installed-windows-worker-restart-at-2dd5f93).
The second x64 run at `f8cf6b1` passed the complete installed worker
restart again. The ARM64 observer captured a foreign foreground window
over its selected point before the first Quit.
[Second Windows recovery run](rw01-storage-contract.md#installed-windows-worker-restart-at-f8cf6b1).

At `1d3af9a` a normal start of the installed WPF 3.0.4 executable on
Windows x64 and ARM64 reopened the retained Rust primary in the same
session. Each original Rust inventory worker read the new file twice.
Both installations were removed. On ARM64 the foreground request was
declined. At `ef28520` both start orders reopened the original window on
each architecture. The reverse WPF trials stopped at the subsequent Quit
selection. Standard-user cross-session writer exclusion remains open.
[Native Windows activation and independent readbacks](rw02-instance.md#installed-windows-secondary-at-1d3af9a).
[Both start orders and native Quit outcome](rw02-instance.md#both-installed-windows-launch-orders-at-ef28520).
The installed x64 WPF primary passed through orderly Quit at both
`2dd5f93` and `f8cf6b1`. ARM64 reopened the WPF window at both
commits. With Rust primary the ARM64 worker passed twice and the two
recent x64 kernel traces lost events.
[Repeated native measurements](rw02-instance.md#installed-windows-activation-at-f8cf6b1).

On Fedora x64 the Rust YAML adapter preserved the physical line and paragraph
separators written by .NET 3.0.4 in paths, album names and filters. Known
values retain their own anchors when later unknown properties reuse a
name. All 74 profiles and 204 C# readbacks passed. The Windows and Linux
managed release assemblies each reopened 34 Unicode outputs and 22 alias
outputs on that Linux host.
The correction at `0bb39bf` matched the shipping reader on the three
compact mappings it rejected. Windows and Ubuntu x64 and ARM64 each
passed all 82 profiles and 224 C# readbacks. Independent replay checked
all 448 generated YAML files.
[Physical separators](rw02-yaml.md#physical-unicode-breaks-in-shipping-saves) ·
[Property and alias controls](rw02-yaml.md#anchors-on-recognized-and-skipped-properties) ·
[Four native compact mapping runs](rw02-yaml.md#four-native-anchor-and-compact-mapping-exchanges-at-0bb39bf).

At `e2f161b` each of the four native hosts passed 59 YAML cases including
160 C# readback comparisons. All four preserved the leading U+FEFF in a
saved album and passed 20 realtime scenarios, including namespace
acknowledgement over either transport and peer-observed disconnects.
On both Ubuntu architectures the original and relinked Rust builds read
the expected sub-microsecond timestamp from the held file.
[Four-host YAML](rw02-yaml.md#native-format-mark-exchange-at-e2f161b) ·
[Four-host transport](rw02-realtime-transport.md#four-native-transport-results-at-e2f161b) ·
[Offline relinks](rw02-combined-profile.md).

At `ead9fb3` each Windows host completed all three WPF reference trials.
Both retained ARM64 Mailbox profiles met all eleven same-host limits.
An ordinary second launch reopened the original ARM64 window in the
background. Both retained x64 Mailbox profiles exceeded the scan-close
and scan-reopen limits. On x64 an ordinary second launch focused the
retained window. Both architectures passed the ordinary and reopened
filename trials. Visible tray activation and notification, reversible
contrast, standard-user cross-session ownership, mixed DPI and RDP
remain open.
[Windows timing and archive details](rw02-windows-window.md#windows-results-at-ead9fb3).

The `0bb39bf` repeat gave eleven of eleven limits for both Windows ARM64
Mailbox profiles and eight for each x64 profile. The x64 idle close also
exceeded its limit on this host. Both foreground keyboard trials passed.
The ordinary ARM64 second launch reopened the window without foreground
focus. Both Ubuntu desktop jobs at `3d67a46` passed the eleven resource
limits and the installed handover.
[Windows repeat](rw02-windows-window.md#windows-results-at-0bb39bf) ·
[Ubuntu repeat](rw02-native-gui.md#ubuntu-native-results-at-3d67a46).

At `de3eec4` the focused x64 workflow completed both native DWM trials.
Disabling transitions on the original HWND left scan close and reopen
above their WPF ceilings. The three ordinary retained trials met eight of
eleven limits. RW-02 remains open.
[WPF limits, file activity, editor pixels and archive](../../tools/rust-qa/windows-warm-window/dwm-transitions.md#native-windows-x64-result-at-de3eec4).

At `c52da2d` the x64 GUI processed 238 close requests during a pending
frame wait and hid the original window before the frame was available.
It met nine of eleven same-host WPF limits. Under inventory load, close
p95 was 22.03 ms against 19.77 ms and reopen was 45.88 ms against
21.70 ms. The Rust worker completed two scans of 100,000 files. The
archive also confirms the reopened editor's pixels and clean shutdown.
[Native measurement and original traces](rw02-windows-window.md#one-shot-frame-readiness-on-windows-x64-at-c52da2d).

Every native host at `4e3dbc4` added one case-compatible Rust row in
each of its two C# databases. Both subsequent C# upserts preserved its
ROWID and every existing row. Independent readback covered 32 SQLite
files. This closes the native insertion trial under RI-AC03.
[Four-target originals and runtime versions](rw02-legacy.md#native-sqlite-insert-and-two-c-upserts-at-4e3dbc4).

At `5efe1f1` Rust opened ordinary .NET saves with 100 and 300 watch
folders and wrote unchanged and edited copies on all four targets. The
C# loader read both. The 301-folder result was identical across targets
and the original UTF-8 and UTF-32LE files retained their hashes.
[Four native YAML exchanges](rw02-yaml.md#four-native-saved-folder-exchanges-at-5efe1f1).

On Fedora x64, Rust backed up a configured, signed 3.0.4 process's live
WAL after an upload. A new signed process opened the returned database
and successfully uploaded a second image. The peer observed the original
image once across both lifetimes. This adds installed evidence for a
shipping worker consuming Rust's backup under RI-AC03.
[Installed backup, restart and readback](rw01-storage-contract.md#installed-fedora-worker-resumes-from-a-live-rust-backup).

At `e2f161b` both Ubuntu desktops passed all eleven resource checks. The
GUI answered all 117 x64 and 184 ARM64 requests issued during observed
file reads. [Ubuntu desktop evidence](rw02-native-gui.md#ubuntu-native-results-at-e2f161b).

| Criteria | Current result | Evidence needed for completion |
| --- | --- | --- |
| RI-AC01 / PAR-01…10 | Open | Complete package and feature matrix with actual Rust results |
| RI-AC02 | Open | Four native candidate executables and dependency/runtime inventory |
| RI-AC03 | Open | [Exact-row updates on copies of three C# writer profiles](rw02-legacy.md#updating-a-known-row-on-finalized-copies), WAL/crash and native full-volume results. [New Rust insertions](rw02-legacy.md#c-readback-of-newly-inserted-rust-rows) showed a lookup mismatch across casing profiles on Linux x64. The [first C# writes after rollback](rw02-legacy.md#first-c-upsert-after-rollback) produced eight duplicate entries across four synthetic copies. A [three-profile insertion check](rw02-legacy.md#inserting-a-new-row-across-three-qualified-rollback-profiles) then preserved 24 new rows through 144 C# upserts without duplicates. [Detached YAML readback](rw02-yaml.md#reading-the-original-yaml-file-bytes) covers BOM selection and malformed data. On all four targets the [shipping worker resumed from a Rust backup](rw01-storage-contract.md#four-worker-restarts-on-each-native-target) after download, upload, deletion and interrupted timestamp repair. Production write policy, migration and rollback after Rust engine activity remain open. |
| RI-AC04 | Open | Independent native safe-fs and integration reviews, adversarial failures and sentinels |
| RI-AC05 | Open | Both start orders passed with active inventory and upload workers on [Fedora](rw02-instance.md#rust-startup-during-a-signed-worker-upload) and [native Ubuntu x64 and ARM64](rw01-storage-contract.md#installed-ubuntu-worker-restart-at-3d67a46). On [both Windows targets](rw02-instance.md#installed-windows-activation-at-d7c084c) the ordinary secondary reactivated the original primary in either order. Both Rust-primary and the x64 WPF-primary trials included orderly shutdown. The [ARM64 private WPF-primary trial](rw02-instance.md#installed-arm64-wpf-activation-and-quit-at-972adc6) completed through the shipping Quit and desktop restoration. On ARM64 Default the Quit was covered. Complete candidate handover, standard-user cross-session ownership and durable product shutdown remain open. |
| RI-AC06 | Open | The installed test Flatpak's notification appeared in GNOME Shell and disappeared from its open message list on [Fedora x64 and Ubuntu ARM64](rw02-portal-dialog.md#visible-gnome-notifications-on-linux-arm64). Windows Shell, contrast, mixed DPI and RDP remain open alongside the full candidate’s assistive-technology, resource and graphics checks. |
| RI-AC07 | Open | Independent consumer on four targets and dependency/profile isolation verification |
| RI-AC08 | Open | The [installed 3.0.4 reference](rw01-installed-packages.md#installed-reference-on-all-four-hosts) passed native install, repair and uninstall on Windows and Ubuntu x64/ARM64. After a real upload, installed shipping workers resumed from Rust's live backup on both [Ubuntu](rw01-storage-contract.md#installed-ubuntu-worker-restart-at-3d67a46) and [Windows](rw01-storage-contract.md#installed-windows-worker-restart-at-c4d05b6) architectures. Four Rust candidate packages, offline reconstruction, native upgrades and rollback after Rust sync activity remain open. |
| RI-AC09 | Open | [Four development-build SPDX inventories](rw02-combined-sbom.md) and [corrected notice archives](rw02-combined-notices.md) reproduced from native Cargo logs and original sources. Independent review at `9f68c58` closed the Wayland, Plasma and ring findings. The exact installed packages, object-level linkage, corresponding source and relink material remain open. |
| RI-AC10 | Open | Independent final review with no unresolved acceptance blocker and truthful complete handoff |

All four native targets confirmed old/new local activation in both directions and exclusion
between two cooperative Rust writers. The shipping coordinator could still
start with the new guard held. Both Windows targets observed both lock refusal
directions and reacquisition in sessions 2 and 0 of the same elevated account.
At `1b95ba0` the system listed Basic User in the original console on both
hosts. Its attempt to start the participant at that level returned exit
code 1 with zero output bytes. Neither host started an ordinary-user
writer. Installed handover and standard-user cross-session exclusion remain open.
[Native process evidence](rw02-instance.md) and [cross-session assessment](rw02-cross-session.md).

At `13e4af8` the private consoles in sessions 2 and 0 listed Basic User
on both Windows architectures. All four launches returned zero from the
utility, but none produced a participant identity or writer event. Each
elevated control recorded the expected eight lock events from five writers.
[Native Basic User results](rw02-cross-session.md#native-basic-user-console-results-at-13e4af8).

On Fedora x64, the installed Rust GUI also kept its original read-only
inventory worker while a signed 3.0.4 launch saw the live Rust socket and
exited. The same worker found a new file before and after that launch.
The two synthetic inputs were read-only inside the Rust Flatpak and absent
from the 3.0.4 sandbox. A subsequent Rust launch reopened the original
window. This covers same-session worker continuity. Installed migration
and recovery after application sync remain open.
[Installed interoperation with a running worker](rw02-instance.md#installed-shipping-launch-during-a-rust-inventory).

On Fedora x64 the configured signed 3.0.4 worker also sent a synthetic PNG
while a worker-enabled Rust launch exited at the occupied endpoint. The
test peer held its response across that launch. The signed process retained
the same TCP connection and persisted the expected asset ID exactly once.
After Quit the row reopened from its SQLite backup.
[Configured upload and process lifetime](rw02-instance.md#rust-startup-during-a-signed-worker-upload).

The `13e4af8` canonical Windows tray and launcher trials stopped before
worker startup on both architectures. Their harness held DELETE access on
the directory the worker needed to open. At `4e3dbc4` both canonical
launchers kept their original workers through reopen and drained on Quit.
The x64 window obtained foreground. The ARM64 window reopened in the
background. Neither tray trial demonstrated an actual Shell activation.
[Original logs and correction](rw02-windows-services.md#canonical-gui-startup-on-the-staged-windows-desktop-at-13e4af8) ·
[Corrected native runs](rw02-windows-services.md#corrected-canonical-windows-launcher-at-4e3dbc4).

At `3b4854d` the [watch adapter](rw02-watch-events.md) passed fifteen
filesystem scenarios on each Ubuntu architecture and thirteen on each
Windows architecture. The Windows nonrecursive watch reported a modification
of the direct child directory, then an addition and a modification of the
direct child file. Its inventory excluded the file below the child directory.
At `7517e3b` both Windows targets also observed a real zero-byte completion
after the notification buffer filled. The replacement registration recovered
all 514 files and took the Windows total to fourteen scenarios. Both Ubuntu
targets repeated fifteen. [Native overflow receipts](rw02-watch-events.md#windows-notification-loss-and-recovery-trial).

At `8091469` all four targets repeated these watch and filesystem checks.
Both Windows architectures also completed the separate direct Rust adapter
trial on FAT16 after their eight recovery cases. The 45-byte file remained
readable through the original handle after rename. Opening the new name and
reading it independently via the volume GUID confirmed the same content.
The independent review matched the four detached images to the expected
database bytes and verified the original backups after cleanup.
[Native FAT16 results](rw02-filesystem.md#ordinary-fat16-adapter-on-native-windows-2026-11-22)
· [Recovery archives](rw02-storage-faults.md#native-windows-fat16-follow-up-at-8091469-2026-11-22).

The Windows
[retained-window variant](rw02-windows-window.md) held the same DX12 device
across an ordinary close and passed the native idle and memory limits on
both architectures in earlier trials. Its Mailbox variant met all eleven
WPF-derived limits on ARM64 four times. Windows x64 met eight, nine, seven
and eight. At `8091469` the x64 scan reopen took 119.95 ms at p95
against 21.987 ms. The dispatch trace located two successful presentations
inside each of 439 independently confirmed hidden-window intervals on x64.
The [native follow-up](rw02-windows-window.md#native-retained-window-results-at-0a2b5ca) qualified the revised retained policy on both Windows targets. Its integration with the actual Shell icon and ordinary activation has separate checks.

At `0a2b5ca` all four hosted C# references matched the 29 baseline files
and 215 semantic assertions. Linux passed 37 Rust workspace tests per
architecture and Windows passed 34, including 19 and 16 filesystem checks
respectively. The ordinary scalar comparison passed 5,844 cases per host.
The managed comparison rejected the hosted runtime patch on all four
targets. Both Windows SMB steps consequently skipped. Each Windows target
still completed its independent eight recovery cases, 208 C# assertions
and FAT16 readback. The corrected two-process runtime selection passed on
Fedora x64. [Native feasibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818246)
· [C# reference](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818262)
· [Runtime qualification](rw02-legacy.md#managed-globalization-invariant-casing-in-net-10012).

At `93ecc35` the four native jobs passed all fourteen steps with the pinned
10.0.12 scalar oracle. Each architecture passed 5,844 requests in each of
the two casing modes. Both Windows hosts also passed their encrypted SMB
and eight recovery cases. The independent replay checked the published
digests of all ten native archives, the original source and both complete
mapping tables. The separate C# reference run used 10.0.15 and again
matched 29 fixture files and 215 assertions per target. Its TRX results
show 566 passed tests on each Ubuntu host and 557 passed with nine
platform-specific skips on each Windows host. [Native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264215)
· [C# reference jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264125).

## Native evidence matrix

At `e2f161b` all fourteen recorded foundation steps passed on every target.
The native workspace ran 34 tests per Windows host and 38 per Ubuntu host.
Separate replay of the downloaded worker-backup archives matched all sixteen
C# restarts to the databases returned by Rust after download, upload, deletion
and interrupted timestamp repair. Each archive included 161 first-party
sources. The four-host exchange index has SHA-256
`ef9ac7d6257c70e0e74bab2bedc4fcf480488c5979c9017ae3661a7cdef68fff`.
[Foundation and backup archives](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563616) ·
[Worker restart contract](rw01-storage-contract.md#four-worker-restarts-on-each-native-target).

At `13e4af8` all four native runners passed the filesystem watch and
rescan checks and restarted the shipping worker from Rust backups after
download, upload, deletion and interrupted timestamp repair. Both Windows
hosts also passed the loopback SMB and FAT recovery checks. All 20 checks
on the draft PR passed for this revision. The separate desktop assessment
covers GUI and platform behavior. [Native jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186668) · [Desktop assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45476186847).

At `21e794f` both Ubuntu desktop jobs passed. Both Windows jobs finished
with outstanding requirements. A foreground keyboard launch restored the
existing GUI and its keyboard focus on both Windows hosts. ARM64 met all
eleven WPF limits in both retained Mailbox profiles. The default x64 profile
met nine, exceeding idle close and scan reopen. The x64 reader announced
all seven expected cues. ARM64 timed out at the German filename editor.
Both contrast supervisors stopped before the first palette change. The
hosted desktops each supplied one 96-DPI console output. The user currently
has no Windows evaluation medium or approved VM for mixed-DPI and RDP trials.
[Windows keyboard](rw02-instance.md#retained-windows-on-the-original-desktop-at-21e794f)
· [Rendering timings](rw02-windows-window.md#native-results-at-21e794f)
· [Ubuntu desktops](rw02-native-gui.md#ubuntu-native-results-at-21e794f)
· [Windows display requirements](rw02-windows-display.md#required-observations-on-a-disposable-native-desktop).

At `e796d30` the Ubuntu desktops each met all eleven X11 limits and
completed all three portal service comparisons. The Windows desktop jobs
failed. On both hosts the new keyboard-launch trial stopped before its
secondary process started and WinRT stopped before showing a notification.
The separate four-target feasibility jobs passed.
[Ubuntu comparisons](rw02-native-gui.md#ubuntu-native-results-at-e796d30) ·
[Desktop jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45271221266).

On November 23, one offline Ubuntu x64 guest passed the installed
Documents package upgrade and downgrade with the same ordinary Flatpak
user. The original package refused the lock, the backport enforced it in
both directions, and restoring the original package restored its refusal.
The user selected feasibility only. Distribution and the four installed
Rust candidate packages remain open.
[Installed portal evidence](rw02-portal-noble.md#installed-patch-and-rollback-on-the-same-native-guest).

At `6084b23` both Ubuntu desktops and the retained Windows ARM64 Mailbox
GUI met all eleven resource limits. Both x64 Mailbox depths met eight.
The two Windows display observers recorded one 96-DPI console monitor
each. Mixed DPI and RDP remain open. Both WinRT history trials verified
their installed shortcut and cleanup. Each sender stopped before showing
a notification. [Windows timing](rw02-windows-window.md#native-results-at-6084b23)
· [Display and session](rw02-windows-display.md#both-retained-windows-display-inventories-at-6084b23)
· [Notification history](rw02-windows-services.md#native-winrt-senders-at-6084b23).

At `1904be7` both Windows targets passed all three mixed-direction edits
in the ordinary window and after reopening the retained window. All four
glyph images matched. The default retained x64 GUI passed nine of eleven
limits. Its scan close and reopen exceeded the same-host WPF limits. ARM64
passed eleven of eleven at both Mailbox frame depths. RI-AC06 remains open.
[Native timing](rw02-windows-window.md#native-results-at-1904be7) · [Original text and glyph evidence](rw02-windows-text.md#captured-ordinary-and-reopened-filenames-at-1904be7).

At `1904be7` all four native targets passed four shipping-worker restarts
from Rust-produced SQLite backups. Detached replay matched the 16 reports,
including the peer's retained upload and trash, the pending repair journal
and the completed repair after restart. The installed Rust sync engine's own
rollback still requires RW-07. [Original archives and counts](rw01-storage-contract.md#four-worker-restarts-on-each-native-target).

At `653f255`, all four targets passed the shipping reference suite and both
cross-language backup exchanges. In each upload case the separate peer
retained the eight original bytes and asset ID. Each restarted C# worker
reconciled the same album from Rust's backup and made zero further transfers.
All eight readbacks reproduced the reporting process's exact original bytes.
At `e558b42` the C# references also preserved an actual timestamp change
and a peer deletion across database restores on all four targets. The same
revision passed the separate four-target feasibility run. Its eight upload
and download reports reproduced byte-for-byte, including the returned
databases and transfer counts. The four archives retained 156 first-party
sources each. The installed Rust candidate's own sync and rollback
remain open. [Native feasibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220170042).
[Hosted reference](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595572) · [Upload and download](rw01-storage-contract.md#peer-content-after-a-synthetic-upload) · [Repair and deletion](rw01-storage-contract.md#external-state-after-deletion-and-timestamp-repair).

| Environment | Baseline oracle | Rust runtime/security | GUI/accessibility | Install/upgrade/rollback |
| --- | --- | --- | --- | --- |
| Windows x64 | Core and worker reference passed (562 passed, nine Linux-only skips) | 34 workspace tests, 16 local filesystem checks, 14 watch scenarios, five traces and 5,844 scalar comparisons per casing mode. Encrypted SMB 3.1.1 passed at `6af7100`. NTFS alias gate, eight recoveries and 208 C# assertions passed. | DX12 recovery, Startup, NVDA, Unicode editing, masking, clipboard and Japanese IME passed. At `4e3dbc4` both retained Mailbox profiles met all eleven WPF limits, both ordinary and keyboard launches restored focus, and the native WinRT history trial passed. At `989bb33` each Mailbox profile met nine limits, and none of the 256 sampled Explorer points showed the registered tray icon’s marker. On Server 2022, Explorer opened the hidden-start GUI at `3c4d62c` and reopened the window after close at `29ce1c0`. Each passed when tested first. Visible notifications, contrast, mixed DPI and RDP remain open. | Original 3.0.4 MSI passed native install, repair and removal with 439 files verified. Candidate pending. |
| Windows ARM64 | Core and worker reference passed (562 passed, nine Linux-only skips) | 34 workspace tests, 16 local filesystem checks, 14 watch scenarios, five traces and 5,844 scalar comparisons per casing mode. Encrypted SMB 3.1.1 passed at `6af7100`. NTFS alias gate, eight recoveries and 208 C# assertions passed. | DX12 recovery, Startup, NVDA, Unicode editing, masking, clipboard and Japanese IME passed. At `4e3dbc4` and `989bb33` both retained Mailbox profiles met all eleven WPF limits and WinRT history passed. A keyboard launch restored focus. The ordinary WPF and retained Rust windows reopened in the background. At `989bb33` Explorer declined icon registration. Visible notifications, contrast, mixed DPI and RDP remain open. | Original 3.0.4 MSI passed native install, repair and removal with 438 files verified. Candidate pending. |
| Linux x64 | Core and worker reference passed (571 passed) | 38 workspace tests at `e2f161b`, 19 filesystem checks, 15 watch scenarios, five policy traces and 5,844 scalar comparisons per casing mode. Real grants, distro lock refusal and private upstream repair. Eight native storage fault cases. | X11/Wayland lifecycle, native Orca speech and masks, IME, clipboard, monitor changes and installed Flatpak grants. X11 passed all eleven resource limits. Plasma panel activation and live appearance changes passed separately on x64. | Original 3.0.4 Flatpak installed, repaired and removed on Fedora and Ubuntu. Candidate pending. |
| Linux ARM64 | Core and worker reference passed (571 passed) | 38 workspace tests at `e2f161b`, 19 filesystem checks, 15 watch scenarios, five traces and 5,844 scalar comparisons per casing mode. Six journal records, eight storage fault recoveries and the combined offline relink. | X11/Wayland lifecycle, native Orca speech and masks, Mozc, integrated text/glyphs, monitor changes and installed Flatpak grants. At `1b95ba0` X11 passed all eleven resource limits and two clicks on the Plasma panel reopened the same GUI window. | Original 3.0.4 Flatpak installed, repaired and removed on Ubuntu. Candidate pending. |

At `6af7100` all four feasibility jobs passed and both Ubuntu desktops met
all eleven limits during independent readback. The original Windows x64
desktop accepted both ordinary launchers and gave the retained HWND keyboard
focus. On ARM64 both ordinary launchers recovered the visible window. The
foreground and keyboard checks failed on that desktop. Private restart and
cleanup passed on both hosts. The elevated cross-session writer check passed.
The standard-user trial requires two eligible sessions.
[Four feasibility jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662890) · [Native desktop observations](rw02-native-gui.md#native-follow-up-at-6af7100).

Independent read-only SQL replay at the same revision verified the four
native storage jobs, 32 database files and 296 rows. The 160 shipping
C# assertions, eight committed-WAL backups, eight untouched version-99
controls and 120 stored-key lookups passed. Each OS's two architectures
produced byte-identical files for all eight database comparisons. The
four-host readback SHA-256 at `6af7100` is `40c83d49c55b62d1c2068546c62a8ce5a3a6be1a1590d40175663b3f9e10e68e`.
At `8566f81`, independent replay of all 32 databases again verified the
296 rows, eight online WAL backups and 160 C# assertions. The four-host
readback SHA-256 is `1e5fa911c03d013b6ddb035da86ddfbcc8f48eb520668415c6d6404248b11683`.
[Originals at 8566f81](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45159516037).
[Native storage archives](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45144662858) · [Storage checks and schema](rw02-legacy.md#native-desktop-storage-at-93ecc35).

At `93ecc35`, both Ubuntu targets repeated all eleven X11 budgets and the
sixteen transport scenarios. All four native targets passed direct SQL
readback of both WAL backups, 30 stored-key lookups and ten controls per
host. All four native input ZIPs, notice ZIPs and SPDX documents reproduced
byte-for-byte from the archived build evidence. Both Ubuntu jobs repeated
the resource and desktop checks at `1e58541`. All four native feasibility
archives at that revision recorded 5,844 checks against each of the two
casing profiles. The two Windows hosts again observed an encrypted SMB 3.1.1
connection on the synthetic share.
[Ubuntu native results](rw02-native-gui.md#native-follow-up-at-1e58541)
· [Native filesystem and compatibility jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45124494628)
· [Notice and SPDX receipts](rw02-combined-notices.md#native-notices-at-93ecc35)
· [Four-host SQL matrix](rw02-legacy.md#native-desktop-storage-at-93ecc35).

The [two native launcher archives at `0a2b5ca`](rw02-instance.md#native-desktop-selection-and-ordinary-reopening-at-0a2b5ca)
identify the private window's actual desktop and the worker retained during
ordinary reopening. The [four archives at `8091469`](rw02-native-gui.md#native-follow-up-at-8091469)
and [previous four archives](rw02-native-gui.md#native-follow-up-at-7517e3b)
bind each hosted result to its revision. The [Plasma panel](rw02-plasma.md),
[system appearance](rw02-appearance.md), [native storage faults](rw02-storage-faults.md)
and [four combined offline builds](rw02-combined-profile.md) have separate
source and runtime evidence. Both Ubuntu hosts completed the private Noble
backport, eight WAL recovery cases and offline combined relinks. Both Windows
targets passed the combined build, Clippy and native smoke. Each hosted
console offered one 96-DPI output. Both private Shell hosts refused their
initial icon registration. Their FAT volumes reached zero free bytes and the
storage worker rejected the supervisor's line ending before recovery. Both
Windows targets then restored the database in both path comparison modes at
`7517e3b` and detached their full private volumes. Both Windows hosts also
passed the [IME with profile cleanup](rw02-windows-ime.md). At `1e58541` Windows x64 again exceeded three window-response limits. Windows tray
activation, mixed-DPI/RDP, installed migration and ordinary-user writer
exclusion still need native evidence. [Native launcher and Shell observations](rw02-instance.md#native-windows-launcher-at-1e58541).

The [four verified archives at `8a8adaa`](rw02-native-gui.md#native-follow-up-at-8a8adaa) record both Ubuntu jobs passing. Each Windows host met six of nine measured idle/startup budgets. Visible memory and idle close/reopen exceeded their limits on both. The new [paired workload](rw02-windows-performance.md) adds real Windows scan observations.

At `72fff40`, both Ubuntu hosts again met all eleven X11 limits, and both
Windows hosts passed the private-desktop keyboard and native Event Log checks.
Windows x64 also passed ordinary mixed-direction editing. Separate Ubuntu
and Fedora x64 observations verified actual Orca speech and synthetic
password masking under X11 and Wayland. [Hosted follow-up](rw02-native-gui.md#native-follow-up-at-72fff40)
and [Orca audio receipts](rw02-ubuntu-reader.md).

All four also passed two live WAL backups, 40 production C# readback assertions,
15 native loopback transport cases and six old/new activation and file-lock
observations per host. Windows ARM64 repeated all 15 transport cases after a
confirmed link against the reconstructed import library.
[Four-host archives](rw02-native-gui.md#four-native-assessment-archives),
[native activation](rw02-instance.md#native-results-on-all-four-targets)
and [ARM64 reconstruction](rw02-windows-imports.md).

Both Windows targets passed all 13 filesystem cases over a verified, encrypted
SMB 3.1.1 loopback share. On Fedora x64 the distribution's document portal
returned `ENOSYS` for the required upload lock. The private upstream backport
enforced it across the actual grant and backing views. [SMB results](rw02-filesystem.md#four-native-hosts)
and [portal and tray results](rw02-linux-services.md).

Ubuntu Noble's published portal and its pristine rebuild also refused the
cooperating lock on a native x64 Noble userspace and Fedora kernel. The
private source backport passed all 42 lock operations with both the ordinary
C# and Rust readers. Subsequent tests on native Ubuntu x64 and ARM64
confirmed the original refusal and the backport's lock enforcement. On
x64 the complete package also passed installation and rollback with the
installed Flatpak. Ubuntu package distribution remains open.
[Noble controls and installed results](rw02-portal-noble.md).

Three native Intel-to-software Wayland recoveries preserved editing and
worker progress. The measured visible and hidden idle intervals recorded
zero application buffer commits. [Fedora x64 results](rw02-wayland-recovery.md).

On Fedora x64 an installed test Flatpak selected a real Documents grant
through a parented GTK chooser under both X11 and Wayland. A fresh process
received `ENOENT` after revocation. Private GNOME Shell displayed and withdrew
the notification. The Background portal created and removed the app's autostart
file, then refused a new request after explicit denial.
[Installed Flatpak and GNOME evidence](rw02-portal-dialog.md).

Fedora x64 exercised native Orca speech output and three protected keystrokes
on X11 and Wayland. X11 also produced an actual Anthy composition and Japanese
commit in the Rust filename field. [IME and screen-reader observations](rw02-native-gui.md#native-composition-and-screen-reader-output).

Fedora x64 matched the shipping log file payloads and journal stream for
all six levels. A separate native journal also recovered each priority and
message. The Windows Event Log steps passed natively on x64 and ARM64 at `72fff40`. A private Ubuntu 24.04 journal also passed locally after receiving a read-only view of the test process’s cgroup.
[Platform log observation and scope](rw02-platform-logs.md).

GNOME Wayland on Fedora x64 committed the same Japanese character from Anthy
with Mesa Mailbox. The same window presented 640 × 400, 1280 × 800 and 800 × 500
buffers as its monitor changed. The integrated GUI now selects the observed
surface mode itself for this Mesa software backend. Both Fedora Anthy and
the signed Ubuntu Mozc engine committed `あ` on the Fedora compositor with
the ordinary application settings. [Native protocol, field and buffer observations](rw02-wayland-input.md). Both native Ubuntu hosts then passed the separate Mozc field and monitor-transition checks, plus installed Flatpak grant and revocation on X11 and Wayland. [Hosted results at `8a8adaa`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642).

The released egui 0.37 text editor deleted the wrong visible Arabic character
in two mixed-direction cases. A narrowly scoped upstream correction passed
the same pointer, keyboard and GPU readback tests on Linux x64, including
numbers inside a right-to-left run. The integrated Linux x64 GUI also passed
the tests in its ordinary filename field. Ubuntu x64 and ARM64 subsequently
passed the same checks at `8b071ab`. Windows DX12 rendered the first control
on both hosts. Complete editing evidence on both Windows targets remains
open. [Comparative font tests](rw02-font-coverage.md) and
[integrated source and field observations](rw02-gui-dependencies.md).

The isolated Fedora graphics variant passed 14 cases across X11 and Wayland.
It recovered from a process-local Vulkan device loss and a controlled Intel
to CPU transition while retaining the worker, edited value and focused field.
[Real adapters, driver events and frame evidence](rw02-graphics.md).

The [YAML probe](rw02-yaml.md) passed on all four native targets at
`11e4e6f`. Each produced 183 Rust assertions and 116 production C# readback
assertions across 38 paired cases and the same offline source tar.

Hosted runners can supply native process evidence but are not assumed to provide
interactive screen-reader, GPU, multi-session, UNC or portal/FUSE acceptance.
Record capabilities actually exercised and unsupported checks explicitly.

## RW-01 local execution record (2026-11-14)

Reference application source remains exactly `19dcbaf`; oracle/test additions were
reviewed over selection checkpoint `8d51734`. Platform: native Fedora 45 x86_64,
.NET SDK 10.0.401, runtime 10.0.12. No production application startup or profile access.

| Check | Actual result | Evidence / limit |
| --- | --- | --- |
| Existing Core suite | 503 passed, zero failed/skipped | `artifacts/rust/baseline-results/core-baseline.trx` |
| Existing Linux GUI/protocol suite | 60 passed, zero failed/skipped | `artifacts/rust/baseline-results/linux-reference.trx`; isolated headless views/D-Bus, not real desktop acceptance |
| New behavior corpus | 63 passed, zero failed/skipped | `artifacts/rust/behavior/results/rw01-behavior-linux-x64.trx` |
| New window corpus | Five passed, zero failed/skipped | `artifacts/rust/baseline-results/rw01-lifecycle.trx` |
| Storage/config export and independent verify | 29 files, 215 assertions, all source/payload hashes match | Checked-in Linux manifest; native Windows output pending |
| Architecture negative control | ARM64 requirement on x64 refused before generation | No emulated native-pass claim |
| Reduced Avalonia provenance | Passed | Exact rebuilt package/assembly hashes against Linux test restore |
| Workflow security | Seven passed, four PowerShell-only skipped | Existing and new publication-isolation regressions; native Windows run pending |
| Independent test/workflow review | No open blocking finding | Read-only source/hash audit; actual Rust security review remains open |

Existing obsolete D-Bus/Bitmap API warnings and an unavailable NuGet advisory
fetch during oracle restore are recorded; no dependency update is inferred.
