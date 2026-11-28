# Ordinary WPF Quit before Windows writer handover

This separate RW-02 trial starts the installed 3.0.4 WPF worker on the
RDP desktop. Its HTTPS policy allows the explicitly configured private
HTTP loopback fixture. The console starts the retained Rust endpoint
while the peer holds the WPF upload. The endpoint must identify the
original WPF pipe server and exit. After HTTP 201 and one committed row,
the RDP observer selects ordinary Quit on that same WPF process. The
console can then start the endpoint and acquire the writer guard.
This measures one orderly transfer in the synthetic profile. Removing the
installed legacy launch paths transactionally remains a packaging check.

Use the [local standard-user console and RDP setup](../../../../docs/rust/rw02-cross-session.md#standard-user-console-and-rdp-handover-on-windows-server-2025-x64)
on the disposable Server 2025 x64 guest. Start with an absent application
profile, two active sessions for `ifw-test` and the existing administrator-
provisioned VM marker. Put native Python 3.11 or later, Git and native
x64 PowerShell 7 on the path of the session startup hooks. Use a checkout
at the observer revision with `core.autocrlf=false` and the packaging
directory present. The script hashes its original source inputs. The
local x64 PowerShell 7.7.0 ZIP has SHA-256
`7c74e03b20a75b59715847439d046a6214b1863ee79b187872980f139bb4a05f`.

Create a fresh `%LOCALAPPDATA%\IFW-MsiSessions\trial-<id>` directory
in that synthetic account. Stage these original inputs there.

| File | Source |
| --- | --- |
| `bin/msi-session-endpoint.exe` | Original [endpoint compiler ZIP](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46096614452/artifacts/15242684323) with SHA-256 `c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf` |
| `bin/instance.exe` | Original [writer compiler ZIP](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46062734833/artifacts/15230355213) with SHA-256 `e432f3837570752f9806891195def9e88bc0befef82375a1327953d3a403bf95`. The executable digest is `134813fb4f69aeadd9fe6f21de922e24a0632a8a007f4aae6a4b220fa216d07b`. |
| `installed.json`, `install.log` | The original guest installation of the 3.0.4 x64 MSI. Its package hash and actual installed executable are checked during replay. |
| `endpoint-info.json` | Existing endpoint receipt with the native compiler ZIP digest and its complete original `build.json`. |

From the corresponding checkout, pass the same `$work` directory to the
following commands, one in each session. The existing embedded Python
runtime uses the explicit fixture path so that sibling modules are importable.

```powershell
$qa = (Resolve-Path tools/rust-qa/instance/cross-session).Path
$bootstrap = 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")'
# Standard-user console
python -B -c $bootstrap $qa "$qa/handover_msi.py" controller $work
# Same standard user's RDP desktop
python -B -c $bootstrap $qa "$qa/handover_msi.py" peer $work
```

Collect the whole trial directory, including failure records and temporary
logs on a refused menu interaction. On success it contains the original
TCP owner row, HTTP bodies, final SQLite files, both native admission
transcripts, the writer transcript, the original WPF logs and the menu
receipt with its popup, highlighted command, cursor and process identity.
The shipped worker logs the start of flushing. The recorded zero exit and
retained SQLite row provide separate observations.

Replay the returned ZIP on the host from a checkout containing the
original observer and compiler revisions.

```sh
python3 -B tools/rust-qa/instance/cross-session/replay_msi_sessions.py \
  observations.zip endpoint.zip \
  c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf wpf-handover
```
