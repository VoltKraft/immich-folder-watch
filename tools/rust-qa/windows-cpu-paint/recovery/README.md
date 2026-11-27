# WARP device replacement while the automatically selected CPU painter is active

On a disposable hosted Windows x64 runner, the test uses the two executables
from the CPU timing trial. The GUI starts its original inventory worker against
an empty synthetic directory and an exclusively bound loopback port. The
observer holds both original process handles. It enumerates their job and
matches both executable paths and creation times. The Windows launcher
observer also recognizes a direct console host of either process by its
full path in the native system directory. Each worker sample retains the
complete job membership and parent PIDs. The observer sends `G` over the GUI's private fixture pipe
after entering `recoverydraft` in the foreground editor. This destroys the
application's own logical wgpu device.

The reader follows the first device's loss callback, the CPU-policy retry and
the second ready WARP device. For each generation it matches CPU mesh records
and full GDI transfers to the independently observed HWND, process, thread and
client dimensions during the field edit. The input observer checks the
replacement's focus and restored text, types `after` and reads the changed pixels
from the unobscured field on the input desktop. The original worker must finish
another inventory after the recovered edit. Both processes must exit through
the GUI's ordinary Quit with status zero, and the owned profile must be removed.
This trial exercises a visible window on the hosted console.

After the [native CPU comparison](../README.md), run these commands with
`$cpu` set to its target-specific `cpu-paint` directory.

```powershell
python -B -m unittest discover -s tools/rust-qa/windows-cpu-paint/recovery
python -B tools/rust-qa/windows-cpu-paint/recovery/run.py $cpu
python -B tools/rust-qa/windows-cpu-paint/recovery/readback.py $cpu
```

Keep the original `cpu.exe`, `ifw-performance-worker.exe`, measurement,
library and source archives and the entire `recovery/` output. The detached
reader reconstructs the native build and checks the observation against the
recorded revision, raw process log, window events and inventory counts. It
validates the native pixel-difference report against the input observer's
source, both PNG hashes, physical crop dimensions and reported changed rows
and columns. The pixel counts are measured by System.Drawing on the native host. The [texture handoff](../handoff/README.md) exercises a supported
device that switches drawing back to wgpu on an unsupported sampler.
