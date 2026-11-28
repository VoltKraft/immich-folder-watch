# RW-01 security and lifecycle contract

Independent static review of source `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`
and the unchanged workflow tree at `009246552cb4c0091196bab9a58cd64d44e5b629`.
This maps requirements to executable reference specifications; it does not claim
Rust acceptance. Actual executions belong in [acceptance](acceptance.md).
Independent Rust filesystem, migration and final integration reviews remain open.

Protect private configuration/keys, authorized media and outside sentinels, SQLite
identities/history/repair intents/tombstones, exclusive writer ownership and
publication identities. Exercise untrusted API/Socket.IO input, filesystem-name
substitution, watcher races, incomplete inventories, cancellation, crashes and
storage failure. Preserve the existing per-user threat model; equivalent access
to process memory/credentials or administrator compromise is outside its claim.
All inputs must be synthetic and independent of installed application profiles.

## Required adversarial cases

The source/test names below resolve within `src/`; they identify reference code,
not passing Rust results. Each row needs native execution on all applicable
targets; ordinary-directory replacement matters as much as links/junctions.

| ID | Required assertion | Reference source / regression suite | Required candidate evidence |
| --- | --- | --- | --- |
| SEC-01 | Root/parent/leaf replacement cannot redirect enumeration, reads or absence | `SecureWatchRoot`, `SecureWatchRootTests`, `WorkerPathSecurityTests` | Outside sentinel bytes/existence/times unchanged after swaps |
| SEC-02 | Upload metadata/digest/content use one retained file; metadata equality never grants cleanup | `SecureWatchFile`, `ImmichAssetClient`, `FolderWatchWorkerPersistenceTests` | Same-size/same-time replacement, retry/restart and mutation-during-upload; fresh successful handle required |
| SEC-03 | Staging/cancellation retain protected directories; publish never replaces | `SecureWatchFile`, native filesystem implementations, `ImmichTransferSecurityTests` | Destination/container replacement, cancellation and write failure preserve data |
| SEC-04 | Creation/rename bind both sides; unavailable atomic operations fail closed | `SecureWatchRoot`, `SecureNativeFileSystem.Linux/Windows`, `SecureWatchRootTests` | Source/destination races, unsupported no-replace, portal/FUSE and UNC |
| SEC-05 | Timestamp repair verifies content/hardlinks and atomically completes state/journal | `FolderWatchWorker.Timestamps`, timestamp persistence and SQLite tests | Crashes before intent/after file change/during completion; equal metadata cannot hide changed content |
| SEC-06 | Internal paths never become media/album events; leases outlive cache eviction | `SecureTransactionPool`, `SecureWatchRootTests`, `WorkerPathSecurityTests` | Bounded cache, live operations after eviction, retained quarantine without blind cleanup |
| SEC-07 | Incomplete local/remote inventories cannot authorize deletion | `FolderWatchWorker`, `ImmichAssetClient`, transfer-security and persistence suites | Missing/malformed/truncated pages, denied enumeration, links and root swaps report unknown/failure |
| SEC-08 | Exact creation-returned album ID/live provenance; startup revokes stale authority | `SqliteSyncStateStore.AlbumOwnership`, `ImmichAssetClient.OwnedAlbums`, album-security suites | Duplicate names, unexpected IDs, offline replacements and delayed rename events |
| SEC-09 | Tombstones precede effects and survive callbacks/restarts | Worker persistence deletion-concurrency tests, `SqliteSyncStateStoreTests` | 120-second expiry, failed persistence, repeated callbacks, no duplicate trash/resurrection |
| SEC-10 | Exact identity/codec compatibility; future state never bootstraps empty state | `SyncAccountScope`, `SqliteSyncStateStoreTests`, storage oracle | Windows/Linux Unicode keys, seven-digit SQL UTC, PascalCase/numeric-enum repair JSON, two-way read/write and future-format nonmutation |
| SEC-11 | Recovery precedes reconciliation; success follows durable completion | Worker startup/timestamp/persistence suites | Failure at DB/filesystem/network boundaries; write failure halts scheduling; monotonic history/no-op restart |
| SEC-12 | WAL-consistent backup and honest rollback after activity | Plan cutover protocol; storage oracle adds backup reference | Quiesced backup API, permissions/hashes, kill/write/full-disk recovery; old binary reads latest valid state after Rust activity |
| SEC-13 | HTTPS default/explicit HTTP; no credentials through redirects/cross-origin | `AppConfigValidator`, `AppHost`, `ConfigVerificationRunner`, transport-security suites | Two-origin REST/polling/WebSocket redirect/downgrade tests; other origin receives no key |
| SEC-14 | Bound streamed/decompressed transfers and fragmented messages | `ImmichTransferLimits`, `BoundedResponseReader`, `ImmichRealtimeTransport`, transfer-security suites | 16 MiB metadata, 64 KiB diagnostic, 128 MiB/125000 assets/500 pages search, 100 GiB download, 1 GiB reserve, 60 s idle/6 h total, 4 MiB realtime |
| SEC-15 | Complete Socket.IO/Engine.IO protocol with bounded reconnect/cancellation | `ImmichRealtimeClient`, `RealtimeTransportSecurityTests` | Handshake/auth, polling/upgrade, heartbeat/events and stop-during-reconnect traces; polling-only is insufficient |
| SEC-16 | Private atomic configuration and validated Save/Apply | `LinuxPrivateDirectory`, `ConfigApplyService`, private-directory/apply tests | Both platforms: linked paths, cancellation/full disk/restart failure; bounded YAML aliases/nesting and redacted diagnostics |
| SEC-17 | Exclusive old/new writer and bounded authenticated failure-distinct IPC | Windows/Linux single-instance coordinators, `UnixSingleInstanceSecurityTests` | Same SID/two sessions, legacy re-entry during handover, stale endpoints, other users, oversized/stalled clients |
| SEC-18 | Serialized apply/restart/quit with ownership until durable shutdown | `AppHostLifecycleTests`, worker persistence/path suites | Bounded busy state, stale-generation rejection, no overlapping writers, join-before-release, installer safe refusal |
| SEC-19 | Portal denial/revocation never expands access; display path is not authority | Folder/document/background portal adapters/tests, `MainWindowBindingTests` | Native grant/denial/revocation/restart/FUSE under unchanged Flatpak permissions |
| SEC-20 | Reachable hidden lifecycle, tray recovery, private bounded notifications/logs | Linux window/tray/notifier/session-log suites | Hidden/close/reopen/Quit, tray-host loss/recovery, cross-platform notification rate/privacy, actual accessibility/GPU evidence |
| SEC-21 | Candidate/installer safety and distribution isolation | MSI compiled/installed upgrade gates; workflow audit below | Four native packages, upgrade/repair/uninstall/rollback, no .NET resources, offline inputs/license/font/native inventory/SBOM |

