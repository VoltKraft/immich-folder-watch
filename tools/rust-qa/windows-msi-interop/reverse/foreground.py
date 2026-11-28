"""Read the original ARM64 Default desktop's WPF and foreground roots without sending input."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import PureWindowsPath

from common import require


def _owner(desk, hwnd):
    pid = w.DWORD()
    tid = desk.owner(hwnd, c.byref(pid))
    return pid.value, tid


def _window(desk, desktop, session, hwnd, expected=None):
    # Membership in the held desktop is checked before reading a foreign class or image.
    identity = _owner(desk, hwnd)
    if (not all(identity) or (expected is not None and identity != expected)
            or desk.pid_session(identity[0]) != session or desk.ancestor(hwnd, 2) != hwnd
            or desk.count_top_level_window(desktop, hwnd) != 1):
        return None
    raw = desk.window(hwnd)
    if (not raw or (raw["pid"], raw["tid"]) != identity or _owner(desk, hwnd) != identity
            or desk.count_top_level_window(desktop, hwnd) != 1):
        return None
    # Desktop.window already reduces the executable path to its basename.
    return {"class": raw["class"], "basename": raw["executable"], "bounds": raw["rect"],
            "desktop": "Default", "session": session}


class ForegroundSamples:
    """Sample one held WPF lifetime. The nested rows contain no foreign handles, IDs or captions."""

    def __init__(self, enabled, launch, api, desk, desktop, session, proc, row):
        self.enabled = enabled
        self.launch, self.api, self.desk = launch, api, desk
        self.desktop, self.session, self.proc, self.row = desktop, session, proc, row

    def original(self):
        state = self.desk.context()
        return (state["session"] == self.session and self.launch.ordinary_console(state, "Default")
                and self.desk.thread_desktop(self.desk.thread()) == self.desktop
                and self.proc.poll() is None
                and self.api.process_identity(int(self.proc._handle)) == self.row["primary"]["created"])

    def record(self, key):
        if not self.enabled:
            return
        sample = self.row[key] = dict(beginQpc=self.api.clock(), root=None, foreground=None, relation="unavailable")
        desk, original = self.desk, self.row["root"]
        own = original["hwnd"]
        identity = (self.proc.pid, original["tid"])
        try:
            if not self.original() or original["pid"] != self.proc.pid:
                return
            root = _window(desk, self.desktop, self.session, own, identity)
            if not root:
                return
            first = desk.foreground()
            top = desk.ancestor(first, 2) if first else None  # GA_ROOT
            if not first:
                relation, fg = "none", None
            elif top == own:
                relation, fg = "wpfRoot", root
            else:
                fg = _window(desk, self.desktop, self.session, top) if top else None
                relation = "otherRoot" if fg else "unavailable"
            if self.original() and _owner(desk, own) == identity and desk.ancestor(own, 2) == own:
                if desk.foreground() != first or (first and desk.ancestor(first, 2) != top):
                    relation, fg = "changed", None
                sample.update(root=root, foreground=fg, relation=relation)
        except OSError as exc:
            # A transient native query cannot confer mouse or keyboard ownership.
            sample["win32Error"] = exc.winerror if getattr(exc, "winerror", None) is not None else exc.errno
        finally:
            sample["endQpc"] = self.api.clock()


def verify(row, key, session):
    """Replay a diagnostic, including an absent or changing foreground."""
    sample = row[key]
    required = {"beginQpc", "endQpc", "root", "foreground", "relation"}
    require(set(sample) in (required, required | {"win32Error"})
            and all(type(sample[k]) is int for k in ("beginQpc", "endQpc"))
            and 0 < sample["beginQpc"] <= sample["endQpc"], "Invalid foreground observation interval")
    root, fg, relation = sample["root"], sample["foreground"], sample["relation"]
    def error(value):
        return isinstance(value, dict) and set(value) == {"win32Error"} and type(value["win32Error"]) is int
    for view in (root, fg):
        if view is None:
            continue
        require(set(view) == {"class", "basename", "bounds", "session", "desktop"}
                and view["desktop"] == "Default" and type(view["session"]) is int and view["session"] > 0
                and view["session"] == session, "Unexpected window fields or input desktop")
        name, klass, bounds = view["basename"], view["class"], view["bounds"]
        require((error(name) or isinstance(name, str) and name and name.isprintable() and name not in (".", "..")
                 and PureWindowsPath(name).name == name and ":" not in name)
                and (error(klass) or isinstance(klass, str) and 0 < len(klass) < 256)
                and (error(bounds) or isinstance(bounds, list) and len(bounds) == 4
                     and all(type(n) is int and -2**31 <= n < 2**31 for n in bounds)
                     and bounds[0] <= bounds[2] and bounds[1] <= bounds[3]),
                "Invalid recorded window class, basename or bounds")
    if root is not None and not error(root["basename"]):
        require(root["basename"].casefold() == PureWindowsPath(row["primary"]["image"]).name.casefold(),
                "The sampled WPF root belongs to another executable")
    require((relation == "wpfRoot" and root is not None and root == fg
             or relation == "otherRoot" and root is not None and fg is not None and fg["session"] == root["session"]
             or relation in ("changed", "none") and root is not None and fg is None
             or relation == "unavailable" and fg is None)
            and ("win32Error" not in sample or relation == "unavailable" and type(sample["win32Error"]) is int),
            "The foreground relation differs from its original window samples")
    return sample
