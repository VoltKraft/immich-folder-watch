# Windows ARM64 import library reconstruction

The realtime assessment uses `ring 0.17.14` to query the ARMv8 crypto
instruction flag through `kernel32!IsProcessorFeaturePresent`. Its Windows
ARM64 graph selects `windows-sys 0.52.0`, `windows-targets 0.52.6` and
`windows_aarch64_msvc 0.52.6`. The Windows x64 transport uses ring's
separately reviewed x64 CPU detection and assembly. [Transport inputs](rw02-realtime-transport.md#dependency-and-native-input-review)
and [Microsoft's API documentation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent).

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

## Reconstructed interface and local link

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
