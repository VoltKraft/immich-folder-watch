"""Exercise a Wayland client's real text-input and output events in a private GNOME session."""

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

from gi.repository import Gio, GLib

from desktop_input import Atspi, read_tree, shortcut, start_accessibility, tap
from native import action
from session import check_alive, checked_start, wait_for
from wayland import protocol


WORK = Path("/qa")
DISPLAY_CONFIG = "org.gnome.Mutter.DisplayConfig"
KEY_RIGHT = 0xff53
KEY_LEFT = 0xff51
SHIFT = 0xffe1
SUPER = 0xffeb
ENGINE_IDS = {"anthy": "anthy", "mozc": "mozc-jp"}


def component(ibus_engine):
    path = Path("/usr/share/ibus/component") / (ibus_engine + ".xml")
    record = ET.parse(path).getroot()
    arguments = shlex.split(record.findtext("exec", ""))
    if not arguments:
        raise RuntimeError(f"Missing {ibus_engine} component executable")
    program = Path(arguments[0])
    if not program.is_absolute() or program.name != "ibus-engine-" + ibus_engine:
        raise RuntimeError(f"Unexpected {ibus_engine} component executable: {program}")
    return path, program, record.findtext("name"), record.findtext("version")


def prepare_shell(stack, ime, monitors, ibus_engine):
    os.environ.update(XDG_CURRENT_DESKTOP="GNOME", XDG_SESSION_TYPE="wayland", GSETTINGS_BACKEND="keyfile")
    shell_version = subprocess.check_output(["gnome-shell", "--version"], text=True, timeout=5).split()[-1]
    Gio.Settings.new("org.gnome.desktop.interface").set_boolean("enable-animations", False)
    Gio.Settings.new("org.gnome.shell").set_string("welcome-dialog-last-shown-version", shell_version)
    if monitors:
        settings = Gio.Settings.new("org.gnome.mutter")
        schema = settings.get_property("settings-schema")
        if schema.has_key("experimental-features"):
            key = "experimental-features"
            if "scale-monitor-framebuffer" in str(schema.get_key(key).get_range()):
                settings.set_strv(key, ["scale-monitor-framebuffer"])
    Gio.Settings.sync()
    if not ime:
        return
    # The keyfile and both buses belong to the new namespace. GNOME and its engine
    # must share the same settings even though they run in separate processes.
    os.environ["IBUS_ADDRESS"] = "unix:path=/tmp/ibus-wayland"
    engine_id = ENGINE_IDS[ibus_engine]
    if ibus_engine == "mozc":
        # Mozc starts in Direct mode by default. This per-user setting is
        # supported by the Noble 2.28 engine, including its --xml enumeration.
        config = Path.home() / ".config/mozc/ibus_config.textproto"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('engines { name: "mozc-jp" longname: "Mozc" layout: "default" rank: 80 }\n'
                          'active_on_launch: true\n')
        _, binary, _, _ = component(ibus_engine)
        xml = subprocess.check_output([binary, "--xml"], timeout=5)
        reported = [n.text for n in ET.fromstring(xml).iterfind(".//engine/name")]
        if engine_id not in reported:
            raise RuntimeError(f"The native Mozc component did not declare {engine_id}: {reported}")
        (WORK / "mozc-engines.xml").write_bytes(xml)
        (WORK / "mozc-ibus-config.textproto").write_bytes(config.read_bytes())
    sources = Gio.Settings.new("org.gnome.desktop.input-sources")
    sources.set_value("sources", GLib.Variant("a(ss)", [("ibus", engine_id)]))
    Gio.Settings.sync()
    log = WORK / "ibus.log"
    daemon = checked_start(stack, ["ibus-daemon", "--single", "--verbose", "--emoji-extension=disable",
                                   "--cache=none", "--address=" + os.environ["IBUS_ADDRESS"]], log)
    wait_for(lambda: check_alive(daemon, log) or Path("/tmp/ibus-wayland").is_socket(), 8,
             "Private IBus daemon did not create the requested socket")


