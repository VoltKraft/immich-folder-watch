"""Timestamp actual GStreamer buffers received from Mutter's single private virtual output."""

import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time

from session import checked_start, check_alive, wait_for
from wayland import WaylandObserver


class MonitorCapture(WaylandObserver):
    def capture(self, stack, gio, glib):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        os.environ["PIPEWIRE_RUNTIME_DIR"] = "/tmp/runtime"
        os.environ["PIPEWIRE_REMOTE"] = "pipewire-0"
        os.environ["GST_DEBUG_FILE"] = "/qa/gstreamer.log"
        os.environ["GST_DEBUG_NO_COLOR"] = "1"
        os.environ["GST_DEBUG"] = "pipewire*:5,GST_CAPS:4"
        Gst.init(None)
        policy_log = Path("/qa/wireplumber.log")
        policy = checked_start(stack, ["wireplumber"], policy_log)
        def policy_ready():
            check_alive(policy, policy_log)
            clients = subprocess.run(["pw-cli", "ls", "Client"], capture_output=True, text=True, timeout=3, check=True)
            return "WirePlumber" in clients.stdout
        wait_for(policy_ready, 8, "No private PipeWire session policy")
        config = "org.gnome.Mutter.DisplayConfig"
        state = self.bus.call_sync(config, "/org/gnome/Mutter/DisplayConfig", config, "GetCurrentState",
                                   None, None, self.flags, 4000, None).unpack()
        if len(state[1]) != 1:
            raise RuntimeError("The diagnostic requires one private virtual output")
        self.connector = state[1][0][0][0]
        service = "org.gnome.Mutter.ScreenCast"

        def command(path, interface, method, args=None):
            return self.bus.call_sync(service, path, interface, method, args, None, self.flags, 4000, None).unpack()

        session, = command("/org/gnome/Mutter/ScreenCast", service, "CreateSession", self.variant("(a{sv})", ({},)))
        stream, = command(session, service + ".Session", "RecordMonitor", self.variant("(sa{sv})", (self.connector, {})))
        nodes = []
        sub = self.bus.signal_subscribe(service, service + ".Stream", "PipeWireStreamAdded", stream, None,
                                        gio.DBusSignalFlags.NONE, lambda *ev: nodes.append(int(ev[5].unpack()[0])))
        stack.callback(self.bus.signal_unsubscribe, sub)
        command(session, service + ".Session", "Start")

        def stream_node():
            context = glib.MainContext.default()
            while context.pending():
                context.iteration(False)
            return nodes[0] if nodes else None

        node = wait_for(stream_node, 6, "No PipeWire node for the selected monitor")
        Path("/qa/monitor-formats.log").write_text(subprocess.check_output(["pw-cli", "enum-params", str(node), "EnumFormat"],
            text=True, timeout=4))
        self.monitor_events = []
        self.monitor_lock = threading.Lock()
        self.monitor_log = stack.enter_context(Path("/qa/monitor-cadence.jsonl").open("w", buffering=1))
        self.record({"capture": self.connector, "node": node})
        pipe = Gst.parse_launch(f"pipewiresrc path={node} ! video/x-raw,format=BGRx ! identity name=frames ! fakesink sync=false")
        element = pipe.get_by_name("frames")

        def frame(identity, buffer):
            caps = identity.get_static_pad("sink").get_current_caps()
            self.record({"pts_ns": int(buffer.pts), "duration_ns": int(buffer.duration),
                         "bytes": int(buffer.get_size()), "caps": caps.to_string() if caps else None})

        element.connect("handoff", frame)
        stack.callback(pipe.set_state, Gst.State.NULL)
        def received():
            error = pipe.get_bus().pop_filtered(Gst.MessageType.ERROR)
            if error:
                detail, debug = error.parse_error()
                self.record({"consumer_error": str(detail), "debug": str(debug)})
                raise RuntimeError(f"GStreamer {detail}: {debug}")
            return any(e.get("bytes", 0) > 0 for e in self.monitor_events)

        if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            received()
            raise RuntimeError("The monitor consumer could not start")
        wait_for(received, 8,
                 "No actual nonempty video buffer reached the GStreamer sink")

    def record(self, row):
        with self.monitor_lock:
            if len(self.monitor_events) >= 8192:
                raise RuntimeError("Private monitor evidence exceeded its bound")
            entry = dict(monotonic_ns=time.monotonic_ns(), realtime_ns=time.time_ns(), **row)
            self.monitor_events.append(entry)
            self.monitor_log.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def key(self, key, down):
        if hasattr(self, "monitor_log"):
            self.record({"keysym": key, "down": down})
        super().key(key, down)

    def report(self, surfaces):
        with self.monitor_lock:
            events = list(self.monitor_events)
        frames = [e for e in events if e.get("bytes", 0) > 0]
        keys = [e["monotonic_ns"] for e in events if "keysym" in e]
        pts = [e["pts_ns"] for e in frames]
        intervals = [(end - start) / 1e6 for start, end in zip(pts, pts[1:])]
        if not intervals or min(intervals) <= 0 or any(t >= (1 << 64) - 1 for t in pts):
            raise RuntimeError("The selected PipeWire monitor did not provide consecutive timestamped video frames")
        trace = self.log.read_text().replace("@", "#")
        outputs = re.findall(r'wl_output#(\d+)\.name\("' + re.escape(self.connector) + r'"\)', trace)
        membership = {}
        for sid in surfaces:
            observed = re.findall(r"wl_surface#" + re.escape(str(sid)) + r"\.enter\(wl_output#(\d+)\)", trace)
            membership[str(sid)] = sorted(set(observed) & set(outputs))
            if not membership[str(sid)]:
                raise RuntimeError("The application surface did not enter the captured virtual output")
        while_typing = sum(keys[0] <= f["monotonic_ns"] <= keys[-1] for f in frames) if keys else 0
        if keys and while_typing < 2:
            raise RuntimeError("No monitor frame cadence during native keyboard input")
        return dict(connector=self.connector, node=events[0]["node"], output_membership=membership,
                    frame_count=len(frames), distinct_pts=len(set(pts)), frames_during_keyboard=while_typing,
                    buffer_sizes=sorted({f["bytes"] for f in frames}), caps=sorted({f["caps"] for f in frames}),
                    interval_ms=dict(min=round(min(intervals), 3), median=round(statistics.median(intervals), 3),
                                    max=round(max(intervals), 3)))


