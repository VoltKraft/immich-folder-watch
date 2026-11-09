# Project Status

## Active security remediation (2026-11-09)

- Milestone: `M-SECURITY-REMEDIATION-20261109`; in progress.
- Goal run: active in chat `01a1c1ee-b279-76d2-8529-eaf116140007`, created
  2026-11-09; criteria SEC-AC01 through SEC-AC05 fixed in the selected brief.
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
- Next action: implement and validate root-cause fixes, record every disposition,
  independently review, and publish the consolidated PR. No finding marked fixed.

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
