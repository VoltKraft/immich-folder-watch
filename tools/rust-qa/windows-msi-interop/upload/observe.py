"""Observe real uploads from two lifetimes of the original installed WPF."""
from contextlib import ExitStack, closing, contextmanager
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import sys
import threading
import time

from shared import AREA, TARGETS, backup, configuration, endpoint_port, peer, read, require, sha, write
from common import launcher
from database import live_backup, restore, run_helper
from msi_evidence import payload_details
from owners import client_connection, database_owner
from reverse import observe as wpf


class PrivateServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = False

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


@contextmanager
def serving(port, out):
    with PrivateServer(("127.0.0.1", port), peer.UploadPeer) as server:
        server.phase, server.output, server.posts, server.uploads = "original", out, [], []
        server.assets = {peer.FILENAME: (peer.IMAGE, peer.ASSET_ID)}
        server.post_lock, server.received, server.release = threading.Lock(), threading.Event(), threading.Event()
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.release.set()
            server.shutdown()
            thread.join()
            server.server_close()  # all original request threads finished before the last receipt
            write(out / "peer-history.json", server.posts)


@contextmanager
def process(launch, api, desk, image, work, folder, row, machine):
    recorder = launch.recorder
    desktop = launch.check(desk.thread_desktop(desk.thread()), "GetThreadDesktop")
    name = desk.name(desktop)
    require(name == "Default" and launch.ordinary_console(desk.context(), name), "Expected the runner's ordinary desktop")
    api.ensure_no_primary(recorder.sid())
    folder.mkdir()
    log = folder / "wpf.log"
    with ExitStack() as stack:
        stream = stack.enter_context(log.open("xb", buffering=0))
        proc = recorder.start_owned_subject(stack, api, image, work, dict(os.environ), stream, False, recorder.stop_subject)
        handle = int(proc._handle)
        row["primary"] = dict(pid=proc.pid, created=api.process_identity(handle), image=str(image), sha256=sha(image),
                              arguments=[], machine=list(api.machine(handle)), startQpc=proc.benchmark_start_qpc)
        api.verify_job_member(proc.benchmark_job, proc.pid, handle)
        require(api.machine(handle) == (machine, machine), "The installed process is not native to the target")
        fixture = recorder.load_windows_fixture()
        fixture.TITLE = "Immich Folder Watch"
        windows = fixture.Windows(proc.pid, desktop)
        stack.callback(windows.close)
        def wait(check, label, seconds=30):
            def poll():
                windows.pump()
                recorder.wait_running(proc)
                return check()
            return recorder.await_value(poll, label, timeout=seconds, delay=.05)
        try:
            api.resume_owned_process(proc.pid)
            hwnd = wait(lambda: windows.visible(waiting_for_first=True), "Missing installed WPF window")
            row["root"] = dict(hwnd=hwnd, pid=proc.pid, tid=wpf.owned_root(windows, hwnd, proc.pid))
            yield proc, wait, log
            row["after"] = {"qpc": api.clock()}
            row["quit"] = {}
            wpf.invoke_quit(launch, api, windows, proc, folder, row)
            row["quit"]["empty"] = api.wait_job_empty(proc.benchmark_job, 5)
            row["quit"]["jobDrainedQpc"] = api.clock()
            require(row["quit"]["empty"], "The installed primary job did not empty after Quit")
        finally:
            if proc.poll() is None:
                row["fallback"] = recorder.stop_subject(proc, False)
    api.ensure_no_primary(recorder.sid())
    row["mutexReleased"] = True
    row["mutexReleasedQpc"] = api.clock()


def receive(server, proc, wait, row, media, out, name, content):
    require(not server.uploads and not server.received.is_set(), "Unexpected upload before introducing the PNG")
    row["introducedNs"] = time.monotonic_ns()
    with (media / name).open("xb") as file:
        file.write(content)
    shutil.copyfile(media / name, out / name)
    wait(server.received.is_set, "No real asset upload arrived")
    observation, = server.uploads
    require(observation["filename"] == name, "The installed worker uploaded a different file")
    row["connection"] = client_connection(proc, observation)
    row["sampleNs"] = time.monotonic_ns()
    row["upload"] = observation
    server.release.set()


