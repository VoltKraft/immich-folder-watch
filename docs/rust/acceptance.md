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
| RW-02 | In progress | [Four native filesystem, lifecycle-policy and scalar runs](rw02-filesystem.md#four-native-hosts), [legacy codecs](rw02-legacy.md), [storage and WAL](rw02-storage-inputs.md), [resource reference](rw02-performance.md), [GUI inputs](rw02-gui-dependencies.md), [native desktop](rw02-native-gui.md) and [realtime transport](rw02-realtime-transport.md). Four hosts passed the SQLite and transport probes. Desktop, resource, filesystem and dependency qualification continues. |
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
| RI-AC03 | Open | C#↔Rust corpus, unknown-format refusal, WAL/crash/full-disk and post-activity rollback results |
| RI-AC04 | Open | Independent native safe-fs and integration reviews, adversarial failures and sentinels |
| RI-AC05 | Open | Native lifecycle, old/new/cross-session ownership and durable task/DB shutdown tests |
| RI-AC06 | Open | Native desktop and assistive technology evidence, measured budgets and tested graphics behavior |
| RI-AC07 | Open | Independent consumer on four targets and dependency/profile isolation verification |
| RI-AC08 | Open | Exact-revision Actions packages, offline and actual installer/migration evidence |
| RI-AC09 | Open | Audited resolved graph/assets, notices, SBOM and reconstructible source inputs |
| RI-AC10 | Open | Independent final review with no unresolved acceptance blocker and truthful complete handoff |

## Native evidence matrix

| Environment | Baseline oracle | Rust runtime/security | GUI/accessibility | Install/upgrade/rollback |
| --- | --- | --- | --- | --- |
| Windows x64 | Hosted oracle and Core passed (557 passed, nine Linux-only skips) | 27 Rust tests, distinct NTFS 8.3 denial, five policy traces and 5,844 scalar comparisons | Four DX12 lifecycle cases passed on Microsoft Basic Render Driver. Accessibility and real desktop services remain open. | Pending |
| Windows ARM64 | Hosted oracle and Core passed (557 passed, nine Linux-only skips) | Same 27 native tests, distinct NTFS alias, five traces and 5,844 comparisons | Same four DX12 lifecycle cases passed on the native ARM64 executable. Accessibility and real desktop services remain open. | Pending |
| Linux x64 | Hosted oracle and Core passed (566 passed) | 30 hosted Rust tests, five policy traces and 5,844 scalar comparisons | Native X11/Wayland lifecycle and AT-SPI input have local observations. .NET X11 performance measured. Candidate resource comparisons in progress. | Pending |
| Linux ARM64 | Hosted oracle and Core passed (566 passed) | Same 30 native tests, five traces and 5,844 comparisons | Hosted GUI namespace setup failed at `167a03d`; X11/Wayland rerun pending. | Pending |

All four also passed two live WAL backups, 40 production C# readback assertions
and 15 native loopback transport cases per host. [Source-bound four-host archives](rw02-native-gui.md#four-native-assessment-archives).

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
