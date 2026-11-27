# RW-02 Windows display scaling and RDP

The existing native evidence at `8a8adaa400abc7303335c624ea68abed197158da` covers one 1024 × 768 monitor at 96 DPI on each Windows architecture. Both Rust processes selected DX12 and the Microsoft Basic Render Driver. The observed client area was 640 × 400 physical pixels on both hosts. Their process and active console sessions were both 2. The earlier observer did not query the WTS transport or move either HWND between displays. The x64 accessibility trial passed and the ARM64 trial stopped during foreground activation. [Native run 44941845642](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642) · [Prior desktop observations](rw02-windows-desktop.md)

| Native archive | SHA-256 of `windows-input/input.json` | SHA-256 of `windows-desktop/original/observation.json` |
| --- | --- | --- |
| Windows x64 | `45bf0b4692000ee767a86e48ab9af9c49acc32d22e596836eb1c0396ba75a3f4` | `515a84bba5cb6e2d846ab8cefab15412da080edc09f4162e90edd5ecc7dd2b5d` |
| Windows ARM64 | `438eec56d536f6f6feeacc18d904532757b20b3888dfe46652e2259deec18f5c` | `98baf7647253448f20d9707efcf1a99a3d785c7f28955721c0d7af8ddb569579` |

## Hosted console results

Two subsequent source revisions measured the WTS protocol and active display
paths. All four observations found one addressable 1024 × 768 monitor at 96 DPI,
one active CCD path and WTS console protocol 0 in session 2. Each subject
used DX12 on the Microsoft Basic Render Driver and drained normally.
The real x64 filename retained focus and showed changed pixels. The ARM64
field was readable, but could not acquire foreground focus on the original
console. For both architectures the mixed-DPI and RDP rendering results are
unmeasured. [Run at 45dc03b](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44950398558) · [Run at d403fee](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306)

| Revision | Windows | Source frame changed pixels / columns / rows | Display result SHA-256 |
| --- | --- | --- | --- |
| `45dc03b` | x64 | 681 / 86 / 18 | `25059ccb2cf2cb08ccf072f5321dd3e4f0a83172a83eb4fb2de6741aeb9e1cd6` |
| `45dc03b` | ARM64 | Focus unavailable | `d67433cbde6707ca71fa37c4c1b0ab148df3e179c6affb1a9bd0ac7169a88f73` |
| `d403fee` | x64 | 645 / 84 / 18 | `4aafa8175d8e2bb0f8741c1bd034eeb9bd140ee2bf4cc630de09694ca6bb4d43` |
| `d403fee` | ARM64 | Focus unavailable | `27fe8068d687abb9504b4b537ade3a4db6e33a74df47be1d117606d23dce163b` |

