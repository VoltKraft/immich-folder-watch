"""Run only the two owned WPF lifetimes on one fresh ARM64 input desktop."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re

from shared import QA, ROOT, UPLOAD, module, read, require, write

ARM = "aarch64-pc-windows-msvc"
MODE = "owned-private-input"


def valid_name(name):
    return isinstance(name, str) and re.fullmatch(r"IfwQa_[a-f0-9]{32}", name) is not None


def name_present(desk, name):
    from win32 import bind, check
    callback = c.WINFUNCTYPE(w.BOOL, w.LPWSTR, w.LPARAM)
    enum = bind(c.WinDLL("user32", use_last_error=True), "EnumDesktopsW", w.BOOL, w.HANDLE, callback, w.LPARAM)
    require(valid_name(name), "Expected the generated private desktop name")
    found = False

    @callback
    def visit(candidate, _):
        nonlocal found
        if candidate.casefold() == name.casefold():
            found = True
        return True

    check(enum(desk.station(), visit, 0), "EnumDesktopsW(private name)")
    return found


def supervisor(launch, target, out, work, image):
    native = module("ifw_upload_input_desktop", QA / "windows-desktop/run.py")
    receipt = {"supervisorPid": os.getpid(), "status": "incomplete"}

    class FreshDesktop(launch.Desktop):
        def create_detached(self, name):
            require(valid_name(name), "Expected a fresh native desktop name")
            receipt["nameExistedBefore"] = name_present(self, name)
            require(not receipt["nameExistedBefore"], "The generated desktop already exists")
            return super().create_detached(name)

    desk = FreshDesktop()
    try:
        with native.named_input_desktop(desk, receipt) as name:
            state = receipt["afterSwitch"]
            require(state["session"] == receipt["beforeSwitch"]["session"] and valid_switched(state, name),
                    "The supervisor or active input session changed during selection")
            ticket = dict(name=name, parent=os.getpid(), session=state["session"], target=target)
            write(out / "desktop-start.json", ticket)
            worker = receipt["worker"] = {}
            code = native.run_worker(UPLOAD / "observe.py", [target, out, work, image, "--owned-desktop", name],
                                     name, ROOT, worker, timeout_seconds=420)
            require(code == 0, "The private WPF upload observer failed; see upload-observation.json")
        receipt["status"] = "observed"
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            finish_restoration(desk, receipt, launch.recorder.CleanupUnconfirmed)
        finally:
            write(out / "private-desktop.json", receipt)


def finish_restoration(desk, receipt, error):
    from win32 import ordinary_console
    after = receipt["afterRestore"] = desk.context()
    cleanup = receipt.get("cleanup", {})
    if receipt.get("switchToFixture") is not True and cleanup.get("switchBack") is not True:
        receipt["restorationStatus"] = "fixture-not-selected"
        return
    before = receipt["beforeSwitch"]
    if (not ordinary_console(before, "Default") or not ordinary_console(after, "Default")
            or after["session"] != before["session"] or cleanup.get("switchBack") is not True
            or cleanup.get("inputAfterRestore") != "Default" or cleanup.get("originalHandleClosed") is not True
            or cleanup.get("namedClosed") is not True):
        receipt["status"], receipt["restorationStatus"] = "incomplete", "unconfirmed"
        raise error("Restoration of the original console and desktop handles could not be confirmed")
    receipt["restorationStatus"] = "restored"


def valid_switched(state, name):
    from win32 import unlocked_console
    return (unlocked_console(state) and state["inputDesktop"] == name and state["inputObjectReceivesInput"] is True
            and state["threadDesktop"] == "Default" and state["threadReceivesInput"] is False)


def surfaces(desk, handle, witness, root=None):
    from win32 import bind, check
    callback = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    enum = bind(c.WinDLL("user32", use_last_error=True), "EnumDesktopWindows", w.BOOL, w.HANDLE, callback, w.LPARAM)
    result = dict(witnessCount=0, rootCount=0, otherVisible=0)

    @callback
    def visit(hwnd, _):
        result["witnessCount"] += int(hwnd == witness and not desk.visible(hwnd))
        if desk.visible(hwnd):
            if root and hwnd == root["hwnd"]:
                pid = w.DWORD()
                tid = desk.owner(hwnd, c.byref(pid))
                result["rootCount"] += int(root["pid"] == pid.value and tid == root["tid"] and desk.ancestor(hwnd, 2) == hwnd)
            else:
                result["otherVisible"] += 1
        return True

    check(enum(handle, visit, 0), "EnumDesktopWindows(owned input desktop)")
    return result


def check_surfaces(result, root=False):
    require(result == dict(witnessCount=1, rootCount=int(root), otherVisible=0),
            "The owned input desktop contains a missing witness, changed root or another visible window")


@contextmanager
def worker(launch, desk, out, target, name):
    ticket = read(out / "desktop-start.json")
    state = desk.context()
    require(valid_name(name) and target == ARM and launch.ordinary_console(state, name)
            and ticket == dict(name=name, parent=os.getppid(), session=state["session"], target=target),
            "Expected the original supervisor and explicitly selected private input desktop")
    handle = launch.check(desk.thread_desktop(desk.thread()), "GetThreadDesktop(private worker)")
    evidence = dict(pid=os.getpid(), parent=os.getppid(), context=state)
    try:
        with desk.enumeration_witness(name, evidence):
            witness = int(evidence["hiddenEnumerationWindow"], 16)
            evidence["before"] = surfaces(desk, handle, witness)
            check_surfaces(evidence["before"])
            try:
                yield PrivateInput(launch, desk, name, witness)
            finally:
                evidence["after"] = surfaces(desk, handle, witness)
                check_surfaces(evidence["after"])
    finally:
        write(out / "private-worker.json", evidence)


class PrivateInput:
    def __init__(self, launch, desk, name, witness):
        self.launch, self.desk, self.name, self.witness = launch, desk, name, witness

    def root(self, row):
        native = self.desk
        info = row["root"]
        handle = self.launch.check(native.thread_desktop(info["tid"]), "GetThreadDesktop(original WPF UI)")
        result = dict(desktop=native.name(handle), receivesInput=native.receiving_input(handle), context=native.context(),
                      root=dict(info), observerPid=os.getpid(), surfaces=surfaces(native, handle, self.witness, info))
        check_root(result, self.name, row, os.getpid())
        return result

    def child(self, api, exe, args, area, stream, before_resume=None):
        env = dict(os.environ, IFW_QA_ISOLATED="1", IFW_QA_INVENTORY_TOKEN=self.name.removeprefix("IfwQa_"))
        return self.launch.child(api, self.desk, self.name, exe, args, area, env, stream, True,
                                 private=False, named_input=True, before_resume=before_resume)

    def quit(self, api, row, command, area):
        with (area / "quit-helper.log").open("xb", buffering=0) as log:
            with self.child(api, Path(command[0]), command[1:], area, log) as (proc, job, tid):
                api.verify_job_member(job, proc.pid, int(proc._handle))
                def attached():
                    self.launch.recorder.wait_running(proc)
                    handle = self.desk.thread_desktop(tid)
                    if handle and self.desk.name(handle) == self.name and self.desk.receiving_input(handle) is True:
                        return self.name
                    return None
                desktop = self.launch.recorder.await_value(attached, "Quit helper did not attach to the private desktop",
                                                          timeout=10, delay=.01)
                helper = row["quitHelper"] = dict(pid=proc.pid, tid=tid, created=api.process_identity(int(proc._handle)),
                                                 desktop=desktop, machine=list(api.machine(int(proc._handle))),
                                                 observedQpc=api.clock())
                require(helper["machine"] == row["primary"]["machine"], "Incorrect native Quit helper architecture")
                helper["exit"] = proc.wait(timeout=35)
                helper["exitQpc"] = api.clock()
                require(helper["exit"] == 0, "The original Quit helper failed; see quit-menu.json and quit-helper.log")


def check_root(sample, name, row, observer):
    from win32 import ordinary_console
    require(sample["desktop"] == name and sample["receivesInput"] is True and sample["observerPid"] == observer
            and ordinary_console(sample["context"], name) and sample["root"] == row["root"]
            and observer != row["primary"]["pid"], "WPF root, observer or input desktop changed")
    check_surfaces(sample["surfaces"], root=True)


def replay(out, report, first, phases):
    # Use the same native session predicates in detached readback on Linux.
    import sys
    sys.path.insert(0, str(QA / "windows-desktop"))
    from win32 import ordinary_console
    supervisor, ticket, worker = (read(out / path) for path in ("private-desktop.json", "desktop-start.json", "private-worker.json"))
    name = ticket["name"]
    require(report["target"] == ARM and valid_name(name) and ticket["target"] == ARM and supervisor["nameExistedBefore"] is False
            and supervisor["created"] == dict(requested=name, actual=name, supervisorDesktop="Default")
            and supervisor["switchToFixture"] is True and supervisor["supervisorPid"] == worker["parent"] == ticket["parent"]
            and 0 < worker["pid"] == supervisor["worker"]["workerPid"] != worker["parent"] and worker["parent"] > 0,
            "Missing fresh ARM64 desktop, supervisor or original worker identity")
    cleanup = supervisor["cleanup"]
    require(all(context["session"] == ticket["session"] for context in (
                supervisor["beforeSwitch"], supervisor["afterSwitch"], cleanup["beforeRestore"], supervisor["afterRestore"], worker["context"]))
            and ordinary_console(supervisor["beforeSwitch"], "Default") and valid_switched(supervisor["afterSwitch"], name)
            and valid_switched(cleanup["beforeRestore"], name) and cleanup["inputBeforeRestore"] == name and cleanup["switchBack"] is True
            and cleanup["inputAfterRestore"] == "Default" and supervisor["restorationStatus"] == "restored"
            and ordinary_console(supervisor["afterRestore"], "Default")
            and cleanup["namedClosed"] is True and cleanup["originalHandleClosed"] is True and supervisor["worker"]["jobClosed"] is True
            and type(supervisor["worker"]["workerExit"]) is int and ordinary_console(worker["context"], name)
            and int(worker["hiddenEnumerationWindow"], 16) > 0 and worker["hiddenWindowDestroyed"] is True,
            "The owned desktop, worker job or original console restoration was not confirmed")
    check_surfaces(worker["before"])
    check_surfaces(worker["after"])
    for phase in [first, *phases]:
        check_root(phase["privateRoot"], name, phase, worker["pid"])
        require(phase["privateRoot"]["context"]["session"] == ticket["session"], "Different WPF console session")
    if phases:
        require(supervisor["worker"]["workerExit"] == 0 and supervisor["status"] == "observed", "The private observer failed")
    for phase in phases:
        check_root(phase["beforeQuitDesktop"], name, phase, worker["pid"])
        helper = phase["quitHelper"]
        require(phase["beforeQuitDesktop"]["context"]["session"] == ticket["session"] and helper["desktop"] == name
                and helper["machine"] == phase["primary"]["machine"] and helper["exit"] == 0 and helper["created"] > phase["primary"]["created"]
                and helper["pid"] not in (worker["pid"], phase["primary"]["pid"]) and min(helper["pid"], helper["tid"]) > 0
                and phase["quit"]["issuedQpc"] <= helper["observedQpc"] <= helper["exitQpc"] <= phase["quit"]["exitedQpc"],
                "The original Quit helper or WPF root was not on this input desktop")
    return {"name": name, "session": ticket["session"], "originalRestored": True}