def dump(name, data):
    (WORK / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def native_inputs(observer, app, ibus_engine=None):
    paths = {Path("/usr/bin/gnome-shell"), Path(os.environ["VK_DRIVER_FILES"])}
    loaded = re.compile(r"lib(?:mutter-\d+|shell-\d+|wayland-(?:client|server)|vulkan_lvp|ibus-1.0)\.so(?:\..*)?$")
    for pid in (observer.mutter.pid, app.pid):
        for row in Path(f"/proc/{pid}/maps").read_text().splitlines():
            name = row.split()[-1]
            if name.startswith("/") and loaded.fullmatch(Path(name).name):
                paths.add(Path(name))
    engines = []
    description = None
    if ibus_engine:
        metadata, program, bus_name, version = component(ibus_engine)
        description = {"name": bus_name, "version": version, "program": str(program)}
        paths.update((Path("/usr/bin/ibus-daemon"), metadata, program))
        # Only the synthetic processes from our verified private PID namespace
        # are visible. Avoid recording unrelated command lines.
        for process in Path("/proc").glob("[0-9]*"):
            try:
                arguments = (process / "cmdline").read_bytes().decode().strip("\0").split("\0")
            except FileNotFoundError:
                continue
            engine = [Path(a) for a in arguments if a == str(program) or
                      (ibus_engine == "anthy" and a == "/usr/share/ibus-anthy/engine/main.py")]
            if engine and "--xml" not in arguments:
                engines.append({"pid": int(process.name), "entry": str(engine[0])})
                paths.update(engine)
        if not engines:
            raise RuntimeError(f"The active private {ibus_engine} process was missing")
    checksums = {}
    for path in sorted({p.resolve(strict=True) for p in paths}):
        with path.open("rb") as stream:
            checksums[str(path)] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"shell_version": subprocess.check_output(["gnome-shell", "--version"], text=True, timeout=5).strip(),
            "ibus_version": subprocess.check_output(["ibus", "version"], text=True, timeout=5).strip() if ibus_engine else None,
            "readonly_os_files_sha256": checksums, "component": description, "private_engine_processes": engines}


def display_state(observer):
    return observer.bus.call_sync(DISPLAY_CONFIG, "/org/gnome/Mutter/DisplayConfig", DISPLAY_CONFIG,
                                  "GetCurrentState", None, None, observer.flags, 3000, None).unpack()


def configure_outputs(observer, second_scale, *, initial=False):
    serial, monitors, logical, props = display_state(observer)
    raw = {"serial": serial, "monitors": monitors, "logical": logical, "properties": props}
    if initial:
        dump("displays-initial.json", raw)
    if len(monitors) != 2 or len(logical) != 2:
        raise RuntimeError("Two independent Mutter connectors and logical monitors are required")
    # Preserve connector assignment and the active physical modes from Mutter.
    ordered = sorted(logical, key=lambda m: m[0])
    by_name = {physical[0][0]: physical[1] for physical in monitors}
    desired = []
    x = 0
    for index, group in enumerate(ordered):
        name = group[5][0][0]
        mode = next(m for m in by_name[name] if m[6].get("is-current"))
        scale = (1.0, second_scale)[index]
        if scale not in mode[5]:
            raise RuntimeError(f"Connector {name} does not offer requested scale {scale}: {mode[5]}")
        desired.append((x, 0, scale, 0, index == 0, [(name, mode[0], {})]))
        x += round(mode[1] / scale)
    properties = {}
    if props.get("supports-changing-layout-mode"):
        properties["layout-mode"] = GLib.Variant("u", 1)  # Logical
    observer.bus.call_sync(DISPLAY_CONFIG, "/org/gnome/Mutter/DisplayConfig", DISPLAY_CONFIG, "ApplyMonitorsConfig",
        GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 1, desired, properties)),
        None, observer.flags, 3000, None)  # Temporary
    def applied():
        after = display_state(observer)
        logical_after = sorted(after[2], key=lambda group: group[0])
        observed = [(g[0], g[1], g[2], g[3], g[4], g[5][0][0]) for g in logical_after]
        expected = [(g[0], g[1], g[2], g[3], g[4], g[5][0][0]) for g in desired]
        return after if observed == expected else None
    after = wait_for(applied, 5, "Mutter did not apply the requested logical positions and scales")
    dump(f"displays-applied-{second_scale}.json", after)
    return [g[5][0][0] for g in desired]


def app_surface(trace):
    tops = re.findall(r'xdg_toplevel#(\d+)\.set_title\("Desktop input probe"\)', trace)
    if not tops:
        return None
    xdg = re.search(r"xdg_surface#(\d+)\.get_toplevel\(new id xdg_toplevel#" + tops[-1] + r"\)", trace)
    return re.search(r"get_xdg_surface\(new id xdg_surface#" + xdg[1] + r", wl_surface#(\d+)\)", trace)[1]


