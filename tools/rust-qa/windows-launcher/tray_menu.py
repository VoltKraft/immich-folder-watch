"""Select the retained Rust GUI's original tray menu on the local x64 Windows console."""

import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

import local_tray
import native_tray as tray
import observe as launcher
from retained_window import observe_focus
from tray_menu_input import ACTIONS, MenuInput, expected_menus, identify_menu

RESOURCES = launcher.ROOT / "src/ImmichFolderWatch.App.Shared/Resources"
OBSERVERS = [Path(__file__).resolve(), launcher.HERE / "tray_menu_input.py", tray.PROVIDER, launcher.HERE / "tray_msaa.cs",
             launcher.QA / "windows-services/tray-overflow.ps1", Path(tray.__file__), Path(local_tray.__file__),
             Path(launcher.__file__), launcher.HERE / "named_process.py", launcher.QA / "windows-desktop/win32.py",
             launcher.HERE / "retained_window.py", launcher.QA / "windows-services/service_sources.py",
             RESOURCES / "Strings.resx", RESOURCES / "Strings.de.resx"]


def archive_observers(out, report):
    from runpy import run_path
    verify = run_path(str(launcher.QA / "windows-services/service_sources.py"))["verify_checkout"]
    head = report["observerRevision"]
    checked = verify(launcher.ROOT, OBSERVERS, head)
    if checked != report["observerInputs"]:
        raise ValueError("The menu observers differ from their own Git revision")
    with ZipFile(out / "observer-sources.zip", "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("observer.json", json.dumps(dict(revision=head, files=checked)))
        for name in checked:
            archive.write(launcher.ROOT / name, name)


def verify_focus(surface, row):
    latest = row["lastSample"]
    if (row["hwnd"] != int(surface["hwnd"], 16) or row["pid"] != surface["pid"] or latest["thread"] != surface["tid"]
            or row["observed"] is not True or row["applicable"] is not True or row["sameWindowVisible"] is not True
            or row["samples"] < 1 or latest["queryError"] != 0 or not all(latest[k] is True for k in ("foreground", "active", "focused"))):
        raise ValueError("The original editor did not acquire foreground, activation and owned keyboard focus")


def messages(text, pid, hwnd):
    events = []
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n") or not line.startswith("TRAY_MENU_"):
            continue
        if line.startswith("TRAY_MENU_OPENED "):
            match = re.fullmatch(rf"TRAY_MENU_OPENED pid={pid} hwnd={hwnd} id=23 x=(-?\d+) y=(-?\d+) language=(de|en)", line.strip())
            if not match:
                raise ValueError("The menu opening record differs from the original receiver")
            x, y, language = match.groups()
            events.append(dict(event="opened", point=[int(x), int(y)], language=language))
        elif line.startswith("TRAY_MENU_SELECTED "):
            match = re.fullmatch(rf"TRAY_MENU_SELECTED pid={pid} hwnd={hwnd} id=23 action=(open|restart|quit)", line.strip())
            if not match:
                raise ValueError("The selected menu command differs from the original receiver")
            events.append(dict(event="selected", action=match[1]))
    return events


def exited_worker(api, handle):
    code = w.DWORD()
    launcher.recorder.checked(api.exit_code(handle, c.byref(code)))
    if code.value == 259:
        return None
    if code.value:
        raise ValueError(f"The original inventory worker exited with {code.value}")
    times = [w.FILETIME() for _ in range(4)]
    launcher.recorder.checked(api.times(handle, *(c.byref(item) for item in times)))
    return dict(exit=code.value, **{key: (value.dwHighDateTime << 32) + value.dwLowDateTime for key, value in
                                    zip(("creation100ns", "exit100ns"), times)})


def lifecycle(text, first, second):
    """Replay application events; both process handles are checked separately."""
    expected = [f"INVENTORY_WORKER pid={first}",
                f"WORKER_EXIT pid={first} reason=restart success=true",
                f"INVENTORY_WORKER pid={second}", f"WORKER_RESTARTED old={first} new={second}",
                f"WORKER_EXIT pid={second} reason=quit success=true", "CONTROL_READER_STOPPED"]
    seen = [line for line in text.splitlines() if line.startswith(("INVENTORY_WORKER ", "WORKER_EXIT ", "WORKER_RESTARTED ",
                                                                  "CONTROL_READER_STOPPED"))]
    if first == second or seen != expected or not re.search(r"^DRAINED passes=\d+$", text, re.M):
        raise ValueError("The two native workers did not finish in the expected restart and quit sequence")
    return seen


def verify_gesture(action, state, key, created, token, events, labels):
    surface = state["surface"]
    shell = (surface["shellPid"], surface["bar"])
    tray.provider_route(events, shell, {}, final=True)
    first, ready, target = [tray.provider_event(events, stage) for stage in ("first", "ready", "menu-target")]
    colors = tray.marker_colors(token)
    original = tray.confirm_surface(first, key, created, surface["rect"], colors[int(action != "open")])
    for event in (ready, target):
        sampled = tray.confirm_surface(event, key, created, surface["rect"], colors[1], original)
        if tray.confirm_provider(event, sampled, token) != state["iconProvider"]:
            raise ValueError("The archived named Explorer provider changed")
    if target["surface"] != surface or target["action"] != action or state["pointerRestored"] is not True:
        raise ValueError("The context click did not use its original Explorer icon")
    menu = state["menu"]
    language = identify_menu(menu["rows"], labels)
    if (menu["language"] != language or state["opened"]["language"] != language or menu["receiver"] != int(key[1])
            or menu["pid"] != int(key[0]) or menu["receiver"] not in (menu["menuOwner"], menu["popupOwner"])
            or min(menu["hwnd"], menu["menu"], menu["tid"]) <= 0):
        raise ValueError("The command labels and original popup owner do not agree")
    right, left = state["contextClick"], state["commandClick"]
    row = menu["rows"][2 * ACTIONS.index(action)]
    if (right["flags"] != [8,16] or left["flags"] != [2,4] or right["tag"] != left["tag"] or
            not 0 < right["beginQpc"] <= right["endQpc"] <= left["beginQpc"] <= left["endQpc"]
            or (right["queued"], left["queued"]) != (2,2) or right["point"] != surface["point"]
            or left["point"] != [(row["left"] + row["right"]) // 2, (row["top"] + row["bottom"]) // 2]):
        raise ValueError("Missing ordered physical right- and left-button pairs at the two original targets")
    for stage in ("before", "atPoint"):
        icon, item = right[stage], left[stage]
        if (icon["hit"] != surface["hit"] or icon["root"] != surface["root"] or icon["ownerPid"] != shell[0]
                or icon["rect"] != surface["rect"] or any(abs(ch - ((icon["colorref"] >> (8*i)) & 255)) > 8
                    for i,ch in enumerate(bytes.fromhex(surface["rgb"])))
                or item != dict(hit=menu["hwnd"], menu=menu["menu"], ownerPid=menu["pid"], id=row["id"], text=row["text"])):
            raise ValueError("A physical mouse hit changed icon, menu handle, owner or command")
    return [state["opened"], dict(event="selected", action=action)]


def replay(out, archive, digest):
    report = json.loads((out / "result.json").read_bytes())
    if (report["host"] != "local-vm" or report["archiveSha256"] != digest or not launcher.ordinary_console(report["hostContext"], "Default")
            or report["target"] != local_tray.TARGET or report["hostIdentity"].get("vm") is not True
            or report["hostIdentity"]["user"].casefold() != r"ifw-qa25\ifw-test"
            or report["status"] != "passed" or report["sequence"] != list(ACTIONS) or report["cleanupConfirmed"] is not True
            or report["caseProfile"]["cleanupConfirmed"] is not True
            or report["stdinQuit"] is not False or report["primaryExit"] != 0):
        raise ValueError("The complete local menu run or its original standard-user desktop is missing")
    if report["observerInputs"] != {p.relative_to(launcher.ROOT).as_posix(): launcher.recorder.sha(p) for p in OBSERVERS}:
        raise ValueError("Use the original menu observer sources")
    with ZipFile(out / "observer-sources.zip") as sources:
        manifest = json.loads(sources.read("observer.json"))
        if (manifest != dict(revision=report["observerRevision"], files=report["observerInputs"])
                or sorted(sources.namelist()) != sorted(["observer.json", *report["observerInputs"]])
                or any(hashlib.sha256(sources.read(path)).hexdigest() != digest for path, digest in manifest["files"].items())):
            raise ValueError("The archived observer sources are not bound to their recorded revision")
    verify_focus(report["openedWindow"], report["openFocus"])
    files = {p.relative_to(out).as_posix(): launcher.recorder.sha(p) for p in out.rglob("*") if p.is_file() and p != out / "result.json"}
    if files != report["evidenceFiles"]:
        raise ValueError("The native menu evidence files changed")
    with tempfile.TemporaryDirectory() as staging:
        index, warm = local_tray.stage(archive, digest, Path(staging))
        if (report["revision"], report["gui"], report["inventory"]) != (index["revision"], warm["binary"], index["inventory"]):
            raise ValueError("The original native menu binaries differ from their compiler archive")
    text = (out / "primary.log").read_text(encoding="utf-8")
    pid = report["primaryPid"]
    reg = report["registration"]
    key = tuple(str(i) for i in (pid, reg["hwnd"], 23))
    all_events = []
    for action in ACTIONS:
        state = report["actions"][action]
        if state["menu"]["tid"] != reg["receiver"]["tid"] or not state["provider"]["jobEmpty"] or state["provider"]["exit"] != 0:
            raise ValueError("The original receiver thread or physical provider did not complete")
        raw = tray.provider_events(out / action / "provider.log")
        all_events.extend(verify_gesture(action, state, key, report["primaryCreation100ns"], report["caseProfile"]["profile"], raw,
                                         expected_menus(RESOURCES)))
    if messages(text, *key[:2]) != all_events:
        raise ValueError("The original Rust supervisor log does not match the observed physical commands")
    shutdown = {}
    tray.replay_shutdown(text, key, report["caseProfile"]["profile"], shutdown)
    if (report["nativeShutdown"]["reportedCleanupMethod"] != shutdown["reportedCleanupMethod"] or
            not report["nativeShutdown"]["stableRegistration"] or not report["nativeShutdown"]["jobEmpty"]):
        raise ValueError("The original Shell registration or process job did not drain")
    first, second = report["workerBefore"], report["workerAfter"]
    for worker, job, status in ((first, "originalJob", "originalWorkerExit"), (first, "openedJob", "originalWorkerExit"),
                                (second, "replacementJob", "replacementWorkerExit")):
        member, = [m for m in report[job]["members"] if m["role"] == "worker"]
        if (member["pid"], member["creation100ns"], member["parent"], member["image"].casefold()) != (
                worker[0], worker[1], pid, local_tray.WORKER) or report[status]["creation100ns"] != worker[1] or report[status]["exit"] != 0:
            raise ValueError("The independent worker handle and the owned job disagree")
    if not first[1] <= report["originalWorkerExit"]["exit100ns"] <= second[1] <= report["replacementWorkerExit"]["exit100ns"]:
        raise ValueError("The replacement worker overlapped its predecessor")
    return dict(primary=pid, workerBefore=first, workerAfter=second, sequence=report["sequence"], lifecycle=lifecycle(text, first[0], second[0]))


def select_actions(api, desk, gui, trial, env, out, result):
    token = env["IFW_QA_INVENTORY_TOKEN"]
    colors = tray.marker_colors(token)
    native = tray.NativeTray(api, desk, "Default", token)
    log_path = out / "primary.log"
    log = lambda: log_path.read_text(encoding="utf-8", errors="strict")
    desktop = launcher.check(desk.thread_desktop(desk.thread()), "GetThreadDesktop(menu)")
    ctx = result["desktop"] = desk.context()
    if not launcher.ordinary_console(ctx, "Default"):
        raise ValueError("Menu input requires the original unlocked console")
    labels = expected_menus(RESOURCES)
    cases = result["actions"] = {}
    with ExitStack() as stack:
        native.watch_original(stack, result)
        stream = stack.enter_context(log_path.open("xb"))
        proc, job, _ = stack.enter_context(launcher.child(api, desk, "Default", gui, ["--autostart"], trial, env,
                                                           stream, True, private=False))
        created = result["primaryCreation100ns"] = api.process_identity(int(proc._handle))
        result["primaryPid"] = proc.pid
        windows = launcher.recorder.load_windows_fixture().Windows(proc.pid, desktop)
        stack.callback(launcher.release, windows.close, "Could not close the tray-menu window observer")

        def wait(get, detail):
            def sample():
                windows.pump()
                launcher.recorder.wait_running(proc)
                return get()
            return launcher.recorder.await_value(sample, detail, delay=.035)

        def worker_at(pid, field):
            account = result[field] = {}
            item = launcher.primary_job_members(api, desk, job, proc.pid, pid, gui, launcher.system_console_path(api.kernel), account)
            handle = launcher.recorder.checked(api.open(0x100000 | 0x1000, False, pid))
            stack.callback(launcher.release_handle, api.close, "CloseHandle(pinned menu worker)", handle)
            if item[1] != api.process_identity(handle):
                raise ValueError("The observed worker was replaced before its handle was retained")
            return item, handle

        tray.command(proc, b"B")
        key = native.registration(proc, log, wait, result, no_host=False)
        wait(lambda: "READY BackgroundStartup Available" in log().splitlines() and launcher.recorder.idle_complete(log()),
             "The background primary did not finish its initial two inventories")
        if windows.visible():
            raise ValueError("The retained GUI was already visible before menu Open")
        first_pid = launcher.recorder.owned_worker(api, proc, log_path, launcher.recorder.await_value)
        first, first_handle = worker_at(first_pid, "originalJob")
        result["workerBefore"] = first
        original_dpi = launcher.check(desk.awareness(-4), "SetThreadDpiAwarenessContext(menu)")
        stack.callback(launcher.release_handle, desk.awareness, "Restore original menu DPI context", original_dpi)
        result["expectedLabels"] = labels
        inputs = MenuInput(desk, api, key, result["registration"]["receiver"]["tid"], labels)
        completed = []
        for action in ACTIONS:
            point = out / action
            point.mkdir()
            state = cases[action] = dict(provider={})
            environment = dict(env, IFW_QA_LOCAL_TRAY_MENU=action)
            offset = len(log())
            with tray.provider(api, desk, trial, environment, point, key, created,
                              state["provider"], native.witness.original) as (helper, get):
                try:
                    start = wait(lambda: get("first"), "No token-specific icon at the real Explorer surface")
                    rect = tray.shell_rect(int(key[1]))
                    if rect["hresult"] != 0 or not rect["rect"]:
                        raise tray.Unavailable("Explorer did not expose the retained icon")
                    before = tray.confirm_surface(start, key, created, rect["rect"], colors[0] if action == "open" else colors[1])
                    if action == "open":
                        native.require_original("beforeMarker", before)
                        tray.command(proc, b"M")
                        wait(lambda: tray.icon(log(), "changed", key, colors[1]), "No acknowledged marker change")
                        native.witness.markers += 1
                        native.require_original("afterMarker", before)
                    tray.command(helper, b"second\n")
                    ready = wait(lambda: get("ready"), "The exact named Explorer provider was unavailable")
                    surface = tray.confirm_surface(ready, key, created, rect["rect"], colors[1], before)
                    descriptor = tray.confirm_provider(ready, surface, token)
                    native.require_original("beforeInvoke", surface)
                    tray.command(helper, ("menu-" + action + "\n").encode())
                    target = wait(lambda: get("menu-target"), "The provider did not reconfirm the physical context-menu target")
                    actual = tray.confirm_surface(target, key, created, rect["rect"], colors[1], before)
                    if target["action"] != action or descriptor != tray.confirm_provider(target, actual, token) or inputs.menu() is not None:
                        raise ValueError("The icon, requested command or initial popup state changed")
                    native.require_original("providerAttempt", actual)
                    state.update(surface=actual, iconProvider=descriptor)
                    state["contextClick"] = inputs.click(actual["point"], (8, 16), lambda: inputs.verify_icon(actual, tray.shell_rect))
                    menu = state["menu"] = wait(inputs.menu, "The original receiver did not own a visible five-item popup")
                    opened = wait(lambda: messages(log()[offset:], *key[:2]), "No menu opening on the original receiver")
                    if len(opened) != 1 or opened[0].get("language") != menu["language"]:
                        raise ValueError("The native menu and original receiver did not agree before selection")
                    state["opened"] = opened[0]
                    state["commandClick"] = inputs.select(menu, action)
                    native.require_original("afterInvoke", actual)
                    if action == "quit":
                        # Keep the control pipe open. Only the real menu command can satisfy this case.
                        result["primaryExit"] = launcher.wait_for_exit(proc, windows.pump, 18)
                        if result["primaryExit"] != 0:
                            raise ValueError("Menu Quit did not exit the original GUI normally")
                    else:
                        wait(lambda: len(messages(log()[offset:], *key[:2])) >= 2, "The clicked command was not selected")
                    emitted = messages(log()[offset:], *key[:2])
                    if emitted != [state["opened"], dict(event="selected", action=action)]:
                        raise ValueError("The physical choice disagrees with the retained GUI's selected command")
                    state["selected"] = emitted[-1]
                finally:
                    state["pointerRestored"] = inputs.restore()
                    if not state["pointerRestored"]:
                        raise launcher.CleanupUnconfirmed("The synthetic menu pointer was not restored")
                    if action == "quit" and proc.poll() == 0 and state.get("selected") == dict(event="selected", action="quit"):
                        tray.command(helper, b"menu-quit-exited\n")
            completed.append(action)
            if action == "open":
                hwnd = wait(windows.visible, "Open GUI did not show the retained editor")
                native.visible_window(proc, hwnd, result, "openedWindow")
                focus = result["openFocus"] = dict(hwnd=hwnd, pid=proc.pid)
                observe_focus(desk, windows, hwnd, focus)
                verify_focus(result["openedWindow"], focus)
                if worker_at(first_pid, "openedJob")[0] != first:
                    raise ValueError("Open GUI replaced the original worker")
            elif action == "restart":
                first_exit = result["originalWorkerExit"] = wait(lambda: exited_worker(api, first_handle),
                                                                "Restart did not drain the original worker")
                def next_worker():
                    found = re.findall(r"^INVENTORY_WORKER pid=(\d+)$", log(), re.M)
                    if len(found) > 2:
                        raise ValueError("Extra worker launched after one Restart")
                    return int(found[1]) if len(found) == 2 else None
                second_pid = wait(next_worker, "Restart did not launch a second native inventory worker")
                second, second_handle = worker_at(second_pid, "replacementJob")
                result["workerAfter"] = second
                if (first[0] == second[0] or first_exit["creation100ns"] != first[1] or
                        not first[1] <= first_exit["exit100ns"] <= second[1]):
                    raise ValueError("The original worker did not exit before the replacement was created")
                restart_log = lambda: log().split(f"INVENTORY_WORKER pid={second_pid}\n", 1)[1]
                wait(lambda: launcher.recorder.idle_complete(restart_log()), "The replacement did not complete its two inventories")
                if windows.visible() != hwnd or api.process_identity(int(proc._handle)) != created:
                    raise ValueError("Restart replaced the original visible GUI")
        result["replacementWorkerExit"] = exited_worker(api, second_handle)
        if not result["replacementWorkerExit"] or result["replacementWorkerExit"]["creation100ns"] != second[1]:
            raise ValueError("Menu Quit left its replacement inventory worker alive")
        native.check_drain(proc, job, log(), result)
        native.qualify_quiet_shell(log(), result, no_host=False)
        result["lifecycle"] = lifecycle(log(), first_pid, second_pid)
        result["sequence"] = completed
        result["stdinQuit"] = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--replay", type=Path, help="replay an original completed output directory and the compiler archive")
    args = parser.parse_args()
    if args.replay:
        print(json.dumps(replay(args.replay, args.local_archive, args.archive_sha256), indent=2))
        return 0
    out = launcher.ROOT / "artifacts/rust/windows-tray-menu" / local_tray.TARGET
    out.mkdir(parents=True, exist_ok=False)
    report = dict(target=local_tray.TARGET, status="failed")
    try:
        with local_tray.subject(launcher, args.local_archive, args.archive_sha256, report, OBSERVERS) as (api, desk, gui, inventory, _):
            archive_observers(out, report)
            profile = report["caseProfile"] = {}
            with launcher.staged_profile(profile, api, gui, inventory, local_temp=Path(tempfile.gettempdir())) as (exe, trial, env):
                env.update(IFW_QA_WINDOWS_TRAY="1", IFW_QA_MSAA_ICON="1")
                select_actions(api, desk, exe, trial, env, out, report)
        report["status"] = "passed"
    except Exception as exc:
        report["failures"] = launcher.failures(exc)
    finally:
        report["evidenceFiles"] = {p.relative_to(out).as_posix(): launcher.recorder.sha(p) for p in out.rglob("*") if p.is_file()}
        launcher.recorder.write(out / "result.json", report)
    print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
