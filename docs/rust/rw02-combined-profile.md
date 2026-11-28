# RW-02 combined Cargo profile

One development executable resolves the desktop, native service bindings, filesystem, scalar codecs, YAML, SQLite and realtime dependencies together. Cargo 1.100.0 with resolver 3 reproduced its lockfile from an empty directory using only the reviewed sources. The lock SHA-256 is `6bbe711bfc27f7e8389f3073871defda19249d6c7121fd78aaf0337e2235aae7`. The existing source reviews support the isolated AGPL-3.0-only development profile with the notices and exceptions below. The Rust product workspace and the individual feasibility locks have independent release decisions. [Combined manifest](../../tools/rust-qa/combined-profile/Cargo.toml) · [Cargo lockfile](../../tools/rust-qa/combined-profile/Cargo.lock) · [Review digests](../../tools/rust-qa/combined-profile/review.json)

## Resolution and feature unification

The manifest selects the GUI's egui/epaint reconstruction, AccessKit, clipboard, X11/Wayland/Vulkan on Linux and DX12 on Windows. Linux adds the reviewed zbus service and parented portal dependencies. Windows adds the Shell, COM and related Win32 bindings. The shared dependencies select bundled rusqlite with backup, both serde-saphyr codec directions, SHA-256, Tokio, reqwest with an explicit rustls/ring provider, and the existing Tungstenite handshake/frame path. The root directly links the five first-party libraries. The ordinary watch-event probe uses first-party Rust and operating-system interfaces. Its operating-system behavior has its own native evidence. [GUI](rw02-gui-dependencies.md) · [Platform services](rw02-portal-dialog.md) · [Windows services](../../tools/rust-qa/windows-services/Cargo.toml) · [Watch events](rw02-watch-events.md) · [Codec](rw02-legacy.md) · [Storage](rw02-storage-inputs.md) · [YAML](rw02-yaml.md) · [Transport](rw02-realtime-transport.md)

The lock contains 472 registry packages, three private text-engine packages, five repository libraries and the executable. Across the four selected targets Cargo activates 348 registry packages and all three reconstructed inputs. The remaining 124 registry packages supply other target or optional resolutions. All 472 original archives are authenticated on replay. Only the 351 active external inputs enter this native license inventory.

| Cargo target | Normal/build packages including the root | Registry packages | SHA-256 of normal/build feature sets |
| --- | ---: | ---: | --- |
| x86_64-unknown-linux-gnu | 337 | 328 | `e9614ebaff26a85dca6014a94909d2f6354ab015eb3dc22e755662247a88f9ff` |
| aarch64-unknown-linux-gnu | 336 | 327 | `b8bf43f3d188f26867abbdd54e965526fd266820522f94f035b281d21055e1e2` |
| x86_64-pc-windows-msvc | 250 | 241 | `29c99c7d57feaba22a9cf1ae5e378c363fe892b58b60e87120d93e3cc95ecf3a` |
| aarch64-pc-windows-msvc | 249 | 240 | `50fa98571ea1d0719fc73585b7d28c861757355ef6786ff21564cb2c485c91db` |

