# Publishing the editor's AT-SPI tree in Flatpak

Flatpak 1.18.4 supplies an application-side accessibility proxy at
`AT_SPI_BUS_ADDRESS=unix:path=/run/flatpak/at-spi-bus`. Its filter permits
an application to embed its own root. In the installed test ref, querying
`org.a11y.Status.IsEnabled` on the session bus returned
`org.freedesktop.DBus.Error.ServiceUnknown`. AccessKit 0.24.1 waits for that
property before constructing its AT-SPI bus. The original executable therefore
showed and translated its editor while Orca could announce only the Tab keys.
[Flatpak proxy contract](https://github.com/flatpak/flatpak/blob/1.18.4/common/flatpak-run-dbus.c#L414-L442)
and [original AccessKit event loop](https://github.com/AccessKit/accesskit/blob/f3026222559c7f5f46d8f25cb7404de68eb149f0/adapters/unix/src/context.rs#L169-L209).

The private adapter checks for Flatpak's instance file and the supplied proxy
address. It connects to that proxy and publishes the application's own
accessible interfaces through the existing `Socket.Embed` implementation.
A missing address or failed connection leaves the adapter inactive. On an
ordinary desktop it continues to follow the session's status property.
A working application proxy can serve a read-only assistive client before
anyone subscribes to events. GTK also gives the address supplied by Flatpak
precedence. [Adapter change](application-bus.patch) ·
[original root registration](https://github.com/AccessKit/accesskit/blob/f3026222559c7f5f46d8f25cb7404de68eb149f0/adapters/unix/src/atspi/bus.rs#L76-L112)
· [GTK application bus discovery](https://github.com/GNOME/gtk/blob/gtk-4-20/gtk/a11y/gtkatspicontext.c#L1748-L1767).

## Rebuilding the Fedora x64 candidate

The compiler starts from the [original language editor](../startup/README.md)
and its native receipt `bfde3d81b0948a70d55221591ec3b57d3a7707a497d889d3758ccbdfbfd1fac0`.
It verifies the original 385-package directory source, GUI text and font
inputs, then reconstructs the 28-file `accesskit_unix 0.24.1` crate from
archive SHA-256 `30d5192871228c54f1b0fb4a85cef000e11a3804f25d2165f14afa0daa67f3f6`.
The changed files are `src/context.rs` and `src/atspi/bus.rs`. The original
manifest declares MIT or Apache-2.0. The build retains the pinned upstream
MIT, Apache-2.0 and Chromium notices alongside the source changes.
[Original notices and upstream URLs](../../../../rust/audit/gui-inputs.json).

```sh
python3 -B tools/rust-qa/gui/flatpak-accessibility/build.py \
  --stock artifacts/rust/combined-profile/editor-language-replay-verified \
  --vendor artifacts/rust/combined-profile/editor-language-clean-vendor-01/registry/src/reviewed \
  --output artifacts/rust/flatpak-accessibility/replay
```

For a warm build, `--seed-target` copies the original Cargo target cache into
the new trial directory. The historical build used two jobs and frozen
dependencies in private offline namespaces. The driver defaults to one
compiler job. Cargo resolves the source override through
`metadata --offline`. A structural check allows exactly the replacement of
the adapter's registry identity in the lock. Comparing every compiled target
and feature group to the stock stream yielded 310 matching units and verified
the freshly compiled adapter and linked application. The archive reconstruction,
notices, original and derived file digests, compiler stream and linked
executable are under `artifacts/rust/flatpak-accessibility/second/`.

| Native input or result | SHA-256 |
| --- | --- |
| Original editor | `2b751a662a093ed7e30b629e66c62654caf3d818d317f00c999b28e18471b76f` |
| Candidate editor | `b8938d364a916aea5c862e0da670071a353089176e9716facadf0471df80d438` |
| Patched 28-file compiler tree | `5d2c0ad1d4ca2534018a9ede877a77c1c3fd9470c01707ef4bf493ed1ad34f0f` |
| Derived GUI Cargo.lock | `32398824dd5f297f465cc0809542d828a24cd180c552acfec1180396720c7b76` |
| Native candidate receipt | `c21f6d98033b6574cc887bc393bf0e7ea77a4845630c9be721acc21194d1d909` |

## Original-source reconstruction for the ordinary language editor

[The shared adapter reconstruction](accesskit_source.py) takes the original
crate archive, a fresh compiler directory and a fresh notice directory.
It verifies the published archive and Git revision, applies the existing
patch, and checks the complete source tree against the
[measured before-and-after hashes](source-review.json). Both modified Rust
files match the historically exercised candidate byte-for-byte. The other
26 original files and the three supplemental notice texts also match. A
second reconstruction from the archived crate reproduced the same 28 files.
A truncated archive failed before the helper created either output directory.

The ordinary Fedora x64 editor at `c361c69` supplies its original release
executable, native compiler stream, full GUI graph, directory-source
receipt and 40 first-party inputs. Run the candidate with a copy of the
ordinary release cache and a new output directory.

```sh
area=artifacts/rust
registry=1fde2469c1e00f08882bb863eca1110eb1c45fe78fe55e4b7767fcd3db0388e3
python3 -B tools/rust-qa/gui/flatpak-accessibility/build.py \
  --stock "$area/gui-build" --seed-target "$area/gui-build" --jobs 1 \
  --vendor "$area/gui-registry/$registry/registry/src/reviewed" \
  --output "$area/flatpak-accessibility/current-replay"
```

The ordinary upstream executable had SHA-256
`5357b1f9c71edbd2409257ed503db61e3da50805147de4c07d6c6b6c043677f2`,
with compiler receipt
`b01ed1ba88ee393d4184426e1697b7cc5f8bf4c25914ed8b10f0cb55187b58b0`.
The private relink rebuilt the adapter and the GUI. All 310 compile units
and feature sets matched the upstream editor after accounting for the
adapter's source identity. Among the 40 copied first-party inputs only the
private GUI manifest and its lock changed. The YAML library at `bb3afd5`
and all editor source files were identical. The private executable had
SHA-256 `f1e5dd1c830e4ad66292f22c9c6fdc061c9cb4eead40c017331d512a40d6d08c`.
Its compiler receipt is `artifacts/rust/flatpak-accessibility/current-a4d967d/native.json`,
SHA-256 `68d808ae984b4e8684df87ce8048b479fe795eed14506300d7354b392eabb3e9`.

## Cargo directory source for the normal compiler

The normal GUI and combined source builders use the same reviewed
two-file adapter change. Cargo still identifies `accesskit_unix 0.24.1`
by its original registry URL and archive SHA-256. The offline directory
contains the 28 reconstructed files. Its Cargo checksum manifest records
the original package checksum and the actual per-file hashes, with
SHA-256 `ea3d9c955078b75c4a9b05b35407eb8ab10b2373c61525a1fc2a1e4214954f9b`.
The original and corrected directories use separate receipt-keyed locations.
[Directory builder](../startup/vendor.py) · [Combined source preparation](../../combined-profile/sources.py).

| Local source comparison | Result |
| --- | --- |
| Registry compiler-tree digest for 28 files | `38ba18df2c350eee1ad11b89bad7f79f281a50e93bc3d30f19f14d62057662c8` |
| Corrected 385-package GUI receipt file | `6a169a3b2c15a259d24ee23f10fc4625876808ae121e2edd15469ab1e96d0478` |
| Corrected 473-record combined receipt file | `50bdb77fbcefac1077463f8c0444a2a7ccc13b7629c94c6df0ee876c0c51bdf4` |
| Combined canonical source-inventory digest | `99e9d56cfa775b763633986e90691589d23bbedacc7e5539f4c056f1f74f2be0` |

The registry compiler-tree digest hashes the canonical filename-to-digest
JSON used by Cargo source preparation. The historical private path build
above hashes sorted path names and binary digests. Each calculation covered
the same source bytes. Fresh archive reconstruction reproduced all 384
other GUI rows and all 472 other combined rows. The source comparison
also verified every GUI row against the combined inventory. Its record
is `artifacts/rust/combined-profile/accesskit-source-registry-01/comparison.json`,
SHA-256 `3de85efeb78c21a08bf11b83468c650f8a1c47ac7cfd2aa0f4e4d5c7bef1d2ca`.

For the historical control, `compiler_directory(registry, gui, stock=True)`
selects the original adapter. The standalone startup vendor CLI retains its
historical default and accepts `--corrected` for the normal source selection.
The [registry check](test_registry.py) accepts the original `.crate` as
its sole argument. It compares both Cargo trees and rejects each swapped
profile. A third modified file also failed verification after the test
updated its local Cargo checksum manifest.

## Installed observations on Fedora x64

The private stock and candidate Flatpaks used the same runtime, permissions,
saved German and English profiles, ordinary launcher and Orca 51.2. The stock
GUI had no application root in three samples with an idle registry, and no
editor fields were announced with the reader active. The candidate provided
its root at all three idle samples. With Orca active, the observer matched
both installed windows and each AT-SPI root to the PID of that window's
Flatpak proxy. Orca spoke the filename, protected-field role, language switch
and Quit in the expected order during physical keyboard traversal. The English
and German speech segments contained 474,010 and 477,576 bytes of audio.
Each GUI also opened and closed normally on a private desktop where Flatpak
had no accessibility socket to offer. Both runs ended with an empty test
installation. The detailed observations, focus transcripts and original
audio are under `artifacts/rust/flatpak-gui-launch-assessment/x11-cbgjya4t/`
(stock) and `x11-ue6d30bk/` (candidate). [Installed observer](../flatpak/README.md).

Outside Flatpak the same candidate completed the private Fedora X11 keyboard,
IBus and Orca check, including protected-field masking and a backward selection
across an ordinary second launch. Its native result is
`artifacts/rust/gui-run/x11-qih95zgk/results.json`, SHA-256
`96e05d8844a8c9ef7e0fa9eb269241166182686fe9648fd6be1bc8365f9ccd63`.

## Desktop status changes outside Flatpak

The [desktop status observer](desktop_status.py) toggled `IsEnabled` on a
separate, private session bus. The same mapped X11 window and GUI PID 23
survived all four samples. Starting with status off yielded zero roots,
turning it on exposed root `:1.3`, disabling it removed that root, and
enabling it again registered `:1.4`. Quit removed the final root and exited
zero. Run the observer with the candidate executable as its sole argument.
The original result is `artifacts/rust/flatpak-accessibility/desktop-status-1k9hds8a/status.json`,
SHA-256 `7ae11d5f9eea3a987e89d2d4ddbb2e8def517f136d8da717fb8ec633dfd624c3`.

Use the ordinary release ELF as the sole argument to repeat the check
with the normal compiler profile. Before startup the observer verifies
the adjacent compiler receipt, its first-party inputs, the original Cargo
unit stream, target graph and corrected registry inventory. On the
private X11 desktop it matches the running ELF and window PID. It follows
each previously observed AT-SPI root through disable and Quit by asking
the registry for its current children.

```sh
python3 -B tools/rust-qa/gui/flatpak-accessibility/desktop_status.py \
  artifacts/rust/gui-build/release/native-gui-assessment
```

On Fedora x64 the normal executable had SHA-256
`8701338776267200c277de2dc7a7f73969716509e0dcc6f9524770531524aeaa`.
Both observers retained its compiler receipt
`a47f684efaf5791e54ebda2e3c9b5b98a6d7de3bf2c8a5a1668444bd0acc90ad`.
The same X11 window `4194306` and PID 27 remained present throughout the
off/on/off/on sequence. The registry returned zero, one, zero and one
root, respectively. The two active registrations were `:1.3` and `:1.4`.
After Quit both registrations and the window were gone, and the original
process exited zero. The result is
`artifacts/rust/flatpak-accessibility/desktop-status-yp4yoxn8/status.json`,
SHA-256 `956eda2f8f8750850beb315f9e16b97f6f667d233b32651ebdf60456c6846a20`.

On a separate private Mutter Wayland desktop Orca 51.2 spoke the German
filename and password field roles, the language switch and the English Quit
button during keyboard traversal. Protected input produced bullet speech.
Closing the editor with Alt+F4 and launching it normally again retained
the original PID 437 and its backward Unicode selection. Shift+Left
extended the selection from offset 2 to 1 with the other endpoint at 5,
and the next character replaced it. The report and original audio are under
`artifacts/rust/gui-run/wayland-tb_t4rf8/`. The report SHA-256 is
`2921c4827e1dcb11ee09cb406a714fff45948643cf9ed3eb2a8034ddd801b838`.
