"""Observe the editor's real Quit button after its private Linux watcher disappears."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
WORK = Path("/qa")
WATCHER = "org.kde.StatusNotifierWatcher"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside():
    sys.path[:0] = ["/driver", "/gui"]
    from desktop_input import Atspi, nodes, read_x11_tree, start_accessibility, tap
    from native import BUS_NAME, X11Observer, call, desktop_owner, second_launch
    from profile_text import ink
    from session import checked_start, check_alive, fresh_profile, private_session, stop, wait_for

    inputs = json.loads((WORK / "inputs.json").read_bytes())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or any(os.readlink(f"/proc/self/ns/{key}") == value for key, value in inputs["namespaces"].items())):
        raise RuntimeError("Use the isolated tray loss observer")
    os.umask(0o077)
    Path.home().mkdir()
    Path("/tmp/runtime").mkdir()
    media = WORK / "files"
    media.mkdir()
    (media / "first.jpg").write_bytes(b"one")
    env = fresh_profile(WORK / "profile", media)
    os.environ["XDG_CONFIG_HOME"] = env["XDG_CONFIG_HOME"]
    with ExitStack() as stack:
        display, server = private_session(stack)
        x = X11Observer(display)
        enabled = start_accessibility(stack)
        watcher_log = WORK / "watcher.log"
        watcher = checked_start(stack, [sys.executable, "/gui/watcher.py"], watcher_log)
        wait_for(lambda: check_alive(watcher, watcher_log) or "WATCHER_READY" in watcher_log.read_text(),
                 5, "Private watcher did not acquire its name")
        log = WORK / "primary.log"
        primary = checked_start(stack, ["/app/native-gui-assessment"], log)
        window = wait_for(lambda: check_alive(primary, log) or x.poll(), 15, "Primary did not map")
        x.focus_for_input()
        def sample():
            return read_x11_tree(primary.pid)
        def button(tree, label):
            return next((n for n in tree if n["name"] == label and n["role"] in ("button", "push button")), None)
        def focus(label):
            for _ in range(8):
                node = button(sample(), label)
                if node and node["focused"]:
                    return node
                tap(x, 0xff09)
                time.sleep(.12)
            raise ValueError(f"Keyboard did not reach {label}")
        def notice(prefix):
            return next((n["name"] for n in sample() if n["name"] and n["name"].startswith(prefix)), None)
        def has_owner(name):
            answer = call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus.NameHasOwner", name)
            if answer not in ("(true,)", "(false,)"):
                raise ValueError("Unexpected bus ownership reply")
            return answer == "(true,)"

        wait_for(lambda: enabled() and button(sample(), "Beenden"), 8, "No accessible Quit button")
        ready = log.read_text()
        if ("READY Visible Available" not in ready or "REGISTERED " + BUS_NAME not in watcher_log.read_text()
                or notice("Kein Tray-Symbol") or not has_owner(WATCHER)):
            raise RuntimeError("The observed primary did not start with acknowledged tray registration")
        owner = desktop_owner()
        if owner["pid"] != primary.pid:
            raise ValueError("Unexpected application bus owner")
        match = re.search(r"^INVENTORY_WORKER pid=(\d+)$", ready, re.M)
        pid = int(match[1])
        proc = Path(f"/proc/{pid}")
        worker_fd = os.pidfd_open(pid)
        stack.callback(os.close, worker_fd)
        poll = select.poll()
        poll.register(worker_fd, select.POLLIN)
        if (int((proc / "stat").read_text().rsplit(")", 1)[1].split()[1]) != primary.pid
                or not (proc / "exe").samefile("/app/ifw-performance-worker")):
            raise ValueError("Unexpected child or worker image")
        wait_for(lambda: "INVENTORY_COMPLETE files=1 changed=0 pass=1" in log.read_text(), 8,
                 "The original worker did not finish its second initial scan")
        stop(watcher)
        wait_for(lambda: not has_owner(WATCHER), 3, "Watcher name is still owned")
        german = wait_for(lambda: notice("Kein Tray-Symbol"), 5, "Missing German tray notice")
        focus("English")
        tap(x, 0x20)
        english = wait_for(lambda: notice("No tray icon"), 5, "Missing English tray notice")
        if not button(sample(), "Quit") or x.poll() != window:
            raise ValueError("The fallback changed the window or omitted the translated Quit button")
        x.close()
        wait_for(lambda: check_alive(primary, log) or not x.poll(), 5, "Window remained mapped after Close")
        (media / "hidden.jpg").write_bytes(b"two")
        hidden_scan = wait_for(lambda: re.search(r"^INVENTORY_COMPLETE files=2 changed=1 pass=\d+$",
                                                 log.read_text(), re.M), 9, "Closed window stalled the original worker")
        if x.poll() or poll.poll(0) or desktop_owner() != owner:
            raise ValueError("The hidden primary or its original worker changed")
        reopened = second_launch(stack, primary, WORK / "secondary.log")
        wait_for(lambda: x.poll() == window, 5, "The ordinary launch did not remap the original window")
        x.focus_for_input()
        after = wait_for(lambda: notice("No tray icon"), 5, "Missing notice after the ordinary second launch")
        quit_button = focus("Quit")
        node = next(n for n in nodes(primary.pid) if n.get_name() == "Quit" and n.get_component_iface()
                    and n.get_state_set().contains(Atspi.StateType.FOCUSED))
        box = Atspi.Component.get_extents(node, Atspi.CoordType.WINDOW)
        quit_button["bounds"] = [box.x, box.y, box.width, box.height]
        quit_button["pixels"] = ink(display, window, quit_button["bounds"])
        tap(x, 0x20)
        primary.wait(timeout=12)
        lines = log.read_text().splitlines()
        exits = [line for line in lines if line.startswith("WORKER_EXIT ")]
        if (after != english or primary.returncode != 0 or not poll.poll(0) or has_owner(BUS_NAME) or x.poll()
                or exits != [f"WORKER_EXIT pid={pid} reason=quit success=true"]
                or [line for line in lines if line.startswith("INVENTORY_WORKER ")] != [f"INVENTORY_WORKER pid={pid}"]
                or not re.fullmatch(r"DRAINED passes=[1-9]\d*", lines[-1])):
            raise ValueError("The visible Quit button did not drain the original processes")
        report = {"display": server, "window": hex(window), "watcherExited": watcher.returncode,
                  "primary": owner, "workerPid": pid, "hiddenScan": hidden_scan[0], "secondLaunch": reopened,
                  "germanNotice": german, "englishNotice": english, "reopenedNotice": after,
                  "keyboardQuit": quit_button, "primaryExit": primary.returncode, "workerExit": exits[0],
                  "workerPidfdExited": True, "drained": lines[-1], "applicationNameReleased": True}
        (WORK / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def launch(subject):
    root = HERE.parents[2]
    sys.path.insert(0, str(HERE.parent / "performance"))
    from linux import namespace
    subject = subject.resolve(strict=True)
    if not subject.is_relative_to(root / "artifacts/rust/performance/subjects"):
        raise ValueError("Supply the private subject built by performance/build_worker.py")
    gui, worker = subject / "native-gui-assessment", subject / "ifw-performance-worker"
    build = json.loads(gui.with_suffix(".inputs.json").read_bytes())
    pair = json.loads((subject / "worker.inputs.json").read_bytes())
    if (build["target"] != f"{platform.machine()}-unknown-linux-gnu"
            or sha(gui) != build["binary_sha256"] or sha(gui) != pair["gui_sha256"]
            or sha(worker) != pair["worker_sha256"] or any(sha(root / key) != value
            for record in (build, pair) for key, value in record["sources"].items())):
        raise ValueError("The paired worker, GUI or current sources differ from the compiler receipts")
    parent = root / "artifacts/rust/gui-run"
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="tray-loss-quit-", dir=parent))
    print(output, flush=True)
    drivers = (Path(__file__), HERE / "native.py", HERE / "watcher.py", HERE / "desktop_input.py", HERE / "profile_text.py",
               *(HERE.parent / "performance" / f for f in ("linux.py", "session.py", "x11.py", "observations.py")))
    inputs = {"gui": build, "worker": pair, "drivers": {str(p.relative_to(root)): sha(p) for p in drivers},
              "namespaces": {k: os.readlink(f"/proc/self/ns/{k}") for k in ("user", "net", "ipc", "pid", "mnt")}}
    (output / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    command = namespace(output, subject, None, desktop_spike=True)
    command[command.index("--chdir"):] = ["--ro-bind", str(HERE), "/gui", "--setenv", "XDG_RUNTIME_DIR", "/tmp/runtime",
        "--setenv", "GSETTINGS_BACKEND", "memory", "--setenv", "LP_NUM_THREADS", "2", "--chdir", "/qa", "--",
        "/usr/bin/python3", "-B", "/gui/tray_loss_quit.py", "--inside"]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    elif len(sys.argv) == 2:
        launch(Path(sys.argv[1]))
    else:
        raise SystemExit("Expected the paired GUI and worker subject directory")
