# RW-02 native GUI assessment

On 2026-11-20 the Linux x64 assessment started without allocating a native
window, accepted activation on a private session bus and reopened after a native
close. The isolated test executable uses the existing `desktop-lifecycle`
policy and the [reviewed GUI profile](rw02-gui-dependencies.md). Its separate
[Cargo workspace](../../tools/rust-qa/gui/Cargo.toml) and generated lockfile
belong to the development fixture. All 374 third-party lock records, checksums
and dependency edges match the assessed dependency graph. The fixture adds
direct Linux references to the already selected futures-lite 2.6.1 and zbus
5.19.0 with its asynchronous I/O features.

The first hosted Ubuntu builds at `167a03d` authenticated the locked GUI
inputs and reached the isolated build launcher. Both architectures received
`RTM_NEWADDR: Operation not permitted` during loopback setup. The hosted
fixture now checks the caller UID and private namespace capability before
building. It can provision a temporary, root-owned test launcher with an
AppArmor user-namespace grant specific to that executable on the disposable
VM. [Hosted run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44816389612).

At `06298d9` the Ubuntu x64 and ARM64 fixtures successfully built the native
GUI and passed all four lifecycle scenarios independently under both X11 and
Wayland. The two executables had SHA-256
`c9f365cf40035653bd0e0f409aace88c8fea882e4f46306fbced9b71247db9fd`
and `54f1f14022792793f1e85b2bdbc5b051dfd41b9cd4cb0c8c167f20e268dd5a92`
respectively. Their Actions ZIPs matched `854b44df94f8d891b152562092839eeb272bd539114504c50f4f296e4bdbcd69`
and `ee549449e778561144fb94741953379eefb82c26cf46793d7576167aa1564366`.
In the following input scenario the private AT-SPI launcher reported a dconf
write failure. The observer saw only the desktop root on both backends.
The revised fixture gives the launcher an in-memory settings backend, reads
back its enabled state and identifies the tested application by its native
process ID. This passed the complete keyboard, masking and clipboard checks
on local X11 and Wayland. Hosted input results remain pending.
[Hosted logs and retained per-backend results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44818255659).

At `4961746`, both Ubuntu architectures also passed AT-SPI on both X11
and Wayland. All four independent reports recorded focus passing through
Dateiname, Kennwort and English, three protected bullets and the Unicode
clipboard round trip. The x64 and ARM64 archives matched SHA-256
`5c805eca86d2a14317477a370c8450c7a8c36ff8219e97d41d337407e8035b0d`
and `213838cd18cea87fbf6cecfcb4cd48b977aa4ceb72e50b19c88573b38c096feb`
respectively. A separate YAML archive comparison failed in that run.
[Native Ubuntu results](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44820760903).

## Four native assessment archives

All four archives at `167a03dcb414ab1172713520a77b7517a6046b13` matched
the SHA-256 sums published by Actions. Both Windows machines rendered with
the DX12 Microsoft Basic Render Driver and the system FXC compiler. Each
passed foreground startup, fallback after tray refusal, hidden startup followed
by activation, and quitting before the first show. An independent WinEvent
hook saw zero show events in the last case and the subject recorded zero UI
passes. The three visible cases each closed through WM_CLOSE and reopened.
The tray availability input in these cases came from the test pipe. The
[Windows services fixture](rw02-windows-services.md) exercises the Shell
registration and shortcut APIs independently.

| Native host | GUI result | Actions archive SHA-256 |
| --- | --- | --- |
| Windows Server 2025 x64, build 26100 | Four DX12 lifecycle cases, executable `e5c15f31ade5ae35e91f31dc0688e737be3052a241ae5d40c8387d21a1b6e960` | `6e98768bea3bdf722d5f8d094ada0244c38f57ab47b16d180d62536e59b7737d` |
| Windows 11 ARM64, build 26200 | Four DX12 lifecycle cases, executable `efc7152a5ccd79d8533484709786cc24bcad7e024175d55045e541d9fe2d3840` | `8a00a511eaa349ff6fcbfc40316fd488f61a9c30d476a0c12e1e5df25afb4d0f` |
| Ubuntu x64 | Namespace setup denied before GUI execution | `ef9d072a8f6b65a3ca6b096b4122279bf32a8ec1921ba64ae192f1a3094921e6` |
| Ubuntu ARM64 | Namespace setup denied before GUI execution | `d93e9b44e39aba80c1e90a2083b4aed7d39729cf32b4bba020c1f04cb74a57df` |

On each of these hosts the [SQLite workload](rw02-storage-inputs.md) backed
up both live 24,752-byte WALs. The production C# readers using .NET 10.0.15
and SQLite 3.53.4 passed 40 assertions per host. All 15 independent
[transport scenarios](rw02-realtime-transport.md) passed per host. The
redirect target recorded zero requests and zero credentials. Verification
covered the 253 Windows or 254 Linux storage evidence files and all ten
indexed transport outputs in each archive.

## Native follow-up at 8a8adaa

Both Ubuntu jobs completed every assessment step. The Windows archives retain
the successful and failed phases independently. All four downloads matched
the Actions artifact SHA-256 and passed a full ZIP CRC check. The workflow
used revision `8a8adaa400abc7303335c624ea68abed197158da`.
[Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44941845642).

| Native target | Artifact ID / members | Archive SHA-256 |
| --- | --- | --- |
| Linux x64 | 14722553649 / 667 | `c2bc67a30e06733aa39442fbf46e093695cf7e22ba458a8d08c3cab80e2b02ca` |
| Linux ARM64 | 14722697726 / 667 | `15e6cbb30eb60be6ef1b3171fe447730dfa1f3825d5ac6fbe04157945a33b321` |
| Windows x64 | 14722303102 / 544 | `ce09fae0f455e589a50971c8db1aca44aa3f8a58171c7b149563941991c083f6` |
| Windows ARM64 | 14722289089 / 537 | `595f39ad9e7fe6fe7227db52a5e6097374eec214977c3a919c2ea48007d409be` |