def keyboard_focus(trace, surface):
    devices = {}
    for event in re.finditer(r"wl_keyboard#(\d+)\.(enter|leave)\(\d+, (?:wl_surface#(\d+)|nil)", trace):
        devices[event[1]] = event[3] if event[2] == "enter" else None
    return [device for device, focused in devices.items() if focused == surface]


def attached_frame(trace, surface, scale, start):
    """Resolve an actual committed root buffer, retaining object-ID reuse in wire order."""
    viewport = re.search(r"get_viewport\(new id wp_viewport#(\d+), wl_surface#" + surface + r"\)", trace)
    if not viewport:
        return None
    pattern = re.compile(
        r"wl_shm_pool#\d+\.create_buffer\(new id wl_buffer#(?P<buffer>\d+), \d+, (?P<w>\d+), (?P<h>\d+), [^)]*\)"
        r"|wp_viewport#" + viewport[1] + r"\.set_destination\((?P<vw>\d+), (?P<vh>\d+)\)"
        r"|wl_surface#" + surface + r"\.attach\(wl_buffer#(?P<attached>\d+), [^)]*\)"
        r"|wl_surface#" + surface + r"\.(?P<commit>commit)\(\)")
    buffers = {}
    logical = None
    pending = None
    for event in pattern.finditer(trace):
        if event["buffer"]:
            buffers[event["buffer"]] = ([int(event["w"]), int(event["h"])], event[0])
        elif event["vw"]:
            logical = [int(event["vw"]), int(event["vh"])]
        elif event["attached"]:
            pending = (event["attached"], event[0]) if event.start() >= start else None
        elif pending and logical and pending[0] in buffers:
            dimensions, creation = buffers[pending[0]]
            if all(pixels * 120 == points * scale for pixels, points in zip(dimensions, logical)):
                return {"buffer": pending[0], "pixels": dimensions, "viewport_logical": logical,
                        "create": creation, "attach": pending[1], "commit": event[0]}
            pending = None
    return None


def output_observation(log, surface, connector, scale, start, previous):
    trace = protocol(log.read_text())
    outputs = re.findall(r'wl_output#(\d+)\.name\("' + re.escape(connector) + r'"\)', trace)
    if not outputs:
        return None
    output = outputs[-1]
    xdg = re.search(r"get_xdg_output\(new id zxdg_output_v1#(\d+), wl_output#" + output + r"\)", trace)
    if not xdg:
        return None
    geometry = {}
    for field in ("logical_position", "logical_size"):
        values = re.findall(r"zxdg_output_v1#" + xdg[1] + r"\." + field + r"\((-?\d+), (-?\d+)\)", trace)
        if not values:
            return None
        geometry[field] = [int(i) for i in values[-1]]
    fraction = re.search(r"get_fractional_scale\(new id wp_fractional_scale_v1#(\d+), wl_surface#" + surface + r"\)", trace)
    if not fraction:
        return None
    preferred = f"wp_fractional_scale_v1#{fraction[1]}.preferred_scale({scale})"
    offset = trace.find(preferred, start)
    if offset < 0:
        return None
    events = re.findall(r"wl_surface#" + surface + r"\.(enter|leave)\(wl_output#(\d+)\)", trace)
    current = set()
    for action_name, native_output in events:
        if action_name == "enter":
            current.add(native_output)
        else:
            current.discard(native_output)
    if current != {output}:
        return None
    membership = re.findall(r"wl_surface#" + surface + r"\.(?:enter|leave)\(wl_output#\d+\)", trace[start:])
    if previous is None or previous["connector"] != connector:
        if f"wl_surface#{surface}.enter(wl_output#{output})" not in membership:
            return None
        if previous and f"wl_surface#{surface}.leave(wl_output#{previous['output']})" not in membership:
            return None
    frame = attached_frame(trace, surface, scale, offset)
    keyboards = keyboard_focus(trace, surface)
    if not frame or not keyboards:
        return None
    return {"surface": surface, "connector": connector, "output": output, "preferred_scale": preferred,
            "scale_120ths": scale, "surface_membership_events": membership, "focused_wl_keyboards": keyboards,
            **geometry, "frame": frame}


