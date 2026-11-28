"""Observe an ordinary second process, its primary and the live inventory worker on private X11."""
import hashlib
import ctypes
import os
from pathlib import Path
import select
import signal
import subprocess
import time


GUI = Path("/app/native-gui-assessment")
WORKER = Path("/app/ifw-performance-worker")
BUS = "org.freedesktop.DBus"


def identity(pid):
    directory = Path("/proc") / str(pid)
    def fields():
        return (directory / "stat").read_text().rsplit(")", 1)[1].split()
    before = fields()
    image = directory / "exe"
    name = os.readlink(image)
    info = image.stat()
    after = fields()
    if before[19] != after[19] or before[1] != after[1]:
        raise ProcessLookupError("Process identity changed during observation")
    return dict(pid=pid, parent=int(after[1]), startTicks=int(after[19]), executable=name,
                device=info.st_dev, inode=info.st_ino)


def workers():
    result = []
    for directory in Path("/proc").iterdir():
        if directory.name.isdecimal():
            try:
                if os.readlink(directory / "exe") == str(WORKER):
                    result.append(identity(int(directory.name)))
            except (FileNotFoundError, ProcessLookupError):
                continue
    return sorted(result, key=lambda item: item["pid"])


def query_bus(subject, method, name):
    return subject.bus.call_sync(BUS, "/org/freedesktop/DBus", BUS, method,
                                 subject.glib.Variant("(s)", (name,)), None,
                                 subject.gio.DBusCallFlags.NO_AUTO_START, 1000, None).unpack()[0]


def bus_owner(subject):
    name = query_bus(subject, "GetNameOwner", "org.example.IfwGuiProbe")
    return {"name": name, "pid": query_bus(subject, "GetConnectionUnixProcessID", name)}