Ubuntu x64 and ARM64 each passed all 11 same-host X11 resource limits, both
Vulkan loss paths, installed Flatpak chooser/grant/revoke on X11 and Wayland,
real Mozc composition and mixed-scale monitor moves. Windows x64 retained
focus and the visible filename across DX12 device replacement and accepted
the next edit. NVDA produced all seven ordered observations on x64 and the
first German filename label on ARM64. On both Windows architectures the
measured Rust visible working set and idle close/reopen p95 exceeded their
limits. Both hosted Windows cross-session trials stopped before the second
writer ran. [Paired Linux results](rw02-performance.md#hosted-linux-results-at-8a8adaa),
[Windows resource comparison](rw02-windows-performance.md),
[screen reader](rw02-windows-reader.md) and [foreground](rw02-windows-desktop.md).

## Native follow-up at 72fff40

Both Ubuntu desktop jobs passed the paired X11 resource check again. Each
host ran three 100,000-file inventories per application. Each Rust summary
met all eleven preset same-host .NET limits. Both jobs' only failure was
the isolated systemd journal, which reported a missing cgroup root.
Each downloaded ZIP matched the Actions digest and passed its CRC check.
[Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423350)
and [local Ubuntu journal reproduction](rw02-platform-logs.md).

| Native target | Artifact ID | Files | ZIP SHA-256 | Visible / hidden RSS | Scan show / close p95 |
| --- | --- | ---: | --- | --- | --- |
| Ubuntu x64 | 14724159073 | 669 | `76b99df2277ef686167d4ed18f2ca91706b2ad6b90eb97bf35cd33607e4a8da0` | 124.262 / 124.262 MiB | 0.99 / 0.40 ms |
| Ubuntu ARM64 | 14724163459 | 669 | `e75ff65c6965dc52d8b2d13234b4941629d7283ed26eb4dac2fdf1066618e137` | 119.184 / 119.203 MiB | 0.90 / 0.36 ms |

Both Windows ZIPs also matched their published SHA-256 sums and passed
all CRCs. Each host met six of nine measured WPF limits. All six scan trials
on each host stopped when the ETW recorder failed to compile against the
Windows SDK. The three exceeded limits below show candidate / maximum.

| Target | Artifact ID and entries | ZIP SHA-256 | Visible memory (MiB) | Idle close p95 (ms) | Idle reopen p95 (ms) |
| --- | --- | --- | ---: | ---: | ---: |
| Windows x64 | 14725165298 (568) | `46a87220532d869cbc3c17a36e21e3f994675c8e6f6595ec3fec41cd9f688e46` | 190.191 / 142.107 | 66.274 / 14.383 | 174.066 / 18.337 |
| Windows ARM64 | 14724566613 (556) | `823392ebb1a04a766e68a971482d389eb8ce259d9d6bef0cbd3b3d124b510009` | 193.258 / 147.506 | 134.435 / 13.236 | 182.427 / 14.999 |

Windows x64 passed the ordinary mixed-direction filename test, keyboard
and replacement DX12 window. Both Windows architectures passed the dedicated
private-desktop input test. Both recorded twelve file records and six
independently formatted Event Log entries, then removed the disposable log.
NVDA announced the seven ordered cues with the three expected password
masks on x64. The filename stayed nonempty after Delete. On ARM64 NVDA
announced the initial filename label among six speech entries. Windows
installed and removed the official Japanese Basic Typing component on
both hosts. Neither host reached a composition trial after provisioning.
[Reader](rw02-windows-reader.md), [Japanese input](rw02-windows-ime.md)
and [pixel replay](rw02-font-coverage.md#pixel-readback-on-windows-and-linux-at-72fff40).

The original ARM64
desktop still failed foreground keyboard input and replacement-window
editing. The original Windows resource comparison and full reader assessment
remain open. The compatibility, native feasibility and PR CI workflows all
passed at this revision. [Native feasibility](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423423)
· [Compatibility oracle](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945423415)
· [PR CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44945427967).

## Native follow-up at d403fee

Two consecutive runs exercised the same retained-window and reader revisions.
Each archive matched the SHA-256 published by Actions and passed its ZIP
integrity check. The second run used `d403feefce23cad5357bf3fb0b49af03f012333e`.
[First run at 45dc03b](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44950398558)
and [repeat at d403fee](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44953046306).

| Target | Repeat archive ID | Entries | SHA-256 |
| --- | ---: | ---: | --- |
| Linux x64 | 14728361571 | 716 | `15150629dd51f2fdc0d5b9792f4f46a6ff0a49ac7c989e00cb7aaf0c12d383e6` |
| Linux ARM64 | 14728287422 | 716 | `eba8a926a0d9e7c161f58c288e2e10854f3b1106a34efad1306cb5c832c15f44` |
| Windows x64 | 14728933001 | 646 | `6e4391e0eebe43292f538115201178642a8395fba1aaece3900733fa20387c17` |
| Windows ARM64 | 14729417789 | 658 | `454cf16b2d6a637d0fcce5b20c9bb082bd3e7fcc68c052e2f951bd46be9455ca` |

On each Ubuntu target the paired X11 comparison again passed all eleven
budgets, including three scans of 100,000 actual files. Orca produced four
ordered control announcements and three password masks on both X11 and
Wayland. Each system journal retained six correctly prioritized records.
Both jobs stopped the separate Noble portal rebuild when Meson's private
Python module could not be imported. A corrected local x64 rebuild repeated
the grant comparisons. [Orca](rw02-ubuntu-reader.md#hosted-ubuntu-x64-and-arm64),
[journal](rw02-platform-logs.md) and [Noble portal](rw02-portal-noble.md).

Both Windows targets met the retained GUI's memory and idle budgets. The real
scan exposed slower close/reopen responses against WPF. The first run completed
the native NVDA clipboard gesture on both targets. ARM64 repeated that pass.
On x64 the second run produced all seven speech cues and submitted Delete
to the owned window. Its selection-range read raised an error before the
clipboard round trip finished. The separate ordinary-field suite passed all
three editing cases on x64. On ARM64 it painted the eight glyphs and selected
the intended character in both Arabic cases, then failed before recording
the resulting filename. The standalone font stress passed on both architectures
in the repeat. [Retained window](rw02-windows-window.md),
[NVDA](rw02-windows-reader.md) and [ordinary editor](rw02-windows-text.md).

Both Windows hosts exposed a single 1024 × 768 console monitor at 96 DPI.
The x64 original-desktop frame was observable. WWAHost covered the ARM64
original-desktop field. Neither archive observed an interactive tray activation
or an independent notification UIA element. On x64 Shell accepted the icon and
reported the balloon shown. ARM64 exercised the visible fallback. Both
Japanese typing trials restored the original language list after Windows
reported the installed Japanese language tag as `ja`. Composition and
mixed-DPI/RDP rendering remain open. Both cross-session trials stopped
before starting a writer while reading a one-byte token flag.
[Shell](rw02-windows-services.md), [display](rw02-windows-display.md),
[Japanese input](rw02-windows-ime.md) and [writer fixture](rw02-cross-session.md).

## Native follow-up at a66e045

[Run 45034293002](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45034293002)
tested `a66e0456a85a62844e2de2fd155aaeac3577f87c`.

| Native target | Actions artifact | Bytes | Verified ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Ubuntu x64 | 14760086825 | 19,080,621 | `952af7287fdc998da81b8ee60b78ffc6624c34b2c9669df26068440cc3b83367` |
| Ubuntu ARM64 | 14759414052 | 19,072,390 | `a8485efb20406d82b35a2132932ff19e1913cfe5c0e973af3b1e7ef362448e91` |
| Windows x64 | 14759798302 | 16,166,162 | `cdba4f57b20c8514ffdc3cb6b0ca96922f0a90e03a0c42af4ce4839f8ccce12c` |
| Windows ARM64 | 14760717709 | 16,190,262 | `d948467208066df5859e32c062074e6623cc83939086f1874ce2aa07bdcefef9` |

Both Ubuntu targets passed all eight WAL recovery cases, their offline combined
builds and modified Wayland relinks, and the Noble Documents portal comparison.
Both desktops followed light/dark settings across hide/reopen and a portal
restart. Their portals exported only the color-scheme setting. On x64 two
real Plasma panel clicks reopened the window. On each target the integrated
graphics workload rejected the newly reviewed filesystem sources against its
older worker digest and the job failed. Revision `c5606ec` binds the
current workload to the individually reviewed worker inputs. Its Fedora
replay recovered the renderer, focus and background work. The historical
graphics experiment still uses its original digest.
[Graphics replay](rw02-graphics.md#local-integrated-observations),
[storage fault evidence](rw02-storage-faults.md), [combined profile](rw02-combined-profile.md)
and [Noble portal](rw02-portal-noble.md).

Both Windows targets passed all three ordinary filename edits, the NVDA
speech and clipboard check, and the native combined-profile build and smoke
test. The separate ARM64 font probe completed all four cases. The x64 probe
timed out waiting for its first mixed-text caret after producing the same
frame as ARM64. Each Windows VM exposed one active 1024 × 768 output at 96
DPI in console session 2. Mixed-DPI moves and RDP rendering remain open.
[Ordinary editor](rw02-windows-text.md), [standalone font probe](rw02-font-coverage.md),
[NVDA](rw02-windows-reader.md) and [display topology](rw02-windows-display.md).

The Japanese IME delivered preedit followed by a committed あ to the
ordinary field on both hosts. Both restored the original keyboard layout,
language list and optional capability state. The x64 trial finished. On
ARM64, removing the temporary GUI profile raised a Windows sharing
violation (error 32), so the composition evidence survives with failed
cleanup. Both hosts observed their elevated same-account writers exclude
one another across sessions 2 and 0 in both directions. The standard-user
trials stopped before opening the guard because Secondary Logon was stopped.
[Japanese input](rw02-windows-ime.md#hosted-execution) and [writer handover](rw02-cross-session.md).

On Windows x64 the retained GUI passed the window controls. Both scan modes
lacked a baseline after the older filesystem checksum stopped worker staging.
The storage fault fixture stopped while copying a live SQLite WAL index
before its first process kill. All four overall desktop jobs recorded failure.
[Storage](rw02-storage-faults.md), [graphics inputs](rw02-graphics.md#local-integrated-observations)
and [workflow run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45034293002).

## Native follow-up at 3b4854d

[Run 45039099730](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730)
tested `3b4854d867f614a956042dfe987ecc7c008e53ec`. Both Ubuntu jobs passed.
Both Windows jobs finished with failed checks and uploaded their results.
Each of the four ZIPs matched the size and SHA-256 published by Actions and
passed archive integrity checks.

| Native target | Actions artifact | Bytes | Verified ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Ubuntu x64 | 14762715938 | 19,506,512 | `a495111a590cc54b72753cf57fba93f17e24802acddf873dea88170c12d92114` |
| Ubuntu ARM64 | 14761634190 | 19,567,805 | `e70016232c6a366280d2181de23d67fa400eac7255b9683a4b89e414bbc3b000` |
| Windows x64 | 14763571611 | 17,940,316 | `eb9cb84546da440577f10018dc09882a0ba8983989a12bfef6ff87b862b35f46` |
| Windows ARM64 | 14763606202 | 17,898,754 | `cbbeaafadbfa07160aaf83f38a0157e6aa20ba960874d28be41cbd4204982257` |

On each Ubuntu host the Rust and .NET references used the same X11 server,
workload and recorder. All eleven limits passed over three independent
100,000-file trials. The native runs exercised Mesa device loss during
X11 and Wayland rendering as well as startup without a driver.

| Native target | Startup (ms) | Visible memory (MiB) | Scan close p95 (ms) | Scan reopen p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Ubuntu x64 | 252.05 | 124.371 | 0.39 | 0.93 |
| Ubuntu ARM64 | 204.15 | 119.957 | 0.33 | 0.89 |

Both Ubuntu hosts repeated eight storage fault recoveries with 208 C# assertions,
16 corruption rejections and eight final snapshot checks. In each ZIP 465
of 466 indexed storage files matched directly. Actions omitted one tracked
`.gitattributes` file from its source snapshot. Its exact 78 bytes were
recovered and verified independently from the Git revision. Both combined
native builds and modified Wayland relinks also passed.
[Linux x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/job/137259319428)
· [Linux ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/job/137259319481)
· [Storage fixture](rw02-storage-faults.md).

On Windows ARM64 the retained DX12 window using Mailbox passed all eleven
limits against WPF. Its scan close/reopen p95 was 7.00/4.20 ms against
13.94/15.09 ms. Windows x64 passed eight limits. Its scan close took
22.23 ms against 30.85 ms and reopen took 124.14 ms against 21.92 ms.
Its idle close and reopen also exceeded their limits. The ordinary filename
editor and NVDA passed on both targets. The separate font observer passed
four ARM64 cases and stopped at initial field focus on x64. Japanese input
produced a real preedit and commit on ARM64. On x64 both input gestures
inserted a literal `a`. Both restored the original language and input layout.
[Native window measurements](rw02-windows-window.md) · [Font controls](rw02-font-coverage.md)
· [IME receipts](rw02-windows-ime.md).

Each Windows host completed six storage recovery cases and 144 C# assertions
before the private FAT volume filled. Both recorded Windows error 112, SQLite
error 13 and zero available bytes. The Rust worker rejected the supervisor's
line ending before recovery, and both volumes detached. Both private Explorer
instances declined the initial tray registration. The fixture stopped before
input and restored the original desktop. Neither hosted console provided
mixed-DPI or RDP. [Windows x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/job/137259319529)
· [Windows ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45039099730/job/137259319278)
· [Storage](rw02-storage-faults.md) · [Shell](rw02-windows-services.md).

## Native follow-up at 7517e3b

The desktop run at `7517e3b6be84645bc0d40603750b003dd5792104`
completed on all four architectures. Both Ubuntu jobs passed. Both Windows
jobs uploaded their successful checks and their failures. All four archive
sizes, published SHA-256 values and member CRCs were verified.
[Desktop run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45047460092).

| Native target | Actions artifact | Bytes | Members | Verified ZIP SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Ubuntu x64 | 14767174366 | 19,674,394 | 1,275 | `afd05f889c75c40f2a1f3cebc9f413c9fc48c488160f1fa1f0f45bd68e0f8b6c` |
| Ubuntu ARM64 | 14767039018 | 19,702,098 | 1,254 | `c7414bb9aeeefd60aa6d662ee39e2d20b2de365793d5dd8f29d490e4f8a2885e` |
| Windows x64 | 14767884653 | 11,290,438 | 738 | `7077364108250c99d95f6de2680d4404b1aacc1a1c3cfe3f3b06c2f29ebe658b` |
| Windows ARM64 | 14769325725 | 11,255,107 | 747 | `d13678adf699c7e9fed734fd7ce9324ec182149f317aa7a53b1a4258caf0108c` |

Both Windows hosts passed the three ordinary editor cases, the four separate
font cases, seven ordered NVDA cues and real Japanese composition, including
removal of the temporary GUI profile. The IME had also passed with cleanup
on each architecture at `8b64330`. The retained Mailbox window met all eleven
WPF-derived limits on ARM64 in both repeats. On x64 it met nine at `8b64330`
and seven at `7517e3b`. The latter took 122.81 ms at p95 to reopen during a
scan against a 19.555 ms limit. Both Windows display inventories reported
one 96-DPI console output. Neither private notification area produced a user
activation. [Filename and font controls](rw02-font-coverage.md)
· [IME receipts](rw02-windows-ime.md) · [Paired window trials](rw02-windows-window.md)
· [Shell results](rw02-windows-services.md).

The native x64 winit import test also passed on both revisions. The four
development SPDX documents generated by the runners at `7517e3b` reproduced
byte-for-byte. Each Ubuntu desktop archive contains eight successful storage
fault cases. The corresponding Windows volume trials ran in the separate
native feasibility workflow. [Native x64 links](rw02-windows-imports.md#native-windows-x64-reconstruction)
· [SPDX inventories](rw02-combined-sbom.md#inventories-generated-on-all-four-native-runners)
· [Windows volume recovery](rw02-storage-faults.md#windows-native-recovery-at-7517e3b).

On Fedora x64 the GUI sources from `f4d5b3a` built offline with the pinned
compiler. The ELF SHA-256 was
`a0d204b66ce0525812f68c7a85f7a553566cb32f9c8419a9cc677a2c12b8d845`.
The X11 run passed the four lifecycle cases, keyboard traversal, Orca speech
and masking, clipboard and Anthy composition. GNOME Wayland committed あ and
observed the same surface at 100%, 200%, 125% and 100% across two virtual
outputs. The X11 and Wayland results have SHA-256
`634e452849db0b848aa441057e103730fe582144f8e45172be5ed42dfae43db8` and
`a05a917e9b1bce8ccfb978fb5e3d602348f337e3266f82bfa0bd75fc451927ad`.
The build's sixteen source hashes, twelve driver hashes and nineteen Wayland
evidence hashes matched their retained files.

## Native follow-up at 8091469

Both Ubuntu jobs passed at `80914693b6db24a5a76f4a5035c6ec880605ddc3`.
Independent readback matched the native archive digests, the two reference
builds and the measurement sources. On each host the .NET baseline and Rust
candidate ran three scans of 100,000 synthetic files. Recomputing the values
from the captured samples reproduced all eleven limits and results.
[Native desktop run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343500).

| Ubuntu target | Startup, Rust / limit | Visible / hidden RSS | Scan reopen p95, Rust / limit | Scan close p95, Rust / limit | Native archive SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| x64 | 197.84 / 1,394.232 ms | 124.848 / 124.598 MiB | 0.89 / 15.95 ms | 0.41 / 15.60 ms | `d6e2ec401f7cce722b257474f827c6497248bf7acc13fba23c35e4cee6e8a949` |
| ARM64 | 212.74 / 1,495.908 ms | 119.738 / 119.738 MiB | 0.90 / 16.18 ms | 0.37 / 15.531 ms | `bba64617926f39e363b4de32bfdaedcf6f7b419ad4ae5a3185ebbf64018cdd0a` |

Both Rust subjects recorded zero idle CPU, XDamage events and render
passes during the sampled visible and hidden intervals. All Rust input
observations began and ended during directory reads. One ARM64 .NET
reopen finished 0.24 ms after its final read and before scan completion.
The ordinary p95 includes that observation. On both X11 and Wayland Orca
announced four labels and three password masks. Both hosts also recorded
Mozc composition, four font cases and scale changes across virtual outputs.
Ubuntu x64 recorded two actual Plasma panel activations. The source-bound
metric, GUI and storage readback is retained in
`artifacts/rust/hosted-desktop-storage/45067343500/linux-native-readback.json`,
SHA-256 `9d997d5d230d05b7c880994f7f0f72471926fe8ee1d085e15e3c8a9f10428f34`.

Both Windows private Shells kept the same visible taskbar through two icon
registration attempts, 3,023 ms apart on x64 and 3,146 ms on ARM64. Each
returned `0x80004005`, an empty icon rectangle and zero pointer callbacks.
Each fixture removed its own temporary directory and returned to the original
input desktop. The original x64 Shell accepted and removed the icon and
reported a balloon-show callback. The original ARM64 Shell declined the icon.
The separate writer archives contain successful elevated same-account exclusion
on each host. Both native standard-user trials stopped before the first
writer operation because the Basic User prerequisite was unavailable.

| Windows target | Tray archive SHA-256 | Cross-session archive SHA-256 |
| --- | --- | --- |
| x64 | `7a3d8ce093ffda820e15a363d92b1d68bb3c6419d4ba7a5274e435572b5a8351` | `721634ecb5ff5e78cf49b1d8b119a843b30256ffd4cf1f56f3e961a997bc578a` |
| ARM64 | `01a79ad54ff14fc70da83acbb4ab12d7f66331d0dc899326ab241f0979aa2ad8` | `a791d2382f98a27c5632b37ec730fee711f42c9d200841fff0e6561e1337c9d3` |

Both complete Windows desktop jobs failed. Their retained Mailbox
comparison met eight limits on x64 and all eleven on ARM64. The separate
canonical ARM64 recorder lost 310,757 ETW records in its third file trace.
Its two aggregate scan metrics are unmeasured. The WPF and retained trials
had usable native file traces on both architectures.
[Paired measurements and hidden-window readback](rw02-windows-window.md#presentations-while-the-root-hwnd-was-hidden).

| Target | Complete archive, bytes / members | Archive SHA-256 |
| --- | ---: | --- |
| Windows x64 | 11,703,424 / 765 | `e006b1b16a722d987ccd93b6af16acbdbc39cefbd6b72f6a4f352a705aeb64ab` |
| Windows ARM64 | 11,458,223 / 774 | `006ea53bb6c5450e94fa0c47c41792d286ee8431d4cc5f8d53875f1cebe76958` |

The ordinary launcher fixture timed out waiting for its first visible window
on the private desktop on both hosts. The primary reported a ready DX12 CPU
renderer and worker activity. Neither trial reached the second launch. On
x64 a later Win32 170 during desktop cleanup obscured the timeout in the
JSON result. The job log preserves both errors. The separate Japanese IME
trial observed composition and removed its temporary profile on both targets
for a third time. Each host had one 96-DPI console output. The display
observer saw the x64 source frame. On ARM64 the owned field did not acquire
focus. Mixed DPI and RDP remain open. Both hosts passed the sixteen
loopback transport cases. [Launcher fixture](rw02-instance.md#ordinary-second-launch-of-the-windows-gui)
· [Display observations](rw02-windows-display.md) · [Native TLS readback](rw02-realtime-transport.md#tls-endpoint-identity).

## Native follow-up at 0a2b5ca

Both native Ubuntu desktop jobs passed at
`0a2b5ca19bcd7cb7be7a5f77415e05b8237ca47a`. The two complete Actions
archives matched their published digests. Recomputing the three
100,000-file trials from the samples reproduced all eleven X11 limits and
results per architecture. Both targets ran the X11 and Wayland lifecycle
tests, Orca, Japanese composition, scale transitions, four font cases,
private portal tests and all sixteen loopback transport scenarios.
[Desktop assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45077818235).

| Ubuntu target | Startup, Rust / limit | Scan reopen p95, Rust / limit | Scan close p95, Rust / limit | Complete archive SHA-256 |
| --- | ---: | ---: | ---: | --- |
| x64 | 177.27 / 1,059.924 ms | 1.00 / 15.70 ms | 0.45 / 15.91 ms | `9140f6d7de06c69cf7613a520a7b96be5baac1db0951ece0fef1be8f47e19bf0` |
| ARM64 | 212.77 / 1,508.724 ms | 0.94 / 16.01 ms | 0.38 / 15.56 ms | `530df797129d78886cff29b4a77fd499d0a1daf42a20f6e0c1c3d55a2e616c2b` |

Each Ubuntu target also completed two online SQLite backups, 40 C# storage
assertions, eight recoveries with 208 C# assertions, and the YAML
comparison with 183 Rust assertions and 116 C# assertions. A separate SQL
reader reopened each archived C# casing database in memory, checked its
integrity, schema and all four tables, and matched all 15 Rust lookup results
in each comparison mode on both hosts. The hosted fixture recorded ten
additional controls per host. Both targets produced identical fixture
database bytes for each mode. The retained native readback has SHA-256
`33d803a9ded82aeac9188dc00e29ab133f09815a59fcc216e1d45d1403477533`,
and the SQL readback has
`e620a9fd356c2a40ef15ab913ab5dd6479bd26db8ebffd4c87976bf7fd9828ba`.
[Stored-key experiment](rw02-legacy.md#stored-sqlite-identities-across-two-casing-profiles)
· [Native notice and SPDX replay](rw02-combined-notices.md#native-notices-at-0a2b5ca).

On both Windows targets the ordinary second launch on the original desktop
reopened a window using the existing primary and worker. The private
launches created the windows on the original desktop, and both secondary
jobs counted a second, unidentified process. The Windows launcher checks
failed. [Native launcher observations](rw02-instance.md#native-desktop-selection-and-ordinary-reopening-at-0a2b5ca).

Both original Windows archives also contain the first four-host run where
the Linux X11 subjects and the retained Windows Mailbox subjects all met
their eleven same-host limits. Windows x64 scan reopen p95 was 11.343 ms
against 22.096 ms. ARM64 measured 4.261 ms against 15.175 ms. The x64
ordinary root-wake trace had zero successful presentations in 303 hidden
intervals. The original-policy control had 423 in 204 intervals. ARM64
recorded none in any of its three traces. Both canonical Windows subjects
met six of eleven limits and both retained FIFO subjects met ten.
[Windows budgets, interval counts and source archives](rw02-windows-window.md#native-retained-window-results-at-0a2b5ca).

The two Windows archives also passed the three ordinary field edits, all
seven ordered NVDA cues and Japanese IME preedit and commit of U+3042. Both
restored the original input layout and removed the private profile. Each
host passed 16 transport sessions, 183 Rust YAML assertions, 116 C# YAML
assertions and the combined build. All 74 combined build source hashes
matched the revision. The display inventory again showed one 1024 × 768
console monitor at 96 DPI. Only x64 observed a changed field frame on that
original desktop. Both mixed-DPI and RDP observations remain open. The
separate Windows service and GUI readback has SHA-256
`7a2f50ec7d168baacfc557c0499011448be81f71abe1c71c1f54e7b7ef40ad83`.

## Native follow-up at 93ecc35

Both Ubuntu desktop jobs passed. Recomputing the metrics from three
100,000-file scans per executable and architecture reproduced all eleven
limits on X11. Each Rust run recorded zero visible and hidden idle render
passes and damage events. The original Orca audio and focus receipts passed
on X11 and Wayland. Both hosts exercised Wayland scale changes of 100%,
200%, 125% and 100%. The packaged and unmodified Documents portal continued
to refuse the upload lock. The isolated backport passed the lease test.
[Ubuntu x64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275439)
· [Ubuntu ARM64 job](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45083264235/job/137401275167).

| Native target | Rust startup median | Reopen during scan, p95 | Close during scan, p95 | Full archive |
| --- | ---: | ---: | ---: | ---: |
| Ubuntu x64 | 170.80 ms | 1.08 ms | 5.37 ms | `14780360288` |
| Ubuntu ARM64 | 207.72 ms | 0.92 ms | 0.38 ms | `14779783396` |

The independent desktop, transport and storage readback has SHA-256
`ddf93d395c4e0ceeb68bccca88d45a1ea5e1d34b4928c634825c87a3dcdd73e9`.
All 22 native compiler receipt files per host reproduced the GitHub digest
of the published input ZIP. Offline notice generation reproduced the
published x64 and ARM64 ZIPs with 1,799 and 1,796 members. The regenerated
SPDX documents matched the original bytes in the full archives and passed
schema validation. They contain 446 and 445 packages respectively, each
with 1,063 relationships.
[Direct SQLite comparison](rw02-legacy.md#native-desktop-storage-at-93ecc35)
· [Windows ordinary launcher](rw02-instance.md#ordinary-second-launch-and-private-desktop-at-93ecc35)
· [Windows integrated Shell](rw02-windows-services.md#original-explorer-and-the-primary-gui-at-93ecc35).

### Fedora input and lifecycle after the focus change

On Fedora x64 the frozen native build from the application sources at
`1e58541` ran on both a private X11 desktop and a private Wayland desktop
with Mailbox presentation. On each, the external observer verified all
four lifecycle cases, including startup without a tray, activation from
the background and quit before any window was shown. Native keyboard input
traversed the filename, password and language controls. The German filename
round-tripped through the system clipboard, the password exposed three
mask characters, and the keyboard switch changed the labels to English.

The readback matched 45 Git inputs on each backend and the running binary
to SHA-256 `5a85ad18b635e016856d1ddbd3f616ac0be1500b8d99d3b14239ff1799754c6d`.
The X11 and Wayland result hashes are respectively
`4fd25b4792a917291199b4e80775e1f61ef688e03a5483a8a08850db323529ae` and
`09e8382b645bd8020657516d58df980cd97127f06b4f8183f5d7f1f93ad6bd50`.
The combined readback is `artifacts/rust/gui-run/source-readback-1e58541.json`
with SHA-256 `241946cc32b0750c5b907b7c5d09fcece10533e74549b4128e57b767f061c09d`.
[Isolated native observer](../../tools/rust-qa/gui/native.py)
· [Windows foreground mechanism](rw02-instance.md#explicit-windows-foreground-requests).

## First-frame regression

The original `with_visible(false)` prototype created its eframe event loop
during background startup. Xvnc reported a mapped 640 × 400 window 177 ms
after launch. At 835 ms the app reported a visible window, background intent
and five UI passes. Foreground startup, native close, reopening and quit worked.
In eframe 0.37.0, the native integration shows the window after its first paint.
The resolved winit Wayland adapter also implements `Window::set_visible` as an
empty method. The original external observation has SHA-256
`99f6aeaecfe458c4db87f19094e683ba9529b93c4b036828f7051c58824a79b4`.
The preserved sources, fonts, executable, X server and D-Bus logs reside under
`artifacts/rust/gui-run/eager-first-frame/`. The tracked
[evidence index](../../tools/rust-qa/gui/evidence/native-linux-x64.sha256)
binds the raw records retained under the ignored artifact directory.

The revised supervisor blocks on its bounded control queue before creating the
first native window. An acknowledged tray registration permits background
startup. Failure of the first registration reveals the UI. A native close
releases the eframe window and returns to the same supervisor. Model state and
the activation endpoint survive. A visible window receives repaint wakeups on
control delivery. Quitting before the first activation completes without
initializing the renderer. No upstream crate patch is required.

## Isolated native runs

Both native Linux backends selected the Mesa lavapipe Vulkan CPU adapter
reported as llvmpipe (LLVM 23.1.5, 256 bits). Xvnc 1.16.2 exposed independent
root-window map and unmap notifications. Mutter 51.1 used a headless virtual
monitor, with X11 disabled for the subject. Its compositor-side Wayland trace
identifies the titled xdg_toplevel, committed root-surface buffers, close
requests and surface destruction. The driver uses Mutter's private virtual
keyboard for Alt+F4.

| Scenario | X11 | Wayland |
| --- | --- | --- |
| Background start, absent StatusNotifierWatcher | Window mapped | Toplevel buffer committed |
| Background start with registered item | Zero maps before SNI activation | Zero maps before SNI activation |
| Quit before first show | Zero maps and zero UI passes | Zero maps and zero UI passes |
| Close, stay active, reopen through a separate desktop client | WM_DELETE_WINDOW, unmap, map | Alt+F4, compositor close, destruction, new mapped surface |
| Visible startup and explicit quit | Window opened and process drained | Window opened and process drained |

The isolated Linux app exports real D-Bus methods at the SNI item and
freedesktop application paths. A synthetic watcher registers the item on the
private bus. The absent-tray case runs with no watcher name owner. The fixture
currently covers primary activation and initial registration. Desktop-panel
rendering, watcher replacement, menu parity, native notifications, portals,
physical GPU/device loss, real multi-monitor scaling and an engine running
through shutdown still require evidence. See the [acceptance record](acceptance.md)
for target and stage status.

## Keyboard, accessibility and rendering

On both backends a separate AT-SPI client read the titled frame, named
filename entry, password role and language button. Native Tab events moved
focus through Dateiname, Kennwort and English. The fixture accepted three
synthetic password characters. AT-SPI returned `•••`. Space activated the
language button, updated the field names to Filename and Password and retained
the button's focus. Ctrl+C, clearing the field and Ctrl+V restored
`Grüße – Sommer.jpg`. The X11 observer recorded a clipboard selection owner.
Mutter recorded a Wayland data-device selection with input serial 56.
The indexed `x11-kl1urbp4` and `wayland-74ulqton` records contain source
and compiler hashes, native window events and accessibility trees. Both runs used executable SHA-256
`06abf418bfefa3a0b21011663e2ba9d234767c6ebc21d87c84f27f52c1bbd4d9`.
The release build, rustfmt check and frozen all-target Clippy check with
warnings denied passed with pinned Rust 1.100.0 on Linux x64.

With default Mesa presentation on the virtual Wayland monitor, two key presses
arrived at the compositor. The application model and accessibility tree had
one character after the three-second deadline. A repeat with a private PipeWire
monitor consumer also stopped at one character. Selecting the Mesa Mailbox
present mode passed the lifecycle and keyboard tests twice on this software
adapter. The stack decision still requires testing display timing and renderer
selection on the supported hardware and desktops. The index lists the default
input observation and both raw compositor traces.

### Native composition and screen-reader output

On Fedora x64 the X11 fixture started the actual Anthy 1.5.18 engine and
registered it on the private IBus 1.5.35 instance. Direct engine selection
and readback confirmed Anthy's `default` keyboard layout. The IBus CLI also
attempts a layout switch, which returned failure for that layout. A native
key press produced a nonempty IME preedit. Return produced a one-character
IME commit, and an independent AT-SPI client read `あ` from the filename
field. The fixture's two Latin fonts still require a CJK rendering check.
[IBus CLI implementation](https://github.com/ibus/ibus/blob/1.5.35/tools/main.vala#L477-L552).

Under both X11 and Wayland, Orca 51.1 followed the actual keyboard focus and
sent the control names and roles to Speech Dispatcher 0.12.1. It announced
the German filename and password, the English language button and the
renamed Filename field. The three password keystrokes produced exactly three
spoken mask symbols. eSpeak NG 1.52 generated non-silent samples for a
private ALSA file device. The sample-prefix hashes can be checked against
the retained raw files. These tests exercise the native accessibility and
speech stack with synthetic input and a software audio sink.

| Fedora x64 run | Native input and speech | Observed audio bytes |
| --- | --- | ---: |
| `x11-m34b3ex8` | Four lifecycle cases, AT-SPI, Anthy preedit and commit, Orca | 939,144 |
| `wayland-eoyrquw0` | Four lifecycle cases, AT-SPI and Orca under Mutter with Mailbox presentation | 743,308 |

Both runs used the measured executable SHA-256
`5bd230d24989fc251b789bb152afdf78e5a4353fda1150e809f6a250ef61af3f`.
Wayland composition, mixed-direction editing, other monitor configurations
and assistive technology on the remaining targets still require observations.
[Source-bound desktop evidence](../../tools/rust-qa/gui/evidence/native-linux-x64.sha256)
and [native speech observer](../../tools/rust-qa/gui/screen_reader.py).

## Reproduction

At `2e7ed89`, Windows x64 passed the full keyboard sequence. Focus traversed
Dateiname, Kennwort, English and Filename. Three keystrokes produced three
masks in both UI Automation patterns, the translated controls appeared, and a
Unicode filename completed a real clipboard round trip. Windows ARM64 confirmed
the same German names, password protection and access to the input desktop.
Its foreground request and coordinate-checked click did not acquire the test
window, so the observer withheld all keystrokes. Both desktops measured 96 DPI
on one 1024 × 768 monitor. The retry records the click location and active
console session. It can raise only the synthetic window before repeating the
owner/point checks. The corresponding downloaded x64 and ARM64 archives had
SHA-256 `cb2d3533ca1ee0ea2077fdd0c94887e49311a1a133208830ee57a69340f83eac`
and `20e7ef5cbb8bce2fa72358b614616735f914b13a9ba9499bf65ea3cea9479922`.
[Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44828363871).

The separate [portable NVDA assessment](rw02-windows-reader.md) coordinates
the foreground driver with actual screen-reader announcements and records the
source of protected-character feedback.

Use a native pinned Rust toolchain and the reviewed font files under
`rust/assets/fonts`. Supply a Cargo registry cache containing the locked crates.
Run the Linux checks from the repository root.

```sh
python3 tools/rust-qa/gui/build.py
python3 tools/rust-qa/gui/build.py --clippy
python3 tools/rust-qa/gui/native.py --backend x11 --input
python3 tools/rust-qa/gui/native.py --backend wayland --input --present-mode mailbox
```

The offline build mounts its compiler, source, registry and fonts read-only
inside bubblewrap. Each invocation of the observer creates a fresh artifact
directory and private mount, network, PID, IPC and user namespaces. The tests
run in a synthetic home with a private D-Bus and display. The default software
driver comes from the native Mesa lavapipe manifest. `--binary` accepts a
separately built native assessment. The build script writes the executable
digest, compiler identity and input hashes alongside its binary. The observer
embeds that record when supplied alongside the tested executable.

On the originating host, check its retained records with
`sha256sum --check tools/rust-qa/gui/evidence/native-linux-x64.sha256`.

Use the Wayland command without the present-mode option for the default
presentation diagnostic. Add `--capture` to attach a private PipeWire/GStreamer
consumer to the virtual monitor. The optional XIM diagnostic uses
`--backend x11 --input --ime` with IBus, ibus-x11, Anthy and xprop installed.
Add `--screen-reader` to an input run with Orca, Speech Dispatcher, its eSpeak NG
module and its ALSA plugin installed to exercise native synthesized output.
The ordinary Linux observers use bubblewrap, Xvfb or Xvnc, libX11, libXdamage,
libXtst, gdbus, PyGObject and Mesa lavapipe. Wayland additionally uses Mutter's
headless, virtual-monitor and RemoteDesktop interfaces. The accessibility
case uses at-spi2-core and its introspection bindings.

The Windows fixture accepts an initial tray result on its inherited input pipe
and bounded open, close or quit commands. The [Windows observer](../../tools/rust-qa/observe-windows-gui.py)
owns the OS-specific observation. The local keyboard and compositor traces
come from Fedora x64.

The separate Windows `--input-only` case attaches the system UI Automation
client to the observed HWND and checks its process ID. The client reads German
and English control names, follows keyboard focus, checks the protected
password field and verifies a Unicode clipboard round trip. Each keyboard
operation requires the observed HWND to own foreground input. The report
retains the observed DPI, monitor size, protected-pattern behavior and the
last completed input checks if the host cannot supply interactive input.
At `11e4e6f` both Windows UI Automation clients identified Dateiname, Kennwort
and English and the protected password property, on a 1024 × 768, 96 DPI monitor.
On x64, Tab reached both edit controls and the native application received
one synthetic password character. The observer then met a Windows sharing
violation reading the application's active log. The observer now uses a
shared read handle and matches complete lines. On ARM64 the test window
failed the foreground check before any keystroke. The follow-up records the
input desktop, requests focus through the owned UI Automation element and
can click its bounds only after checking the live screen point against that
HWND and PID. Each keystroke still requires the input desktop and foreground
window to match. [Native inputs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44825008977)
and [Windows foreground rules](https://learn.microsoft.com/windows/win32/winmsg/window-features).
[Windows UI Automation observer](../../tools/rust-qa/observe-windows-input.ps1).

At `5895c0b`, Windows x64 again passed the complete keyboard, protected text,
language and Unicode clipboard sequence. On Windows ARM64 the process and
active console both reported session 2. The observer could read the owned
controls on the input desktop, but raising the test window did not make the
filename field's screen point belong to that HWND. The observer sent zero
keys. Native ARM64 focus, typing and screen-reader evidence remain open.
[Windows x64 and ARM64 input records](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44831851264).

The `--device-recovery` fixture edits the real filename field, captures its
visible pixels and requests destruction of the process's own DX12 device.
It requires an observed device-loss callback and a new HWND, a visible
redrawn field with the original draft and native focus, and an edit that
changes the captured pixels. The normal close, reopen and quit sequence
must also pass after recovery. Native Windows results for this fixture are
pending. [Observer and process-bound controls](../../tools/rust-qa/observe-windows-gui.py).

In the integrated run, Windows x64 delivered the destruction callback and
initialized generation two on WARP. Both the original and replacement windows
were briefly visible to the observer. The observer now waits for the original
to disappear before sending any further input. The initial Latin render
control also passed on both Windows hosts. Later pointer cases failed to
observe a caret. The input fixture now posts each client position immediately
before its corresponding button message and records whether the physical
screen point belonged to the foreground test window. Acceptance still requires
the expected visual caret, selection, deletion and follow-up edit.
[Native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/44835826452).
