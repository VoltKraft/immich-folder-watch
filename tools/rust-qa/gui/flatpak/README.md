# Installed Linux editor and tray language

The installed test ref starts its ordinary `/app/bin/native-gui-assessment` through
the existing Flatpak launcher. Both saved-language cases use the same installed
application and the same private X11 desktop. The original Fedora x64 executable
includes the reviewed startup settings reader. Its SHA-256 is
`2b751a662a093ed7e30b629e66c62654caf3d818d317f00c999b28e18471b76f`.
The harness verifies the original compiler receipt, compilation units, source
files and supply receipt before installation. The two renderer reference frames
are mounted read-only for the outside observer. [Startup build](../startup/README.md)
and [six-frame renderer comparison](../../windows-cpu-paint/headless/README.md).

From the repository root, on the Fedora x64 host with the pinned Freedesktop
Platform and Mesa extension installed, run the following against the retained
originals.

```sh
python3 -B tools/rust-qa/gui/flatpak/run.py \
  --startup-gui artifacts/rust/combined-profile/editor-language-supply/native-target/release/native-gui-assessment \
  --startup-receipt artifacts/rust/combined-profile/editor-language-replay-verified/native.json \
  --startup-pixels artifacts/rust/egui-cpu-assessment/headless-ycr1rvcu/pixels \
  --tray-menu
```

For the ordinary Linux GUI, select the directory produced by
`build-gui-probe.py`. The observer checks the executable and its current
first-party sources against the native compiler receipt. It uses the same
German and English reference images for both binaries.

```sh
python3 -B tools/rust-qa/gui/flatpak/run.py \
  --gui-build artifacts/rust/gui-build \
  --startup-pixels artifacts/rust/egui-cpu-assessment/headless-ycr1rvcu/pixels \
  --tray-menu
```

The fixture installs one private test commit and seeds
`$XDG_CONFIG_HOME/immich-folder-watch/config.yaml` for that app under a synthetic
home. For each ordinary primary, the observer follows its outer PID, Flatpak PID
namespace and XID. It verifies that the original configuration file resolves
to the same device and inode inside the sandbox, reads the actual environment,
and compares the file digest before launch and after exit. The parent desktop
does not change language. The German locale variable is observable by the
application even when the minimal Platform lacks the optional system locale data.

| Saved preference | Primary's LC_ALL | Visible labels on first editor | First registered menu |
| --- | --- | --- | --- |
| `en` | `de_DE.UTF-8` | Filename, Password, Deutsch, Quit | Open GUI, Restart, Quit |
| `de` | `en_US.UTF-8` | Dateiname, Kennwort, English, Beenden | GUI öffnen, Neustart, Beenden |

The observer compares four physical X11 label crops with the two original
640 × 400 GPU frames at 100% scale. Each glyph mask must match its expected
reference exactly and differ from the other language. The menu peer reads
revision 1 through the installed process's session-bus proxy. Ordinary and
background second launches reopen the original XID. After replacing the tray
watcher, the observer reads the same translated menu again, selects Open and
Quit, and verifies the wire replies and all four process exits. This fixture
runs the GUI without an inventory worker. The [native startup trial](../startup/README.md)
separately exercises the worker.

The existing ordinary second-launch and watcher replacement check remains
available for the staged GUI.

```sh
python3 -B tools/rust-qa/gui/flatpak/run.py tray-loss-quit-fedora-01 --tray-menu
```

## Accessibility on the private desktop

The observer enables the private accessibility service, records its registry
owner and matches a real GTK push button to its process by name and role. The
control window exits before the installed GUI launches. For each saved language
the observer enumerates the same registry for two seconds while the installed
window is visible. The registry returned no applications
in either interval. The eight physical label matches above establish that
sighted users could see the controls. The external AT-SPI client could not
discover those controls for a screen reader on this desktop.