def quit_primary(subject, original, liveness, report):
    from session import stop
    result = report["primaryCleanup"] = {}
    try:
        # Even a failed control can transfer the well-known name to a different
        # process. Direct Quit to the original, independently verified connection.
        name = original["owner"]["name"]
        if (subject.process.poll() is not None or identity(subject.process.pid) != original["primary"]
                or query_bus(subject, "GetConnectionUnixProcessID", name) != subject.process.pid):
            raise RuntimeError("The pinned primary connection or process is unavailable at cleanup")
        subject.bus.call_sync(name, "/org/example/IfwGuiProbe", "org.freedesktop.Application", "ActivateAction",
                              subject.glib.Variant("(sava{sv})", ("quit", [], {})), None,
                              subject.gio.DBusCallFlags.NO_AUTO_START, 3000, None)
        result["quitDestination"] = name
        subject.process.wait(timeout=8)
    except (OSError, RuntimeError, subject.glib.Error, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    finally:
        stop(subject.process)
    subject.reader.join(timeout=2)
    result.update(exit=subject.process.returncode, bothProcessesExited=len(liveness.poll(0)) == 2,
                  drained=not subject.reader.is_alive() and any(line.startswith("DRAINED passes=") for line in subject.tail))


def visible_pid(window):
    result = subprocess.check_output(["xprop", "-id", str(window), "_NET_WM_PID"], text=True, timeout=2).strip()
    prefix = "_NET_WM_PID(CARDINAL) = "
    if not result.startswith(prefix) or not result[len(prefix):].isdecimal():
        raise ValueError("X11 did not report the window's PID")
    return int(result[len(prefix):])


def reap_secondary(child, report):
    # Keep the leader waitable until the group is signalled. Its PID cannot be
    # recycled into another group while we clean up a failed, long-lived GUI.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    report["exit"] = child.wait(timeout=3)
    orphans = report["reapedDescendants"] = []
    deadline = time.monotonic() + 3
    while True:
        try:
            pid, status = os.waitpid(-child.pid, os.WNOHANG)
        except ChildProcessError:
            break
        if pid:
            orphans.append({"pid": pid, "exit": os.waitstatus_to_exitcode(status)})
        elif time.monotonic() >= deadline:
            raise RuntimeError("A secondary descendant did not terminate inside its private process group")
        else:
            time.sleep(.01)


def launch(subject, display, arguments, environment, before, window, report):
    if display.visible() is not None:
        raise RuntimeError("Launch requires the original window to be hidden")
    report.update(arguments=arguments, hiddenBefore=True, samples=[])
    output = Path("/qa") / ("second-background.log" if arguments else "second-ordinary.log")
    with output.open("wb") as log:
        child = subprocess.Popen([GUI, *arguments], env=environment, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        report["secondaryPid"] = child.pid
        start = time.monotonic()
        try:
            while True:
                subject.alive()
                sample = {"workers": workers(), "visibleXid": display.visible()}
                try:
                    sample["owner"] = bus_owner(subject)
                except subject.glib.Error as error:
                    sample["ownerError"] = str(error)
                if not report["samples"] or report["samples"][-1]["state"] != sample:
                    report["samples"].append({"ms": round((time.monotonic() - start)*1000), "state": sample})
                status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if status is not None and (status.si_code != os.CLD_EXITED or status.si_status != 0
                                           or sample["visibleXid"] == window):
                    break
                if time.monotonic() - start >= 8:
                    report["timeout"] = True
                    break
                time.sleep(.025)
        finally:
            reap_secondary(child, report)
            report["elapsedMs"] = round((time.monotonic() - start) * 1000)
    with output.open("rb") as log:
        log.seek(max(0, output.stat().st_size - 2048))
        report["outputTail"] = log.read().decode(errors="replace")
    if any(item["state"].get("owner") != before["owner"] or item["state"]["workers"] != before["workers"]
           for item in report["samples"]):
        raise RuntimeError("A second launch changed the primary D-Bus owner or the inventory worker set")
    if report.get("timeout") or report["exit"] != 0 or report["reapedDescendants"]:
        raise RuntimeError("The secondary failed to exit successfully and reopen the window before the deadline")
    if display.visible() != window or visible_pid(window) != subject.process.pid:
        raise RuntimeError("The second process did not reopen the original primary's retained X11 window")
    report["reopenedXid"] = window


def observe(stack, subject, display, leaf, window, report):
    from session import action, wait_for
    # Inside this isolated PID namespace, adopt any worker left behind by a
    # failed secondary. waitpid below only reaps that launch's process group.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "Cannot supervise secondary descendants")
    primary = identity(subject.process.pid)
    if primary["executable"] != str(GUI) or visible_pid(window) != primary["pid"]:
        raise ValueError("The original mapped window must belong to the staged executable")
    baseline = report["before"] = {"primary": primary, "owner": bus_owner(subject), "workers": workers(), "xid": window}
    if (baseline["owner"]["pid"] != primary["pid"] or len(baseline["workers"]) != 1
            or baseline["workers"][0]["parent"] != primary["pid"]):
        raise ValueError("Expected the original GUI and its single inventory worker")
    liveness = select.poll()
    for pid in (primary["pid"], baseline["workers"][0]["pid"]):
        fd = os.pidfd_open(pid)
        stack.callback(os.close, fd)
        liveness.register(fd, select.POLLIN)
    stack.callback(quit_primary, subject, baseline, liveness, report)
    raw = (Path("/proc") / str(primary["pid"]) / "environ").read_bytes()
    environment = dict(row.split(b"=", 1) for row in raw.split(b"\0") if row)
    if (environment.get(b"HOME") != b"/tmp/home" or environment.get(b"XDG_CONFIG_HOME") != b"/qa/hidden/config"
            or environment.get(b"IFW_QA_BENCHMARK") != b"1" or environment.get(b"IFW_QA_ISOLATED") != b"1"
            or environment.get(b"DBUS_SESSION_BUS_ADDRESS") != b"unix:path=/tmp/session-bus"):
        raise ValueError("Expected the original subject's private GUI environment")
    report["environmentSha256"] = hashlib.sha256(raw).hexdigest()
    attempts = report["launches"] = []
    for arguments in ([], ["--background"]):
        action(subject, display, False)
        attempt = {}
        attempts.append(attempt)
        launch(subject, display, arguments, environment, baseline, window, attempt)
    previous = len(subject.inventories)
    start = time.monotonic()
    # Creating a child changes directory mtime and ctime. Enumerating the
    # directory changes atime. Only the subject enumerates this synthetic leaf.
    original = leaf.stat()
    marker = 1_000_000_000
    os.utime(leaf, ns=(marker, original.st_mtime_ns))
    if leaf.stat().st_atime_ns != marker:
        raise RuntimeError("Could not mark the synthetic leaf's directory access time")
    (leaf / "after-second-launch.jpg").touch(exist_ok=False)
    def discovered():
        subject.alive()
        return next((row for row in subject.inventories[previous:] if row[:2] == (1, 1)), None)
    changed = wait_for(discovered, 12, "The original worker did not discover the file after activation")
    stop = time.monotonic()
    seen = leaf.stat()
    report["postLaunchInventory"] = dict(entry=changed, seconds=round(stop-start, 4), directoryInode=seen.st_ino,
                                        directoryDevice=seen.st_dev, beforeAccessNs=marker, afterAccessNs=seen.st_atime_ns)
    if seen.st_atime_ns <= marker or (seen.st_dev, seen.st_ino) != (original.st_dev, original.st_ino):
        raise RuntimeError("The synthetic leaf lacks an independent directory-access observation")
    after = report["after"] = {"primary": identity(subject.process.pid), "owner": bus_owner(subject),
                               "workers": workers(), "xid": display.visible()}
    if after != baseline or liveness.poll(0) or visible_pid(window) != primary["pid"]:
        raise RuntimeError("The original primary, worker or visible client changed")
    action(subject, display, False)