The archived SHA-256 manifests covered the native reports, logs and retained
field images. Replaying the two original x64 PNG pairs reproduced all six
pixel counts. All fourteen observer input hashes per report matched the
revision, including Windows checkout line endings on three shared scripts.
[Four-target archive identifiers](rw02-native-gui.md#native-follow-up-at-d403fee).

GitHub documents the two standard VM labels and their CPU, memory and disk
specifications. The observed jobs supplied a console already in use by the
test, with one active output. Windows can reconfigure existing display paths.
The indirect display model for an additional virtual monitor needs a display
driver to announce its arrival. A second configured display and an active RDP
session therefore remain external prerequisites for the observations below.
The older receipts did not inventory inactive targets. [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) · [Windows display configuration](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setdisplayconfig) · [Indirect display monitor arrival](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/iddcx-objects)

## Native observation

At `a66e045` Windows Server x64 and Windows 11 ARM64 each enumerated one
1024 × 768 monitor with a 1024 × 720 work area and 96 DPI. The all-path
DisplayConfig query returned one available, active target on each VM.
Both used the DX12 Microsoft Basic Render Driver and WTS console session 2
(protocol 0). Neither host exposed a second addressable target or an RDP
session. The mixed-DPI and RDP frame results are unmeasured on both hosts.

| Windows host | Filename field on the source display | Display result SHA-256 |
| --- | --- | --- |
| x64 | The edit changed 681 pixels across 86 columns and 18 rows. The observer restored the text. | `233acf7cb17f6e7cf05e52d939291f69a39c8541f29d43a3a5b41df55fd1658f` |
| ARM64 | UI Automation read the field and its 280 × 22 pixel bounds. It could not focus the field for the edit, so this run captured no field frames. | `a47e08ccf16b1e44f76b0a1a1722ef587c13dec6fc096bc1f5044f398e1a1aca` |

[Native archives](rw02-native-gui.md#native-follow-up-at-a66e045).

Run after the canonical Rust GUI build on the matching Windows target. Output goes to the new `artifacts/rust/gui-native/<target>/windows-display/` directory. The fixture verifies the PE architecture, Git revision, binary digest, compiler sources, audited dependency graph and fonts. It pins the verified image, starts it in its own kill-on-close job, and limits the application profile to fresh temporary directories. [Display runner](../../tools/rust-qa/windows-display/run.py) · [Build verification](../../tools/rust-qa/windows-text/run.py)

```bash
python3 tools/rust-qa/build-gui-probe.py "$NATIVE_TARGET"
python3 tools/rust-qa/windows-display/run.py "$NATIVE_TARGET"
```

### Both retained Windows display inventories at 6084b23

Both hosts supplied one 1024 × 768 monitor with a 1024 × 720 work area at
96 DPI in a console session. Each retained Rust process presented through
the DX12 Microsoft Basic Render Driver with Mailbox, one queued frame and
the Wait policy. A close hid the original HWND. Quit drained the worker
and the host removed the private profile.

| Host | Retained display observation | Retained result SHA-256 |
| --- | --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14864735127) | Process 7676 retained HWND `0x240174` and one device generation. The filename edit changed 681 screen pixels on the source monitor. | `8c160b7131304f4ff429cf0e6e1e2310e8392cc09585923e715c412304b69e5a` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14864132829) | Process 10576 retained HWND `0x14016e` and one device generation. The source-monitor field did not receive focus during the UI Automation step, so the capture recorded no edited frame. | `e966cb0b664091ae850c9fe47d6c694ab66989ab64d1cd78c333532d7149a0b3` |

The hosted displays could not exercise a move to a monitor with different
DPI or a connected RDP session. The [separate filename test](rw02-windows-text.md)
has its own keyboard and glyph evidence.

### Hosted display and field capture at f155b65

Both Windows hosts again reported a single 1024 × 768 monitor at 96 DPI
and WTS console protocol 0. The original and retained GUIs used the
recorded native binaries. On x64 both source-display captures reached
the filename editor but failed to resolve `Get-FieldPngHash`. The field
observer imported the capture function without the digest helper it
called. The same error stopped the canonical and reopened filename
observers on both architectures. The separate reader and IME trials
passed. The original topology and session observations remain usable.
[x64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14991846627) · [ARM64 originals](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937295/artifacts/14990910738).

The shared capture function now includes its PNG digest operation. A
regression test runs each actual importer in a separate PowerShell
process with an empty module path and autoload disabled. Both reproduced
the missing helper from the earlier source and both corrected importers
returned the independently calculated digest of the test PNG.

### Source-monitor capture at 5efe1f1

Both x64 display observers again captured an actual edited
field on the source monitor. The canonical and retained GUI ran on the
same single 96-DPI console display. The two ARM64 display observers
reported the same topology and protocol. Neither obtained foreground
focus for its source-monitor picture. The separate ordinary and reopened
filename trials passed on both hosts. Each architecture still requires
a mixed-DPI desktop and an actual RDP session.
[x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996554328) · [ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45548715758/artifacts/14996337844).

### Required observations on a disposable native desktop

