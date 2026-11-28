# Installed 3.0.4 MSI preflight and Windows cutover trials

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

Use a disposable Server 2025 x64 overlay with 3072 MiB RAM and an active RDP
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

## Private MSI transaction for the original x64 launch paths

The [test-only successor](transaction/Cutover.wxs) uses the shipping UpgradeCode
and matches exactly the original x64 3.0.4 ProductCode. It installs the archived
Rust preflight in its own Program Files directory. The package checks the
`IFW-QA25` computer name and an explicit test property on first install. The
shipping MSI and its installed files are ordinary Windows Installer inputs.

The [installer observer](transaction/admin.ps1) requires all WPF processes to
have exited before each operation. It records the machine registration, installed
executable digest and desktop shortcut target after each transaction. The
[profile owner](transaction/standard.py) starts in a separate, ordinary RDP
session and restores the synthetic YAML, SQLite database, WAL and SHM from the
original [one-upload WPF handover](wpf-handover.md). It hashes those four files
before and after each installation change, runs the archived Rust preflight
and attempts an ordinary launch at the removed WPF path.

The first upgrade injects a Type 19 MSI error after `InstallExecute` and before
`InstallFinalize`. The repeat omits that property. Both upgrades place
`RemoveExistingProducts` immediately after `InstallInitialize`; Windows
Installer owns removal and rollback. To return to the old version after a
successful upgrade, the administrator uninstalls the private successor and
reinstalls the original 3.0.4 MSI from the read-only medium. The standard user
then opens the installed WPF application and selects its ordinary tray Quit.
[Windows Installer removal sequencing](https://learn.microsoft.com/en-us/windows/win32/msi/removeexistingproducts-action) ·
[Executing the script within the transaction](https://learn.microsoft.com/en-us/windows/win32/msi/installexecute-action).

### Reproducing the transaction

Use one disposable 3072 MiB Server 2025 x64 VM with the original per-machine
3.0.4 installation, the bound standard-user marker from the preflight above,
and a fresh `ifw-test` RDP profile. Supply the original compiler archive above
as `endpoint.zip`, the 3.0.4 x64 MSI as `shipping.msi`, the previous WPF
handover guest archive as `handover.zip`, and the project's pinned
`WixToolset.Sdk.6.0.2.nupkg` as `wix.nupkg`. Put the matching
`Cutover.wxs` and `admin.ps1` beside them on the read-only DVD. Restore the
matching LF checkout and native Python and PowerShell 7 for the RDP observer.
On the local administrator console run the following command.

```powershell
& D:\admin.ps1 -Disc D:\
```

In the standard user's ordinary RDP session run the observer from that checkout.
It takes input from the same read-only DVD.

```powershell
$qa = (Resolve-Path tools/rust-qa/instance/cross-session/transaction).Path
$bootstrap = 'import runpy,sys;sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name="__main__")'
python -B -c $bootstrap "$qa\standard.py" D:\ "$env:LOCALAPPDATA\IFW-MsiSessions\trial-transaction-01"
```

Retain the raw install logs, preflight streams, compiled private MSI, phase
receipts, original WPF Quit evidence and guest transfer record. The
[independent reader](transaction/replay.py) takes the guest ZIP, original
compiler ZIP, original WPF handover ZIP and delivered checkout ZIP in that
order. It checks the retained rollback script's copy of the original executable
and compares each phase with the original profile bytes and compiler evidence.

### Server 2025 x64 result at 2ba4006

On November 28, 2026, the local guest ran the observers from
`2ba40065a08f096345c402eee45f3d0f5c9d4f6a`. The standard user was in
RDP session 2 and the local administrator performed the MSI operations.

| Observation | Native result |
| --- | --- |
| Baseline | Windows registered 3.0.4, the public desktop shortcut targeted the original WPF executable, and the standard-user preflight returned 20. |
| Failed major upgrade | Windows Installer returned 1603 after executing the private failure action. The rollback script copied the original `ImmichFolderWatch.exe` from its own `C:\Config.Msi\*.rbf` file. The 3.0.4 registration, original executable hash, shortcut and native veto 20 were present again. |
| Successful major upgrade | Windows Installer returned 0. The private successor replaced 3.0.4 in the machine registration. The public desktop shortcut disappeared. Starting the original WPF executable in RDP returned Win32 error 2. The installed Rust preflight returned 21 for the remaining upgrade-family registration. |
| Ordinary return to 3.0.4 | Both successor removal and original MSI reinstallation returned 0. The registration, original executable and shortcut returned. The standard user's restored WPF process, PID 6344, owned editor HWND 131274 and tray receiver HWND 197074. The observer selected the highlighted Quit command 3 on popup HWND 262322. WPF exited 0. |

At all four samples the profile owner read identical bytes for the original
YAML, database, WAL and SHM. The input database held one shipping-worker
upload row and passed SQLite `quick_check`. Its WAL was empty after the
previous worker's orderly Quit.

The guest ZIP has SHA-256
`da7fd6fc5e48951cd685c92736c43229392c29a4fb766147aa6cb1f7c5a9a59e` and
742,624 bytes. The private compiled MSI has SHA-256
`91a5067d1e266862c865096f78806e5d6f9b6e7c7f181ad0ab5a08583e320600`.
The original DVDs, guest archive, host readback and negative controls are under
`artifacts/rust/local-windows-server-2025-x64/20261128/cutover-transaction-03`.
Changing the native preflight stream, the original executable's rollback
destination, or a recorded database digest caused independent replay to fail.
After ACPI shutdown the host found the port closed and no remaining QEMU
process. It verified the original disk and firmware metadata and removed both
temporary SSD overlays. QMP recorded 3,758,096,384 bytes of base RAM and zero
hotplugged bytes.

The trial establishes transactional replacement of the installed x64 launch
paths while WPF is already drained. RI-AC05 still requires exclusion of a
competing launch during the transaction, treatment of unregistered copies,
and rollback after a production Rust writer has actually changed the profile.
The private candidate continued to veto writes. Native ARM64 migration
remains open.

### Installed path and process snapshot after commit

In the three completed x64 archives, Windows Installer returned 0 for the
upgrade before the administrator checked the registration and the installed
paths. The private successor was registered, the old desktop shortcut was
absent, and an ordinary launch from the removed WPF path returned Win32
error 2. The administrator reported zero processes named
`ImmichFolderWatch`. The standard user's separate system-wide Toolhelp
snapshot completed without a matching executable name. The successor's
preflight returned 21 and kept the writer disabled.
[Administrator and RDP observations](transaction/running-wpf.md#windows-server-2025-x64-results)
· [Toolhelp enumeration](../../../../tools/rust-qa/windows-performance/native.py#L554).

The [detached reader](transaction/replay.py) reports these observations in
`postCommit`. It reproduced them from the original `cutover-transaction-03`,
`cutover-running-wpf-01` and `cutover-running-wpf-3072` archives. The 3072 MiB
guest archive has SHA-256
`d45a7673d47af1d0bea990dd3fc67656ffed674c33ab3b0b524e5c8a752d0b1b`.

The [updated administrator observer](transaction/admin.ps1) first checks
the original executable's file attributes, then queries `Win32_Process`
across sessions for its executable name. It writes
`committed-inventory.json` in the administrator's transaction directory
before checking the results. Each matching row records its PID, session
and whether its image path matched the installed path, differed or was
unavailable. Failure of either query remains visible independently. An
unresolved path, a process-query failure or any matching row stops the
trial. The read-only check samples the known installation at this point
in time. Other executable names and later launches remain outside it.

Local tests exercised the actual PowerShell reader with synthetic CIM
responses and checked that the detached reader rejected missing, occupied
and indeterminate observations. The earlier archives used `Get-Process`
and Toolhelp.

A fresh 3072 MiB Windows Server 2025 x64 guest ran the extended observer
from `2e7a0f3bc10b1354bd43866b9a947b8f16d917f2`. In RDP session 2,
the running WPF editor (PID 7548) survived the refused upgrade and exited
through its own tray menu. Windows Installer rolled back the deliberately
failed attempt (1603), then committed the ordinary retry (0). Before the
successor was uninstalled, the administrator observed the original installed
path absent and an empty `Win32_Process` result. Both queries completed
without errors. Independently, the standard user's Toolhelp snapshot found
zero WPF processes, the original shortcut count was zero, and launching
the original path returned Win32 error 2. The successor's read-only
preflight returned 21.

The private MSI removal and original 3.0.4 reinstall each returned 0.
The restored WPF editor (PID 7640) opened and quit through its tray menu.
The detached reader matched all four synthetic profile files across the
observed phases. After ACPI shutdown the host verified the loopback RDP
port was closed, QEMU had exited, the disk and firmware base metadata
matched the initial values, and both temporary overlays were removed.

The originals are under
`artifacts/rust/local-windows-server-2025-x64/20261128/cutover-committed-2e7a0f3`.
The SHA-256 of `share/original-guest.zip` is
`ad0c0f28f2b2d2ea3618a95ed7fc423f33affcbb90fbc69284d65c9bc6c77776`.
Its `committed-inventory.json` has SHA-256
`a639724e6dbafea3379f834cd9bb31c9c90e2983b60c4c5f1991154760d3b998`.
`readback.json` identifies the original executable, private product code,
MSI digest, transactions and profile hashes. `shutdown.json` records the host
readback.

The [separate profile-return trial](transaction/rust-return.md) checks the
album value in the reinstalled WPF editor using an archived Windows x64
Rust configuration and an isolated copy of the database files.
