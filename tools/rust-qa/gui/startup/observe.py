"""Read the elected GUI's initial editor and tray labels in four synthetic Fedora sessions."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
WORK = Path("/qa")
CASES = {
    "saved-en": ("de_DE.UTF-8", "en", "en"),
    "saved-de": ("en_US.UTF-8", "de", "de"),
    "system-de": ("de_DE.UTF-8", None, "de"),
    "system-en": ("en_US.UTF-8", None, "en"),
}
LABELS = {"de": (["Dateiname", "Kennwort", "English", "Beenden"], ["GUI öffnen", "Neustart", "Beenden"]),
          "en": (["Filename", "Password", "Deutsch", "Quit"], ["Open GUI", "Restart", "Quit"])}


def digest(path):
    with path.open("rb") as contents:
        return hashlib.file_digest(contents, "sha256").hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inside():
    sys.path[:0] = ["/gui", "/driver"]
    from desktop_input import Gio, GLib, read_x11_tree, start_accessibility
    from native import BUS_NAME, X11Observer, desktop_owner
    from session import check_alive, checked_start, fresh_profile, private_session, stop, wait_for

    parameters = json.loads((WORK / "input.json").read_bytes())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or any(os.readlink(f"/proc/self/ns/{key}") == value for key, value in parameters["namespaces"].items())):
        raise ValueError("Use the private GUI startup launcher")
    os.umask(0o077)
    Path.home().mkdir()
    Path("/tmp/runtime").mkdir()
    media = WORK / "files"
    media.mkdir()
    (media / "first.jpg").write_bytes(b"first synthetic file")
    locale, setting, expected = CASES[parameters["case"]]
    env = fresh_profile(WORK / "profile", media)
    config = Path(env["XDG_CONFIG_HOME"]) / "immich-folder-watch/config.yaml"
    if setting:
        with config.open("a", encoding="utf-8") as stream:
            stream.write(f"localization:\n  language: {setting}\n")
    before = digest(config)
    env.update(HOME="/tmp/home", XDG_RUNTIME_DIR="/tmp/runtime", LC_ALL=locale)
    editor, menu = LABELS[expected]
    log = WORK / "primary.log"
    with ExitStack() as stack:
        display, server = private_session(stack)
        observer = X11Observer(display)
        enabled = start_accessibility(stack)
        primary = subprocess.Popen(["/app/native-gui-assessment"], stdout=stack.enter_context(log.open("w")),
                                   stderr=subprocess.STDOUT, env=env)
        stack.callback(stop, primary)
        window = wait_for(lambda: check_alive(primary, log) or observer.poll(), 15, "The editor did not open")
        observer.focus_for_input()

        def read_editor():
            check_alive(primary, log)
            tree = read_x11_tree(primary.pid)
            controls = [row for row in tree if row["name"] in editor and row["role"] in
                        ("text", "entry", "password text", "button", "push button")]
            return controls if {row["name"] for row in controls} == set(editor) else None

        controls = wait_for(lambda: enabled() and read_editor(), 8, "The initial accessible editor language differs")
        owner = desktop_owner()
        if (owner["pid"] != primary.pid or "READY Visible Unavailable" not in log.read_text()
                or not Path(f"/proc/{primary.pid}/exe").samefile("/app/native-gui-assessment")):
            raise ValueError("The initial editor did not belong to the elected primary without a tray")
        watcher_log = WORK / "watcher.log"
        watcher = checked_start(stack, [sys.executable, "/gui/watcher.py"], watcher_log)
        registered = f"REGISTERED {BUS_NAME} {owner['busName']}"
        wait_for(lambda: check_alive(watcher, watcher_log) or registered in watcher_log.read_text().splitlines(), 8,
                 "The new watcher did not receive the original GUI's registration")
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        def call(path, interface, method, args):
            return bus.call_sync(owner["busName"], path, interface, method, args, None,
                                 Gio.DBusCallFlags.NONE, 3000, None).unpack()
        path, = call("/StatusNotifierItem", "org.freedesktop.DBus.Properties", "Get",
                     GLib.Variant("(ss)", ("org.kde.StatusNotifierItem", "Menu")))
        revision, (root, _, rows) = call(path, "com.canonical.dbusmenu", "GetLayout",
                                        GLib.Variant("(iias)", (0, -1, ["label"])))
        entries = [(row[0], row[1]["label"]) for row in rows]
        if root != 0 or revision != 1 or entries != list(enumerate(menu, 1)) or observer.poll() != window:
            raise ValueError(f"The first registered menu differs: {revision}, {entries}")
        wait_for(lambda: check_alive(primary, log) or "INVENTORY_COMPLETE files=1 changed=0 pass=1"
                 in log.read_text().splitlines(), 8, "Initial inventory did not finish")
        pid, = re.findall(r"^INVENTORY_WORKER pid=(\d+)$", log.read_text(), re.M)
        proc = Path("/proc") / pid
        if (not (proc / "exe").samefile("/app/ifw-performance-worker")
                or int((proc / "stat").read_text().rsplit(")", 1)[1].split()[1]) != primary.pid):
            raise ValueError("The running child differs from the supplied worker")
        fd = os.pidfd_open(int(pid))
        stack.callback(os.close, fd)
        poll = select.poll()
        poll.register(fd, select.POLLIN)
        (media / "second.jpg").write_bytes(b"second synthetic file")
        observed = wait_for(lambda: re.search(r"^INVENTORY_COMPLETE files=2 changed=1 pass=\d+$",
                            log.read_text(), re.M), 8, "The original child missed the new file")
        worker = {"pid": int(pid), "scan": observed[0], "executableSha256": digest(proc / "exe")}
        call(path, "com.canonical.dbusmenu", "Event", GLib.Variant("(isvu)", (3, "clicked", GLib.Variant("i", 0), 0)))
        status = primary.wait(timeout=12)
        lines = log.read_text().splitlines()
        has_owner, = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                   "NameHasOwner", GLib.Variant("(s)", (BUS_NAME,)), None,
                                   Gio.DBusCallFlags.NONE, 3000, None).unpack()
        if (status != 0 or has_owner or observer.poll() or not re.fullmatch(r"DRAINED passes=[1-9]\d*", lines[-1])
                or digest(config) != before):
            raise ValueError("Menu Quit, worker drain, or settings preservation failed")
        worker["exit"] = f"WORKER_EXIT pid={worker['pid']} reason=quit success=true"
        if worker["exit"] not in lines or not poll.poll(0):
            raise ValueError("The original inventory child did not exit on Quit")
        write(WORK / "result.json", {"case": parameters["case"], "locale": locale, "saved": setting,
                                     "expected": expected, "editor": controls, "tray": entries, "revision": revision,
                                     "owner": owner, "registered": registered, "display": server, "window": hex(window),
                                     "drained": lines[-1], "exit": status, "worker": worker,
                                     "configurationSha256BeforeAndAfter": before})


def launch(args):
    root = GUI.parents[2]
    sys.path.insert(0, str(GUI.parent / "performance"))
    from linux import namespace
    output = args.output.resolve()
    if not output.is_relative_to(root / "artifacts/rust") or output.exists():
        raise ValueError("Supply a fresh output directory under artifacts/rust")
    gui = args.gui.resolve(strict=True)
    worker = args.worker.resolve(strict=True) / "ifw-performance-worker"
    compiled = args.compiler_receipt.resolve(strict=True)
    build = json.loads(compiled.read_bytes())
    if build["target"] != platform.machine() + "-unknown-linux-gnu" or digest(gui) != build["binarySha256"]:
        raise ValueError("GUI bytes differ from the verified native compiler receipt")
    if "compilerSources" in build:
        sys.path.insert(0, str(GUI))
        from compiler_inputs import linux_project_sources
        paths = {p.relative_to(root).as_posix(): digest(p) for p in linux_project_sources(root)}
        if (paths.pop("tools/rust-qa/gui/Cargo.lock") != build["lockSha256"] or paths != build["compilerSources"]
                or digest(compiled.parent / "compiler.jsonl") != build["compilerStreamSha256"]
                or digest(compiled.parent / "graph.json") != build["graphSha256"]
                or digest(compiled.parent / "registry-sources.json") != build["registryReceiptSha256"]):
            raise ValueError("The ordinary GUI no longer matches its sources or compiler archive")
    receipt = worker.parent / "worker.inputs.json"
    binding = json.loads(receipt.read_bytes())
    worker_sources = json.loads((GUI.parent / "performance/worker-inputs.json").read_bytes())
    if (digest(worker) != binding["worker_sha256"] or worker_sources != binding["sources"]
            or any(digest(root / name) != checksum for name, checksum in worker_sources.items())):
        raise ValueError("Worker bytes differ from its native compiler receipt")
    output.mkdir(parents=True)
    shutil.copyfile(compiled, output / "gui-compiler.json")
    app = output / "app"
    app.mkdir()
    for original, name in ((gui, "native-gui-assessment"), (worker, "ifw-performance-worker")):
        shutil.copy2(original, app / name)
    drivers = [Path(__file__), GUI / "native.py", GUI / "desktop_input.py", GUI / "watcher.py",
               *(GUI.parent / "performance" / name for name in ("linux.py", "session.py", "x11.py", "observations.py"))]
    write(output / "inputs.json", {"guiSha256": digest(gui), "workerSha256": digest(worker),
                                   "guiCompilerReceiptSha256": digest(compiled), "workerReceiptSha256": digest(receipt),
                                   "drivers": {str(p.relative_to(root)): digest(p) for p in drivers}})
    for name in CASES:
        directory = output / name
        directory.mkdir()
        write(directory / "input.json", {"case": name,
                                         "namespaces": {k: os.readlink(f"/proc/self/ns/{k}")
                                                        for k in ("user", "net", "ipc", "pid", "mnt")}})
        command = namespace(directory, app, None, desktop_spike=True)
        command[command.index("--chdir"):] = ["--ro-bind", str(GUI), "/gui", "--setenv", "XDG_RUNTIME_DIR",
            "/tmp/runtime", "--setenv", "GSETTINGS_BACKEND", "memory", "--setenv", "LP_NUM_THREADS", "2",
            "--chdir", "/qa", "--", "/usr/bin/python3", "-B", "/gui/startup/observe.py", "--inside"]
        subprocess.run(command, check=True)
    # Use the same synthetic files that the elected GUI and worker actually read.
    sys.path.insert(0, str(GUI.parent / "yaml/startup"))
    import compare as shipping
    environment = {"HOME": str(output), "PATH": "/usr/bin:/bin", "DOTNET_CLI_HOME": str(output),
                   "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_EnableDiagnostics": "0"}
    reference = shipping.oracle(args.sdk.resolve(strict=True), args.signed_repo.resolve(strict=True), output, environment)
    results = {}
    for name, (locale, setting, expected) in CASES.items():
        directory = output / name
        home = directory / "profile"
        config = home / "config/immich-folder-watch/config.yaml"
        result = json.loads((directory / "result.json").read_bytes())
        dotnet = shipping.read(reference, home, {**environment, "HOME": str(home / "home"),
                                                 "LC_ALL": locale, "XDG_CONFIG_HOME": str(home / "config")})
        if (dotnet["language"] != expected or dotnet["setting"] != (setting or "auto") or dotnet["read"] != "loaded"
                or dotnet["path"] != str(config) or digest(config) != result["configurationSha256BeforeAndAfter"]):
            raise ValueError(f"The installed 3.0.4 configuration or culture readback differs for {name}: {dotnet}")
        results[name] = dict(result, shipping=dotnet)
    write(output / "results.json", {"cases": results, "signedCommit": shipping.REVISION,
                                     "signedAssemblies": shipping.ASSEMBLIES,
                                     "referenceSourceSha256": digest(GUI.parent / "yaml/startup/Reference.cs")})


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--gui", type=Path, required=True)
        parser.add_argument("--worker", type=Path, required=True, help="Original source-bound worker subject directory")
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--sdk", type=Path, required=True, help="Pinned local .NET SDK root")
        parser.add_argument("--signed-repo", type=Path, required=True, help="Local original shipping OSTree repository")
        parser.add_argument("--compiler-receipt", type=Path, required=True,
                            help="build.json from the ordinary native build or native.json from qualify.py")
        launch(parser.parse_args())
