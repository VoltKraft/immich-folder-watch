"""Inside observer for the existing recovery scenario's stationary and closed Wayland window."""

import os
from pathlib import Path
import time

from desktop_input import read_tree, tap
from original_scenarios import TrayStatus, WaylandCommits, pixels, start_accessibility
from original_scenarios import exercise as exercise_graphics
from original_scenarios import worker_identity
from session import check_alive, wait_for


def cpu_seconds(pid):
    # proc(5) fields 14 and 15, following the final parenthesis of the command name.
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def exercise(stack, case, process, observer, damage, frames, log, media, tray, *, require_queue_completion):
    result = exercise_graphics(stack, case, process, observer, damage, frames, log, media, tray,
                               require_queue_completion=require_queue_completion)
    worker = result["initial_worker"]

    def idle(visible):
        time.sleep(1)
        check_alive(process, log)
        if bool(observer.poll()) != visible:
            raise RuntimeError("Unexpected Wayland window state before idle sampling")
        damage.drain()
        before_events = len(observer.events)
        before = time.monotonic()
        cpu_before = cpu_seconds(process.pid) + cpu_seconds(worker["pid"])
        time.sleep(15)
        used = cpu_seconds(process.pid) + cpu_seconds(worker["pid"]) - cpu_before
        elapsed = time.monotonic() - before
        commits = damage.drain()
        if bool(observer.poll()) != visible or any(event["event"] in ("map", "unmap")
                                                    for event in observer.events[before_events:]):
            raise RuntimeError("The application's window changed visibility during idle sampling")
        if worker_identity(process.pid) != worker or commits > int(visible):
            raise RuntimeError(f"Post-recovery idle: visible={visible}, observed {commits} application frames")
        return {"seconds": round(elapsed, 4), "root_buffer_commits": commits,
                "gui_and_worker_cpu_percent_one_core": round(used * 100 / elapsed, 4)}

    # Move native focus out of the blinking filename editor for stationary-window
    # measurement. The original scenario already read its post-recovery native key.
    def focused_control():
        return next((node for node in read_tree(process.pid) if node.get("focused") and node["role"]
                     in ("entry", "password text", "button")), None)
    current = wait_for(focused_control, 4, "The recovered editor lacks focus")
    for _ in range(4):
        if current["role"] == "button":
            break
        tap(observer, 0xff09)
        current = wait_for(lambda: (node if (node := focused_control()) and node != current else None), 4,
                           "Native Tab did not move focus to the next control")
    if current["role"] != "button":
        raise RuntimeError("A stationary button must have focus before the visible idle interval")
    result["stationary_control"] = current
    result["visible_idle_after_recovery"] = idle(True)
    observer.close()
    wait_for(lambda: not observer.poll() and "WINDOW_RELEASED" in log.read_text(), 8,
             "Compositor close did not release the recovered window")
    result["hidden_idle_after_recovery"] = idle(False)
    return result
