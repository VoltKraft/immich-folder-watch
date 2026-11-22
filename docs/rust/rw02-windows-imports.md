# Windows x64 and ARM64 import library reconstruction

The realtime assessment uses `ring 0.17.14` to query the ARMv8 crypto
instruction flag through `kernel32!IsProcessorFeaturePresent`. Its Windows
ARM64 graph selects `windows-sys 0.52.0`, `windows-targets 0.52.6` and
`windows_aarch64_msvc 0.52.6`. The Windows x64 transport uses ring's
separately reviewed x64 CPU detection and assembly. [Transport inputs](rw02-realtime-transport.md#dependency-and-native-input-review)
and [Microsoft's API documentation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent).

On x64 the combined GUI profile reaches `windows_x86_64_msvc 0.52.6` through
`winit 0.30.13 → windows-sys 0.52.0 → windows-targets 0.52.6`. Winit calls
`GetCurrentThreadId` on entry to its Windows event loop and during CRT
initialization to remember the primary thread. It calls `CreateWindowExW`
for the event loop's internal message target. The 111-package hosted x64
transport graph contains ring, windows-sys 0.61.2 and windows-link 0.2.1.
[Combined graph](rw02-combined-profile.md) · [Winit event-loop source](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/src/platform_impl/windows/event_loop.rs)
· [Native transport graph receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45034293002).

## Microsoft sources and notices

The target crate identifies Microsoft revision `db06b51c2ebb743efb544d40e3064efa49f28d38`.
The source archive at that revision contains the same 5,210,890-byte library
as the reviewed registry crate. The reconstruction starts from three WinMD
inputs. The Win32 metadata is version 61.0.15, the WDK input is 0.12.8
and the merged Windows SDK contracts are 10.0.26100.1. Microsoft explicitly
licenses these metadata files under MIT or Apache-2.0. The assessment
selects MIT and preserves both complete notice files. [Upstream metadata and licensing](https://github.com/microsoft/windows-rs/blob/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/libs/bindgen/default/readme.md)
and [original Microsoft MIT notice](https://github.com/microsoft/windows-rs/blob/db06b51c2ebb743efb544d40e3064efa49f28d38/license-mit).

The filtered source tar contains 396 exact Microsoft files and a SHA-256
manifest. It includes the WinMD inputs, reader, both generator components,
371 C baselines, provenance and licenses. The 34,150,400-byte tar has SHA-256
`cfb0c1357c9b3bc7cb0b746ffce50d23a25b78aeeeaccb1c4e6ad1fa280d979b`.
The build compiles the unchanged metadata reader with the pinned Rust compiler.
It compiles the metadata portion of Microsoft's helper separately since only
the unrelated workspace scanner uses regex. The complete upstream generator
and helper sources remain in the tar. The receipt binds the first-party
recipe and all three independently checked registry archives. [Input selection](../../tools/rust-qa/windows-imports/inputs.py),
[Microsoft's reader entry point](https://github.com/microsoft/windows-rs/blob/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/tools/lib/src/lib.rs)
and [MSVC generator](https://github.com/microsoft/windows-rs/blob/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/tools/msvc/src/main.rs).

## ARM64 reconstructed interface and local link

On Linux x64, all 20,551 WinMD declarations matched Microsoft's 371 C
baselines byte for byte, including the argument counts for 19,200 stdcall
signatures and 1,351 cdecl signatures. Two independent LLVM 23.1.5 builds
using the release Rust toolchain produced the same ARM64 import archive. Its
DLL names, case-sensitive function names, lookup hints and code import types
matched every original short COFF record. Both libraries contained 1,113
descriptor objects. The representative caller uses the original Rust
bindings, the system ABI and the same processor feature constant as ring.
It produced a byte-identical ARM64 PE with each import archive. The PE
imports one system function, `kernel32.dll!IsProcessorFeaturePresent`.
[Rust caller](../../tools/rust-qa/windows-imports/probe.rs) and [PE/COFF import format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#the-idata-section).

| Object | Bytes | SHA-256 |
| --- | ---: | --- |
| Original published import library | 5,210,890 | `ca85dd7757f338ba00d0bc19229f176ee426a707425ee4fcf205ec491a95bd5a` |
| Reconstructed LLVM import library | 5,068,350 | `20a536fcdb075d5a2ff93d1977d7a4420503396acba98c712d39ab3928fd1830` |
| Linked ARM64 binding probe, both libraries | 2,048 | `7403c4ab6abc7c3436ece021a365e7ebf0a94663c0791d21b7dc4bfccfc829d3` |
| Recovered WinMD signatures | 748,900 | `42f61a3ed6e4a64242abbab22818307d4f4b3ed23584425a42b03957214880f0` |

The Linux trial also resolved a fresh private copy of the complete transport
offline. It verified all 152 locked registry archives. The private path
override changed the library alone within the ARM64 package. The remaining
lock entries and original source files matched. Native execution and
byte-for-byte reconstruction with Microsoft's actual librarian are separate
checks.

The source-bound Linux receipts are under `artifacts/rust/windows-imports/runs/`.
The direct upstream run `arm64-n0s_nk97/result.json` has SHA-256
`ceafcd7dff067235a12edae5bb108a4aa732ca84d8654cf1e7d2afcf8c460de0`.
The offline filtered-source and full-lock run `arm64-c434eb4a/result.json`
has SHA-256 `ac49c500cbcf509e859ca88b9d88a2dc29b7899a4fa82caa6f5e71519a28c371`.
Both used 45 files from the checksum-pinned ARM64 standard-library component.
The three negative controls rejected a changed import type, an unreviewed source
tar and an unrelated lockfile change.

## Windows x64 reconstruction

The original x64 crate SHA-256 is
`589f6da84c646204747d1270a2a5661ea66ed1cced2631d546fdfb155959f9ec`.
Its target directory, both license notices and published import archive match
Microsoft revision `db06b51c2ebb743efb544d40e3064efa49f28d38`. Microsoft's
generator uses the same WinMD function list and 371 C baselines for both
64-bit targets. The x64 comparison checked every AMD64 descriptor and short
COFF member, including the machine, undecorated function name, DLL, lookup
hint and code-import type. The source distinguishes 19,200 stdcall and 1,351
cdecl declarations. On x64 the compiler uses the Windows x64 calling
convention for these ordinary functions. The probe calls the original Rust
`extern "system"` bindings with zero arguments and with an integer argument.
[Microsoft x64 ABI](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170)
· [Target source](https://github.com/microsoft/windows-rs/tree/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/targets/x86_64_msvc)
· [Binding probe](../../tools/rust-qa/windows-imports/probe_x64.rs).

| Fedora x64 cross-link with pinned Rust 1.100.0 and LLVM 23.1.5 | Bytes | SHA-256 |
| --- | ---: | --- |
| Published AMD64 archive | 5,210,890 | `24d8cbc445955b0d48041948a3c71ce2cddb948c089b25ec7106fadd9f3efde0` |
| Source-built AMD64 archive, both independent builds | 5,068,350 | `cc85942812c02a5ad0195125c77c50f9cee24b2c6bf3351881cd203351151bf6` |
| AMD64 probe PE with either archive | 2,048 | `2eabd604806c3d3e57210b7f126f86826e46cbd7536ec74716f74c612455558f` |

Both archives contain all 20,551 functions and 1,113 descriptor objects.
The linked PE imports only `kernel32.dll!GetCurrentThreadId` and
`user32.dll!GetSystemMetrics`. The separate event-loop executable uses the
complete Apache-2.0 winit 0.30.13 source from the combined lock. The fixture
verified all 372 original GUI registry archives and reproduced the combined
x64 feature lists for winit and the three binding packages. The private
Cargo override replaces the target library with the LLVM rebuild. The
remaining lock entries stay equal. Cross-compiling winit in both builds
produced 14 calls to `GetCurrentThreadId` and two to `CreateWindowExW` in
each target's optimized LLVM IR. [Winit fixture](../../tools/rust-qa/windows-imports/winit.rs)
· [Cargo and MSVC relink checks](../../tools/rust-qa/windows-imports/winit_relink.py).

The 2026-11-22 offline upstream-source run is recorded in
`artifacts/rust/windows-imports/runs/x64-xexvnzss/result.json`, SHA-256
`83ba1b82d46a0f2c314cd588c585d56dca310a18893a3775fd17c68f92aff6be`.
The ARM64 replay from the filtered tar retained its previous LLVM archive and
probe PE hashes, and verified all 152 registry archives of the transport.
Its receipt is `arm64-bdtc56rs/result.json`, SHA-256
`6aba0e9b820396059c34ac79079773f30687b8cc24a183b2a885a023724ada89`.
The five input tests passed, including rejection of the other COFF machine
and a link response resolving the same filename in the wrong directory.

Native x64 execution and byte-for-byte regeneration with Microsoft's
librarian remain open. The native command builds the published and rebuilt
winit consumers independently. It requires a full-path linker response, a
map entry for an executed binding, matching PE imports, successful creation
of the event loop on the primary thread and winit's expected rejection on
a worker thread. A separate native observer checks all three linked DLLs
against the system APIs on two live threads and reads four virtual desktop
metrics. Each observer confirms native AMD64 using `IsWow64Process2`.

## Repeat the checks

Use the pinned toolchain under `artifacts/rust/toolchain`. The first command
can acquire the public source tarball, target std archive and three registry
archives. Later runs can consume the original acquisition or the verified
filtered tar offline. The `--transport` option needs the isolated cache
populated by the existing native realtime assessment. All private working
copies, build products and original downloads stay under ignored
`artifacts/rust/windows-imports`. The hosted upload selects the run JSON.

```sh
python3 tools/rust-qa/windows-imports/run.py --acquire
python3 tools/rust-qa/windows-imports/run.py --source-tar /path/to/corresponding-source.tar --transport
python3 -m unittest discover -s tools/rust-qa/windows-imports -p test_inputs.py
```

For x64, prepare the GUI's private registry cache first. The first command
below uses the cached source tar and official cross-target standard library
on Linux. Run the second command on the native Windows x64 candidate host
after the GUI assessment has fetched its locked sources.

```sh
python3 -B tools/rust-qa/windows-imports/run.py --target x86_64-pc-windows-msvc --source-tar /path/to/corresponding-source.tar
python -B tools/rust-qa/windows-imports/run.py --target x86_64-pc-windows-msvc --acquire --native
```

On native Windows ARM64, run `python tools/rust-qa/windows-imports/run.py --acquire --native --transport`
after the passing realtime assessment. The driver locates Visual Studio
with `vswhere`, validates the active ARM64 `cl.exe` and `lib.exe` paths
under that installation, and records their file hashes. It can activate the
ARM64 Visual Studio environment if needed. Microsoft's original generator
rebuilds the umbrella archive. A native Rust observer checks
`IsWow64Process2`, loads each linked test DLL and compares 64 feature IDs
and ring's exact ID against the actual system API. The full transport uses
the LLVM reconstruction in a fresh offline build. The checks require the
absolute input path in MSVC's link response, the original PE imports and all
15 loopback cases. Each result distinguishes original library bytes, linked
image bytes and native execution. [Driver](../../tools/rust-qa/windows-imports/run.py),
[isolated full transport relink](../../tools/rust-qa/windows-imports/relink.py)
and [MSVC response file](https://learn.microsoft.com/en-us/cpp/build/reference/link-repro-full-path-rsp?view=msvc-170).

Candidate packaging still needs to select the actual archive, include its
corresponding sources, notices and build recipe in the combined offline
distribution and record the resulting product graph. Raw acquisition caches
are private build inputs.

At `2e7ed89` the Windows ARM64 runner checked all 20,551 signatures and
produced the same LLVM archive twice, SHA-256
`20a536fcdb075d5a2ff93d1977d7a4420503396acba98c712d39ab3928fd1830`.
The separate reconstruction step did not inherit the previous step's Visual
Studio environment. It stopped before the MSVC build and transport relink.
The retry initializes and verifies the compiler and librarian in each step.
The independent command-shell fallback uses a local batch file for the quoted
installation path. [Native ARM64 run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828363871).

At `5895c0b`, native ARM64 MSVC 14.52.37025 regenerated the published
5,210,890-byte library byte-for-byte. Its generator and the independent LLVM
build covered 20,551 signatures from 371 DLLs. The published, regenerated
MSVC and rebuilt LLVM libraries produced the same PE test image, SHA-256
`7403c4ab6abc7c3436ece021a365e7ebf0a94663c0791d21b7dc4bfccfc829d3`.
All three images ran as native ARM64, returned the same answers for 64
processor features and confirmed ring's feature ID 30. MSVC's link response
identified the isolated LLVM library in the separate full transport build.
Its import table retained 145 entries, and all 15 native loopback cases
passed. The result SHA-256 was
`6c5363923a64b1683c12cb89a2855224fcb2512626b2281913fe87ef32afb1e5`.
[Native reconstruction and relink](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264/job/136618468330).
