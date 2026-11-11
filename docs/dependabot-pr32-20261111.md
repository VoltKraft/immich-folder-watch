# PR #32 reduced Avalonia verification (2026-11-11)

## Scope and revision

The user selected shipped-component auditing, a reduced Avalonia build and the
D-Bus compatibility fix on [PR #32](https://github.com/VoltKraft/immich-folder-watch/pull/32),
followed by CI and CodeQL. Merging, automatic merging, main publication and a
release are excluded. The reviewed PR head is
`ce0b711d33f6fa07c364445b96fb2bbc831b9354`; remote main remains
`df4839852bb84efef35a83cc429d51ce55b9ed1e` (v3.0.2).

Implementation and detailed reproducibility instructions live on the PR branch:
[component audit](https://github.com/VoltKraft/immich-folder-watch/blob/ce0b711d33f6fa07c364445b96fb2bbc831b9354/docs/avalonia-component-audit-20261111.md),
[maintenance contract](https://github.com/VoltKraft/immich-folder-watch/blob/ce0b711d33f6fa07c364445b96fb2bbc831b9354/docs/reduced-avalonia.md).
This closing record is saved locally; it does not publish the correction on main.

## Findings and implemented correction

Both downloaded v3.0.2 Linux bundles contain the original Avalonia 12.0.3
Controls/Fluent assemblies, matching the official NuGet bytes. Their actual
managed types and compiled resources confirm inclusion of the identified
MS-PL/Silverlight-derived components. The existing release is affected too;
merely deferring the version update was not a remedy. Both Windows MSI audits
found no Avalonia namespace implementations among 415 managed assemblies each.

Private Avalonia and Avalonia.Themes.Fluent `12.1.6.1` now reconstruct reviewed
net10 assemblies from upstream commit `cf8e564674700348947e93ab19105f27afe859a9`
using exact SDK 10.0.401. The explicit removal manifest excludes unused affected
controls/resources; original notices and supplementary Apple/SixLabors notices
are preserved. Other Avalonia packages stay at official 12.1.6. The app's used
controls and popup behavior retain regression coverage. Both app and portable
tests use MIT-licensed Tmds.DBus.Protocol 0.94.1, resolving the NU1605 downgrade.

Exclusive package-source mapping, reproducible inputs, scoped caches and archive
provenance prevent silent official-package substitution. Flatpak reconstructs
private packages offline and verifies the published DLLs and installed notices.
Independent review identified and verified a fix for a jointly tampered extracted
metadata/DLL cache: expected bytes now come directly from rebuilt package ZIPs.
Future Avalonia upgrades require a fresh coordinated source/component review.

## Local and native artifact evidence

- 501 portable Core tests and all 60 Linux tests pass with no local skips.
- The tooling suite succeeds (146 cases, four local PowerShell platform skips);
  the additional persistent-cache regression also passes independently, giving
  147 relevant cases. The hosted Windows security step covers PowerShell cases.
- Three independent package build roots produce identical private archives;
  actual publish provenance, original-DLL substitution negative controls and
  joint metadata/DLL-tampering regression pass.
- All 16 synthetic light/dark page previews render; inspected folders/settings
  previews show no missing templates. Real dropdown/tooltip tests cover both themes.
- Both offline feeds generate; 95 combined official archive hashes and installed
  official/private notices were checked.
- Both final native candidate builds pass. Downloaded x86_64/aarch64 bundles were
  imported into isolated OSTree repositories without installation. All 240 managed
  assemblies per architecture pass the excluded-type audit; no parse failures.
  Controls/Fluent match the locally rebuilt package bytes and installed provenance.
  Apple, SixLabors and D-Bus notices match the reviewed source bytes exactly.

Final candidate bundle SHA-256:

- `x86_64`: `be69a99986d53c253ff2fd13906bc84475828f3afd57e15c2a1379d5465f2eef`
- `aarch64`: `13df9273bbf5c39c941c971a1ba800bf980057ac62ca828ba6b617c6293a726e`

These are CI test artifacts, not a published release. Both architectures share:

- Controls: `dd06f5e9243d3a95f45c0985a1f92c96d517e7bc746ea6d768c06125f8c08d04`
- Fluent: `8f762376626068c2da4db11a9ece2775cd510e23c9705be7790dc28e4196c654`

## Hosted validation

All final-head checks are successful. GitHub reports 14 successful check runs
(including aggregate CodeQL), PR state OPEN/CLEAN, no auto-merge request and
repository auto-merge false.

- [CI 43062881077](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43062881077): all eight jobs succeed. Linux passes 501 Core and 60 Linux tests,
  with no skips. Windows passes 492 Core, 41 portable GUI and 36 Windows tests;
  9 Core and 19 Linux-only cases are platform skips. All 147 tooling tests pass in
  the hosted packaging job, with no skips.
- [CodeQL 43062868442](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43062868442): all four analyses succeed.
- [NuGet 43062866015](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43062866015): succeeds.

Earlier hosted failures exposed and verified fixes for the exact SDK selection
(10.0.404 selected by the old roll-forward policy), transient Flatpak HOME caches
(explicit persistent offline cache plus real two-HOME restore regression), and
Ubuntu mirror DNS failures (resolvable HTTPS mirror fallback retaining APT
signature verification). No security check or test was disabled.

The first final-head Windows attempt failed the existing
`WaitUntilReadyAsync_ReturnsTrue_AfterLockIsReleased` test after its three-second
budget. Independent review confirmed both test and checker are unchanged from
main; asynchronous lock release/poll scheduling can exhaust that margin, but the
exact scheduling cause was not instrumented. One unchanged-job rerun passed; no
assertion relaxation or production change was made. The Linux system-package step
stalled for over ten minutes, so the run was cancelled for log inspection before
restarting the affected jobs. Its log stopped during Ubuntu index downloads;
the replacement runner passed package installation, build, provenance and all
tests. Successful candidate artifacts remain recorded above.

## Boundary and next action

PR #32 remains open with no auto-merge request; repository auto-merge remains
disabled. No PR merge, main push, version bump, tag, release or deployment occurred.
Existing v3.0.2 Linux assets are unchanged: the correction reaches users only
after a separately authorized merge and new release. No live Immich connection,
installed desktop smoke test or blanket legal certification is claimed.

Milestone `M-PR32-REDUCED-AVALONIA-20261111` is complete for preparation and
validation. Next action requires explicit authorization to merge; publishing a
new release remains separate. The previously identified source-component blocker
is remediated in the reviewed PR artifacts, not in the existing published assets.