def accessible_frame_bounds(pid):
    try:
        # The desktop also contains GNOME/IBus clients. Resolve the selected
        # application by its bus credentials before querying any frame.
        desktop = Atspi.get_desktop(0)
        desktop.clear_cache()
        for i in range(min(64, desktop.get_child_count())):
            app = desktop.get_child_at_index(i)
            if not app or app.get_process_id() != pid:
                continue
            app.clear_cache()
            for j in range(min(24, app.get_child_count())):
                frame = app.get_child_at_index(j)
                if not frame or frame.get_role() != Atspi.Role.FRAME or frame.get_name() != "Desktop input probe":
                    continue
                frame.clear_cache()
                coordinates = {}
                for name, space in (("screen", Atspi.CoordType.SCREEN), ("window", Atspi.CoordType.WINDOW)):
                    bounds = frame.get_extents(space)
                    coordinates[name] = [bounds.x, bounds.y, bounds.width, bounds.height]
                return coordinates
        return None
    except GLib.Error as error:
        # A just-mapped client may still be registering its tree. The caller
        # bounds retries and requires both coordinate queries to succeed.
        if error.domain != "atspi_error" or error.code != 1:
            raise
        with (WORK / "atspi-registration.log").open("a") as out:
            print(str(error), file=out)
        return None


def check_monitors(observer, log, connectors, app):
    surface = wait_for(lambda: app_surface(protocol(log.read_text())), 5, "No application-owned titled surface")
    steps = []
    sequence = [("initial", 0, 120), ("move right", 1, 240), ("change active output scale", 1, 150),
                ("move left", 0, 120)]
    for action_name, index, scale in sequence:
        start = len(protocol(log.read_text())) if steps else 0
        server_at = observer.log.stat().st_size if steps else 0
        if action_name == "change active output scale":
            configure_outputs(observer, scale / 120)
        elif action_name in ("move right", "move left"):
            shortcut(observer, KEY_RIGHT if index else KEY_LEFT, SUPER, SHIFT)
        connector = connectors[index]
        step = wait_for(lambda: output_observation(log, surface, connector, scale, start, steps[-1] if steps else None),
                        8, f"No fresh output and committed {scale}/120 frame on {connector}")
        with observer.log.open("rb") as stream:
            stream.seek(server_at)
            server = protocol(stream.read().decode())
        events = [step["preferred_scale"], *step["surface_membership_events"]]
        frame = step["frame"]
        attach = server.find(frame["attach"], server.find(frame["create"]))
        if (not all(event in server for event in events) or frame["create"] not in server
                or attach < 0 or frame["commit"] not in server[attach:]):
            raise RuntimeError(f"The private compositor did not corroborate the output and frame on {connector}")
        _, physical, logical, _ = display_state(observer)
        group = next(g for g in logical if g[5][0][0] == connector)
        modes = next(m[1] for m in physical if m[0][0] == connector)
        mode = next(m for m in modes if m[6].get("is-current"))
        expected_size = [round(dimension / group[2]) for dimension in mode[1:3]]
        if (step["logical_position"] != list(group[0:2]) or step["logical_size"] != expected_size
                or group[2] * 120 != scale):
            raise RuntimeError("Client output geometry and Mutter logical-monitor state differ")
        observer.focus_for_input()
        step["atspi_frame_bounds"] = wait_for(lambda: accessible_frame_bounds(app.pid), 5,
                                               "The independent AT-SPI reader did not find the titled frame")
        step["action"] = action_name
        steps.append(step)
        dump("monitor-steps.json", steps)
    return steps


