# RW-02 Windows display scaling and RDP

The existing native evidence at `8a8adaa400abc7303335c624ea68abed197158da` covers one 1024 × 768 monitor at 96 DPI on each Windows architecture. Both Rust processes selected DX12 and the Microsoft Basic Render Driver. The observed client area was 640 × 400 physical pixels on both hosts. Their process and active console sessions were both 2. The earlier observer did not query the WTS transport or move either HWND between displays. The x64 accessibility trial passed and the ARM64 trial stopped during foreground activation. [Native run 44941845642](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642) · [Prior desktop observations](rw02-windows-desktop.md)

| Native archive | SHA-256 of `windows-input/input.json` | SHA-256 of `windows-desktop/original/observation.json` |
| --- | --- | --- |
| Windows x64 | `45bf0b4692000ee767a86e48ab9af9c49acc32d22e596836eb1c0396ba75a3f4` | `515a84bba5cb6e2d846ab8cefab15412da080edc09f4162e90edd5ecc7dd2b5d` |
| Windows ARM64 | `438eec56d536f6f6feeacc18d904532757b20b3888dfe46652e2259deec18f5c` | `98baf7647253448f20d9707efcf1a99a3d785c7f28955721c0d7af8ddb569579` |

## Native observation

Run after the canonical Rust GUI build on the matching Windows target. Output goes to the new `artifacts/rust/gui-native/<target>/windows-display/` directory. The fixture verifies the PE architecture, Git revision, binary digest, compiler sources, audited dependency graph and fonts. It pins the verified image, starts it in its own kill-on-close job, and limits the application profile to fresh temporary directories. [Display runner](../../tools/rust-qa/windows-display/run.py) · [Build verification](../../tools/rust-qa/windows-text/run.py)

```bash
python3 tools/rust-qa/build-gui-probe.py "$NATIVE_TARGET"
python3 tools/rust-qa/windows-display/run.py "$NATIVE_TARGET"
```

A separate invocation on an expressly authorized disposable native Windows VM uses `--isolated-vm`. This requires an already active, unlocked console or RDP session on its Default input desktop. On a native x64 VM, run the following after the canonical x64 build.

```powershell
python tools/rust-qa/windows-display/run.py x86_64-pc-windows-msvc --isolated-vm
```

| Field in `result.json` | Observation |
| --- | --- |
| `inventoryPassed` | The source-bound DX12 process, visible HWND, window DPI and real German filename field occupy the same measured display. The report includes the addressable HMONITORs and work areas, active DisplayConfig paths where available, physical client and DWM bounds, WTS protocol and session state. |
| `sourceFrameObserved` | The current input desktop allowed the observer to focus the owned filename, change its synthetic text, verify two distinct physical field frames and restore the control text. An unavailable foreground or obscured field can leave a valid one-monitor inventory. |
| `mixedDpiPassed` | The same foreground Rust HWND moved between two addressable displays with independently measured different DPI. Its focused field retained the fixed text across the move. The window DPI, physical field height and fixed three-character range followed the new scale. Another field edit changed the drawn pixels on that monitor. |
| `rdpSessionObserved`, `rdpRenderer`, `rdpRenderingObserved` | WTS protocol 2 identifies an existing RDP session. The application adapter and HWND are bound to that session. The raster proof runs on the source display before any mixed-DPI move. Console sessions and unmeasured raster results retain their own status. |

The observer queries active DisplayConfig paths and maps their GDI sources to the enumerated monitors. Windows can deny the CCD query inside an RDP session or when the graphics driver lacks this capability. The raw result retains the failing API and Win32 status. To establish an addressable display and its DPI, the observer creates a hidden, nonactivating, per-monitor-aware window at the center of each work area. It checks `MonitorFromWindow`, reads `GetDpiForWindow` and destroys the witness. Each visible app observation independently reads the Rust window’s own HMONITOR and DPI. [Topology observer](../../tools/rust-qa/windows-display/topology.py) · [QueryDisplayConfig](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig) · [GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow) · [WTS protocol](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ne-wtsapi32-wts_info_class)

All text operations resolve the fixed process’s `Dateiname` editor through UI Automation. The physical crop is limited to the verified synthetic field. The recorder checks every point against the owned HWND before and after capture. Two same-position screenshots, matching hashes and changed row and column counts witness a new drawn frame. The mixed-DPI comparison allows pixel rounding at both measured scales. The fixture changes only its observer thread’s DPI context and the position of the owned test window. It closes the GUI through its native close message, observes the hidden window and renderer release, drains the supervisor and removes the temporary profile. [Field observer](../../tools/rust-qa/windows-display/field.ps1) · [Existing ownership and hit tests](../../tools/rust-qa/windows-text/Pointer.cs)

A null qualification and its recorded prerequisite indicate an unmeasured case. Mixed DPI and RDP remain unmeasured when the respective prerequisites are absent. The new observer has seven passing portable checks for Win32 layouts, topology changes, input eligibility, geometry, focus and frame evidence. PowerShell 7.7 parsed the field observer and compiled its shared native bridge. Native execution of this observer is pending. [Regression checks](../../tools/rust-qa/windows-display/test_display.py)

```bash
python3 -B -m unittest discover -s tools/rust-qa/windows-display -p 'test_*.py'
```