def exercise(launch, api, desk, image, work, out, report, row, profile, marker):
    inputs = report["profile"]
    media, database = work / "wpf-media", profile / "sync-state.db"
    port = endpoint_port(inputs["endpoint"])
    machine = TARGETS[report["target"]][1]
    installed = read(out / "installed.json")
    require(Path(installed["exe"]) == image and installed["exeSha256"] == sha(image)
            == payload_details(read(out / "payload-installed.json"), TARGETS[report["target"]][0]),
            "Expected the original installed WPF apphost and cabinet")
    require(Path(inputs["directory"]) == profile and Path(inputs["media"]) == media and not list(media.iterdir())
            and marker.name == inputs["marker"] and marker.read_text(encoding="ascii") == marker.name.removeprefix(".rw02-owned-")
            and not wpf.profile_outputs(profile) and inputs["configSha256"] == sha(profile / "config.yaml")
            and (profile / "config.yaml").read_text(encoding="utf-8") == configuration(media, inputs["endpoint"])
            and endpoint_port(inputs["proxy"]) != port and all(os.environ.get(k) == inputs["proxy"] for k in
                ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")) and os.environ.get("NO_PROXY") == "127.0.0.1,localhost,::1",
            "Expected only the freshly marked upload profile and the separate closed proxy")
    expected_sweep = f"Persistent reconciliation for uploadAll queued 0 changed file(s) from {media}."
    helper = work / "installed_upload_backup.exe"
    def run(stem):
        return run_helper(work, out, profile, marker, port, report["backupBuild"], stem)
    with ExitStack() as pins:
        for file in (helper, image, profile / "config.yaml", marker):
            pins.enter_context(launch.recorder.pin_path(api, file, False))
        server = pins.enter_context(serving(port, out))
        first = row["original"] = {}
        with process(launch, api, desk, image, work, out / "original", first, machine) as (proc, wait, log):
            wait(lambda: expected_sweep in log.read_text(encoding="utf-8", errors="replace"), "Missing first empty original sweep")
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as reader:
                reader.execute("BEGIN")
                require(reader.execute("PRAGMA journal_mode").fetchone() == ("wal",)
                        and reader.execute("SELECT count(*) FROM sync_entries").fetchone() == (0,),
                        "The pinned WPF read transaction does not have the empty WAL view")
                first["earlyExit"] = run("rust-pre-upload")
                require(first["earlyExit"] != 0 and b"expected the signed worker's committed upload" in
                        (out / "rust-pre-upload.stderr").read_bytes() and not (work / "installed-returned.db").exists(),
                        "The Rust helper accepted an empty live database")
                receive(server, proc, wait, first, media, out, peer.FILENAME, peer.IMAGE)
                def committed_original():
                    current = backup.snapshot(database)["tables"]
                    entries = current["sync_entries"]
                    return (len(current["sync_account_status"]) == 1 and len(entries) == 1
                            and (entries[0][4], entries[0][6]) == (peer.FILENAME, peer.ASSET_ID))
                wait(committed_original, "No durable original account and upload history")
                first["sqlite"] = live_backup(database, work, out, reader, run)
                first["jobAtBackup"] = sorted(api.job_pids(proc.benchmark_job))
                api.verify_job_member(proc.benchmark_job, proc.pid, int(proc._handle))
                launch.recorder.wait_running(proc)
                wait(lambda: any(p.get("kind") == "matched-image" and p.get("status") == 201 for p in server.posts),
                     "Original asset response did not complete")
                (out / "original-before-quit.log").write_bytes(log.read_bytes())
                write(out / "live.json", dict(observation=first, posts=server.posts, prefixSha256=sha(out / "original-before-quit.log")))
        require(first["quit"]["empty"] and first["mutexReleased"], "The first WPF still owns its runtime")
        archived = restore(profile, out)
        identity_handle = api.path_handle(database, False, allow_writer=True)
        try:
            attributes, identity = api.file_info(identity_handle)
            require(not attributes & 0x410, "The restored database is not a regular file")
            second = row["restored"] = dict(originalFiles=archived, fileId=list(identity), inputSha256=sha(database))
            server.phase, server.uploads = "restored", []
            server.received.clear()
            server.release.clear()
            server.assets[backup.NEW_NAME] = (backup.NEW_IMAGE, backup.NEW_ID)
            with process(launch, api, desk, image, work, out / "restored", second, machine) as (proc, wait, log):
                wait(lambda: expected_sweep in log.read_text(encoding="utf-8", errors="replace"),
                     "No restored startup reconciliation of the unchanged PNG")
                second["fileOwner"] = wait(lambda: database_owner(database, proc, second["primary"]["created"]),
                                           "The restored WPF never opened this database")
                named = api.path_handle(database, False, allow_writer=True)
                try:
                    second["fileOwner"]["fileId"] = list(api.file_info(named)[1])
                finally:
                    launch.check(api.close(named), "CloseHandle")
                require(second["fileOwner"]["fileId"] == second["fileId"] and not server.uploads
                        and (media / peer.FILENAME).read_bytes() == peer.IMAGE and backup.snapshot(database)["tables"]["sync_entries"]
                        == backup.snapshot(out / "installed-returned.db", standalone=True)["tables"]["sync_entries"],
                        "The restored WPF changed the original file or entry")
                (out / "restored-first-sweep.log").write_bytes(log.read_bytes())
                second["reconciledNs"] = time.monotonic_ns()
                receive(server, proc, wait, second, media, out, backup.NEW_NAME, backup.NEW_IMAGE)
                def committed():
                    current = backup.snapshot(database)["tables"]
                    saved = backup.snapshot(out / "installed-returned.db", standalone=True)["tables"]
                    return (len(current["sync_entries"]) == 2 and current["sync_account_status"]
                            and current["sync_account_status"][0][2] > saved["sync_account_status"][0][2])
                wait(committed, "Restored worker did not commit its second upload and account history")
                require(api.file_info(identity_handle)[1] == identity, "The restored database identity changed")
                last = out / "restored-before-quit.snapshot.db"
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(last)) as dest:
                    src.backup(dest)
                    require(dest.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",), "Incomplete final snapshot")
                require(backup.snapshot(last, standalone=True) == backup.snapshot(database), "The final live WPF state changed")
                second["liveStateSha256"] = sha(last)
                (out / "restored-before-quit.log").write_bytes(log.read_bytes())
                write(out / "restored-before-quit.json", second)
        finally:
            launch.check(api.close(identity_handle), "CloseHandle")
        require((media / peer.FILENAME).read_bytes() == peer.IMAGE and (media / backup.NEW_NAME).read_bytes() == backup.NEW_IMAGE,
                "The resumed shipping worker altered either synthetic image")
        row["profileFiles"] = wpf.save_outputs(profile, out, api, launch.recorder)


def run(target, out, work, image):
    launch = launcher()
    from native import known_folder
    require(launch.recorder.hosted() and os.getenv("GITHUB_REPOSITORY") == "VoltKraft/immich-folder-watch"
            and os.getenv("GITHUB_REF") == "refs/heads/rewrite/rust" and out == AREA / "upload" / target
            and work.parent == Path(os.environ["RUNNER_TEMP"]).resolve() and work.name.startswith("ifw-msi-"),
            "Use the native installed upload trial on the fresh rewrite runner")
    api, desk = launch.recorder.Win32(), launch.Desktop()
    require(api.machine(-1) == (TARGETS[target][1], TARGETS[target][1]), "Incorrect native observer architecture")
    profile = known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091") / "Immich Folder Watch"
    marker, = profile.glob(".rw02-owned-*")
    report = read(out / "result.json")
    require(report["revision"] == os.environ["GITHUB_SHA"] and report["run"] == os.environ["GITHUB_RUN_ID"]
            and report["target"] == target and re.fullmatch(r"\.rw02-owned-[a-f0-9]{32}", marker.name),
            "The upload observer is bound to another run or profile")
    row = {"status": "incomplete"}
    try:
        exercise(launch, api, desk, image, work, out, report, row, profile, marker)
        row["status"] = "observed"
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        if not launch.recorder.CleanupUnconfirmed.in_chain(exc) and not (out / "wpf-profile").exists():
            try:
                row["partialProfileFiles"] = wpf.save_outputs(profile, out, api, launch.recorder)
            except (OSError, ValueError) as capture_error:
                row["partialCaptureError"] = str(capture_error)
        raise
    finally:
        write(out / "upload-observation.json", row)


if __name__ == "__main__":
    run(sys.argv[1], *(Path(a).resolve() for a in sys.argv[2:]))
