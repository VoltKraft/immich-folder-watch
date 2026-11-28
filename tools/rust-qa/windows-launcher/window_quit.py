"""Quit the real window after the Windows Shell refuses its background tray registration."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ART = QA.parents[1] / "artifacts/rust"
TARGET = "aarch64-pc-windows-msvc"
OUT = ART / "gui-native" / TARGET / "windows-quit-private"
PAIR = ART / "windows-display-inputs"


def verify_quit(log, result):
    pid, worker = result["primaryPid"], result["inventoryPid"]
    button = result["button"]
    if (worker == pid or result["primaryExit"] != 0 or result["workerAliveAfterQuit"]
            or result["workerAtButton"] != [pid, "ifw-performance-worker.exe"]
            or result["window"]["pid"] != pid or result["window"]["desktopMatches"] != 1
            or button["pid"] != pid or button["hwnd"] != result["window"]["hwnd"]
            or button["name"] != "Beenden" or button["method"] != "InvokePattern"
            or not button["enabled"] or button["offscreen"] or min(button["width"], button["height"]) <= 0):
        raise ValueError("Missing original visible Quit button, successful process exit or worker shutdown")
    token = result["profile"]
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("Missing the original staging token")
    tray = re.findall(rf"^TRAY_REGISTER phase=initial pid={pid} hwnd=([1-9][0-9]*) id=23 token={token} added=0 version4=0$", log, re.M)
    if len(tray) != 1:
        raise ValueError("Expected one refused registration for the original tray receiver")
    def at(pattern):
        matches = list(re.finditer("^" + pattern + "$", log, flags=re.MULTILINE))
        if len(matches) != 1:
            raise ValueError("Expected one GUI or inventory receipt: " + pattern)
        return matches[0].start()

    start = at(f"INVENTORY_WORKER pid={worker}")
    refused = at(r"gui_tray\.initial\.add=false")
    registration = at(rf"TRAY_REGISTER phase=initial pid={pid} hwnd={tray[0]} id=23 token={token} added=0 version4=0")
    ready = at("READY Visible Unavailable")
    cleanup = at(rf"TRAY_CLEANUP pid={pid} hwnd={tray[0]} id=23 registered=0 removed=0")
    worker_exit = at(f"WORKER_EXIT pid={worker} reason=quit success=true")
    stopped = at("CONTROL_READER_STOPPED")
    drained = at(r"DRAINED passes=[1-9][0-9]*")
    # Quit wakes the inventory owner before the GUI loop returns. Its exit can
    # precede or follow tray cleanup. Both owners finish before the reader stops.
    if not (start < refused < registration < ready < min(cleanup, worker_exit)
            and max(cleanup, worker_exit) < stopped < drained):
        raise ValueError("The GUI drained before completing its startup and both shutdown paths")
    for sweep, changed in enumerate([1, 0]):
        if log.splitlines().count(f"INVENTORY_COMPLETE files=1 changed={changed} pass={sweep}") != 1:
            raise ValueError("The original worker did not scan the synthetic file twice")
    if "WORKER_RESTART" in log or re.search(r"^gui_tray\.\w+\.add=true$", log, re.M):
        raise ValueError("Unexpected tray registration or worker restart during the window Quit")


def observe_hosted(name, desktop, launcher, native, result):
    recorder = launcher.recorder
    receipt = json.loads((PAIR / "display-build.json").read_bytes())
    build = json.loads((PAIR / "canonical/build.json").read_bytes())
    gui = PAIR / "canonical/native-gui-assessment.exe"
    worker = PAIR / "ifw-performance-worker.exe"
    files = receipt["files"]
    if (receipt["revision"] != os.environ["GITHUB_SHA"] or receipt["target"] != TARGET
            or build["source"] != receipt["revision"] or build["target"] != TARGET
            or recorder.sha(gui) != build["binarySha256"] or recorder.sha(gui) != files["canonical/" + gui.name]
            or recorder.sha(worker) != receipt["inventory"]["worker"] or recorder.sha(worker) != files[worker.name]
            or any(native["pe_machine"](path) != 0xaa64 for path in (gui, worker))):
        raise ValueError("Expected the original native ARM64 GUI and worker from this build")
    images = {"gui": build["binarySha256"], "worker": receipt["inventory"]["worker"]}
    result.update(source=receipt["revision"], target=TARGET, run=receipt["run"], attempt=receipt["attempt"],
                  compilerReceipt=recorder.sha(PAIR / "canonical/build.json"),
                  pairReceipt=recorder.sha(PAIR / "display-build.json"))
    observe_window(name, desktop, launcher, native, result, gui=gui, worker=worker, images=images, output=OUT)


def observe_window(name, desktop, launcher, native, result, *, gui, worker, images, output, local_temp=None):
    if not native["ordinary_console"](desktop.context(), name) or not re.fullmatch(r"IfwQa_[0-9a-f]{32}", name):
        raise ValueError("Expected the observer on its private active console desktop")
    recorder = launcher.recorder
    win = recorder.Win32()
    result.update(observerPid=os.getpid(), images=images, before=desktop.context())
    with tempfile.TemporaryDirectory(dir=local_temp or os.environ["RUNNER_TEMP"]) as temp:
        pair = Path(temp)
        shutil.copyfile(gui, pair / "native-gui-assessment.exe")
        shutil.copyfile(worker, pair / "ifw-performance-worker.exe")
        with launcher.staged_profile(result, win, pair / "native-gui-assessment.exe", images, local_temp=local_temp) as (exe, trial, env):
            (trial / "empty/quit-fixture.jpg").write_bytes(b"synthetic inventory")
            env["IFW_QA_WINDOWS_TRAY"] = "1"
            env["PSModuleAnalysisCachePath"] = str(trial / "ModuleAnalysisCache")
            program, result["observerHosts"] = native["select_powershell"](trial, "accessibility", env)
            if not program:
                raise RuntimeError("Missing native UI Automation observer")
            logfile = output / "gui.log"
            with logfile.open("xb", buffering=0) as stream:
                with subprocess.Popen([exe, "--autostart"], cwd=trial, env=env, stdin=subprocess.PIPE,
                                      stdout=stream, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW) as app:
                    try:
                        result["primaryPid"] = app.pid
                        result["inventoryPid"] = recorder.owned_worker(win, app, logfile, recorder.await_value)
                        app.stdin.write(b"B")  # Release both the native registration and the inventory.
                        app.stdin.flush()
                        handle = desktop.thread_desktop(desktop.thread())
                        with closing(recorder.load_windows_fixture().Windows(app.pid, handle)) as windows:
                            def fallback_window():
                                recorder.wait_running(app)
                                current = logfile.read_text(encoding="utf-8")
                                if ("READY Visible Unavailable" in current
                                        and "INVENTORY_COMPLETE files=1 changed=0 pass=1" in current):
                                    return windows.visible(waiting_for_first=True)
                                return None
                            hwnd = recorder.await_value(fallback_window, "No original visible tray fallback", delay=.08)
                        window = desktop.window(hwnd)
                        count = desktop.count_top_level_window(handle, hwnd)
                        result["window"] = {"hwnd": hwnd, "pid": window["pid"], "tid": window["tid"], "desktopMatches": count}
                        if window["pid"] != app.pid or count != 1 or not native["ordinary_console"](desktop.context(), name):
                            raise ValueError("The fallback window is outside the private input desktop")
                        parent, image = win.processes().get(result["inventoryPid"], (0, ""))
                        result["workerAtButton"] = [parent, image.casefold()]
                        if result["workerAtButton"] != [app.pid, "ifw-performance-worker.exe"]:
                            raise ValueError("Inventory exited before the window was actionable")
                        cmd = [program, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
                               "-File", str(HERE / "window-quit.ps1"), "-SubjectPid", str(app.pid),
                               "-Window", str(hwnd), "-OutputPath", str(output / "button.json")]
                        with (output / "button.log").open("xb") as observer_log:
                            subprocess.run(cmd, env=env, cwd=trial, check=True, timeout=45,
                                           stdin=subprocess.DEVNULL, stdout=observer_log, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                        result["button"] = json.loads((output / "button.json").read_text(encoding="utf-8-sig"))
                        # Stdin remains open throughout. The button must cause both processes to exit.
                        result["primaryExit"] = app.wait(timeout=20)
                        result["workerAliveAfterQuit"] = result["inventoryPid"] in win.processes()
                    finally:
                        if app.poll() is None:
                            app.stdin.close()
                            try:
                                app.wait(timeout=12)
                            except subprocess.TimeoutExpired:
                                app.kill()
                                app.wait(timeout=5)
            verify_quit(logfile.read_text(encoding="utf-8"), result)
    result["after"] = desktop.context()
    if not native["ordinary_console"](result["after"], name):
        raise ValueError("The fixture desktop changed before its supervisor restored the original")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-desktop")
    args = parser.parse_args()
    if (os.name != "nt" or os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ARCH") != "ARM64"
            or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted" or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        parser.error("Select the disposable native Windows ARM64 rewrite runner")
    import observe as launcher
    native = runpy.run_path(str(QA / "windows-desktop/run.py"))
    desktop = native["Desktop"]()
    result = {"verified": False, "source": os.environ["GITHUB_SHA"], "target": TARGET}
    if args.worker_desktop:
        if not re.fullmatch(r"IfwQa_[0-9a-f]{32}", args.worker_desktop):
            parser.error("Expected a generated fixture desktop")
        record = OUT / "window-quit.json"
        try:
            observe_hosted(args.worker_desktop, desktop, launcher, native, result)
            result["verified"] = True
        except Exception as error:
            result["error"] = str(error)
            raise
        finally:
            native["write"](record, result)
        return
    OUT.mkdir(exist_ok=False)
    try:
        with native["named_input_desktop"](desktop, result) as name:
            native["run_worker"](Path(__file__).resolve(), ["--worker-desktop", name], name, QA.parents[1], result)
        result["returnedDesktop"] = desktop.context()
        if (result["workerExit"] or not result["jobClosed"] or result["cleanup"]["inputAfterRestore"] != "Default"
                or not all(result["cleanup"].get(k) is True for k in ("switchBack", "namedClosed", "originalHandleClosed"))
                or not native["ordinary_console"](result["returnedDesktop"], "Default")
                or result["returnedDesktop"]["session"] != result["beforeSwitch"]["session"]):
            raise RuntimeError("Check the original GUI, button log and desktop restoration")
        observed = json.loads((OUT / "window-quit.json").read_bytes())
        if (not observed["verified"] or not observed["cleanupConfirmed"] or observed["observerPid"] != result["workerPid"]
                or observed["before"]["session"] != result["beforeSwitch"]["session"]
                or observed["after"]["session"] != observed["before"]["session"]):
            raise RuntimeError("The original private trial and its cleaned-up profile are required")
        result["verified"] = True
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        native["write"](OUT / "session.json", result)


if __name__ == "__main__":
    main()
