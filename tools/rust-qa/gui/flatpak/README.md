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
registry was therefore reachable from the ref. Screen-reader access to the
installed editor remains open. The installed observation ends at AT-SPI
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