class MainThreadWaits:
    def __init__(self, stack, subject):
        self.subject = subject
        self.proc = Path("/proc") / str(subject.pid)
        if (self.proc / "exe").resolve() != Path("/app/native-gui-assessment") or subject.pid <= 1:
            raise RuntimeError("The wait diagnostic only observes the launched native GUI in the private PID namespace")
        self.samples = stack.enter_context(Path("/qa/main-thread-waits.jsonl").open("w", buffering=1))
        stopped = threading.Event()

        def run():
            for _ in range(4500):
                if stopped.wait(.025) or subject.poll() is not None:
                    break
                row = {"monotonic_ns": time.monotonic_ns(), "realtime_ns": time.time_ns()}
                for name in ("wchan", "syscall"):
                    try:
                        value = (self.proc / "task" / str(subject.pid) / name).read_text().strip()
                        row[name] = value.split()[0] if value else None
                    except OSError as exc:
                        row[name] = exc.errno
                self.samples.write(json.dumps(row, separators=(",", ":")) + "\n")

        sampling = threading.Thread(target=run, daemon=True)
        sampling.start()
        stack.callback(sampling.join)
        stack.callback(stopped.set)

    def after_timeout(self):
        pid = self.subject.pid
        if self.subject.poll() is not None or (self.proc / "exe").resolve() != Path("/app/native-gui-assessment"):
            return
        log = Path("/qa/main-thread-backtrace.log")
        with log.open("w") as output:
            print(f"monotonic_ns={time.monotonic_ns()} realtime_ns={time.time_ns()} private_pid={pid}", file=output, flush=True)
            command = ["gdb", "-q", "-nx", "-nh", "--batch", "-iex", "set auto-load off",
                       "-iex", "set debuginfod enabled off", "-p", str(pid),
                       "-ex", f"python next(t for t in gdb.selected_inferior().threads() if t.ptid[1] == {pid}).switch()",
                       "-ex", "bt 40", "-ex", "detach"]
            try:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=12,
                                        env={**os.environ, "DEBUGINFOD_URLS": ""})
                print(f"debugger_exit={result.returncode}", file=output)
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(f"debugger_unavailable={type(exc).__name__}", file=output)
