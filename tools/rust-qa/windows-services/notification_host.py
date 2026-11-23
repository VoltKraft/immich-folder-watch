"""Correlate the native notification request with the original console's Shell process."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import PureWindowsPath

from native import checked
from win32 import bind, ordinary_console


HOST_FIELDS = ("taskbar_hwnd", "taskbar_pid", "taskbar_tid", "taskbar_creation", "taskbar_session",
               "taskbar_desktop", "shell_hwnd", "shell_pid", "shell_tid")


class ShellWitness:
    def __init__(self, api, desk, session, winroot, stack):
        self.api, self.desk, self.session = api, desk, session
        self.image = PureWindowsPath(winroot) / "explorer.exe"
        self.taskbar = bind(c.WinDLL("user32", use_last_error=True), "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
        self.wait_process = bind(api.kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        self.handle, self.pid = None, None
        bar = self.taskbar("Shell_TrayWnd", None)
        if bar:
            pid = w.DWORD()
            if desk.owner(bar, c.byref(pid)) and pid.value:
                self.pid = pid.value
                self.handle = api.open(0x101000, False, self.pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
                if self.handle:
                    stack.callback(lambda: checked(api.close(self.handle)))

    def sample(self):
        desk = self.desk
        context = desk.context()
        bar, shell = self.taskbar("Shell_TrayWnd", None), desk.shell()
        result = dict(verified=False, context=context, taskbar_hwnd=bar, shell_hwnd=shell)
        if not bar or not shell or not self.handle:
            return result
        for name, hwnd in (("taskbar", bar), ("shell", shell)):
            pid = w.DWORD()
            tid = desk.owner(hwnd, c.byref(pid))
            result.update({name + "_pid": pid.value, name + "_tid": tid,
                           name + "_desktop": desk.name(desk.thread_desktop(tid)) if tid else None})
        size, path = w.DWORD(32768), c.create_unicode_buffer(32768)
        result["taskbar_session"] = desk.pid_session(result["taskbar_pid"])
        result["visible"] = bool(desk.visible(bar))
        result["processWait"] = self.wait_process(self.handle, 0)
        if result["processWait"] != 258 or not desk.image(self.handle, 0, path, c.byref(size)):
            return result
        result["image"] = path.value
        try:
            result["taskbar_creation"] = self.api.process_identity(self.handle)
        except OSError as exc:
            result["creationReadError"] = str(exc)
            return result
        # Recheck the two actual HWND owners after reading through the retained process handle.
        for name, hwnd in (("taskbar", bar), ("shell", shell)):
            pid = w.DWORD()
            if desk.owner(hwnd, c.byref(pid)) != result[name + "_tid"] or pid.value != self.pid:
                return result
        result["verified"] = bool(
            ordinary_console(context, "Default") and context["session"] == self.session
            and self.image == PureWindowsPath(path.value) and result["taskbar_creation"] > 0
            and result["taskbar_session"] == self.session and result["visible"]
            and result["shell_pid"] == result["taskbar_pid"] == self.pid
            and result["shell_desktop"] == result["taskbar_desktop"] == "Default"
            and result["taskbar_tid"] and result["shell_tid"]
            and self.taskbar("Shell_TrayWnd", None) == bar and desk.shell() == shell
            and self.wait_process(self.handle, 0) == 258)
        return result


def native_host(metrics, prefix):
    return {key: metrics.get(prefix + "." + key) for key in (*HOST_FIELDS, "taskbar_present", "taskbar_visible",
                                                              "shell_window", "station_visible", "session", "thread_desktop")}


def stable_registration(samples, native, session):
    original = samples.get("beforeLaunch", {})
    for moment in ("beforeLaunch", "beforeRequest", "afterRequest", "afterQuit"):
        sample = samples.get(moment, {})
        if sample.get("verified") is not True or any(sample.get(k) != original.get(k) for k in HOST_FIELDS):
            return False
    for phase in ("notice", "notice_after"):
        host = native_host(native, phase)
        if (any(host[key] is not True for key in ("taskbar_present", "taskbar_visible", "shell_window", "station_visible"))
                or host["thread_desktop"] != "Default" or host["taskbar_desktop"] != "Default"
                or host["taskbar_session"] != session or host["session"] != session
                or host["shell_pid"] != host["taskbar_pid"]
                or any(type(host[k]) is not int or host[k] <= 0 for k in HOST_FIELDS if k != "taskbar_desktop")
                or any(host[k] != original[k] for k in HOST_FIELDS)):
            return False
    return True


def compare_early(early, late):
    if not early:
        return "early-observation-unavailable"
    if early.get("taskbar_present") is False:
        return "early-taskbar-absent"
    if not late.get("verified"):
        return "late-identity-unverified"
    if (early.get("taskbar_present") is not True or early.get("taskbar_desktop") != "Default"
            or early.get("taskbar_session") != late.get("taskbar_session")
            or any(type(early.get(k)) is not int or early[k] <= 0 for k in
                   ("taskbar_pid", "taskbar_creation", "taskbar_hwnd", "taskbar_tid"))):
        return "early-identity-unverified"
    if (early["taskbar_pid"], early["taskbar_creation"]) != (late["taskbar_pid"], late["taskbar_creation"]):
        return "different-explorer-process"
    if (early["taskbar_hwnd"], early["taskbar_tid"]) != (late["taskbar_hwnd"], late["taskbar_tid"]):
        return "same-explorer-new-taskbar"
    return "same-explorer-and-taskbar"
