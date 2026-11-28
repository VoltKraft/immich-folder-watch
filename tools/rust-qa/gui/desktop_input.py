"""Read the private AccessKit/AT-SPI tree while sending native keyboard events."""

import json
import os
from pathlib import Path
import subprocess
import time
from functools import partial

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib

from native import action, call, second_launch
from session import checked_start, check_alive, wait_for


def nodes(target_pid):
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)
    queue = [Atspi.get_desktop(0)]
    result = []
    while queue and len(result) < 64:
        item = queue.pop(0)
        if not item:
            continue
        item.clear_cache()
        if item.get_role() == Atspi.Role.APPLICATION and item.get_process_id() != target_pid:
            continue
        result.append(item)
        queue.extend(item.get_child_at_index(i) for i in range(min(24, item.get_child_count())))
    return result


def read_tree(target_pid, filename_selection=False):
    result = []
    for item in nodes(target_pid):
        entry = {"role": item.get_role_name(), "name": item.get_name()}
        if item.get_role() == Atspi.Role.APPLICATION:
            entry["process_id"] = item.get_process_id()
        entry["focused"] = item.get_state_set().contains(Atspi.StateType.FOCUSED)
        if item.get_text_iface() is not None:
            entry["text"] = Atspi.Text.get_text(item, 0, -1)
            if entry["role"] == "password text" and entry["text"].strip("•"):
                raise RuntimeError("The password field exposed unmasked text")
            if filename_selection and entry["name"] == "Filename" and entry["role"] in ("entry", "text"):
                entry["caret"] = Atspi.Text.get_caret_offset(item)
                entry["selections"] = []
                for index in range(Atspi.Text.get_n_selections(item)):
                    marks = Atspi.Text.get_selection(item, index)
                    entry["selections"].append([marks.start_offset, marks.end_offset])
        result.append(entry)
    Path("/qa/last-accessibility-tree.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def read_x11_tree(target_pid, filename_selection=False):
    # A desktop child can lose its Accessible interface between enumeration
    # and its next D-Bus call. Discard that scan and start at the desktop again.
    for attempt in range(4):
        try:
            return read_tree(target_pid, filename_selection)
        except GLib.Error as error:
            if (error.domain != "atspi_error" or error.code != 1
                    or error.message != "Unknown interface 'org.a11y.atspi.Accessible'" or attempt == 3):
                raise
            print(f"Retrying X11 accessibility scan for PID {target_pid}: {error}", flush=True)
            time.sleep(.05)


def filename_snapshot(tree):
    snapshot = tree()
    if any(n["name"] == "Dateiname" and n["role"] in ("text", "entry") for n in snapshot):
        return snapshot
    return None


def tap(observer, key):
    observer.key(key, True)
    observer.key(key, False)


def shortcut(observer, key, *modifiers):
    for modifier in modifiers:
        observer.key(modifier, True)
    tap(observer, key)
    for modifier in reversed(modifiers):
        observer.key(modifier, False)


def check_reopened_selection(stack, observer, app, log, tree, backend, original):
    evidence = {"primaryPid": app.pid}
    path = Path("/qa/selection-reopen.json")

    def expect(stage, value, caret, selections):
        def matches():
            check_alive(app, log)
            field = next((n for n in tree(filename_selection=True) if "selections" in n), None)
            evidence[stage] = field
            return (field and field["focused"] and field["text"] == value
                    and field["caret"] == caret and field["selections"] == selections)

        try:
            wait_for(matches, 6, f"Unexpected filename focus, text, caret or selection at {stage}. See {path}")
        finally:
            path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")

    tap(observer, 0xff50)  # Home
    for _ in range(5):
        tap(observer, 0xff53)  # Right
    for _ in range(3):
        shortcut(observer, 0xff51, 0xffe1)  # Shift+Left selects üße backwards
    expect("beforeClose", original, 2, [[2, 5]])

    original_window = observer.poll()
    evidence["close"] = observer.close()
    state = "WINDOW_HIDDEN" if backend == "x11" else "WINDOW_RELEASED"
    wait_for(lambda: check_alive(app, log) or (not observer.poll() and state in log.read_text()),
             10, f"Native close did not reach {state}")
    evidence["secondLaunch"] = second_launch(stack, app, Path("/qa/input-secondary.log"))
    reopened_window = wait_for(lambda: check_alive(app, log) or observer.poll(), 10,
                               "Second launch did not reopen the window")
    if backend == "x11":
        if reopened_window != original_window:
            raise RuntimeError("X11 did not reopen the retained window")
        # The private X server has no window manager to focus the remapped
        # top-level. Give it keyboard input, without focusing a widget.
        evidence["focusedX11TopLevel"] = reopened_window
    observer.focus_for_input()
    expect("afterReopen", original, 2, [[2, 5]])
    # Moving the active end distinguishes a backwards selection from a
    # forwards selection with the same AT-SPI start and end offsets.
    shortcut(observer, 0xff51, 0xffe1)
    expect("afterShiftLeft", original, 1, [[1, 5]])
    tap(observer, ord("x"))
    expect("afterReplacement", original[:1] + "x" + original[5:], 2, [])
    return evidence


def ibus_start(stack):
    os.environ.update(IBUS_ADDRESS="unix:path=/tmp/ibus-probe", XMODIFIERS="@im=ibus")
    log = Path("/qa/ibus.log")
    ibus = checked_start(stack, ["ibus-daemon", "--single", "--xim", "--verbose", "--emoji-extension=disable", "--cache=none",
                                 "--address=unix:path=/tmp/ibus-probe"], log)
    wait_for(lambda: check_alive(ibus, log) or Path("/tmp/ibus-probe").is_socket(),
             5, "Private IBus daemon did not create its socket")
    subprocess.run(["ibus", "engine", "xkb:us::eng"], check=True, timeout=5)
    def owns_xim():
        prop = subprocess.run(["xprop", "-root", "XIM_SERVERS"], capture_output=True, text=True)
        return "@server=ibus" in prop.stdout
    wait_for(owns_xim, 5, "IBus XIM server did not own its native X selection")


def start_accessibility(stack):
    at_log = Path("/qa/atspi.log")
    launcher = checked_start(stack, ["/usr/libexec/at-spi-bus-launcher", "--launch-immediately"], at_log)

    def address():
        check_alive(launcher, at_log)
        try:
            return call("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus.GetAddress")
        except Exception:
            return None

    wait_for(address, 5, "Private AT-SPI bus did not start")
    call("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties.Set",
         "org.a11y.Status", "IsEnabled", "<true>")
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    def enabled():
        value, = bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties",
                               "Get", GLib.Variant("(ss)", ("org.a11y.Status", "IsEnabled")),
                               GLib.VariantType.new("(v)"), Gio.DBusCallFlags.NONE, 2000, None).unpack()
        return value is True
    wait_for(enabled, 3, "The private accessibility service did not enable AT-SPI")
    Atspi.set_timeout(1500, 2500)
    return enabled


