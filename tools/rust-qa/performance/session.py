"""Private benchmark driver. Use linux.py, which creates the required namespaces."""

from collections import deque
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time

from x11 import Display
from observations import DirectoryReads, Frames


WORK = Path("/qa")
POLL = 0.005
clock = time.monotonic


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


def checked_start(stack, command, log):
    output = stack.enter_context(log.open("w"))
    process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
    stack.callback(stop, process)
    return process


def check_alive(process, log):
    if process.poll() is not None:
        raise RuntimeError(f"{process.args[0]} exited ({process.returncode}): {log.read_text()[-1800:]}")


def wait_for(probe, timeout, message):
    deadline = clock() + timeout
    while True:
        result = probe()
        if result:
            return result
        if clock() >= deadline:
            raise TimeoutError(message)
        time.sleep(POLL)


def private_session(stack):
    Path("/tmp/.X11-unix").mkdir()
    Path("/tmp/.X11-unix").chmod(0o1777)
    config = Path("/tmp/session.conf")
    config.write_text("""<busconfig>
  <type>session</type><listen>unix:path=/tmp/session-bus</listen>
  <auth>EXTERNAL</auth><policy context="default">
    <allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>
  </policy>
</busconfig>
""")  # No service activation directories are configured.
    bus_log = WORK / "dbus.log"
    bus = checked_start(stack, ["dbus-daemon", "--nofork", "--nopidfile",
                                "--config-file", str(config)], bus_log)
    wait_for(lambda: check_alive(bus, bus_log) or Path("/tmp/session-bus").is_socket(),
             10, "Private D-Bus startup timed out")
    if shutil.which("Xvfb"):
        command = ["Xvfb", ":93", "-screen", "0", "1280x900x24"]
    else:
        command = ["Xvnc", ":93", "-geometry", "1280x900", "-depth", "24",
                   "-localhost", "-rfbport", "-1", "-rfbunixpath", "/tmp/private-rfb"]
    command += ["-nolisten", "tcp", "-noreset", "-ac"]
    xlog = WORK / "xserver.log"
    server = checked_start(stack, command, xlog)

    def open_display():
        check_alive(server, xlog)
        try:
            return Display()
        except OSError:
            return None

    display = wait_for(open_display, 15, "Private X11 startup timed out")
    stack.callback(display.close, display.display)
    return display, command[0]


