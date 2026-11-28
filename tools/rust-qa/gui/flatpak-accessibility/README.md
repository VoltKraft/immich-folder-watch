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
the new trial directory. The build uses two jobs and frozen dependencies in
private offline namespaces. Cargo resolves the source override through
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
