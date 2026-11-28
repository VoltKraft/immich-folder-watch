# Retained Rust tray menu on the local Windows x64 console

Use the new, source-matching `rust-tray-windows-x64-<revision>` compiler ZIP
and its original Actions SHA-256. Follow the [retained tray setup](../../../docs/rust/rw02-windows-services.md#retained-explorer-activation-on-the-local-windows-x64-vm)
for the disposable Server 2025 guest. On its original unlocked console,
start the comparison as the standard `IFW-QA25\ifw-test` user.

```powershell
python -B tools/rust-qa/windows-launcher/tray_menu.py --local-archive D:\tray.zip --archive-sha256 $digest
```

One synthetic hidden-start primary processes the three menu selections in
order. Each right-click is delivered through Windows input to the real
Explorer icon after the original provider, physical hit, icon color and
Shell rectangle agree. The first comparison changes the token-specific
color. Each subsequent comparison rechecks that color. The observer reads
the native popup handle, owning thread, receiver, command IDs, separators,
labels and item bounds. It compares all three labels against the shipping
English and German resources. The left-button click requires a second
readback of the same menu and a physical hit on the selected row.

Open must show a visible editor owned by the original GUI. Restart must
drain its first native inventory worker before creating a second child,
and the replacement must complete its initial inventory passes. Both
workers are identified by their job, executable, PID, parent PID and
creation time. Their retained process handles provide the actual exit
codes and times. Quit must end the primary naturally, stop the input
reader, drain the replacement worker, remove the icon, leave an empty
process job and restore Explorer's flyout and the cursor. The primary's
control pipe stays open until its exit.

Collect `artifacts/rust/windows-tray-menu/x86_64-pc-windows-msvc/` with its
primary log, three provider logs and result. On a checkout containing the
original compiler and observer sources, replay the original compiler ZIP
and the downloaded evidence directory together.

```powershell
python -B tools/rust-qa/windows-launcher/tray_menu.py --local-archive D:\tray.zip --archive-sha256 $digest --replay D:\evidence\x86_64-pc-windows-msvc
```
