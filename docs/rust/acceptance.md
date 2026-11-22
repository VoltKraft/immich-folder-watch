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
| RW-02 | In progress | [Four native filesystem, lifecycle-policy and scalar runs](rw02-filesystem.md#four-native-hosts), [legacy codecs](rw02-legacy.md), [storage and WAL](rw02-storage-inputs.md), [fault recovery](rw02-storage-faults.md), [combined graph and offline relink](rw02-combined-profile.md), [native desktop](rw02-native-gui.md#native-follow-up-at-7517e3b) and [realtime transport](rw02-realtime-transport.md). The [stack decision](rw02-stack-decision.md) records the remaining native requirements. |
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
| RI-AC03 | Open | [Stored path keys on authentic C# backups from two ICU profiles](rw02-legacy.md#stored-sqlite-identities-across-two-casing-profiles), WAL/crash and native full-volume results. Production write policy, complete migration and rollback after sync activity are pending. |
| RI-AC04 | Open | Independent native safe-fs and integration reviews, adversarial failures and sentinels |
| RI-AC05 | Open | Native lifecycle, old/new/cross-session ownership and durable task/DB shutdown tests |
| RI-AC06 | Open | Native desktop and assistive technology evidence, measured budgets and tested graphics behavior |
| RI-AC07 | Open | Independent consumer on four targets and dependency/profile isolation verification |
| RI-AC08 | Open | Exact-revision Actions packages, offline and actual installer/migration evidence |
| RI-AC09 | Open | [Four development-build SPDX inventories](rw02-combined-sbom.md) and [corrected notice archives](rw02-combined-notices.md) reproduced from native Cargo logs and original sources. Independent review at `9f68c58` closed the Wayland, Plasma and ring findings. The exact installed packages, object-level linkage, corresponding source and relink material remain open. |
| RI-AC10 | Open | Independent final review with no unresolved acceptance blocker and truthful complete handoff |

All four native targets confirmed old/new local activation in both directions and exclusion
between two cooperative Rust writers. The shipping coordinator could still
start with the new guard held. Both Windows targets observed both lock refusal
directions and reacquisition in sessions 2 and 0 of the same elevated account.
At `3b4854d` the fixture temporarily started and restored Secondary Logon on
both hosts. The standard-user probe stopped during trust-level enumeration,
before any ordinary-user process acquired the guard. Installed handover and
standard-user cross-session exclusion remain open.
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
WPF-derived limits on ARM64 three times. Windows x64 met eight, nine and
seven. At `7517e3b` the x64 scan reopen took 122.81 ms at p95 against
a 19.555 ms limit.

## Native evidence matrix

| Environment | Baseline oracle | Rust runtime/security | GUI/accessibility | Install/upgrade/rollback |
| --- | --- | --- | --- | --- |
| Windows x64 | Hosted oracle and Core passed (557 passed, nine Linux-only skips) | 33 workspace tests, 16 filesystem checks locally and over encrypted SMB, 14 watch scenarios, five policy traces and 5,844 scalar comparisons. NTFS alias gate, eight database recoveries and 208 C# assertions passed. | Four DX12 lifecycle cases, Startup readback, original Shell registration and balloon callback. At `7517e3b` all three ordinary editor and all four standalone font cases passed, including NVDA, masking and clipboard. The IME twice committed あ with full cleanup. Retained Mailbox met seven of eleven limits in the latest run. | Pending |
| Windows ARM64 | Hosted oracle and Core passed (557 passed, nine Linux-only skips) | 33 workspace tests, 16 filesystem checks locally and over encrypted SMB, 14 watch scenarios, five traces and 5,844 scalar comparisons. NTFS and SMB alias gates, eight database recoveries and 208 C# assertions passed. | Four DX12 lifecycle cases and Startup readback. All three ordinary edits, four standalone font cases, NVDA speech, masks and clipboard passed. The Japanese IME twice committed あ with full cleanup. Retained Mailbox met all eleven limits three times. | Pending |
| Linux x64 | Hosted oracle and Core passed (566 passed) | 36 workspace tests, 19 filesystem checks, 15 watch scenarios, five policy traces and 5,844 scalar comparisons. Real grants, distro lock refusal and private upstream repair. Eight native storage fault cases. | X11/Wayland lifecycle, native Orca speech and masks, IME, clipboard, monitor changes and installed Flatpak grants. X11 passed all eleven resource limits. Plasma panel activation and live appearance changes passed separately on x64. | Pending |
| Linux ARM64 | Hosted oracle and Core passed (566 passed) | 36 workspace tests, 19 filesystem checks, 15 watch scenarios, five traces and 5,844 comparisons. Six journal records, eight storage fault recoveries and the combined offline relink. | X11/Wayland lifecycle, native Orca speech and masks, Mozc, integrated text/glyphs, monitor changes and installed Flatpak grants. X11 passed all eleven resource limits. | Pending |

The [four archives at `7517e3b`](rw02-native-gui.md#native-follow-up-at-7517e3b)
and [earlier four archives](rw02-native-gui.md#native-follow-up-at-3b4854d)
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
passed the [IME with profile cleanup](rw02-windows-ime.md). Windows tray
activation, mixed-DPI/RDP, x64 response limits, installed migration and
ordinary-user writer exclusion still need native evidence.

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
C# and Rust readers. A supported Ubuntu package and native Ubuntu-kernel
results are still outstanding. [Noble controls](rw02-portal-noble.md).

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
