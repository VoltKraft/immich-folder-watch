"""Observe the live GUI's own retries after a refused initial add on the input desktop."""
import time


def observe(native, proc, windows, log, result, *, records, read_rect):
    registration = result["registration"]
    key = tuple(str(registration[k]) for k in ("pid", "hwnd", "iconId"))
    initial = ("initial", *key, native.token, "0", "0")
    report = result["afterRefusedAdd"] = {"observations": []}
    if not native.witness or not native.witness.live("beforeRetryObservation"):
        report["end"] = "original Explorer unavailable"
        return
    # The first two normal backoff intervals are three and six seconds.
    # Let the application's receiver schedule every attempt on its own.
    start = time.monotonic()
    seen = []
    while True:
        windows.pump()
        if proc.poll() is not None:
            raise ValueError("The primary exited while observing its refused tray registration")
        text = log()
        rows = records(text, "TRAY_REGISTER")
        if (not rows or rows[0] != initial or rows[1:1 + len(seen)] != seen
                or any(row[1:5] != (*key, native.token) for row in rows)):
            raise ValueError("The integrated receiver or its registration history changed")
        elapsed = time.monotonic() - start
        if any(row[0] != "retry" for row in rows[1:]) or any(
                line.startswith(("TRAY_HOST ", "TRAY_TASKBAR ")) for line in text.splitlines()):
            report["end"] = "Shell change observed"
            break
        if len(rows) > 1 + len(seen):
            seen = rows[1:]
            owner = native.desk.window(registration["hwnd"])
            if (not owner or any(owner[k] != registration["receiver"][k] for k in ("pid", "tid", "class", "hwnd"))
                    or not native.witness.live("afterRetry" + str(len(seen)))):
                report["end"] = "original Explorer or receiver unavailable"
                break
            shell = read_rect(registration["hwnd"])
            report["observations"].append(dict(elapsedMs=round(elapsed * 1000), registrations=list(seen),
                                               receiver=owner, independentIcon=shell))
            if seen[-1][-2:] == ("1", "1"):
                report["end"] = "v4 acknowledgement observed"
                break
            if len(seen) >= 2:
                report["end"] = "two automatic retries observed"
                break
        if elapsed >= 15:
            report["end"] = "observation deadline"
            break
        time.sleep(.1)
    report["sameExplorerAtEnd"] = native.witness.live("afterRetryObservation")
    report["elapsedMs"] = round((time.monotonic() - start) * 1000)