## Legacy gaps that Rust must improve

- SEC-10: `SqliteSyncStateStore.OpenConnectionAsync` sets `journal_mode=WAL`
  before checking `user_version`. The oracle records whether bytes/journal mode
  change for an unsupported database. Rust must inspect read-only before any
  mutation. Existing future-version tests alone do not prove nonmutation.
- SEC-17: Windows `Local\\` mutexes are session-scoped; a Rust-only added guard
  cannot prevent an older process from entering. Controlled legacy handover and
  same-user cross-session exclusion need native evidence.
- SEC-17: Windows IPC reads to EOF without a byte/time limit; Linux bounds bytes
  to 64 but lacks a per-client read deadline. These are gaps, not behavior to copy.
- SEC-16: Windows Save/Apply uses ordinary `WriteAllTextAsync`; Linux has a
  private atomic writer. Rust must provide atomic failure-safe writes on both.
- YAML currently reads the complete file. Bounded parsing, comprehensive migration
  crash/storage-pressure coverage and notification privacy require new evidence.

These observations do not authorize using a broken legacy behavior as a passing
Rust expectation. No production remediation is claimed by this record.

## Publication isolation

| Workflow | Inspected gate | Consequence for this goal |
| --- | --- | --- |
| `ci.yaml` | Push only main/develop/Flatpak; read-only PR CI | Rewrite push alone does not start shipping CI; draft PR code changes start validation |
| `flatpak-validation.yaml` | Read-only workflow call; `test` Flatpak branch | Candidate artifacts only |
| `pages-artifact-validation.yaml` | Read-only workflow call | Synthetic upload/download; no deployment |
| `release.yaml` | Successful same-repo CI push on main, or manual dispatch on main | Rewrite/PR cannot pass prepare; publication/downstream dispatch depend on it |
| `flatpak-pages.yaml`, `winget.yaml`, `flathub.yaml` | Release/manual triggers | Never manually dispatch these for this goal |

The reviewed existing workflows cannot publish production through the authorized
branch push/draft PR. New candidate workflows require separate review for read-only
permissions, immutable actions, no secrets/stable deployment and native-result
integrity. A prepared workflow is not execution evidence.
