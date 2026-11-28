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

Open must show a visible editor owned by the original GUI. A passive check
waits up to two seconds for its root to become the foreground and active
window with keyboard focus on that root or one of its own children. Restart must
drain its first native inventory worker before creating a second child,
and the replacement must complete its initial inventory passes. Both
workers are identified by their job, executable, PID, parent PID and
creation time. Their retained process handles provide the actual exit
codes and times. Quit must end the primary naturally, stop the input
reader, drain the replacement worker, remove the icon, leave an empty
process job and restore Explorer's flyout and the cursor. The primary's
control pipe stays open until its exit.

Collect `artifacts/rust/windows-tray-menu/x86_64-pc-windows-msvc/` with its
primary log, three provider logs, result and `observer-sources.zip`. The
source archive identifies the exact observer revision and contains the
SHA-256-verified observer files used on this guest. On a checkout containing the
original compiler and observer sources, replay the original compiler ZIP
and the downloaded evidence directory together.

```powershell
python -B tools/rust-qa/windows-launcher/tray_menu.py --local-archive D:\tray.zip --archive-sha256 $digest --replay D:\evidence\x86_64-pc-windows-msvc
```

## Local Server 2025 result at 56b7ae8

On November 28, 2026, the native x64 Server 2025 guest completed all three
physical selections in one standard-user console session. Explorer PID 4384
presented the token-specific icon. Each physical right-click produced a
five-row Win32 popup owned by the same receiver (HWND 393704, thread 4820
of GUI PID 3808). Each popup contained `GUI öffnen`, `Neustart` and
`Beenden` with command IDs 1, 2 and 3 and two separators.

| Physical selection | Independent observation |
| --- | --- |
| GUI öffnen | The original editor HWND `0x5012c` became visible, foreground and active. Thread 6156 held keyboard focus in that editor. |
| Neustart | The first inventory worker, PID 3412, exited with code 0. The replacement, PID 6396, was created 18.6502 ms later and completed both initial inventories. The same visible GUI remained. |
| Beenden | The replacement worker and GUI exited with code 0. The GUI stopped its control reader, drained the job and deleted its original Shell icon. The control pipe remained open until exit. |

The original pointer and closed flyout were restored after each command.
Offline replay recovered all three choices and the same worker lifecycle
from the original guest logs, process handles and native compiler archive.
The first attempt stopped before selecting Open. The second verified Open
and Restart, then stopped at three UI Automation elements with the same
chevron name. The final observer requires a unique visible, enabled button
for the original Explorer and verifies its physical point before use.

The [compiler run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46109542388)
produced the [original x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46109542388/artifacts/15249183642)
at `56b7ae8884ee1341b30ea37811e21c2dc057ea86`. Its SHA-256 was
`d44f68f72f604ee69864e334fc360a8b5791df5bdf6db122984aa34394837ad0`.
The isolated observer checkout `674dc2e4694859160e40b1c8273950401cfc12f5`
applied the selector change from `dbfe23e` to `90923b4` and retained the
original compiler inputs. The guest archive of 104,135 bytes had SHA-256
`6678e7526f9c9cd45b5be5be64e5c4b7e2d38039f989cedfe4cce1762ab3c755`.
Its original bytes, checkout, source manifest and replay are under
`artifacts/rust/local-windows-server-2025-x64/20261128/tray-menu-56b7ae8/attempt-3/`.