def check_input(stack, observer, backend, ime, screen_reader=False):
    # The private session deliberately has no dconf writer.
    os.environ["GSETTINGS_BACKEND"] = "memory"
    enabled = start_accessibility(stack)
    reader = None
    if screen_reader:
        from screen_reader import ScreenReader
        reader = ScreenReader(stack)
    if ime:
        ibus_start(stack)
    log = Path("/qa/input-app.log")
    app = checked_start(stack, ["/app/native-gui-assessment"], log)
    tree = partial(read_x11_tree if backend == "x11" else read_tree, app.pid)
    wait_for(lambda: check_alive(app, log) or observer.poll(), 10, "Input probe did not map")
    observer.focus_for_input()
    if not enabled():
        raise RuntimeError("The accessibility service disabled AT-SPI before window registration")
    initial = wait_for(lambda: filename_snapshot(tree), 8, "Editable filename missing from the accessibility tree")
    names = {(node["role"], node["name"]) for node in initial}
    if (("password text", "Kennwort") not in names
            or not names.intersection({("push button", "English"), ("button", "English")})):
        raise RuntimeError("Password field or language button does not have its accessible name or role")
    if reader:
        # Start once the reader has announced the actual language button. Tab then
        # traverses all four tested controls, including the first editable filename.
        for _ in range(6):
            if any(n["focused"] and n["name"] == "English" for n in tree()):
                break
            tap(observer, 0xff09)
            time.sleep(.12)
        else:
            raise RuntimeError("Could not position native focus before the speech traversal")
        reader.begin()
    traversal = []
    for _ in range(6):
        tap(observer, 0xff09)  # Tab
        time.sleep(.10)
        focus = [n for n in tree() if n["focused"] and n["name"] in ("Dateiname", "Kennwort", "English")]
        if focus:
            traversal.append(focus[0]["name"])
            if reader:
                reader.wait_label(focus[0]["name"])
        if traversal and traversal[-1] == "Kennwort":
            break
    if not traversal or traversal[-1] != "Kennwort":
        raise RuntimeError("Keyboard focus did not reach the password field")
    for size, key in enumerate("xyz", start=1):
        tap(observer, ord(key))
        wait_for(lambda: any(n["role"] == "password text" and len(n.get("text", "")) == size for n in tree()),
                 3, f"Missing masked character {size}. See input-app.log and last-accessibility-tree.json")
    masked = wait_for(lambda: next((n.get("text") for n in tree() if n["role"] == "password text"
                                    and len(n.get("text", "")) == 3), None), 3, "Missing masked AT-SPI text")
    if masked != "•" * 3:
        raise RuntimeError("Password text did not expose exactly three mask characters")
    tap(observer, 0xff09)
    time.sleep(.1)
    if not any(n["focused"] and n["name"] == "English" for n in tree()):
        raise RuntimeError("Tab did not reach the language button")
    traversal.append("English")
    if reader:
        reader.wait_label("English")
    tap(observer, 0x20)
    wait_for(lambda: any(n["name"] == "Filename" for n in tree()), 3, "Keyboard language switch failed")
    english = tree()
    details = {"backend": backend, "initial": initial, "tab_order": traversal, "password_accessible_text": masked,
               "after_keyboard_language_switch": english}
    tap(observer, 0xff09)
    if any(n["name"] == "Quit" and n["role"] in ("push button", "button") for n in english):
        wait_for(lambda: any(n["name"] == "Quit" and n["focused"] for n in tree()), 3, "Quit focus missing")
        traversal.append("Quit")
        tap(observer, 0xff09)
    wait_for(lambda: any(n["name"] == "Filename" and n["focused"] for n in tree()), 3, "Filename focus missing")
    if reader:
        reader.wait_label("Filename")
    shortcut(observer, ord("a"), 0xffe3)  # Control
    shortcut(observer, ord("c"), 0xffe3)
    owner = wait_for(observer.clipboard_owner, 3, "No native clipboard selection owner")
    tap(observer, 0xff08)  # Backspace
    wait_for(lambda: any(n["name"] == "Filename" and n.get("text") == "" for n in tree()), 3,
             "Filename did not clear before paste")
    shortcut(observer, ord("v"), 0xffe3)
    original = "Grüße – Sommer.jpg"
    wait_for(lambda: any(n["name"] == "Filename" and n.get("text") == original for n in tree()),
             3, "Unicode filename did not round-trip through native copy and paste")
    details["clipboard"] = {"text": original, "native_owner_or_selection_serial": owner}
    if reader is not None:
        details["screen_reader"] = reader.result()
    details["selectionReopen"] = check_reopened_selection(stack, observer, app, log, tree, backend, original)
    if ime:
        shortcut(observer, ord("a"), 0xffe3)
        engine_log = Path("/qa/anthy.log")
        native_engine = checked_start(stack, ["/usr/libexec/ibus-engine-anthy"], engine_log)
        gi.require_version("IBus", "1.0")
        from gi.repository import IBus
        engine_bus = IBus.Bus.new()
        def registered():
            check_alive(native_engine, engine_log)
            return any(e.get_name() == "anthy" for e in engine_bus.list_active_engines())
        wait_for(registered, 10, "Anthy did not register on the private IBus connection")
        # The IBus CLI also tries to replace the XKB layout. Anthy uses the
        # existing private layout, so ask and verify the daemon directly.
        if not engine_bus.set_global_engine("anthy"):
            raise RuntimeError("The private IBus daemon refused the Anthy engine")
        engine = engine_bus.get_global_engine()
        if engine is None or engine.get_name() != "anthy":
            raise RuntimeError("The active private IBus engine did not change to Anthy")
        Path("/qa/ime-selection.json").write_text(json.dumps({
            "engine": engine.get_name(), "layout": engine.get_layout(), "connected": engine_bus.is_connected(),
        }, indent=2))
        tap(observer, ord("a"))
        wait_for(lambda: "IME preedit chars=1" in log.read_text(), 4, "No native Anthy preedit reached egui")
        tap(observer, 0xff0d)  # Return
        wait_for(lambda: any(n["name"] == "Filename" and n.get("text") == "あ" for n in tree()),
                 4, "IBus did not commit the synthetic Japanese character")
        stages = [line for line in log.read_text().splitlines() if line.startswith("IME ")]
        if not any(line.startswith("IME preedit chars=") and line != "IME preedit chars=0" for line in stages):
            raise RuntimeError("Filename changed without a non-empty native composition preedit")
        if "IME commit chars=1" not in stages:
            raise RuntimeError("No native composition commit for the single Japanese character")
        details["ime"] = {"engine": "IBus Anthy via XIM", "text": "あ", "events": stages}
    action("quit")
    if app.wait(timeout=8) != 0:
        raise RuntimeError("Input fixture failed to shut down")
    return details