Cargo resolves each target from the same manifest and lock. For each target the checker replays the GUI, realtime, YAML, storage, performance-worker and applicable platform manifests against those same sources. All four targets reproduce the reviewed GUI and realtime inventories. The GUI digests include the corrected protocol and original notice inventory. The storage/YAML metadata graphs match the previously recorded inputs. Each selected external package and individual feature was active in a constituent graph for that target. Combining components produces four previously separate feature combinations. [Resolver and baseline checks](../../tools/rust-qa/combined-profile/graphs.py) · [Cargo tree semantics](https://doc.rust-lang.org/cargo/commands/cargo-tree.html#feature-unification)

| Targets | Source-reviewed combination |
| --- | --- |
| Linux x64 and ARM64 | futures-util 0.3.34 enables the sink adapter beside the GUI's async/await helpers. syn 3.0.10 enables the immutable syntax visitor beside traversal, folding and the mutable visitor for procedural macros. The crate sources gate these modules separately. |
| Windows x64 and ARM64 | windows 0.62.2 enables Shell, Storage, Remote Desktop and station/desktop modules alongside graphics, input and accessibility. windows-sys 0.61.2 supplies WinSock, WDK and I/O bindings alongside the GUI's clipboard, shell and graphics modules. Each feature selects generated namespace declarations from the same reviewed archive. |

The per-target JSON records each feature group and all contributing baselines. The text trees preserve build edges, proc macros and repeated nodes. Fourteen package names legitimately have multiple selected versions across the four targets, including `syn` 2/3, `windows-sys` 0.52/0.61, `rustix` 0.38/1.1 and three major/minor lines of `getrandom`. Their version-qualified identities and hashes remain separate. The x64 graphs select `core_detect` 1.0.0. Each Windows graph selects its architecture-specific 0.52.6 import library. [Version inventory](../../tools/rust-qa/combined-profile/review.json) · [futures-util source](https://static.crates.io/crates/futures-util/futures-util-0.3.34.crate) · [syn source](https://static.crates.io/crates/syn/syn-3.0.10.crate) · [Windows binding source](https://static.crates.io/crates/windows/windows-0.62.2.crate) · [windows-sys source](https://static.crates.io/crates/windows-sys/windows-sys-0.61.2.crate)

## Source, notices and native inputs

The corrected four-target inventory binds 639 named source notice entries, 19 supplemental notice files, five unmodified fonts, 101 Wayland protocol XMLs, 509 native paths and 16 shader paths. It also records 1,187 distinct original attribution blocks from 1,981 source paths across the union of the target graphs. Sixty-nine active packages include a build script or procedural macro. Its canonical SHA-256 is `689a15afb366727d89ed22233bd6c64b841e5d0a2520ef8cdd10bf1b7d7c6640`. The native runs at `7517e3b` retain the earlier inventory `244bec73e64cb8702e4c8a409c1d5f985160f173b11ea601a17c0ae027a456ca`, which omitted the core protocol, several original notice files and file-local attributions. A file count includes source examples and fixtures. Actual build-script link directives and executable imports have separate receipts. [Source preparation](../../tools/rust-qa/combined-profile/sources.py) · [License inventory](../../tools/rust-qa/combined-profile/licenses.py) · [Compiler unit verification](../../tools/rust-qa/combined-profile/units.py)

- The private directory source keeps both the upstream archive checksum and the exact compiler-tree digest. The shared YAML filter removes the promotional CLion SVG and its README promotion from base64 0.23.1 across the combined graph, including reqwest's dependency. All 30 YAML trees match their approved post-filter digests. The original private archive cache contains the excluded asset. The raw caches and the 124 inactive packages lack distribution approval under this profile. [Filtered corresponding source](rw02-yaml.md#reviewed-inputs-and-corresponding-sources)
- Retain the release notices omitted by the egui and AccessKit packages, the Chromium, tiny-skia, Khronos, Weston, HarfRust and Unicode source/data attributions, and the four nested granit-parser notices. The GUI's three reconstructed sources, generated Unicode data and all five Noto font binaries retain their individual source and license pins. The fonts require their original OFL and copyright notices. [GUI and font obligations](rw02-gui-dependencies.md) · [Text reconstruction](../../rust/audit/gui-text-inputs.json) · [Font bundling terms](https://openfontlicense.org/ofl-faq/)
- SQLite uses the reviewed 3.54.1 amalgamation and the MIT-licensed Rust bindings. The runner supplies the reviewed load-extension omission flags and checks both SQLite compile options at runtime. The ring crypto sources and assembly carry the ISC/Apache and embedded file-specific attributions. Windows x64's 12 selected preassembled ring objects have a separate reconstruction. [SQLite build inputs](rw02-storage-inputs.md#native-sqlite-and-build-boundaries) · [ring reconstruction](rw02-realtime-transport.md#dependency-and-native-input-review)
- The source archive at Microsoft revision `db06b51c2ebb743efb544d40e3064efa49f28d38` contains the same 0.52.6 import library bytes as the two native registry packages. SHA-256 is `24d8cbc445955b0d48041948a3c71ce2cddb948c089b25ec7106fadd9f3efde0` on x64 and `ca85dd7757f338ba00d0bc19229f176ee426a707425ee4fcf205ec491a95bd5a` on ARM64. Both copies of the Microsoft MIT and Apache notices also match. Native MSVC regenerated the published archive on each architecture. The LLVM alternative ran with the ARM64 transport and, in two x64 trials, with the real winit event loop. Full product packaging still owns the selected import variant, source bundle and installed image. [Pinned Microsoft source tree](https://github.com/microsoft/windows-rs/tree/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/targets) · [Original comparison](../../tools/rust-qa/combined-profile/check_imports.py) · [Native rebuild and relink](rw02-windows-imports.md)
- Eighteen selected Wayland XML documents declare LGPL-2.1-or-later. The assessment preserves their individual authors, source bytes and license texts. Its Linux relink control changes the compiled KWin blur-manager interface version from 1 to 2 in a private copy of the real XML. Cargo selects it via a path patch and verifies that every other lock entry and dependency edge is identical. The running executable reports the modified generated interface version after relinking. Product delivery still needs corresponding application/library sources, notices and an independently usable relink recipe for the actual installed binary. [Relink control](../../tools/rust-qa/combined-profile/relink.py) · [Wayland source review](rw02-gui-dependencies.md#locked-assessment-and-additional-rights-holders) · [Cargo path patches](https://doc.rust-lang.org/cargo/reference/overriding-dependencies.html) · [LGPL text](https://spdx.org/licenses/LGPL-2.1-or-later.html)

The observed ELF has four direct dynamic dependencies on this Fedora x64 host, namely `libgcc_s.so.1`, `libm.so.6`, `libc.so.6` and `ld-linux-x86-64.so.2`. The compiler also reports static SQLite and ring and an X11 loader link directive. A desktop session can load X11, Wayland, xkbcommon, Vulkan loaders/ICDs and accessibility services at runtime. Windows can load DXGI, D3D12 and shader/compiler DLLs. The installed software package must identify its actual loaded components and the terms of any additional redistributed DXC binaries. The desktop graphics and performance fixtures own adapter selection, rendering and timing. [Graphics evidence](rw02-graphics.md) · [Native input boundaries](rw02-gui-dependencies.md#native-interfaces-and-outstanding-checks)

The scalar probe accepts a supplied .NET invariant-casing map. This executable exercises the legacy timestamp codec. A shipping casing table still needs a selected source and compatibility policy for the observed differences between .NET/ICU hosts. The combined dependency profile brings in ICU data for URL handling and a separately reconstructed Unicode 16 bidirectional table for text layout. Their notices and purposes are independent. [Casing evidence](rw02-legacy.md#casing-source-and-license-audit) · [Realtime Unicode inputs](rw02-realtime-transport.md#dependency-and-native-input-review) · [Text source pins](../../rust/audit/gui-text-inputs.json)

## Native qualification

The single-process smoke opens one synthetic file through the existing directory handle and revalidates its file identity. It round-trips a filename and 100-nanosecond timestamp through YAML, the legacy codec, SHA-256 and in-memory SQLite. It decodes an in-memory RFC 6455 frame and the Engine.IO ping, builds an HTTPS request with a private empty trust store, processes desktop lifecycle/log output and tessellates a label with the reviewed fonts. On Linux it reads actual Wayland interface descriptors and parses the portal bus name. It calls the linked eframe native entry inside a private namespace with all display endpoints absent and requires the specific winit event-loop refusal. An independent ELF symbol readback checks the native entry and the Vulkan backend. On Windows the code constructs the selected native Shell structure. The runner compares each compiler-reported package and feature group, requires successful linking, records static SQLite/ring directives and inspects the linked executable. [Probe](../../tools/rust-qa/combined-profile/src/main.rs) · [Native observer](../../tools/rust-qa/combined-profile/native.py)

Linux x64 builds run with a private home and network, mount, process and IPC namespaces. The process has a read-only synthetic root. Existing desktop, portal, transport and migration fixtures retain responsibility for window input, a real grant, certificate validation against peers and shipping-format parity. Before release, inspect the four installed artifact graphs, corresponding sources and notices, runtime-loaded GPU/window-system components and actual shader compiler selection. The platform's portal/FUSE, IME, accessibility services and graphics drivers remain deployment-specific. The normal Windows path uses the runner's native Visual Studio environment. [Desktop evidence](rw02-native-gui.md) · [Portal deployment constraint](rw02-portal-noble.md) · [Acceptance record](acceptance.md)

On 2026-11-21 the native Fedora x64 compiler produced 402 build-host/target units for the 337 package identities. Release Clippy passed with warnings denied. The normal executable SHA-256 was `251fa576febb4d5e7cdfa3f7536770a1d14c18242a377eb9d1fc6bc79153719d`. After the private LGPL source change it was `e60ce41f42a4085ba4d4d9de60104a3440861a9648b159f823db013926b64bbf`. Both retained one native eframe entry and 541 Vulkan backend symbols and both returned the expected private winit error. Only the observed blur-manager version changed from 1 to 2 in the application output. The ordinary source bytes, matching LGPL license and all other lock edges stayed intact. The raw local records are in `artifacts/rust/combined-profile/first/native-renderer/{native,relink}.json`. This first Fedora run examined the other three target resolvers. The later hosted native observations appear below.

An initial pointer-retention control passed the Cargo and text checks while the ELF contained neither the eframe entry nor its Vulkan backend. The actual UI function pointer, headless entry call and independent symbol witness address this observed gap. An initial targeted Cargo update also changed unrelated dependency edges during the LGPL control. The lock verifier rejected it before linking. Regenerating the complete private control lock offline preserved every other dependency edge. [Native checks](../../tools/rust-qa/combined-profile/native.py) · [Lock and missing-unit controls](../../tools/rust-qa/combined-profile/test_profile.py)

At `a66e045` all four native hosts reproduced the same Cargo lock from an
empty directory, compiled the combined profile and ran its smoke test. Both
Ubuntu hosts also rebuilt the modified Wayland dependency offline. The blur
interface version changed from 1 to 2 and every other smoke value matched.
All 21 indexed outputs on each Ubuntu host and all 16 on each Windows host
matched their hashes. Each host bound 68 source files to the tested revision,
including seven files checked out with CRLF on Windows. The Windows smoke
retained the eframe function pointer and checked the Shell interface layout.
The interactive desktop observations use separate executables.

| Host | Native packages / compiler units | Archived result SHA-256 |
| --- | ---: | --- |
| Ubuntu x64 | 337 / 402 | `127623e7888d25bc9c7e663c3b83ff01b74de131b5069aee7482deb3f7766eaf` |
| Ubuntu ARM64 | 336 / 401 | `0fdd486ee263e298d2c6e8726b1e8a3ea9812f53dc68e78c490e8dfa7ee789e3` |
| Windows x64 | 250 / 281 | `7967cdf54de0caa86b46017a96e94c39deb25135f0002029c7e173cb784fae94` |
| Windows ARM64 | 249 / 280 | `8cdc361ceb3fd0f1f4616a7fa34cf90b87d6936dc5af8e04e53ca4dad3ef9bc9` |

[Native assessment and ZIPs](rw02-native-gui.md#native-follow-up-at-a66e045).

The GUI Shell feature at `76650d4` was already part of the combined
Windows profile. A Fedora x64 offline replay reproduced the four combined
graphs, the original empty-root lock and both Microsoft import-library
comparisons. The native smoke and Clippy passed with 337 compiled packages
and 402 units. After the LGPL binding was edited and relinked, the executable
reported version 2 of `org_kde_kwin_blur_manager`. The run began at
`706cb94` with the pending profile changes. All 74 recorded source files
matched the committed Git bytes at `76650d4` and the hashes of all 21
outputs were verified. The receipt in
`artifacts/rust/combined-profile/runs/integrated-tray-features-02/result.json`
has SHA-256 `506138998efe6e24b9b582e9b6a1a30d5a911177e0bf08311bb319046690e8ba`.
[Windows GUI binding review](rw02-gui-dependencies.md#windows-notification-area-bindings).

The Fedora x64 build with the [Linux file timestamp conversion](rw02-legacy.md#linux-file-modification-times)
read the same open file in the original and relinked executables.
Both matched its modification time of 1,795,219,200,000,000,199 Unix
nanoseconds to the SQL value ending in `.0000001+00:00`. All 74 recorded
source hashes matched `c51491b`. The local result at
`artifacts/rust/combined-profile/runs/mtime-fingerprint-02/result.json`
has SHA-256 `1a82fbdc3a1076fa5c76d7052f4ad9ce6b8561602ec66a6630c105f8f711b0a3`.

Both native Ubuntu hosts at `e2f161b` reported
`2026-11-21T00:00:00.0000001+00:00` for the synthetic file in the
original and relinked executables. Detached replay checked 74 first-party
inputs against Git and all 21 indexed outputs per host. The x64 compiler
reported 402 units and ARM64 reported 401. Both relinks recovered the
same SQLite value after the Wayland interface changed from version 1 to 2.
[x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15001344710) · [ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15001819213).

### Offline reconstruction with the legacy upload comparison

At `6cd7757` the Fedora x64 builder reproduced the reviewed lock and all
four target graphs from the cached original inputs. The native compiler
reported 337 packages and 402 compilation units. The five upload results
matched the earlier Fedora run byte for byte. The Wayland relink changed
the observed blur interface from version 1 to 2. Detached verification
matched all 78 source inputs to the Git revision and all 27 output hashes
to their files. The SPDX readback verified 446 packages and 1,063
relationships in this native development build.

The original report at
`artifacts/rust/combined-profile/runs/held-upload-6cd7757-01/result.json`
has SHA-256 `955437b27ad61587329d4f7d073a0cc72efc2105cef820543c9c550d26d37f05`.
[Five shipping multipart cases](rw02-legacy.md#legacy-upload-identities-from-the-held-file) ·
[Development SBOM scope](rw02-combined-sbom.md).

At the same revision the two native Ubuntu jobs produced the same five
upload results as Fedora, including both streamed bodies and the original
file's identifiers. Each of the ten archived process logs matched its
per-case digest. The input corpus, original and replacement file bytes,
78 source inputs and 27 indexed outputs were checked separately on each
architecture. The x64 compiler reported 337 packages and 402 units. The
ARM64 compiler reported 336 packages and 401 units. Each modified Wayland
binding reported interface version 2 after the original reported version 1.
The three Linux upload reports share SHA-256
`9566c011122e9a568338013265ab4aeaa02cc0be2a378f64b9528407d54ac054`.
[Ubuntu x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15213091920) ·
[Ubuntu ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15213152399).

The native Windows ARM64 build at the same revision reported 249 packages
and 280 compiler units. All five synthetic filenames were replaced while
the original upload file was open. Each retry rewound to position zero
and returned the original device ID and bytes, including the 70,679-byte
case. Independent replay checked 78 source inputs and 22 output hashes.
All 23 files in the dedicated archive matched their copies in the desktop
archive. Its native build receipt has SHA-256
`f7b2df12b63764d3cc8d2e9e76aae68847986c8febd2fea6e53958b2bcd74f8c`.
[Windows ARM64 compiler and upload receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15218516011) ·
[Windows ARM64 original files](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15219815690).

The Windows x64 build reported 250 packages and 281 compiler units.
Independent replay verified all 78 source inputs, 22 indexed outputs and
the original and replacement files for all five cases. After each pathname
was replaced, the device asset ID matched the original file. The first
read and the retry from offset zero both returned its bytes. The x64 and ARM64
Windows upload reports share SHA-256
`28caaf8ebb730fb5c08559fd295171a64797126df1ae011cd8376fb004c9d1e1`.
This completes the five held-file cases on native Linux and Windows, each
on x64 and ARM64. Separate Windows desktop checks in the same run failed.
[Windows x64 compiler and upload receipt](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15220466574) ·
[Windows x64 original files](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15220771583) ·
[Native C# reference tests](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242375).

## HTTP CONNECT challenge metadata

The combined manifest and the realtime assessment both select the same
private Cargo path for `hyper-util` 0.1.21. The offline preparation checks
the original crates.io archive, reconstructs the two changed Rust files
and verifies every file before Cargo resolves the profile. The Linux
build and relink namespaces mount this tree read-only. The change makes
the proxy's `Proxy-Authenticate` fields on a 407 CONNECT response
available to the transport client.
[Maintained patch](../../tools/rust-qa/realtime/hyper-util-connect.patch) ·
[Reconstruction and checksum pins](../../tools/rust-qa/realtime/hyper_util_source.py).

| Combined input | SHA-256 |
| --- | --- |
| Upstream archive, git revision `23a868965964c1d6bb1b94f30ba4c420a4bebe7c` | `ddc03d96684f9226b8a787cdb71488417b53ab5ea8fdb1dac946cb9431cc8bff` |
| Maintained patch | `761b075d5fbf1d5c98c478bcc6f443898a1171973d4dcc557380ce45d84f9cd0` |
| Reconstructed 62-file tree | `acd12c39160b6bfe7d7872fcbb6b7974ae880b23e01936576934c23127f4d4a4` |
| Original MIT license | `9e0a97848ea543aef745c98e84fde696a9a3e0735538f6daefdd3cb1942effc1` |
| Combined Cargo.lock, reproduced offline from an empty directory | `88c614991fbfbdc84d461dfd44d5d359f7272e2064d5fd758df21be93a4b14d2` |

The source review compared all four target graphs and the 351 active
external package records to the preceding source profile. Only
`hyper-util` changed compiler source. The 471 registry identities in
the lock now accompany the reconstructed path. All dependency edges,
normal/build feature groups and selected license texts matched the
preceding profile. In its SPDX source record, the upstream archive and
compiled tree have separate hashes. The notice bundle reads the MIT
license from the archive and its two source attribution excerpts from
the reviewed compiler tree.
The second full offline replay retained the four target reports and the
aggregate inventory in
`artifacts/rust/combined-profile/runs/hyper-connect-offline-01/`.
Its `result.json` has SHA-256
`4598651b581275d3db4b7309cc80ac690434ca28f79ba1ccdba29e57e09d0055`.
The historical Linux x64 input at `0a2b5ca` also reproduced its original
1,799-member notice ZIP byte-for-byte, SHA-256
`a72d43330f20778444c50f7f5333f3be13635da3a50423164dbbf8e7f23993fa`.
[Four-target profile](../../tools/rust-qa/combined-profile/review.json) ·
[Original native notice archive](rw02-combined-notices.md#native-notices-at-0a2b5ca).

The notice cache prepares the path dependency alongside the 471 registry
archives. In an empty project source directory, it reconstructed
`hyper-util` offline from a secondary acquisition cache. A second pass
verified the retained original and compiler tree after removal of that
secondary archive. The cold-cache receipt is
`artifacts/rust/combined-profile/runs/hyper-connect-cold-cache-01/result.json`,
SHA-256 `1875ca302a8da9059383a6ab22308806345015ecebd08f6eb05fa38ce7cc5679`.
[Notice source preparation](../../tools/rust-qa/native-notice-input.py).

### Native Linux x64 results at c0523e1

The Fedora x64 compiler linked the reconstructed `hyper-util` from its
read-only mount with `client,client-legacy,client-proxy,default,http1,tokio`.
Cargo recorded 337 packages and 402 compiler units. Clippy, the headless
GUI and storage checks, and the five held-file upload cases passed.
The offline Wayland relink changed the observed blur-manager version
from 1 to 2. The ordinary executable had SHA-256
`5edb138330e95f9408642223d9be80c36c55db2082bbd551d9cf95ef4e63eb2f`.
The relinked executable had SHA-256
`0271ed1b43ba143a82cda600a3511c88a6075308de9b0f3d3aae799a41bba1cb`.

The first compiler process at `51b08d4` stopped before linking. The
completed run used a detached checkout of `c0523e1` and a private copy
of the prior Cargo cache. All 80 witnessed source files matched between
the two revisions. The finished run records its hashes in
`artifacts/rust/combined-profile/runs/hyper-connect-native-c0523e1/result.json`,
SHA-256 `e8af75006fef78c4bbeba034ad60b1d872789726d229dc848d181191c0d0b76a`.

The local input ZIP generated a 1,799-member notice archive. Its SPDX
document contains 446 packages and 1,063 relationships and passed the
pinned SPDX 2.3.1 schema. Independent readback matched the original MIT
license, both changed source hashes and the compiled package. The ZIPs,
SPDX document and their hashes are under
`artifacts/rust/combined-profile/verification/hyper-connect-c0523e1/`.
The verification receipt has SHA-256
`19f26d9502f3b3a154f0693ff7dce9d6edef3095a08913cdf38f54c066581b24`.
[Source-bound SPDX checks](rw02-combined-sbom.md) · [Notice checks](rw02-combined-notices.md).

## Linux HTTP Digest source profile

The Linux transport at `ed9268e` uses RustCrypto `md-5` 0.11.0 when an
HTTP proxy offers the corresponding Digest algorithm. Its other direct
inputs, `sha2` 0.11.1 and `percent-encoding` 2.3.2, were already in the
combined profile. The combined root now directly selects `md-5` and
`percent-encoding` on Linux with their default features disabled.
The existing cross-platform `sha2` selection supplies the Linux input.
[Shipping client and Rust comparison](rw02-linux-tls-basic-proxy.md#authority-bound-digest-on-fedora-x64).

The crate archive has SHA-256
`69b6441f590336821bb897fb28fc622898ccceb1d6cea3fde5ea86b090c4de98`.
Its 18 unchanged files yield compiler tree SHA-256
`fe2a0b687a9f61ecf7d80eccd1632b9ad24b3092ea61c5effbb36b5c82c05242`.
At upstream commit `b5051e5a5e7dc86a6c27c1ec7a390744ebcfb97a`,
the selector, the portable Rust compression module and both original
license files matched the archive byte-for-byte. The profile selects
MIT and retains both `LICENSE-MIT` and `LICENSE-APACHE`. For Linux x64
and ARM64 the reviewed selector chooses `src/compress/soft.rs`. The
LoongArch implementation has a separate target condition. The SPDX
generator and notice manifest identify the selected source files by
upstream revision, path and SHA-256.
[RustCrypto selector](https://github.com/RustCrypto/hashes/blob/b5051e5a5e7dc86a6c27c1ec7a390744ebcfb97a/md5/src/compress.rs) ·
[Portable Rust source](https://github.com/RustCrypto/hashes/blob/b5051e5a5e7dc86a6c27c1ec7a390744ebcfb97a/md5/src/compress/soft.rs).

The offline comparison added four edges on each Linux target. The root
selects `md-5` and `percent-encoding` directly, and `md-5` depends on
`cfg-if` and `digest`. No features were enabled on `md-5`. All earlier
package feature sets matched. The two Windows target trees remained
byte-identical and contain no `md-5` package. These source results apply
to the new lock, SHA-256
`ff44785e595316c7182d7a020b5904f632c67fa0ac0e8d5d239c684794c00793`.
The target comparison and original-source checks are in
`artifacts/rust/combined-profile/verification/digest-upstream-ed9268e/`.
The comparison receipt `comparison.json` has SHA-256
`d83031ef05be6a82f9890b561ddbdc8cf57d0ae8f166d614f49319f85d49b121`.
The second complete source replay reproduced the empty lock and all four
target graphs in `artifacts/rust/combined-profile/runs/digest-offline-ed9268e-02/`.
Its `result.json` has SHA-256
`053f2793ee3fcb9cf3565ac01561fd1c21fb53dba82c3853cc02c78be9da426f`.

For a new Windows x64 build, transfer the compiler ZIP and its published
digest to the local VM. The target-specific SPDX test reads the compiled
units and verifies that the Linux-only `md-5` package is absent even
though the four-target source inventory includes it. The earlier Server
2025 receipt belongs to the `36190f1` lock and executable.
[Windows x64 compiler and guest procedure](../../tools/rust-qa/windows-local/README.md#combined-profile-on-server-2025-at-36190f1).

### Native Linux x64 Digest inventory at 2f63c15

The native Fedora x64 build at `2f63c15` produced 403 compiler units
from 338 Cargo packages. The compiler reported one `md-5` library with
an empty feature set. Its original dependency file lists the selector
and `src/compress/soft.rs`. The release executable had SHA-256
`2476487e3c5e6451d74091bf036d491ee32a9a79c0c366ddc9b47b0835a0f04f`.
Clippy, the headless smoke test and all five held-file upload cases
passed. Rebuilding with the changed Wayland XML moved the linked
interface from version 1 to version 2. The native receipt is
`artifacts/rust/combined-profile/runs/digest-native-2f63c15/result.json`,
SHA-256 `064a4b07906c8c7bbc89f81ca8d6d53c99da9ccefe54cd72a967bfc74f6f3f24`.

The SPDX document passed the official 2.3.1 schema with 447 packages
and 1,067 relationships. The native notice archive contained 1,802
members, including both original license files for `md-5`. Their bytes
matched the upstream source archive. The check also matched the
compression-source paths and hashes across the SPDX and notice records.
The compiler dependency file, ordinary executable, SPDX document and
notice ZIP are indexed by
`artifacts/rust/combined-profile/verification/digest-2f63c15/verification.json`,
SHA-256 `ccc46ca7d4698c60fcb2b53cf6e0f81ef7bceb4809b7706591d498632ce27a1c`.

### Native Ubuntu ARM64 Digest inventory at 378b36a

Two fresh offline builds on Ubuntu 24.04 ARM64 compiled 402 units from
337 packages each. Their compiler inventories identify `md-5` 0.11.0
with no enabled features on `aarch64-unknown-linux-gnu`. Both ordinary
executables had SHA-256
`c14a806900c1b0ee4fc38cbf40207b66ef49e8001110a274170de571f9a70945`.
Both modified Wayland executables had SHA-256
`26c9105cb9a761ca4e04b2450748f3d10ca6e14a074a45ef6115323057f1c68f`
and reported interface version 2 after the original version 1. Clippy
passed twice. Each native headless smoke test tessellated one primitive
and observed winit declining to open a missing display. Each of the five
held-file upload cases reproduced the Fedora x64 corpus output byte-for-byte.
[Native run and original artifacts](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46107679867).

The detached replay verified both original compiler ZIPs against their
Actions digests, matched all 82 first-party source hashes in each receipt
to Git blobs at `378b36ac78bb85e3d8be7f9e9d96679702b0dcca` and checked
all 27 referenced outputs in each ZIP. The first and second ZIP digests
were `babe45130a057195b4abfda7ab80014b2518c8fc0df575d035dca7a1ec83c3d7`
and `b57201467df167c3fcb3c63674c440e56918724b4d587758e8605e033e03ad7b`.
The first ZIP reproduced the hosted SPDX 2.3.1 document byte-for-byte
with 446 packages and 1,067 relationships. Its original notices also
reproduced byte-for-byte, including both upstream licenses for `md-5`
among the 1,799 archive members. The four original Actions digests and
independent checks are recorded in
`artifacts/rust/combined-profile/verification/ubuntu-arm64-378b36a/verified.json`.

The focused Ubuntu 24.04 ARM64 job installs the pinned native compiler,
reconstructs the reviewed GUI inputs and retains the original crate
archives. Two fresh offline builds each run Clippy, exercise the five
upload cases, and relink the modified Wayland binding. The job compares
their source inventories, target profiles, observed upload data and
both smoke results. It retains both native compiler receipt ZIPs.
The SPDX and original notice files are regenerated from the first ZIP
using its Actions digest and compared byte-for-byte. The native SPDX
validator also checks the pinned official 2.3.1 JSON schema.
[Focused Ubuntu ARM64 workflow](../../.github/workflows/rust-linux-arm64-combined.yaml).

## GUI startup language in the combined source audit

The ordinary Linux GUI at `c361c69` loads the saved language through the
reviewed YAML library. The combined audit reconstructed its 385 registry
inputs inside the 473 original-source records for the full candidate.
The verified GUI subset has SHA-256
`1fde2469c1e00f08882bb863eca1110eb1c45fe78fe55e4b7767fcd3db0388e3`.
The full audit checks the YAML library's source tree and library entry
selected by Cargo. It also reconstructs the filtered compiler files for
`base64 0.23.1` from the original archive.
[Four GUI source reports](../../tools/rust-qa/gui/startup/README.md#current-yaml-library-at-bb3afd5)

| Target | GUI packages | Combined packages | Combined registry packages |
| --- | ---: | ---: | ---: |
| Linux x64 | 251 | 338 | 328 |
| Linux ARM64 | 250 | 337 | 327 |
| Windows x64 | 135 | 250 | 240 |
| Windows ARM64 | 135 | 249 | 239 |

Fedora x64 resolved all four Cargo targets. Fifteen existing inventory
entries gained the GUI as a consuming component. Comparing all other fields
with the previous inventory at `2f63c15` reproduced every license, notice,
font, shader and compiler-source digest. The four combined feature maps,
typed trees and original source inventories also reproduced exactly.
The updated inventory has canonical SHA-256
`28434e461302a3c88890e1e0e29763566e5da7a0003661932bcf000e6933c302`.
The [combined review](../../tools/rust-qa/combined-profile/review.json) has
file SHA-256 `fe9e9fb94be8b777c4a5353a0344c5e9b9316caa148d5269bc28478dfb3d2939`.

## Reproduction

The native command also runs the [five held-file upload cases](rw02-legacy.md#legacy-upload-identities-from-the-held-file).
The native receipt indexes `legacy-upload.json`, which identifies the corpus,
the two streamed bodies, the directory-entry result and the retry position
for each case.

Run from the repository root after installing the pinned native toolchain and preparing the existing GUI sources and fonts. The source runner consumes the private GUI, storage, realtime and YAML acquisition caches. Its default path is offline. `--fetch` can acquire missing original archives from crates.io and verifies their existing SHA-256 pins before use. All Cargo resolution, builds and relinks operate offline. The ordinary native Linux path needs bubblewrap, the C toolchain and binutils. Windows requires the matching Visual Studio environment, `dumpbin` and the reviewed ring build tools. Windows ARM64 uses its disposable hosted runner. New Windows x64 runtime checks belong on the local disposable VM. [Toolchain contract](../../rust/toolchain-inputs.json) · [GUI preparation](../../tools/rust-qa/build-gui-probe.py) · [Native VS setup](../../tools/rust-qa/enter-windows-build.ps1)

```sh
python3 -B -m unittest discover -s tools/rust-qa/combined-profile -p test_profile.py
python3 -B tools/rust-qa/combined-profile/run.py
python3 -B tools/rust-qa/combined-profile/run.py --native x86_64-unknown-linux-gnu --relink
```

Substitute `aarch64-unknown-linux-gnu` on native ARM64 Linux. On the Windows ARM64 runner, enter the appropriate VS environment and pass `--native aarch64-pc-windows-msvc`. The historical x64 runner command includes execution. A new x64 run requires a compiler archive and local guest replay. Add `--check-imports` where the source-bound Microsoft tar from the Windows import assessment is available. Each command accepts a fresh `--output artifacts/rust/combined-profile/runs/NAME`. Upload only the receipt directory. The temporary Cargo home, original archive containing the excluded promotional logo and build trees stay outside it. [Runner](../../tools/rust-qa/combined-profile/run.py)
