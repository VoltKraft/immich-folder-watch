# Read-only Windows preflight for the installed 3.0.4 MSI

The [cutover protocol](../../../../docs/rust-rewrite-plan.md#cutover-protocol)
requires exclusive ownership across Windows sessions for the entire handover.
An installed copy of WPF can start after an orderly Quit. The native preflight
identifies the registered shipping package even with its executable closed.
Transactional prevention of later launches and admission of a production writer
remain open under RI-AC05.

## Native decision

`msi-session-endpoint.exe --preflight-installed-writer` requires the marked
standard account on a disposable Windows desktop. It reads the two original
machine ProductCodes through `MsiGetProductInfoExW` with machine context and
a null user SID. The Windows SDK defines `State`, `VersionString`, and
`PackageCode`. Windows Installer returns `5` for an installed product and
`1` for an advertised product. The release payload records bind the two
ProductCode/PackageCode pairs to the original x64 and ARM64 packages.
[Windows Installer query](https://learn.microsoft.com/en-us/windows/win32/api/msi/nf-msi-msigetproductinfoexw) ·
[Windows SDK header](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/Msi.h) ·
[Original MSI identities](../../../RustCompatibilityOracle/installed/windows.ps1) ·
[Native preflight](installed_writer.rs)

| Exit | Meaning |
| --- | --- |
| 20 | Installed machine ProductCode, version 3.0.4, and matching release PackageCode. The known installation vetoes writer admission. |
| 21 | A queried product has another state or package identity, or Windows Installer reports a member of the same upgrade family. A registration remains. |
| 22 | The MSI inventory query failed. The original Windows error is printed. |
| 23 | No recognized machine instance or visible upgrade-family registration was found. Exclusive handover still requires separate evidence. |

The [upgrade-family query](https://learn.microsoft.com/en-us/windows/win32/api/msi/nf-msi-msienumrelatedproductsw)
also covers advertised products visible to the calling account. An empty
inventory cannot establish whether a portable or unregistered copy can start.
All four exits are read-only decisions. The test never opens the shared profile
for writing or grants migration authority.

## Native trial and replay

Use a disposable Server 2025 x64 overlay with 4 GiB RAM and an active RDP
session for its ordinary `ifw-test` user. Install the pinned release MSI into
the overlay. Preserve the installer log and receipt in the existing test marker
directory. Begin with an absent `%LOCALAPPDATA%\Immich Folder Watch` profile.
The checkout on the guest must reproduce the exact compiler sources with LF
line endings and include `packaging/windows`. Use native Python, Git and
PowerShell 7. The probe runs once before WPF starts and again while the original
installed WPF process owns its visible editor and tray receiver.

From the checkout, invoke the [guest observer](observe_installed_writer.py) with
the original endpoint ZIP, its Actions SHA-256 and a fresh trial directory.
The embedded Python installation uses the same sibling-module bootstrap as
the [ordinary WPF handover](wpf-handover.md).

```powershell
$qa = (Resolve-Path tools/rust-qa/instance/cross-session).Path
$bootstrap = 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")'
$work = "$env:LOCALAPPDATA\IFW-MsiSessions\trial-preflight-01"
python -B -c $bootstrap $qa "$qa/observe_installed_writer.py" $archive $digest $work
```

Archive the original work directory with its native process transcripts, captured
standard-user identities, installation record, WPF menu receipt and guest result.
The [host reader](replay_installed_writer.py) checks the compiler and observer
sources against Git, compares both original exits and reopens the installer log
and WPF menu evidence.

```sh
python3 -B tools/rust-qa/instance/cross-session/replay_installed_writer.py \
  original-guest.zip endpoint.zip "$actions_sha256" --checkout checkout.zip
```

## Local Server 2025 observation on November 28, 2026

The native x64 compiler built revision `3913061126d920676fe30b74923236fe1cf3625e`.
The guest ran the observer from `33e149b75a9036e2b76ba1dc669851c6ea8b86cc`.
QMP reported 4 GiB of base memory and zero hotplugged bytes. The installer
registered the original per-machine MSI in the fresh overlay. Both preflights ran
in RDP session 2 of its standard account. [Compiler run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46115384790) ·
[Original compiler archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46115384790/artifacts/15251114708)

| Observation | Native result |
| --- | --- |
| Before the first WPF start | Preflight PID 1896 returned exit 20. Both process snapshots were empty and the application profile was still absent after exit. |
| With the installed WPF desktop active | Preflight PID 2336 returned the identical veto. The installed process, PID 4756, owned editor HWND 131454 and tray receiver HWND 196714 before and after. |
| Ordinary Quit | The original highlighted command 3 on the WPF popup received its native mouse click. WPF exited zero. |

Each raw native line identifies machine context, installed state 5, version
3.0.4, ProductCode `{50554B02-DB63-4388-A959-8F0B25856F5A}` and PackageCode
`{19DC3747-2CBD-4D6A-9960-AB0AA4B65947}`. The separate 64-bit machine uninstall
entry identified version 3.0.4 and publisher VoltKraft across both samples.
The original verbose install log also retained `ALLUSERS=1` and the upgrade code.

| Original input or evidence | SHA-256 |
| --- | --- |
| Compiler ZIP | `0f19d7e208bb84aa0aa9839da944cafc0cdf17ea91a3e47bae222af4bdf4b634` |
| Original native x64 endpoint | `34a148bb978c325e9315f9ca21d4861fd9131e917137303b358320eb39ee6b9f` |
| Observer checkout ZIP | `c3d0b0858665f0bf6acf4119ef94a800adb3bb6064fa8b21a4e1749b144664f3` |
| Guest ZIP, 212,745 bytes | `8a905a1627b5608c216fe56bfe40e6e1b9384d78ee4055a2cfddfe2899f1dba4` |

The original ZIPs and `readback.json` are under
`artifacts/rust/local-windows-server-2025-x64/20261128/installed-preflight-3913061/`.
The host verified the guest-reported ZIP length and digest, five compiler source
hashes, 21 guest-observer source hashes, the AMD64 PE, installation identity,
standard process tokens and menu anchor. Changed copies with a different active
exit code, window handle or idle transcript each failed replay. This observation
covers installed-package identification on x64. Production writer prevention,
transactional handover and the native ARM64 installation trial remain open.

After RDP disconnected, ACPI shut the guest down normally. The host found no
remaining QEMU process, open scratch handle or listener on the trial port.
`shutdown.json` retains the memory readback and matches both backing images to
their pretrial size, inode and modification time. The disposable overlays were
then removed.
