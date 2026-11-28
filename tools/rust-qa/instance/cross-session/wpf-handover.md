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

## Local Server 2025 handover at bfd99b2

On November 28, 2026, the same ordinary test account held active console
session 2 and RDP session 3 in the local 4 GiB Server 2025 x64 guest.
The original 3.0.4 WPF process in RDP, PID 9076, uploaded the synthetic
69-byte PNG. During that request Windows refused Rust PID 8968 with
`ERROR_PIPE_BUSY` (231). A connection to the occupied pipe identified
PID 9076 as its server. Independent readback attributed the upload socket
to that same WPF process, matched the original multipart image and verified
HTTP 201 and one durable SQLite row.

The pinned helper selected command 3 on popup HWND 262746. The original
WPF editor HWND 66126 and tray receiver HWND 66114 belonged to thread
9064. Both the file log and the console output after Quit contained the
worker's shutdown signal and start of flushing. The original process
exited with code 0. Windows process times place the creation of the new
Rust endpoint, PID 9168, 126.0706 ms after that exit. The console then
acquired the writer guard using PID 9100. Both Rust processes released
ownership and exited with code 0. The recovered YAML retained file ID
`844424930294451`, all 441 bytes and SHA-256
`601aaf68c3c3785227866759f4257b10d8c1c72776aef83e75ecfba1527d81cc`.
The final retained SQLite database contained the same single upload.
The original worker emits its flush-start message before completing its
shutdown work. The zero exit and committed row are independently observed.

### Original evidence and subsequent source readback

The guest checked out `bfd99b2648be5870cf707f55d8a8322c174e82ab`
from a single-revision Git object pack on its read-only test DVD. The
checkout ZIP had SHA-256
`a9ffbb86764040daf0d2558a1f4c67a06cb62482de052060f11013028f6b75e2`.
The ISO had SHA-256
`e337039469dbfbc3e40b625cce1e77b6756e3bc49ee54179ca8a69bfb31bff4d`.
The guest wrote its native observations and 22 source hashes into a
306,210-byte ZIP with SHA-256
`0f30bc04dfe0337bf4bb5cab177d1ee048a314d342618f59719343c4d42dbcae`.

The first replay stopped because the original manifest omitted three
modules loaded directly from files. After the test, the original guest's
standard user read all three files from its still-present checkout, ran
`git diff --quiet HEAD --` for their paths, and returned their original
bytes on the serial port. The separate ZIP identifies the exact commit,
guest ZIP and original manifest hash. Its SHA-256 is
`26e2c158e558616a76434ad72e85ee52f3393ee2f449b78053e613011d0e50ff`.
The host verified all three supplementary files against the committed
blobs. Subsequent observers include these modules in the initial manifest.

| Module read back after the test | SHA-256 |
| --- | --- |
| `tools/rust-qa/instance/run.py` | `d469943c5cfa3919066876a8298af261f42d17f7dc5987b037cf6197300e1bb8` |
| `tools/RustCompatibilityOracle/installed/interop/shipping_upload.py` | `2dad415a3fbf80e35b9b793f91fc71fa87077c0f7ead52b126f798ea3714dc80` |
| `tools/RustCompatibilityOracle/installed/interop/installed_backup.py` | `1d45059cb41c94ed0b11ddad610594fb4f083f5ff91c63ac38b15997efa9275e` |

The original native observations, supplement and detached result are under
`artifacts/rust/local-windows-server-2025-x64/20261128/handover-bfd99b2/`.
Replaying this run requires both ZIPs. The independent `readback-01.json`
has SHA-256 `4b35f7b0bf58db2664f8366d504c656a9adbe3b85e24ed96a9b8e8e39a72be49`.

```sh
run=artifacts/rust/local-windows-server-2025-x64/20261128/handover-bfd99b2
python3 -B tools/rust-qa/instance/cross-session/replay_msi_sessions.py \
  "$run/share/handover-01.zip" "$run/disc/endpoint.zip" \
  c0ebe49184496b7b18e6146e4cf0fcaedae24d6a68ea39fbad5654ea6a38cfaf \
  wpf-handover --source-supplement "$run/source-supplement.zip"
```

After ACPI shutdown, the host found no remaining QEMU process, open test
disk handle or listener on the trial's loopback RDP port. It removed the
trial's Windows and UEFI overlays. The size, inode and modification time
of both base images matched the pre-test observations. The guest's QMP
memory record showed 4,294,967,296 bytes of base memory and zero hot-plugged
bytes. The host retained its comparison in `shutdown.json`.