def check_ime(observer, log, app, ibus_engine):
    import gi
    gi.require_version("IBus", "1.0")
    from gi.repository import IBus
    bus = IBus.Bus.new()
    def engine():
        value = bus.get_global_engine()
        return value.get_name() if value else None
    engine_id = ENGINE_IDS[ibus_engine]
    wait_for(lambda: bus.is_connected() and engine() == engine_id, 10,
             f"GNOME Shell did not select the configured private {engine_id} engine")
    def filename():
        return next((n for n in read_tree(app.pid) if n["name"] == "Dateiname" and n.get("focused")), None)
    for _ in range(6):
        if filename():
            break
        tap(observer, 0xff09)
        time.sleep(.12)
    if not filename():
        raise RuntimeError("The independent AT-SPI reader did not find a focused filename")
    context = bus.current_input_context()
    if not context or not context.startswith("/org/freedesktop/IBus/InputContext_"):
        raise RuntimeError("IBus did not report a focused input context")
    dump("native-inputs.json", native_inputs(observer, app, ibus_engine))
    shortcut(observer, ord("a"), 0xffe3)
    tap(observer, 0xff08)
    wait_for(lambda: filename() and filename()["text"] == "", 4, "The selected field did not clear")
    at = len(log.read_text())
    server_at = observer.log.stat().st_size
    tap(observer, ord("a"))
    def preedit():
        text = protocol(log.read_text()[at:])
        return re.search(r'zwp_text_input_v3#(\d+)\.preedit_string\("あ",', text) and "IME preedit chars=1" in text
    wait_for(preedit, 6, "No Wayland preedit with Japanese text reached the assessment app")
    tap(observer, 0xff0d)
    def committed():
        field = filename()
        return field and field["text"] == "あ" and "IME commit chars=1" in log.read_text()[at:]
    wait_for(committed, 6, f"The private {engine_id} Return did not commit あ into the focused field")
    trace = protocol(log.read_text())
    surface = app_surface(trace)
    stages = protocol(log.read_text()[at:])
    offered = re.search(r'zwp_text_input_v3#(\d+)\.preedit_string\("あ",[^)]*\)', stages)
    ime_object = "zwp_text_input_v3#" + offered[1]
    commit = re.search(re.escape(ime_object) + r'\.commit_string\("あ"\)', stages)
    keyboards = keyboard_focus(trace, surface)
    rectangles = re.findall(re.escape(ime_object) + r"\.set_cursor_rectangle\((-?\d+), (-?\d+), (\d+), (\d+)\)", trace)
    if (not commit or not keyboards or not rectangles or ime_object + ".enter(wl_surface#" + surface + ")" not in trace
            or ime_object + ".enable()" not in trace):
        raise RuntimeError("Input context, focused surface, and native Wayland commit must match")
    with observer.log.open("rb") as stream:
        stream.seek(server_at)
        server = protocol(stream.read().decode())
    if offered[0] not in server or commit[0] not in server:
        raise RuntimeError("The compositor did not independently emit the same preedit and commit")
    field = filename()
    result = {"global_engine": engine(), "ibus_address": os.environ["IBUS_ADDRESS"], "focused_input_context": context,
            "configured_sources": Gio.Settings.new("org.gnome.desktop.input-sources").get_value("sources").unpack(),
            "surface": surface, "focused_wl_keyboards": keyboards, "last_surface_local_cursor_rectangle": rectangles[-1],
            "client_and_compositor_preedit": offered[0], "client_and_compositor_commit": commit[0],
            "field": field, "egui": [s for s in stages.splitlines() if s.startswith("IME ")]}
    if ibus_engine == "mozc":
        # The conversion server is a separate program from the IBus adapter.
        servers = []
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                executable = (proc / "exe").readlink()
            except (FileNotFoundError, PermissionError):
                continue
            if executable.is_relative_to("/usr") and executable.name == "mozc_server":
                with executable.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                servers.append({"pid": int(proc.name), "program": str(executable), "sha256": digest})
        if not servers:
            raise RuntimeError("The Mozc conversion server was missing from the private desktop")
        result["conversion_servers"] = servers
    return result


def exercise(stack, observer, *, ime, monitors, ibus_engine):
    result = {}
    wait_for(lambda: "GNOME Shell started at " in observer.log.read_text(), 12, "Private GNOME startup did not complete")
    def shell_property(method, args):
        return observer.bus.call_sync("org.gnome.Shell", "/org/gnome/Shell", "org.freedesktop.DBus.Properties",
                                      method, args, None, observer.flags, 3000, None).unpack()
    prop = ("org.gnome.Shell", "OverviewActive")
    shell_property("Set", GLib.Variant("(ssv)", (*prop, GLib.Variant("b", False))))
    wait_for(lambda: not shell_property("Get", GLib.Variant("(ss)", prop))[0], 4, "Desktop overview remained open")
    if monitors:
        connectors = configure_outputs(observer, 2.0, initial=True)
    start_accessibility(stack)
    log = WORK / "gnome-input-application.log"
    app = checked_start(stack, ["env", "WAYLAND_DEBUG=client", "/app/native-gui-assessment"], log)
    wait_for(lambda: check_alive(app, log) or observer.poll(), 12, "The assessment app did not map")
    observer.focus_for_input()
    if monitors:
        result["monitor_transitions"] = check_monitors(observer, log, connectors, app)
    if ime:
        result["composition"] = check_ime(observer, log, app, ibus_engine)
    else:
        dump("native-inputs.json", native_inputs(observer, app))
    action("quit")
    if app.wait(timeout=8) != 0:
        raise RuntimeError("The private GNOME assessment application did not shut down")
    return result
