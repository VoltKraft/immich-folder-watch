"""Replay the original HWND, authenticated Rust pipe, installed worker and separate quit observation."""
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import QA, module, read, sha

QUIT_SOURCE = "f50baad6accfd09afc3e86beb9908027b8498525f6a787f35d217841c86c9e5c"

def show_order(row):
    root, sec = row["root"], row["secondary"]
    events = row["events"]
    matches = [(i, e) for i, e in enumerate(events) if i >= sec["cursor"] and e["hwnd"] == root["hwnd"]]
    if len(matches) != 1 or matches[0][1]["event"] != "show" or matches[0][1]["root"] is not True:
        raise ValueError("Missing unique native root SHOW after the release cursor")
    index, event = matches[0]
    earliest, resumed, final = sec["releaseTick"], sec["resumedTick"], row["after"]["observedTick"]
    stamp = earliest + ((event["winEventTimeMs"] - earliest) & 0xffffffff)
    probe = sec["afterResume"]
    if (not 0 <= earliest <= resumed <= probe["beginTick"] <= probe["endTick"] <= final <= earliest + 35000
            or not earliest <= stamp <= final or not sec["cursor"] <= probe["cursorBefore"] <= probe["cursorAfter"] <= len(events)
            or not sec["releaseQpc"] <= probe["beginQpc"] <= probe["endQpc"] <= row["after"]["qpc"]
            or (probe["pid"], probe["hwnd"], probe["tid"], probe["created"]) !=
               (root["pid"], root["hwnd"], root["tid"], row["primary"]["created"])
            or type(probe["visible"]) is not bool):
        raise ValueError("The native root query or SHOW lies outside the measured resume interval")
    if not probe["visible"] and (probe["cursorAfter"] > index or stamp < probe["beginTick"]):
        raise ValueError("The purported hidden-after-resume sample contradicts the actual SHOW")
    if stamp > resumed:
        return "distinct native ticks"
    if not probe["visible"]:
        return "original HWND hidden after resume"
    raise ValueError("A tied native SHOW lacks an original hidden-root observation after resume")


def pipe_and_window(row, log, digest, compiled):
    primary, secondary, root = row["primary"], row["secondary"], row["root"]
    wpf, rust = primary["pid"], secondary["pid"]
    hwnd = root["hwnd"]
    before, after = row["before"], row["after"]
    if (any(type(n) is not int or n <= 0 for n in (wpf, rust, hwnd, root["tid"], primary["created"], row["frequency"]))
            or wpf == rust or root["pid"] != wpf or secondary["created"] <= primary["created"]
            or primary["arguments"] != [] or secondary["arguments"] != [] or primary["sha256"] != digest
            or secondary["sha256"] != compiled or (secondary["exit"], secondary["total"], secondary["active"]) != (0, 1, 0)
            or secondary["empty"] is not True or not 0 < before["qpc"] < secondary["releaseQpc"] <= after["qpc"]
            or (before["hwnd"], before["visible"], before["job"]) != (hwnd, False, [wpf])
            or (after["hwnd"], after["visible"], after["job"], after["created"]) != (hwnd, True, [wpf], primary["created"])):
        raise ValueError("The original WPF process or single argument-free Rust secondary differs")
    lines = log.splitlines()
    if (len(lines) != 4 or lines[0] != f"MSI_REVERSE_CONNECTED client={rust} server={wpf} created={primary['created']}"
            or lines[1] != f"MSI_REVERSE_SENT server={wpf} bytes=8"
            or not re.fullmatch(rf"LAUNCHER_FOREGROUND_GRANT server={wpf} state=(granted|denied hresult=-?\d+|unavailable reason=(input-desktop|process-handle|process-identity))", lines[2])
            or lines[3] != f"LAUNCHER_SECONDARY server={wpf}"):
        raise ValueError("The original connected pipe, send or Rust secondary return differs")
    cursor, events = secondary["cursor"], row["events"]
    if type(cursor) is not int or not 2 <= cursor < len(events):
        raise ValueError("Missing absolute WinEvent cursor at suspended secondary release")
    def select(raw):
        picked = [e for e in raw if e["hwnd"] == hwnd]
        if any(e["root"] is not True or not 0 <= e["winEventTimeMs"] <= 0xffffffff for e in picked):
            raise ValueError("Invalid WinEvent on original root")
        return [e["event"] for e in picked]
    if (select(events[:cursor]) != ["show", "hide"] or select(events[cursor:]) != ["show"]
            or [event for h, event, tick in row["lifetimes"] if h == hwnd] != ["create"]):
        raise ValueError("The raw show after release must belong to the original, undestroyed WPF root")
    order = show_order(row)
    if row["showOrder"] != order:
        raise ValueError("The recorded WPF SHOW ordering differs from the native evidence")
    return dict(wpfPid=wpf, rustPid=rust, hwnd=hwnd, uiThread=root["tid"], rustExit=secondary["exit"], order=order)


