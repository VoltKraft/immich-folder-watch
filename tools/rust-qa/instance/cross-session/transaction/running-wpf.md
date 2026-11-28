# Private MSI refusal while WPF is open

The [private successor MSI](Cutover.wxs) uses WiX Util 6.0.2 to check for
`ImmichFolderWatch.exe` before `InstallValidate`. When an occurrence is
found, Windows Installer reports that the user must quit WPF and retry.
The package leaves the application open for the user's ordinary tray Quit.
[WiX process detection](https://docs.firegiant.com/wix/schema/util/closeapplication/).

Use the [synthetic installed-package trial](../installed-writer.md) on the
disposable local Server 2025 x64 guest. Supply the original
`WixToolset.Util.wixext` 6.0.2 NuGet package on the input DVD as
`util.nupkg`. Its SHA-256 is
`19166934d5bcb47857869e943bc55822955d95a0cac17c9dd9956a4705335b3b`.
The existing administrator and standard-user commands also exercise the
already-running application. The standard user opens WPF in RDP before the
administrator starts MSI. The test records the original editor, tray
receiver, PID and creation time across the refusal. It then selects tray
Quit and repeats the existing rollback, successful upgrade and original
reinstallation trials.

Pass `--require-running-veto` to [the host reader](replay.py) with the four
original archives. It checks the install action and native exit in the
verbose MSI log, compares the identities reported by the administrator
and the standard user's desktop, and verifies the original process's menu
selection and exit. The four snapshots of the synthetic YAML, database,
WAL and SHM cover the subsequent rollback and upgrade.

## Windows Server 2025 x64 results

Both the console administrator and the standard user used the same private
guest. The input DVD contained the observer from
`1c5bc66e24fe0f5b067b40e77f073023134870bd` and the original release
MSI with SHA-256
`b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675`.
The first guest archive under
`artifacts/rust/local-windows-server-2025-x64/20261128/cutover-running-wpf-01/share/original-guest.zip`
has SHA-256
`7357f884b0b37cc8ee1c3a5a4af736d1b22854e902aa94354b8ac9eff4701d96`.
The verbose log records `Wix4CloseApplications_X64`, then
`RefuseActiveWpf`, then exit 1603 before the install transaction began.
The standard user in RDP session 2 kept the same WPF PID 6784, editor
HWND 131264 and tray receiver 196706 throughout the refusal.

After tray Quit, Windows Installer restored the original executable from
its rollback file in the deliberately failed upgrade. The ordinary retry,
successor removal and original reinstallation each returned 0. The
reinstalled 3.0.4 editor opened as PID 5196 and exited through its own
tray menu. The four synthetic profile files matched their original hashes
at each observed phase. As a check on the reader, it rejected three
altered copies of the evidence independently, for a changed process ID,
an inserted `InstallInitialize` action and a missing refusal action.

A repeat used a fresh SSD overlay with QEMU reporting 3,221,225,472 bytes
of base RAM and zero hot-plugged bytes. Windows completed the console
administrator sign-in, the original MSI installation and the standard
user's RDP sign-in. WPF PID 2908 kept editor HWND 131518 and receiver
327828 across the refusal. After rollback, retry, removal and
reinstallation, PID 912 opened the restored editor and quit normally.
The same host reader verified all four profile hashes and all MSI exits.
The archive at
`artifacts/rust/local-windows-server-2025-x64/20261128/cutover-running-wpf-3072/share/original-guest.zip`
has SHA-256
`d45a7673d47af1d0bea990dd3fc67656ffed674c33ab3b0b524e5c8a752d0b1b`.
The trial directory also contains `qmp-memory.json`, the guest serial
log and `shutdown.json` recording the release of the overlay.

This trial covers a WPF process already running when MSI checks. A user
launch after that check and writer admission under a production successor
registration remain open.
