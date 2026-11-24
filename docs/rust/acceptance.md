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
| RW-02 | In progress | [Four native filesystem, lifecycle-policy and scalar runs](rw02-filesystem.md#four-native-hosts), [legacy codecs](rw02-legacy.md), [storage and WAL](rw02-storage-inputs.md), [fault recovery](rw02-storage-faults.md), [combined graph and offline relink](rw02-combined-profile.md), [native Windows](rw02-windows-window.md#native-results-at-6084b23), [native Ubuntu](rw02-native-gui.md#ubuntu-native-results-at-e796d30) and [realtime transport](rw02-realtime-transport.md). The [Documents grant trials](rw02-portal-noble.md#native-ubuntu-grant-replay-at-e796d30) completed all 110 operations per architecture. The [installed Ubuntu x64 comparison](rw02-portal-noble.md#installed-patch-and-rollback-on-the-same-native-guest) passed upgrade, contention and rollback. The [stack decision](rw02-stack-decision.md) records the remaining native requirements. |
| RW-03 | Not started | RW-02 accepted; two-way codecs, WAL backup/recovery, writer exclusion, independent safe-fs review and adversarial native tests |
| RW-04 | Not started | RW-03 accepted; all upload modes/order/filter/retry/history and differential protocol/crash evidence |
| RW-05 | Not started | RW-04 accepted; complete bidirectional reconciliation, repairs, tombstones, realtime and deletion gates |
| RW-06 | Not started | RW-03 interfaces and RW-05 acceptance; full GUI/DE/EN/accessibility/performance plus isolated second desktop consumer |
| RW-07 | Not started | RW-05/06 accepted; four packages, offline reconstruction, installed migration/rollback, notices/SBOM and independent final review |

RW-08 is outside this goal. Success at an earlier row does not complete the goal.

## Overall acceptance

| Criteria | Current result | Evidence needed for completion |
| --- | --- | --- |
| RI-AC01 / PAR-01…10 | Open | Complete package and feature matrix with actual Rust results |
| RI-AC02 | Open | Four native candidate executables and dependency/runtime inventory |
| RI-AC03 | Open | [Exact-row updates on copies of three C# writer profiles](rw02-legacy.md#updating-a-known-row-on-finalized-copies), WAL/crash and native full-volume results. [Detached YAML file readback](rw02-yaml.md#reading-the-original-yaml-file-bytes) covers BOM selection and malformed data. On all four targets the shipping worker resumed from a Rust-created backup after download, upload, deletion and interrupted timestamp repair. [Original records](rw01-storage-contract.md#four-worker-restarts-on-each-native-target). Production write policy, migration and rollback after the Rust engine performs these operations remain open. |
| RI-AC04 | Open | Independent native safe-fs and integration reviews, adversarial failures and sentinels |
| RI-AC05 | Open | Native lifecycle, old/new/cross-session ownership and durable task/DB shutdown tests |
| RI-AC06 | Open | Native desktop and assistive technology evidence, measured budgets and tested graphics behavior |
| RI-AC07 | Open | Independent consumer on four targets and dependency/profile isolation verification |
| RI-AC08 | Open | The [installed 3.0.4 reference](rw01-installed-packages.md#installed-reference-on-all-four-hosts) passed native install, repair and uninstall on Windows and Ubuntu x64/ARM64. Four Rust packages, offline reconstruction, native upgrades and rollback after sync activity remain open. |
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
| Windows x64 | Core and worker reference passed (562 passed, nine Linux-only skips) | 34 workspace tests, 16 local filesystem checks, 14 watch scenarios, five traces and 5,844 scalar comparisons per casing mode. Encrypted SMB 3.1.1 passed at `6af7100`. NTFS alias gate, eight recoveries and 208 C# assertions passed. | DX12 lifecycle and recovery, Startup readback, ordinary editor, NVDA, clipboard, masking, font and Japanese IME checks passed. At `1b95ba0` both retained frame depths met 11/11 limits, reopened the same HWND and drew the edited text. Earlier one-frame runs at `549066f` and `ba02f8b` met 9/11 and 8/11. Explorer registered the icons and returned a notification show callback. Shell activation and independent notification presentation remain open. | Original 3.0.4 MSI passed native install, repair and removal with 439 files verified. Candidate pending. |
| Windows ARM64 | Core and worker reference passed (562 passed, nine Linux-only skips) | 34 workspace tests, 16 local filesystem checks, 14 watch scenarios, five traces and 5,844 scalar comparisons per casing mode. Encrypted SMB 3.1.1 passed at `6af7100`. NTFS alias gate, eight recoveries and 208 C# assertions passed. | DX12 lifecycle and recovery, Startup readback, ordinary editor, NVDA, clipboard, masking, font and Japanese IME checks passed. At `1b95ba0` both retained frame depths met 11/11 limits and preserved the draft and native window. At `549066f` and `ba02f8b` both ordinary launchers reopened the GUI. The retained HWND remained in the background, and Explorer refused icon registration. All launcher profiles were removed. A separate private tray profile recovered error 145 at `ba02f8b`. | Original 3.0.4 MSI passed native install, repair and removal with 438 files verified. Candidate pending. |
| Linux x64 | Core and worker reference passed (571 passed) | 37 workspace tests, 19 filesystem checks, 15 watch scenarios, five policy traces and 5,844 scalar comparisons per casing mode. Real grants, distro lock refusal and private upstream repair. Eight native storage fault cases. | X11/Wayland lifecycle, native Orca speech and masks, IME, clipboard, monitor changes and installed Flatpak grants. X11 passed all eleven resource limits. Plasma panel activation and live appearance changes passed separately on x64. | Original 3.0.4 Flatpak installed, repaired and removed on Fedora and Ubuntu. Candidate pending. |
| Linux ARM64 | Core and worker reference passed (571 passed) | 37 workspace tests, 19 filesystem checks, 15 watch scenarios, five traces and 5,844 scalar comparisons per casing mode. Six journal records, eight storage fault recoveries and the combined offline relink. | X11/Wayland lifecycle, native Orca speech and masks, Mozc, integrated text/glyphs, monitor changes and installed Flatpak grants. At `1b95ba0` X11 passed all eleven resource limits and two clicks on the Plasma panel reopened the same GUI window. | Original 3.0.4 Flatpak installed, repaired and removed on Ubuntu. Candidate pending. |

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
