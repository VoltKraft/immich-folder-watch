"""Read the native runner's aggregate Remote Desktop settings, listening state and WTS session counts."""
from collections import Counter
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STATES = ("active", "connected", "connect-query", "shadow", "disconnected", "idle", "listen", "reset", "down", "init")


class Session(c.Structure):
    _fields_ = [("id", c.c_uint32), ("station", c.c_void_p), ("state", c.c_int)]


def session_counts():
    wts = c.WinDLL("wtsapi32", use_last_error=True)
    enumerate_sessions = wts.WTSEnumerateSessionsW
    enumerate_sessions.argtypes = [c.c_void_p, c.c_uint32, c.c_uint32, c.POINTER(c.POINTER(Session)), c.POINTER(c.c_uint32)]
    enumerate_sessions.restype = c.c_int
    protocol = wts.WTSQuerySessionInformationW
    protocol.argtypes = [c.c_void_p, c.c_uint32, c.c_int, c.POINTER(c.c_void_p), c.POINTER(c.c_uint32)]
    protocol.restype = c.c_int
    free = wts.WTSFreeMemory
    free.argtypes, free.restype = [c.c_void_p], None
    rows, count = c.POINTER(Session)(), c.c_uint32()
    if not enumerate_sessions(None, 0, 1, c.byref(rows), c.byref(count)):
        return {"status": "unavailable", "counts": []}
    try:
        if count.value > 1024 or (count.value and not rows):
            return {"status": "unavailable", "counts": []}
        groups = Counter()
        for index in range(count.value):
            row = rows[index]
            state = STATES[row.state] if 0 <= row.state < len(STATES) else "other"
            value, size = c.c_void_p(), c.c_uint32()
            kind = "unavailable"
            if protocol(None, row.id, 16, c.byref(value), c.byref(size)):
                try:
                    if value and size.value == c.sizeof(c.c_uint16):
                        code = c.cast(value, c.POINTER(c.c_uint16)).contents.value
                        kind = {0: "console", 1: "legacy", 2: "rdp"}.get(code, "other")
                finally:
                    if value:
                        free(value)
            groups[(state, kind)] += 1
        return {"status": "observed", "counts": [dict(state=state, protocol=kind, count=n)
                                                 for (state, kind), n in sorted(groups.items())]}
    finally:
        if rows:
            free(rows)


def main():
    if (os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ARCH") != "ARM64"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or os.environ.get("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.environ.get("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise ValueError("Use the native ARM64 rewrite runner")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if revision != os.environ["GITHUB_SHA"]:
        raise ValueError("The venue observation and workflow sources differ")
    script = HERE / "venue.ps1"
    program = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    response = subprocess.check_output([program, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script],
                                       stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    settings = json.loads(response)
    if (set(settings) != {"allowTSConnections", "policySource", "termService", "configuredPortListeners"}
            or not (type(settings["allowTSConnections"]) is bool or settings["allowTSConnections"] == "unavailable")
            or settings["policySource"] not in ("server", "group-policy", "unavailable")
            or settings["termService"] not in ("Stopped", "Start Pending", "Stop Pending", "Running", "Continue Pending",
                                               "Pause Pending", "Paused", "Unknown", "unavailable")
            or settings["configuredPortListeners"] not in ("none", "loopback-only", "other-or-any", "unavailable")):
        raise ValueError("Unexpected data in the aggregate desktop settings")
    sources = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in (Path(__file__).resolve(), script)}
    record = dict(source=revision, run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                  target="aarch64-pc-windows-msvc", inputs=sources, settings=settings, wts=session_counts())
    output = ROOT / "artifacts/rust/windows-display-venue"
    output.mkdir(parents=True, exist_ok=False)
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