def engine_lines(text):
    prefix = r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} [+-]\d\d:\d\d \[Information\] ImmichFolderWatch\.Core\.Services\.FolderWatchWorker: "
    return [line[m.end():] for line in text.splitlines() if (m := re.match(prefix, line))]


def worker_files(out, expected):
    folder = out / "wpf-profile"
    files = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*") if p.is_file()}
    if files != expected or "sync-state.db" not in files or any(
            k not in {"sync-state.db", "sync-state.db-wal", "sync-state.db-shm"} and
            not re.fullmatch(r"(logs|engine-logs)/immich-folder-watch-\d{8}\.log", k) for k in files):
        raise ValueError("The preserved post-exit shipping profile differs")
    messages = []
    for name in sorted(k for k in files if k.startswith("engine-logs/")):
        messages.extend(engine_lines((folder / name).read_text(encoding="utf-8-sig")))
    if messages.count("Folder watcher started with 1 source(s).") != 1:
        raise ValueError("Expected one shipping worker startup in its original log")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        for name in ("sync-state.db", "sync-state.db-wal", "sync-state.db-shm"):
            if name in files:
                shutil.copyfile(folder / name, dest / name)
        db = sqlite3.connect((dest / "sync-state.db").as_uri() + "?mode=ro", uri=True)
        try:
            tables = {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if (db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                    or not {"owned_albums", "sync_entries", "sync_timestamp_repairs"} <= tables
                    or any(db.execute(f"SELECT count(*) FROM {name}").fetchone() != (0,)
                           for name in ("owned_albums", "sync_entries", "sync_timestamp_repairs"))):
                raise ValueError("The shipping worker's post-exit SQLite differs from the empty synthetic source")
        finally:
            db.close()
    return messages


def verify_menu_anchor(menu, root):
    anchor = menu["anchor"]
    rect, point = anchor["clientRect"], anchor["point"]
    width, height = rect["right"] - rect["left"], rect["bottom"] - rect["top"]
    def owned(hit):
        return (hit["hwnd"] > 0 and hit["root"] == root["hwnd"] and hit["pid"] == hit["rootPid"] == root["pid"]
                and hit["tid"] == hit["rootTid"] == root["tid"])
    probes = anchor.get("probes")
    if (not isinstance(probes, list) or not 1 <= len(probes) <= 16 or probes[-1] != anchor["before"] or not owned(probes[-1])
            or any(owned(hit) for hit in probes[:-1])):
        raise ValueError("The tray menu anchor did not use the first owned point")
    column, row = (len(probes) - 1) % 4, (len(probes) - 1) // 4
    eighths = (6, 4, 7, 2)
    expected = dict(x=rect["left"] + eighths[column] * width // 8, y=rect["top"] + eighths[row] * height // 8)
    if (menu["root"] != root["hwnd"] or menu["stage"] != "original-close" or anchor["dpiContext"] != "per-monitor-v2"
            or min(width, height) < 4 or point != expected
            or point != anchor["cursor"] or point != anchor["physicalCursor"]):
        raise ValueError("The tray menu anchor is outside the original WPF client or changed DPI coordinates")
    for hit in (anchor["before"], anchor["after"]):
        if not owned(hit):
            raise ValueError("The tray menu anchor belongs to a different WPF window or thread")


def shutdown(row, messages, menu, post_quit_console):
    q = row["quit"]
    if q["empty"] is not True:
        raise ValueError("The shipping process job did not drain")
    if q["method"] == "owned cleanup":
        if not q.get("error") or q["cleanup"]["method"] not in ("already exited", "owned process terminated after sampling"):
            raise ValueError("Missing evidence of owned cleanup after unavailable Quit")
        return dict(method=q["method"], orderlyProcessExit=False, reason=q["error"])
    root = row["root"]
    verify_menu_anchor(menu, root)
    popup = menu["menuHwnd"]
    interaction = f"tray-menu-quit; popup={popup}; verifiedHighlightedCommandId=3; nativeMouseClick"
    if (q["method"] != "shipping tray Quit" or q["exit"] != 0 or menu["status"] != "invoked"
            or not row["after"]["qpc"] <= q["issuedQpc"] <= q["exitedQpc"]
            or (menu["pid"], menu["created"], menu["receiver"], menu["tid"]) != (
                root["pid"], row["primary"]["created"], q["receiver"], root["tid"])
            or q["tid"] != root["tid"] or q["receiver"] <= 0 or type(popup) is not int or popup <= 0
            or menu["sourceSha256"] != QUIT_SOURCE or menu["rawInteraction"] != interaction):
        raise ValueError("The original native Quit selection, timing or process identity differs")
    started = messages.index("Folder watcher started with 1 source(s).")
    def seen(message):
        return message in messages[started+1:] and f"FolderWatchWorker[0] {message}" in post_quit_console
    return dict(method=q["method"], exit=q["exit"], orderlyProcessExit=True,
                flushStarted=seen("Flushing pending uploads before shutdown."), flushCompletion="unobserved",
                shutdownSignal=seen("Folder watch worker received shutdown signal."))


def verify_prequit(out, report, build, installed):
    row = read(out / "before-quit.json")
    prefix = (out / "wpf-before-quit.log").read_bytes()
    sweep = f"Persistent reconciliation for uploadNew queued 0 changed file(s) from {report['wpfProfile']['media']}.".encode()
    if (row["status"] != "reactivated" or row["revision"] != report["revision"] or row["target"] != report["target"]
            or row["primary"]["image"] != installed["exe"] or row["wpfPrefix"] != sha(out / "wpf-before-quit.log")
            or row["rustLog"] != sha(out / "rust.log")
            or ((out / "wpf.log").exists() and not (out / "wpf.log").read_bytes().startswith(prefix))
            or prefix.count(b"Folder watcher started with 1 source(s).") != 1 or prefix.count(sweep) < 2):
        raise ValueError("The pre-Quit observation or original shipping worker startup differs")
    return pipe_and_window(row, (out / "rust.log").read_text(encoding="utf-8"),
                           installed["exeSha256"], build["application"]["sha256"])


def verify_activation(out, report, build, installed):
    row = read(out / "reverse-activation.json")
    if (row["status"] != "observed" or row["target"] != report["target"] or row["revision"] != report["revision"]
            or row["primary"]["image"] != installed["exe"] or row.get("cleanupConfirmed") is not True
            or not row["stagedDirectory"]["removed"] or not all(x["absent"] for x in row["stagedImageCleanup"].values())
            or row["stagedProfile"]["gui"] != build["assets"]["native-gui-assessment.exe"]
            or row["stagedProfile"]["worker"] != build["assets"]["ifw-performance-worker.exe"]):
        raise ValueError("The reverse assessment does not belong to the measured build or discarded profile")
    context = module("reverse_desktop_readback", QA / "windows-desktop/win32.py")
    if (any(not context.ordinary_console(row[k], "Default") for k in ("desktopBefore", "desktopAfter"))
            or row["desktopBefore"]["session"] != row["desktopAfter"]["session"]):
        raise ValueError("The shipping and Rust processes require the same unlocked Windows session")
    absent = row["missingWpf"]
    absent_log = (out / "missing-wpf.log").read_text(encoding="utf-8")
    if (not 0 < absent["created"] < row["primary"]["created"] or absent["pid"] <= 0
            or (absent["exit"], absent["total"], absent["active"], absent["empty"]) != (1, 1, 0, True)
            or absent_log.splitlines()[:1] != ["MSI_REVERSE_ELECTION_ABSENT"] or "LAUNCHER_" in absent_log):
        raise ValueError("The argument-free executable did not reject a missing WPF installation owner")
    response = verify_prequit(out, report, build, installed)
    before = read(out / "before-quit.json")
    if any(row[k] != before[k] for k in ("primary", "secondary", "root", "events", "lifetimes", "before", "after", "missingWpf")):
        raise ValueError("The completed activation differs from the capture saved before Quit")
    worker = worker_files(out, row["profileFiles"])
    raw = (out / "wpf.log").read_text(encoding="utf-8", errors="replace")
    if raw.count("Folder watcher started with 1 source(s).") != 1:
        raise ValueError("Missing the original WPF process's own worker startup")
    menu_path = out / "quit-menu.json"
    prefix = (out / "wpf-before-quit.log").read_bytes()
    suffix = (out / "wpf.log").read_bytes()[len(prefix):].decode("utf-8", errors="replace")
    stop = shutdown(row, worker, read(menu_path) if menu_path.exists() else {}, suffix)
    if not stop["orderlyProcessExit"] or not (stop["shutdownSignal"] or stop["flushStarted"]):
        raise ValueError("Incomplete WPF worker shutdown; replay the original activation with --before-quit")
    response["workerStop"] = stop
    return response
