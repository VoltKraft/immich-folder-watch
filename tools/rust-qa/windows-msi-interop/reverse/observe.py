"""Launch one argument-free Rust secondary while the original MSI WPF GUI owns the production pipe."""
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import AREA, QA, ROOT, TARGETS, launcher, module, read, sha, write
from msi_evidence import payload_details

START = "Folder watcher started with 1 source(s)."
STOP = "Folder watch worker received shutdown signal."
FLUSH = "Flushing pending uploads before shutdown."


def profile_outputs(profile):
    """List only the seeded files and documented shipping worker outputs on the owned profile."""
    selected = []
    for entry in profile.iterdir():
        info = entry.lstat()
        if getattr(info, "st_file_attributes", 0) & 0x400 or entry.is_symlink():
            raise ValueError("Unexpected link in the isolated shipping profile")
        if stat.S_ISREG(info.st_mode):
            if entry.name in {"sync-state.db", "sync-state.db-wal", "sync-state.db-shm"}:
                if info.st_size > 16 * 1024 * 1024:
                    raise ValueError("Synthetic SQLite output exceeds the profile budget")
                selected.append(entry)
            elif entry.name != "config.yaml" and not re.fullmatch(r"\.rw02-owned-[a-f0-9]{32}", entry.name):
                raise ValueError("Unexpected regular file in the shipping profile")
        elif stat.S_ISDIR(info.st_mode) and entry.name in {"logs", "engine-logs"}:
            for log in entry.iterdir():
                details = log.lstat()
                if (not stat.S_ISREG(details.st_mode) or getattr(details, "st_file_attributes", 0) & 0x400
                        or not re.fullmatch(r"immich-folder-watch-\d{8}\.log", log.name) or details.st_size > 2 * 1024 * 1024):
                    raise ValueError("Unexpected shipping log object")
                selected.append(log)
        else:
            raise ValueError("Unexpected entry in the isolated shipping profile")
    return sorted(selected)


def save_outputs(profile, out, api, recorder):
    destination = out / "wpf-profile"
    destination.mkdir()
    hashes = {}
    for src in profile_outputs(profile):
        relative = src.relative_to(profile)
        target = destination / relative
        target.parent.mkdir(exist_ok=True)
        with recorder.pin_path(api, src, False):
            original = sha(src)
            shutil.copyfile(src, target)
            if sha(target) != original:
                raise ValueError("The original shipping output changed during capture")
            hashes[relative.as_posix()] = original
    return hashes


def owned_root(windows, hwnd, pid, tid=None):
    actual = w.DWORD()
    thread = windows.owner(hwnd, c.byref(actual))
    if not thread or actual.value != pid or windows.ancestor(hwnd, 2) != hwnd or (tid is not None and tid != thread):
        raise ValueError("The original WPF root, process or thread changed")
    return int(thread)


def invoke_quit(launch, api, windows, primary, out, row):
    from native import wpf_tray_receiver
    recorder = launch.recorder
    receiver = wpf_tray_receiver(primary.pid)
    if not receiver or receiver[1] != row["root"]["tid"] or primary.poll() is not None:
        raise ValueError("The shipping tray receiver is unavailable on the original UI thread")
    hwnd, tid = receiver
    q = row["quit"]
    q.update(receiver=hwnd, tid=tid, issuedQpc=api.clock())
    # The product's ordinary context-menu callback opens its TrackPopupMenuEx on the receiver thread.
    if not windows.post(hwnd, 0x401, 0, (1 << 16) | 0x007b):
        raise c.WinError(c.get_last_error())
    legacy_ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run([legacy_ps, "-NoLogo", "-NoProfile", "-NonInteractive", "-STA", "-File", HERE / "quit.ps1",
                    "-ProcessId", str(primary.pid), "-Created", str(row["primary"]["created"]),
                    "-Receiver", str(hwnd), "-ThreadId", str(tid), "-Evidence", out / "quit-menu.json"],
                   cwd=out, check=True, timeout=25)
    code = launch.wait_for_exit(primary, windows.pump, 30)
    if code:
        raise ValueError(f"The shipping WPF Quit command exited with {code}")
    q.update(method="shipping tray Quit", exit=code, exitedQpc=api.clock())