After both primary processes exit, a separate instance of the same test ref
runs the Platform's `gdbus` with its ordinary sandbox policy. The app has IPC
and X11 access and can communicate with `org.kde.StatusNotifierWatcher`. In
that instance both `org.a11y.Status.IsEnabled` and `org.a11y.Bus.GetAddress`
return `org.freedesktop.DBus.Error.ServiceUnknown` on the filtered session bus.
The advertised `AT_SPI_BUS_ADDRESS` points to the mounted
`/run/flatpak/at-spi-bus`. Calling the registry's
`org.a11y.atspi.Accessible.GetChildren` over that socket returns
`org.freedesktop.DBus.Error.AccessDenied`. Through the same socket,
`org.a11y.atspi.Registry.GetRegisteredEvents` returned an empty event list with
exit status 0. Flatpak 1.18.4 permits this latter application-side call. The
registry was therefore reachable from the ref. The stock installed editor did not expose a tree on this desktop. The installed observation ends at AT-SPI
discovery. Orca speech and audio were captured in the separate native Ubuntu
editor trial. [Ubuntu ARM64 Orca results](../../../../docs/rust/rw02-native-gui.md#ubuntu-arm64-selection-and-quit-focus-at-245a921)
and [Flatpak's accessibility proxy rules](https://github.com/flatpak/flatpak/blob/1.18.4/common/flatpak-run-dbus.c#L417-L425).

## Fedora x64 observations

The original `x11-87iho0wg` under
`artifacts/rust/flatpak-gui-launch-assessment` contains the raw screenshots,
glyphs, menu bus traces, private runtime replies and source archive.
Its `result.json` has SHA-256
`9a1f0d54456dceca85e165a05640c95d81089358fc839cc138e48067c5992ef9`.
The installed commit was
`d19112a973856deadd5dfaaae62cb987781db1fb85fedd6a1e61ecf734591086`.
The English and German GUI processes had outer PIDs 85 and 414, their
corresponding desktop-bus proxies had PIDs 81 and 410, and each inner GUI
had PID 2. All eight masks matched their corresponding GPU references exactly.
Overlap with the opposite language ranged from 19.5% to 41.6%. Both primaries
exited with status 0 and the app list was empty after uninstall. The original
second-launch and watcher replacement regression also passed in `x11-8yewtd3e`.

## Screen reader comparison on installed refs

The optional `--screen-reader stock` runs the original compiler receipt above.
`--screen-reader candidate` selects the separate source-bound AccessKit
test executable and receipt. Each run installs a fresh application from just one
binary. Both use the same ref, Flatpak entry point, permissions, runtime,
GPU reference frames and synthetic German and English profiles.

Each trial first opens the ordinary editor without a desktop accessibility bus.
The observer checks that the live sandbox received neither an accessibility
address nor a socket and follows the window through Quit. A second start uses a
working private registry before Orca or the GTK control exists. The observer
reads the registry's application roots and event listeners three times during that
start. It then verifies the native GTK button, starts Orca with Speech Dispatcher,
eSpeak NG and a private ALSA file, and launches the two saved-language cases.
For each installed editor it compares the visible pixels with both language
references, focuses the original XID and sends physical XTest Tab events.
The AT-SPI client's root path and bus name identify the app behind the original
Flatpak proxy. Its outer PID, sandbox PID 2, mapped executable and original XID
are recorded separately in the process witness.

In the stock control, Orca 51.2 registered on the Fedora 2.62.2 AT-SPI bus.
Before Orca started, three samples had empty listener and application lists.
After it started, both languages rendered on screen and each set of four Tab
presses produced only key echoes. Orca's own application was the only registry
root. Both editors reopened on their original XIDs and exited successfully.
The control report in `x11-cbgjya4t/result.json` has SHA-256
`5a398c4ccb75f482164934785428a823aeba783053fc3e8a687b009ab700ba89`.

To run the candidate with the original source-bound compiler output, use the
same pixel directory and its separate native receipt. The tested executable has
SHA-256 `b8938d364a916aea5c862e0da670071a353089176e9716facadf0471df80d438`.
The [private adapter compiler](../flatpak-accessibility/build.py) verifies the
source tree, notices and compiler units.

```sh
python3 -B tools/rust-qa/gui/flatpak/run.py \
  --startup-gui artifacts/rust/flatpak-accessibility/second/target/release/native-gui-assessment \
  --startup-receipt artifacts/rust/flatpak-accessibility/second/native.json \
  --startup-pixels artifacts/rust/egui-cpu-assessment/headless-ycr1rvcu/pixels \
  --tray-menu --screen-reader candidate
```

On Fedora x64 the corrected editor launched and quit normally without an
accessibility socket. With the socket present and zero registered event
listeners, three samples saw its root through proxy PID 572. After Orca
started, the external AT-SPI client found toolkit `AccessKit`, application
`native-gui-assessment`, a named entry, a password field and two buttons in
both languages. Each physical Tab focused the named control at the original
XID and yielded a corresponding Orca speech request.

| Saved | GUI / proxy PID | AT-SPI bus owner | Spoken focus sequence | Non-silent PCM span |
| --- | --- | --- | --- | ---: |
| English | 1103 / 1099 | `:1.8` | Filename, Password, Deutsch, Quit | 474,010 bytes |
| German | 1497 / 1493 | `:1.9` | Dateiname, Kennwort, English, Beenden | 477,576 bytes |

The reported accessible application PID matched the corresponding proxy.
The ordinary launch, background launch and restored tray all reopened each
original window. Both primary processes exited with status 0. The private
app list was empty after uninstall. The full report in
`x11-ue6d30bk/result.json` has SHA-256
`e88062ad400bffe5b5df93f6be4eb74707d4c8eb1be41dce93729bf5cd087b51`.
Each `reader.json` records the byte offset, length and digest of the spoken
traversal's span in `orca-audio.raw`. The exact speech request is in
`orca-debug.log`. This comparison covers the private corrected x64
executable on X11. The canonical editor and shipping application have
separate build and qualification records.

The original command without the Orca option also completed with the final
observer in `x11-uyqg87yr`. It reproduced both stock pixel and menu results,
the GTK control and the empty AT-SPI discovery intervals.

## Orca with the ordinary GUI and current settings reader

The Fedora x64 comparison installed the ordinary editor at `c361c69` and
the private AccessKit build from those same application sources. The paired
compiler receipts bind 310 units each. Among 40 first-party inputs, the
private build changes the GUI Cargo patch declaration and corresponding lock
entry. Both installations used `app/org.example.IfwGuiProbe/x86_64/test`,
the same Platform, Mesa extension, sandbox permissions and observer archive.
The test installs each executable into a fresh private user installation.
[Adapter build and notices](../flatpak-accessibility/README.md).

Both GUIs opened and quit with the accessibility bus absent. With the bus
available and zero registered listeners, all three early samples showed an
empty registry for the stock control. All three candidate samples contained
the root belonging to its Flatpak proxy. A native GTK button was accessible
on each private desktop. With Orca running, both executables drew the four
expected labels in each saved language. The stock editor produced only Tab
echoes and exposed no controls. The candidate's physical Tab traversal produced
the following focus changes and corresponding speech on its original window.

| Saved language | GUI PID / proxy PID | AT-SPI owner | Announced controls in order | Captured PCM bytes |
| --- | --- | --- | --- | ---: |
| English | 1280 / 1276 | `:1.8` | Filename, Password, Deutsch, Quit | 443,584 |
| German | 1674 / 1670 | `:1.9` | Dateiname, Kennwort, English, Beenden | 467,586 |

Both installed GUIs reopened their original windows, exited through Quit and
left an empty private installation. The independent comparison checks the
original screenshots, proxy/PID and XID, Orca speech log and non-silent PCM
spans. It also matches both source lists, compiler lineage, reference frames
and observer before accepting the pair. From the repository root:

```sh
area=artifacts/rust
pixels="$area/egui-cpu-assessment/headless-e94nfyhl/pixels"
candidate="$area/flatpak-accessibility/current-a4d967d"
fixture=tools/rust-qa/gui/flatpak
python3 -B "$fixture/run.py" --gui-build "$area/gui-build" \
  --startup-pixels "$pixels" --tray-menu --screen-reader stock
python3 -B "$fixture/run.py" --startup-gui "$candidate/target/release/native-gui-assessment" \
  --startup-receipt "$candidate/native.json" --startup-pixels "$pixels" --tray-menu --screen-reader candidate
```

Pass the two printed run directories to [verify_reader_pair.py](verify_reader_pair.py),
stock first. The retained pair is under `artifacts/rust/flatpak-gui-launch-assessment/`.

| Evidence | SHA-256 |
| --- | --- |
| Stock `x11-u36lrntk/result.json` | `f356af31e54ea699d8426580219e7f71c6d926055fdc9928701d6946a9f37693` |
| Candidate `x11-_ign7mu3/result.json` | `42f41a232b135f4469ad10f01daa2ce62558eb74af0565f560bd222486e97a25` |
| `reader-pair-b01ed1b-68d808a.json` | `5ca09398bf8875ebf58b5ca399255926b5ab86774680fdcdb1ebf6a4b0915fde` |