Use a dedicated Windows x64 or ARM64 test VM with the matching MSVC build
tools, Windows SDK, native Python, Git Bash and a working system UI Automation
PowerShell host. Use the same rewrite revision for the build and both
observations. The repository's compiler installer verifies and installs the
selected native toolchain inside the checkout. In Git Bash on x64, build once
from the repository root. Use `aarch64-pc-windows-msvc` for the ARM64 VM.
[Native prerequisites](../development.md#rust-feasibility-workspace) · [Compiler installer](../../tools/rust-qa/install-toolchain.sh)

```bash
target=x86_64-pc-windows-msvc
bash tools/rust-qa/install-toolchain.sh "$target"
export PATH="$PWD/artifacts/rust/toolchain/bin:$PATH"
python3 tools/rust-qa/build-gui-probe.py "$target"
python3 tools/rust-qa/windows-warm-window/build.py "$target" --isolated-vm
```

Run the observer from a terminal in the active, unlocked Default input
desktop. Keep the test window visible and unobstructed. For mixed DPI the
desktop must extend across two independently addressable monitors with
different Windows scaling, for example 100% and 150%. Allow enough usable
space on both screens for the scaled 640 × 400 logical client and its frame.
For the RDP trial use an already connected session to the disposable host
and launch the observer inside that session. A single monitor is sufficient
for the RDP rendering check. A client that presents multiple monitors can
supply both trials in one session when Windows actually reports two DPI values.
[Remote Desktop multimonitor behavior](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/mstsc) · [WTS protocol values](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ne-wtsapi32-wts_info_class)

```powershell
$target = 'x86_64-pc-windows-msvc'
python tools/rust-qa/windows-display/run.py $target --isolated-vm --retained --require mixed-dpi
python tools/rust-qa/windows-display/run.py $target --isolated-vm --retained --require rdp
```

Run each command in its corresponding desktop. Repeating `--require` on
one command requires both results from that session. Each required run prints
a fresh result path under `artifacts/rust/gui-native/<target>/windows-display-retained-runs/`.
For comparison, omit `--retained` to use the canonical teardown build and its
`windows-display-runs/` directory. Preserve the full run, the canonical
`build.json` and `graph.json`, and the retained build's `build.json`,
`compiler.jsonl` and `eframe-source.zip`. A requested observation that
could not run returns a nonzero exit and lists the missing qualification.

### Display checks with the measured x64 CPU executable

Use the original [Windows x64 performance and recovery ZIP](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45979619561/artifacts/15191997288)
to run the same executable tested at `483f053` on another disposable x64
desktop. Preserve a local copy for use after Actions retention expires. Its
SHA-256 is `2338eba8784f413b77493bc2d9499d2d2127b5895a748115aaf46ef20407a16b`.
This route requires a checkout of the observer, native x64 Python and system
PowerShell. It runs the archived GUI directly without a new compiler build.

```powershell
$target = 'x86_64-pc-windows-msvc'
$zip = 'C:\QA\windows-x64.zip'
python -B tools/rust-qa/windows-display/run.py $target --isolated-vm --cpu-archive $zip --require mixed-dpi
python -B tools/rust-qa/windows-display/run.py $target --isolated-vm --cpu-archive $zip --require rdp
```

The observer checks the ZIP and matches the GUI and benchmark worker to the
original compiler, timing and recovery records. It stages only the GUI in a
temporary profile. Each result under `windows-display-archived-cpu-runs/`
identifies the test checkout and original binary separately. The observed
filename edit includes the actual presenter route and the native pixel
captures. A `--require source-frame` run on one console can establish that
edit. Mixed DPI and RDP each require their own observation as described above.
[Archive verifier](../../tools/rust-qa/windows-display/cpu_archive.py) ·
[Original WARP recovery](rw02-windows-window.md#warp-device-recovery-on-windows-x64-at-483f053).

At `9313f39` the x64 runner launched the measured executable with SHA-256
`b84080b16e365d5297e5d2eb93be9f647f43b57b21bd80332b9917e85dfa36ec`.
The field edit changed 646 pixels across 84 columns and 18 rows. Replaying
both original PNGs reproduced all three counts. CPU frame 25 completed a
640 × 400 GDI transfer during the interaction on the same HWND. The hidden
window retained its device, the GUI exited normally and the profile was
removed. This console had one 96-DPI monitor and WTS protocol 0. The
mixed-DPI and RDP results remain unmeasured.
[Original report, log and field images](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46017375691/artifacts/15207180592).

### Local Windows Server 2025 x64 display trial

The disposable KVM guest used image 2 from the German Windows Server 2025
Standard Evaluation x64 ISO (Desktop Experience, ISO SHA-256
`64bd88c4cc99068ffc9727cc08f2e56ddc5707d175323f5aa0a8ab1d63d0815f`).
A local standard user ran the observer at `db1f126` with the archived
CPU executable from `483f053`. Windows reported an unlocked Default input
desktop in RDP session 2 (WTS protocol 2). It measured the primary display
at 1600 × 1000 and 96 DPI and the second at 2560 × 1600 and 192 DPI.

On the fresh guest both initial launches exited with `0xc0000135` before
creating a window. The guest lacked the system `VCRUNTIME140.dll`.
Windows verified the Microsoft signature on the x64 Visual C++ v14
Redistributable (installer SHA-256
`9c02c9ed120f671b900e6b9471d890e3b2414117a7e53f4ae2e855466fa2b7c9`).
The installer returned 0 and the system DLL then reported version
`14.52.37029.0`. The two original failure reports are preserved alongside
the subsequent trials.

| Post-install run directory | Required observation | SHA-256 of `result.json` |
| --- | --- | --- |
| `rdp-4rc1sljv` | RDP rendering passed | `b8a88524cfd98bbcacf99cb23d6d795df1fce42fe543ebbce533d2697047a1f0` |
| `mixed-dpi-pr7d_jze` | Mixed-DPI rendering passed | `a91a760650aa0f8b6e35c27f735ebfae0d903e79449c02037bb43a832c9b27f7` |

After an orderly shutdown, QEMU booted the same disk without installation
media. A fresh RDP connection repeated both observations. The RDP report
`rdp-cre_k4v6` had SHA-256
`4e6d932e8ce9d891f3194901549e6b79757de375b3c2b113203c6377095f5ad9`.
The mixed-DPI report `mixed-dpi-mqunrxfm` had SHA-256
`e10e2dd3f4243edf5ca4f5ddb308b34b5726ea5f5c70c2d4c7210d6a4846ae52`.
Both manifests and all four before/after image comparisons verified after
copying the results back to the host. Setup failures, successful trials and
cold-start repeats are archived locally under
`artifacts/rust/local-windows-server-2025-x64/20261127/`.

In each run the same application window moved between the two displays.
Its client grew from 640 × 400 to 1280 × 800 physical pixels. The focused
filename field grew from 22 to 43 pixels high and its three-character prefix
from 23 to 46 pixels wide. Both edits used the CPU/GDI presenter on the
DX12 Microsoft Basic Render Driver. Independent replay of each run's two
PNG pairs reproduced 682 changed pixels across 86 columns and 18 rows on
the source display and 2,313 across 168 columns and 39 rows on the
destination. Both evidence manifests verified. Both GUI processes closed
to their supervisors, exited with code 0 and released their temporary profiles.
These observations cover Windows Server 2025 x64. The ARM64 trials still
require a native desktop with the corresponding displays and RDP session.

### Retained build observations

The retained observer selects the paired executable from the native compiler
output, verifies its first-party sources and keeps the image pinned while the
test runs. On a DX12 CPU adapter advertising Mailbox it verifies the requested
maximum of one queued frame and the Wait policy from the device log. Hardware adapters use their
normal presentation policy. The report records the actual adapter and leaves
unobserved mode and queue depth empty. After closing, the native hide event,
HWND owner and object lifetime must show the original hidden window, with its
original device still alive. Quit must then drain the process. Each hosted
Windows runner collects the available topology for both builds. A positive
mixed-DPI or RDP result requires the corresponding real display or session.
[Retained build and observer](../../tools/rust-qa/windows-display/retained.py).

| Field in `result.json` | Observation |
| --- | --- |
| `inventoryPassed` | The source-bound DX12 process, visible HWND, window DPI and real German filename field occupy the same measured display. The report includes the addressable HMONITORs and work areas, active DisplayConfig paths where available, physical client and DWM bounds, WTS protocol and session state. |
| `possibleTargets` | One read of all CCD source-to-target combinations groups duplicate paths by adapter LUID and target ID. It records the native target-available and path-active flags separately. An available inactive target has no demonstrated window DPI or frame. |
| `sourceFrameObserved` | The current input desktop allowed the observer to focus the owned filename, change its synthetic text, verify two distinct physical field frames and restore the control text. An unavailable foreground or obscured field can leave a valid one-monitor inventory. |
| `mixedDpiPassed` | The same foreground Rust HWND moved between two addressable displays with independently measured different DPI. Its focused field retained the fixed text across the move. The window DPI, physical field height and fixed three-character range followed the new scale. Another field edit changed the drawn pixels on that monitor. |
| `rdpSessionObserved`, `rdpRenderer`, `rdpRenderingObserved` | WTS protocol 2 identifies an existing RDP session. The application adapter and HWND are bound to that session. The raster proof runs on the source display before any mixed-DPI move. Console sessions and unmeasured raster results retain their own status. |

The observer queries active DisplayConfig paths and maps their GDI sources to the enumerated monitors. Windows can deny the CCD query inside an RDP session or when the graphics driver lacks this capability. The raw result retains the failing API and Win32 status. To establish an addressable display and its DPI, the observer creates a hidden, nonactivating, per-monitor-aware window at the center of each work area. It checks `MonitorFromWindow`, reads `GetDpiForWindow` and destroys the witness. Each visible app observation independently reads the Rust window’s own HMONITOR and DPI. [Topology observer](../../tools/rust-qa/windows-display/topology.py) · [QueryDisplayConfig](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig) · [GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow) · [WTS protocol](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ne-wtsapi32-wts_info_class)

All text operations resolve the fixed process’s `Dateiname` editor through UI Automation. The physical crop is limited to the verified synthetic field. The recorder checks every point against the owned HWND before and after capture. Two same-position screenshots, matching hashes and changed row and column counts witness a new drawn frame. The mixed-DPI comparison allows pixel rounding at both measured scales. The fixture changes only its observer thread’s DPI context and the position of the owned test window. It closes the GUI through its native close message, observes the hidden window and renderer release, drains the supervisor and removes the temporary profile. [Field observer](../../tools/rust-qa/windows-display/field.ps1) · [Existing ownership and hit tests](../../tools/rust-qa/windows-text/Pointer.cs)

A null qualification and its recorded prerequisite indicate an unmeasured case.
Ten portable checks cover Win32 layouts, active and possible paths, input
eligibility, geometry, focus, frame evidence and retention of failed qualification
attempts. PowerShell 7.7 parsed the field observer and compiled its shared native
bridge. Both hosted inventories exercised the possible-target query. The
local x64 guest supplied the displays and RDP session for the [archived CPU
executable](#local-windows-server-2025-x64-display-trial).
[Regression checks](../../tools/rust-qa/windows-display/test_display.py) · [Windows active and possible paths](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig) · [Target identification and availability](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-displayconfig_path_target_info)

```bash
python3 -B -m unittest discover -s tools/rust-qa/windows-display -p 'test_*.py'
```