def fresh_profile(profile, media):
    profile.mkdir(mode=0o700)
    environment = os.environ.copy()
    for key, directory in (("HOME", "home"), ("XDG_RUNTIME_DIR", "runtime"),
                           ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                           ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
        path = profile / directory
        path.mkdir(mode=0o700)
        environment[key] = str(path)
    config = profile / "config/immich-folder-watch/config.yaml"
    config.parent.mkdir(mode=0o700)
    config.write_text(f"""immich:
  serverApiUrl: "http://127.0.0.1:9/api"
  apiKey: "synthetic-benchmark"
  allowInsecureHttp: true
watch:
  sources:
    - path: "{media}"
      syncMode: "uploadNew"
      includeSubdirectories: true
      deleteAfterUpload: false
      extensions: [".jpg"]
""")
    return environment


class Subject:
    def __init__(self, stack, spec, profile, media, frames):
        environment = fresh_profile(profile, media)
        self.frames = frames
        if frames:
            environment["IFW_QA_RENDER_FD"] = str(frames.writer)
            if spec["managed"]:
                environment["DOTNET_STARTUP_HOOKS"] = "/qa/AvaloniaFrameProbe.dll"
        self.socket = profile / "runtime/immich-folder-watch.sock"
        self.log = profile / "subject.log"
        self.started = None
        self.completed = []
        self.tail = deque(maxlen=5)
        self.start_time = clock()
        command = ["/runtime/dotnet", "/app/" + spec["entry"]] if spec["managed"] else ["/app/" + spec["entry"]]
        self.process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, errors="replace",
                                        pass_fds=(frames.writer,) if frames else ())
        stack.callback(stop, self.process)

        def consume():
            with self.log.open("w", buffering=1) as out, self.process.stdout as stream:
                for line in stream:
                    observed = clock()
                    out.write(line)
                    self.tail.append(line.rstrip())
                    if spec["start_marker"] in line and self.started is None:
                        self.started = observed
                    if spec["finish_marker"] in line:
                        self.completed.append(observed)

        self.reader = threading.Thread(target=consume, daemon=True)
        self.reader.start()

    def alive(self):
        if self.process.poll() is not None:
            raise RuntimeError(f"Subject exited ({self.process.returncode}): {' | '.join(self.tail)}")

    def probe(self, fn):
        self.alive()
        return fn()

    def show(self):
        with socket.socket(socket.AF_UNIX) as stream:
            stream.settimeout(1)
            stream.connect(str(self.socket))
            stream.sendall(b"SHOW_GUI")

    def usage(self):
        directory = Path("/proc") / str(self.process.pid)
        fields = (directory / "stat").read_text().rsplit(")", 1)[1].split()
        ticks = int(fields[11]) + int(fields[12])  # utime + stime, fields 14 and 15
        for line in (directory / "status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return ticks, int(line.split()[1])
        raise RuntimeError("Subject has no VmRSS")


def action(subject, display, show):
    window = display.visible()
    if bool(window) == show:
        raise RuntimeError("Unexpected visibility before input")
    start = clock()
    if show:
        subject.show()
    else:
        display.request_close(window)
    wait_for(lambda: subject.probe(lambda: bool(display.visible()) == show),
             15, f"Visibility did not change to {show}")
    return start, clock()


def observe(subject, display, seconds, shown):
    if bool(display.visible()) != shown:
        raise RuntimeError("Window visibility does not match measurement phase")
    display.drain()
    ticks, first_rss = subject.usage()
    initial_frames = subject.frames.read() if subject.frames else None
    start = clock()
    rss = [first_rss]
    damage = 0
    while clock() < start + seconds:
        time.sleep(min(0.1, max(0, start + seconds - clock())))
        subject.alive()
        if bool(display.visible()) != shown:
            raise RuntimeError("Window visibility changed during steady measurement")
        damage += display.drain()
        if subject.frames:
            subject.frames.read()
        last_ticks, current_rss = subject.usage()
        rss.append(current_rss)
    elapsed = clock() - start
    metrics = {
        "seconds": round(elapsed, 4),
        "cpu_percent_one_core": round(100 * (last_ticks - ticks) / os.sysconf("SC_CLK_TCK") / elapsed, 3),
        "median_rss_mib": round(statistics.median(rss) / 1024, 3),
        "max_rss_mib": round(max(rss) / 1024, 3),
        "damage_rectangles": damage,
        "damage_rectangles_per_second": round(damage / elapsed, 3),
    }
    if subject.frames:
        frames = subject.frames.read() - initial_frames
        metrics.update(render_passes=frames, render_passes_per_second=round(frames / elapsed, 3))
    return metrics


def run_trial(spec, display, trial, media, phase):
    profile = WORK / f"{phase}-{trial}"
    with ExitStack() as stack:
        display.drain()
        frames = Frames(stack) if phase == "paint" else None
        reads = DirectoryReads(stack, media) if phase == "scan" else None
        subject = Subject(stack, spec, profile, media, frames)
        try:
            wait_for(lambda: subject.probe(display.visible), 60, "Window did not map")
            startup_ms = round(1000 * (clock() - subject.start_time), 2)
            initial_damage = display.drain()
            wait_for(lambda: subject.probe(lambda: subject.started is not None), 60,
                     "Worker scan start not observed")
            if reads:
                return scan_response(subject, display, spec, startup_ms, initial_damage, reads)
            wait_for(lambda: subject.probe(lambda: len(subject.completed) >= spec["passes"]),
                     45, "Empty source reconciliation did not complete")
            time.sleep(3)
            if frames and not (frames.read() and frames.ready):
                raise RuntimeError("Frame counter did not report both attachment and initial rendering")
            shown = observe(subject, display, spec["seconds"], True)
            action(subject, display, False)
            time.sleep(3)
            hidden = observe(subject, display, spec["seconds"], False)
            display.drain()
            before_show = frames.read() if frames else None
            action(subject, display, True)
            # Check this observer really detects presentation changes on the selected server.
            damage_control = wait_for(display.drain, 3, "Show control produced no XDamage")
            result = {"startup_ms": startup_ms, "shown": shown, "hidden": hidden,
                      "show_control_damage_rectangles": damage_control}
            if frames:
                result["show_control_render_passes"] = wait_for(lambda: frames.read() - before_show, 3,
                                                                "Reopening produced no instrumented render pass")
            return result
        except Exception as error:
            raise RuntimeError(f"{error}\nLast application output: {' | '.join(subject.tail)}") from error


def scan_response(subject, display, spec, startup_ms, initial_damage, reads):
    events, visible = [], True
    damage = initial_damage
    deadline = clock() + 240
    while len(subject.completed) < spec["passes"] and clock() < deadline:
        before, after = action(subject, display, not visible)
        visible = not visible
        events.append((before, after, "show" if visible else "close"))
        damage += display.drain()
        time.sleep(0.1)
    if len(subject.completed) < spec["passes"]:
        raise TimeoutError("Reconciliation did not finish before the scan deadline")
    end = subject.completed[spec["passes"] - 1]
    first_read, last_read, directories = reads.scan_bounds(subject.started, end)
    active = [{"input": kind, "at_ms": round(1000 * (before - subject.started), 2),
               "latency_ms": round(1000 * (after - before), 2), "finished_during_directory_reads": after <= last_read}
              for before, after, kind in events if first_read <= before <= last_read]
    return {"startup_ms": startup_ms, "scan_window_seconds": round(end - subject.started, 4),
            "pass_completion_seconds": [round(t - subject.started, 4) for t in subject.completed[:spec["passes"]]],
            "directories_observed": directories,
            "directory_read_interval_ms": [round(1000 * (t - subject.started), 2) for t in (first_read, last_read)],
            "damage_rectangles_through_last_input": damage,
            "input_samples": active}


def run():
    spec = json.loads((WORK / "spec.json").read_text())
    for kind in ("net", "mnt", "pid", "ipc", "user"):
        if os.readlink(f"/proc/self/ns/{kind}") == spec["outer_namespaces"][kind]:
            raise RuntimeError(f"Missing private {kind} namespace")
    if (Path.home() != Path("/tmp/home") or os.environ.get("DISPLAY") != ":93"
            or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"):
        raise RuntimeError("Use the isolated launcher")
    os.umask(0o077)
    Path.home().mkdir()
    if spec["managed"] and spec["measure_render_passes"]:
        references = ["-reference:" + str(path) for path in sorted(Path("/reference-assemblies").glob("*.dll"))]
        subprocess.run(["/runtime/dotnet", "/compiler/csc.dll", "-nologo", "-noconfig", "-nostdlib+",
                        "-target:library", "-deterministic+", "-out:/qa/AvaloniaFrameProbe.dll",
                        *references, "/driver/StartupHook.cs"], check=True)
    empty, tree = WORK / "empty", WORK / "files"
    empty.mkdir()
    tree.mkdir()
    for index in range(spec["files"]):
        folder = tree / f"d{index // 1000:04d}"
        if index % 1000 == 0:
            folder.mkdir()
        (folder / f"fixture-{index:06d}.jpg").touch(exist_ok=False)
    trials = []
    with ExitStack() as stack:
        display, server = private_session(stack)
        for trial in range(1, spec["trials"] + 1):
            print(f"Trial {trial}/{spec['trials']}: measuring idle", flush=True)
            idle = run_trial(spec, display, trial, empty, "idle")
            print(f"Trial {trial}/{spec['trials']}: measuring scan", flush=True)
            scan = run_trial(spec, display, trial, tree, "scan")
            trial_results = {"idle": idle, "scan": scan}
            if spec["measure_render_passes"]:
                print(f"Trial {trial}/{spec['trials']}: counting render passes", flush=True)
                trial_results["paint"] = run_trial(spec, display, trial, empty, "paint")
            trials.append(trial_results)
    (WORK / "results.json").write_text(json.dumps({"xserver": server, "xdamage": display.damage_version,
                                                  "trials": trials}, indent=2) + "\n")


if __name__ == "__main__":
    if sys.platform != "linux":
        sys.exit("Linux is required")
    run()