def exercise(launch, api, desk, gui, trial, env, image, work, out, row, profile):
    recorder = launch.recorder
    original = read(out / "installed.json")
    digest = payload_details(read(out / "payload-installed.json"), TARGETS[row["target"]][0])
    if Path(original["exe"]) != image or original["exeSha256"] != digest:
        raise ValueError("Expected the original installed and cabinet-bound WPF apphost")
    sid = recorder.sid()
    api.ensure_no_primary(sid)
    desktop = launch.check(desk.thread_desktop(desk.thread()), "GetThreadDesktop")
    name = desk.name(desktop)
    row["desktopBefore"] = desk.context()
    if name != "Default" or not launch.ordinary_console(row["desktopBefore"], name):
        raise ValueError("The original unlocked Windows test desktop is required")
    fixture = recorder.load_windows_fixture()
    fixture.TITLE = "Immich Folder Watch"
    lifetime_type = module("ifw_reverse_window_lifetime", QA / "windows-warm-window/window_lifetime.py").WindowLifetime
    env["IFW_QA_MSI_SECONDARY"] = "1"
    baseline = read(out / "result.json")["wpfProfile"]
    empty_sweep = f"Persistent reconciliation for uploadNew queued 0 changed file(s) from {baseline['media']}."
    if (not re.fullmatch(r"http://127\.0\.0\.1:[1-9]\d{0,4}", baseline["endpoint"])
            or any(os.environ.get(k) != baseline["endpoint"] for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"))
            or os.environ.get("NO_PROXY") != "127.0.0.1,localhost,::1" or sha(profile / "config.yaml") != baseline["configSha256"]
            or profile_outputs(profile) or not Path(baseline["media"]).is_relative_to(work)):
        raise ValueError("The shipping profile, loopback proxy or media directory differs")
    with (out / "missing-wpf.log").open("xb", buffering=0) as stream:
        with launch.child(api, desk, name, gui, [], trial, env, stream, False, private=False) as (missing, job, _):
            code = missing.wait(timeout=10)
            counts = api.job_accounting(job)
            row["missingWpf"] = dict(pid=missing.pid, created=api.process_identity(int(missing._handle)), exit=code,
                                     active=counts.active, total=counts.total, empty=api.wait_job_empty(job, 3))
    api.ensure_no_primary(sid)
    if (code != 1 or counts.total != 1 or counts.active or not row["missingWpf"]["empty"]
            or (trial.parent / "launcher.pid").read_bytes() or profile_outputs(profile)
            or "MSI_REVERSE_ELECTION_ABSENT" not in (out / "missing-wpf.log").read_text(encoding="utf-8").splitlines()):
        raise ValueError("The same compiled Rust executable did not decline the absent WPF election")
    with ExitStack() as stack:
        stack.enter_context(recorder.pin_path(api, image, False))
        if sha(image) != digest:
            raise ValueError("The executable differs from the pinned installed payload")
        wpf_log = out / "wpf.log"
        stream = stack.enter_context(wpf_log.open("xb", buffering=0))
        primary = recorder.start_owned_subject(stack, api, image, work, dict(os.environ), stream, False, recorder.stop_subject)
        first = row["primary"] = dict(pid=primary.pid, created=api.process_identity(int(primary._handle)),
                                      image=str(image), sha256=digest, arguments=[])
        windows = fixture.Windows(primary.pid, desktop)
        stack.callback(windows.close)
        life = lifetime_type(primary.pid)
        stack.callback(life.close)

        def wait(check, label):
            def poll():
                windows.pump()
                recorder.wait_running(primary)
                return check()
            return recorder.await_value(poll, label, timeout=25, delay=.025)

        def root_events():
            return [e["event"] for e in windows.events if e["hwnd"] == hwnd]

        try:
            api.resume_owned_process(primary.pid)
            hwnd = wait(lambda: windows.visible(waiting_for_first=True), "Missing initial WPF window")
            tid = owned_root(windows, hwnd, primary.pid)
            row["root"] = dict(hwnd=hwnd, tid=tid, pid=primary.pid)
            def worker_ready():
                text = wpf_log.read_text(encoding="utf-8", errors="replace")
                return START in text and text.count(empty_sweep) >= 2
            wait(lambda: root_events() == ["show"] and any(x[:2] == (hwnd, "create") for x in life.events)
                 and worker_ready(), "Missing original WPF SHOW, CREATE or two initial worker reconciliations")
            windows.close_window(hwnd)
            wait(lambda: windows.visible() is None and not windows.is_visible(hwnd) and root_events() == ["show", "hide"],
                 "The WPF primary did not retain and hide its original root")
            owned_root(windows, hwnd, primary.pid, tid)
            marker = trial.parent / "launcher.pid"
            marker.write_bytes(f"{primary.pid} {first['created']}".encode("ascii"))
            stack.enter_context(recorder.pin_path(api, marker, False))
            row["before"] = dict(qpc=api.clock(), hwnd=hwnd, visible=False, job=sorted(api.job_pids(primary.benchmark_job)))

            tick = recorder.bind(api.kernel, "GetTickCount64", c.c_uint64)

            def before_resume(proc):
                windows.pump()
                if (windows.is_visible(hwnd) or root_events() != ["show", "hide"] or primary.poll() is not None
                        or api.process_identity(int(primary._handle)) != first["created"]):
                    raise ValueError("The original WPF process or hidden root changed before ResumeThread")
                owned_root(windows, hwnd, primary.pid, tid)
                row["secondary"] = dict(pid=proc.pid, created=api.process_identity(int(proc._handle)), sha256=sha(gui),
                                        arguments=[], cursor=len(windows.events), releaseQpc=api.clock(), releaseTick=tick())

            rust_log = stack.enter_context((out / "rust.log").open("xb", buffering=0))
            with launch.child(api, desk, name, gui, [], trial, env, rust_log, False, private=False,
                              before_resume=before_resume) as (second, job, _):
                sec = row["secondary"]
                sec["resumedTick"] = tick()
                check = sec["afterResume"] = dict(hwnd=hwnd, pid=primary.pid, tid=owned_root(windows, hwnd, primary.pid, tid),
                                                   created=api.process_identity(int(primary._handle)), cursorBefore=len(windows.events),
                                                   beginTick=tick(), beginQpc=api.clock())
                check["visible"] = bool(windows.is_visible(hwnd))
                check.update(endQpc=api.clock(), endTick=tick(), cursorAfter=len(windows.events))
                owned_root(windows, hwnd, primary.pid, tid)
                recorder.wait_running(primary)
                sec["exit"] = launch.wait_for_exit(second, windows.pump, 10)
                counts = api.job_accounting(job)
                sec.update(total=counts.total, active=counts.active, empty=api.wait_job_empty(job, 3))
                if (sec["exit"], counts.total, counts.active, sec["empty"]) != (0, 1, 0, True):
                    raise ValueError("The Rust secondary failed or started another process")
                wait(lambda: windows.visible() == hwnd and root_events() == ["show", "hide", "show"],
                     "The Rust secondary did not reopen the original WPF window")
            owned_root(windows, hwnd, primary.pid, tid)
            row["after"] = dict(qpc=api.clock(), observedTick=tick(), hwnd=hwnd, visible=bool(windows.is_visible(hwnd)),
                                job=sorted(api.job_pids(primary.benchmark_job)), created=api.process_identity(int(primary._handle)))
            row["events"] = list(windows.events)
            row["lifetimes"] = list(life.events)
            # Persist the already completed activation and original logs even if the menu
            # provider or the worker later fails to finish. Keep the two verdicts independent.
            prefix = wpf_log.read_bytes()
            (out / "wpf-before-quit.log").write_bytes(prefix)
            from reverse.evidence import show_order
            try:
                row["showOrder"] = show_order(row)
            except ValueError as exc:
                row.update(showOrder="inconclusive", orderingError=str(exc))
            status = "inconclusive" if row["showOrder"] == "inconclusive" else "reactivated"
            write(out / "before-quit.json", {**row, "status": status, "rustLog": sha(out / "rust.log"),
                                             "wpfPrefix": sha(out / "wpf-before-quit.log")})
            row["quit"] = {}
            try:
                invoke_quit(launch, api, windows, primary, out, row)
            except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
                row["quit"].update(method="owned cleanup", error=str(exc))
                row["quit"]["cleanup"] = recorder.stop_subject(primary, False)
            row["quit"]["empty"] = api.wait_job_empty(primary.benchmark_job, 5)
            if not row["quit"]["empty"]:
                raise ValueError("The shipping process job did not empty")
            row["profileFiles"] = save_outputs(profile, out, api, recorder)
        finally:
            if primary.poll() is None:
                row["fallback"] = recorder.stop_subject(primary, False)
    api.ensure_no_primary(sid)
    row["desktopAfter"] = desk.context()
    if not launch.ordinary_console(row["desktopAfter"], name):
        raise ValueError("The ordinary test desktop changed")


def run(target, out, work, image):
    if out != AREA / "reverse" / target or not work.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve()):
        raise ValueError("Unexpected reverse observation directory")
    launch = launcher()
    if (not launch.recorder.hosted() or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise ValueError("Use the disposable native rewrite runner")
    build = read(out / "build.json")
    staged = work / "subject"
    if (build["target"] != target or build["source"] != os.environ["GITHUB_SHA"]
            or any(sha(staged / n) != digest for n, digest in build["assets"].items())):
        raise ValueError("The native build and staged observer differ")
    api, desk = launch.recorder.Win32(), launch.Desktop()
    if api.machine(-1) != (TARGETS[target][1], TARGETS[target][1]):
        raise ValueError("Expected a target-native Windows observer")
    from native import known_folder
    profile = known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091") / "Immich Folder Watch"
    row = dict(target=target, revision=build["source"], frequency=api.frequency, status="incomplete")
    inventory = dict(build["base"]["inventory"], gui=build["assets"]["native-gui-assessment.exe"])
    try:
        with launch.staged_profile(row, api, staged / "native-gui-assessment.exe", inventory) as (gui, trial, env):
            exercise(launch, api, desk, gui, trial, env, image, work, out, row, profile)
        row["status"] = "observed"
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write(out / "reverse-activation.json", row)


if __name__ == "__main__":
    run(sys.argv[1], *(Path(a).resolve() for a in sys.argv[2:]))
