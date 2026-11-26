"""Replay the installed WPF live backup or both installed upload lifetimes from original files."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath

from shared import INSTALLED, TARGETS, backup, configuration, endpoint_port, module, observer_sources, peer, read, require, sha
from database import main_rows, replay_pair
from owners import decode_connection
from msi_evidence import payload_details, verify_transactions
from reverse.evidence import engine_lines, shutdown


def asset_history(out, posts, phases, media_port):
    expected = [(phase, filename) for phase, filename, _, _ in phases]
    peer.verify_asset_posts(posts, expected)
    images = iter(phases)
    for i, post in enumerate(posts, 1):
        require(post["bodyFile"] == f"asset-post-{i}.body", "Unexpected asset body path")
        body = (out / post["bodyFile"]).read_bytes()
        require(0 <= len(body) == post["declaredBytes"] == post["bytesRead"] <= 65536
                and sha256(body).hexdigest() == post["bodySha256"] and post["client"][0] == "127.0.0.1"
                and 0 < post["entryNs"] <= post["answeredNs"], "Changed original HTTP body or timing")
        if post["kind"] == "permission-probe":
            require(peer.empty_permission_probe(post["contentType"], body), "Unexpected purported empty permission probe")
            continue
        phase, name, image, row = next(images)
        observation = row["upload"]
        connection = decode_connection(bytes.fromhex(row["connection"]))
        require(connection == dict(pid=row["primary"]["pid"], state=5, client=observation["client"], server=observation["server"])
                and connection["client"] == post["client"] and connection["server"] == ["127.0.0.1", media_port]
                and 0 < connection["client"][1] <= 65535 and connection["client"] != connection["server"]
                and (post["phase"], post["filename"]) == (phase, name) and observation["filename"] == name
                and row["introducedNs"] <= post["entryNs"] <= observation["requestNs"] <= row["sampleNs"] <= observation["responseNs"] <= post["answeredNs"]
                and (out / name).read_bytes() == image and (post["bodySha256"], post["contentType"]) ==
                (observation["bodySha256"], observation["contentType"]) and peer.multipart_image(post["contentType"], body, name, image),
                "The original HTTP connection, process, multipart content or response order differs")


def database_rows(state, scope, source, expected):
    tables = state["tables"]
    require(not tables["owned_albums"] and not tables["sync_timestamp_repairs"]
            and len(tables["sync_account_status"]) == 1 and tables["sync_account_status"][0][:2] == (1, scope)
            and tables["sync_account_status"][0][2] and len(tables["sync_entries"]) == len(expected),
            "Unexpected shipping account, album, repair, or number of entries")
    for i, (row, (name, asset, content)) in enumerate(zip(tables["sync_entries"], expected), 1):
        require((row[0], row[1], row[2], row[4], row[6], row[8], row[10], row[11], row[13])
                == (i, scope, source, name, asset, len(content), 0, 0, None) and row[9] and row[12],
                "Different source path, asset identity, size or activity in SQLite")


def original_wpf(out, report, live_only):
    target, machine = TARGETS[report["target"]]
    installed = read(out / "installed.json")
    payload = read(out / "payload-installed.json")
    release = read(INSTALLED / "release.json")
    require(report["format"] == "ifw-installed-wpf-upload-v1"
            and installed["format"] == "ifw-installed-msi-interop-v1" and installed["target"] == report["target"]
            and installed["sourceCommit"] == report["revision"] and str(installed["workflowRun"]) == report["run"]
            and installed["releaseCommit"] == release["commit"] and installed["package"] == release["assets"][target]
            and installed["exeSha256"] == payload_details(payload, target) and installed["payloadSha256"] == payload["sha256"]
            and set(installed["peMachine"].values()) == {machine} and installed["state"]["installDirectory"]
            and installed["state"]["appProcesses"] == 0 and installed["identity"]["packageCode"] == installed["state"]["packageCode"]
            and installed["configSha256"] == report["profile"]["configSha256"], "Different installed WPF or MSI")
    tx = installed["installTransaction"]
    if live_only:
        verify_transactions(out, {"install.log": tx}, [tx["operation"]], installed["identity"], target, install_only=True)
    else:
        end = read(out / "msi-result.json")
        require(end["target"] == report["target"] and end["sourceCommit"] == report["revision"]
                and str(end["workflowRun"]) == report["run"] and end["releaseCommit"] == release["commit"]
                and end["format"] == "ifw-msi-interop-operations-v1" and end["package"] == installed["package"]
                and end["identity"] == installed["identity"] and end["checkpoints"]["installed"] == installed["state"],
                "The final installer record belongs to a different package, process or observation")
        require(end["cleanup"]["msiRemoved"] and end["cleanup"]["packageCode"] == installed["identity"]["packageCode"]
                and end["operations"][0] == tx["operation"] and tx["sha256"] == report["msiTransactions"]["install.log"]["sha256"]
                and all(not any(end["checkpoints"][key][field] for field in
                                ("installDirectory", "appProcesses", "relatedProducts", "registered")) for key in ("before", "after"))
                and report["profileRemoved"] and report["scratchRemoved"], "Installed WPF removal and cleanups did not finish")
        verify_transactions(out, report["msiTransactions"], end["operations"], installed["identity"], target)
        require(end["status"] == "passed", "The WPF observation was incomplete before uninstall. See upload-observation.json.")
    return installed


def process_image(row, installed, machine):
    proc = row["primary"]
    require(proc["sha256"] == installed["exeSha256"] and proc["image"] == installed["exe"]
            and proc["arguments"] == [] and proc["machine"] == [machine, machine] and proc["pid"] == row["root"]["pid"]
            and min(proc["created"], proc["pid"], row["root"]["hwnd"], row["root"]["tid"]) > 0,
            "The original WPF process, machine or window owner differs")


def verify(out, report, live_only):
    from backup_build import verify_archived_build
    require(observer_sources(out, report["revision"]) == report["observerSources"]
            and verify_archived_build(out, report["target"], report["revision"]) == report["backupBuild"],
            "Different original build or observer archive")
    installed = original_wpf(out, report, live_only)
    profile = report["profile"]
    endpoint, media = profile["endpoint"], profile["media"]
    port = endpoint_port(endpoint)
    require(endpoint_port(profile["proxy"]) != port and PureWindowsPath(media).name == "wpf-media"
            and PureWindowsPath(media).parent.name.startswith("ifw-msi-")
            and (out / "shipping-upload.yaml").read_text(encoding="utf-8") == configuration(media, endpoint)
            and sha(out / "shipping-upload.yaml") == profile["configSha256"], "Different owned synthetic upload config")
    first_png = peer.FILENAME, peer.ASSET_ID, peer.IMAGE
    second_png = backup.NEW_NAME, backup.NEW_ID, backup.NEW_IMAGE
    machine = TARGETS[report["target"]][1]
    account = sha256(f"{endpoint}/api\n{peer.TEST_KEY}".encode()).hexdigest()
    live = read(out / "live.json")
    first = live["observation"]
    process_image(first, installed, machine)
    sweep = f"Persistent reconciliation for uploadAll queued 0 changed file(s) from {media}."
    prefix = (out / "original-before-quit.log").read_bytes()
    require(live["prefixSha256"] == sha(out / "original-before-quit.log") and (out / "original/wpf.log").read_bytes().startswith(prefix)
            and sweep.encode() in prefix
            and b"Folder watcher started with 1 source(s)." in prefix and first["primary"]["pid"] in first["jobAtBackup"]
            and first["earlyExit"] != 0 and b"expected the signed worker's committed upload" in (out / "rust-pre-upload.stderr").read_bytes(),
            "Missing WPF worker, empty initial sweep, live job or pre-commit refusal")
    phases = [("original", peer.FILENAME, peer.IMAGE, first)]
    asset_history(out, live["posts"], phases, port)
    info = first["sqlite"]
    raw, wal, returned = (out / name for name in ("live-source.db", "live-source.db-wal", "installed-returned.db"))
    response = read(out / "rust-live-upload.stdout")
    require(not list(out.glob("installed-returned.db-*")) and (sha(raw), sha(wal), sha(returned))
            == (info["main"], info["wal"], info["returned"]) and main_rows(raw) == info["pinnedRows"] == 0
            and response["sqliteSourceId"] == report["backupBuild"]["sqlite"] and response["accountScope"] == account
            and response["returnedSha256"] == sha(returned), "Original SQLite files or helper response changed")
    old = backup.snapshot(returned, standalone=True)
    database_rows(old, account, media, [first_png])
    require(replay_pair(out, raw.name) == old, "Original main/WAL do not reproduce the complete standalone return")
    header = wal.read_bytes()[:32]
    page_size = int.from_bytes(header[8:12], "big")
    frames, rest = divmod(wal.stat().st_size - 32, 24 + page_size)
    require(len(header) == 32 and header[:4] in (bytes.fromhex("377f0682"), bytes.fromhex("377f0683"))
            and 512 <= page_size <= 65536 and not page_size & (page_size - 1)
            and frames > 0 and not rest, "Malformed original WAL")
    result = dict(liveBackup=sha(returned), walFrames=frames, firstAsset=peer.ASSET_ID)
    if live_only:
        return result
    row = read(out / "upload-observation.json")
    original, second = row["original"], row["restored"]
    process_image(second, installed, machine)
    require(row["status"] == "observed" and all(original[k] == v for k,v in first.items())
            and second["primary"]["created"] > first["primary"]["created"]
            and original["quit"]["exitedQpc"] <= original["quit"]["jobDrainedQpc"] <= original["mutexReleasedQpc"]
            <= second["primary"]["startQpc"] <= second["after"]["qpc"]
            and second["reconciledNs"] <= second["introducedNs"] and second["inputSha256"] == info["returned"], "The restored WPF did not follow the captured original")
    owner = second["fileOwner"]
    require((owner["pid"], owner["created"]) == (second["primary"]["pid"], second["primary"]["created"])
            and PureWindowsPath(owner["registeredFile"]) == PureWindowsPath(profile["directory"]) / "sync-state.db"
            and owner["fileId"] == second["fileId"] and len(second["fileId"]) == 2 and second["fileId"][1] > 0,
            "Missing owner or identity of the restored database")
    preserved = out / "original-after-quit"
    require({p.name: sha(p) for p in preserved.iterdir()} == second["originalFiles"]
            and replay_pair(preserved, "sync-state.db") == old, "Original post-Quit state changed")
    posts = read(out / "peer-history.json")
    require(posts[:len(live["posts"])] == live["posts"], "Original held request history changed after restart")
    asset_history(out, posts, [*phases, ("restored", backup.NEW_NAME, backup.NEW_IMAGE, second)], port)
    files = out / "wpf-profile"
    require({p.relative_to(files).as_posix(): sha(p) for p in files.rglob("*") if p.is_file()} == row["profileFiles"],
            "Changed final WPF profile files")
    final = replay_pair(files, "sync-state.db")
    prequit = read(out / "restored-before-quit.json")
    captured = out / "restored-before-quit.snapshot.db"
    require(all(second[k] == v for k,v in prequit.items()) and sha(captured) == second["liveStateSha256"]
            and backup.snapshot(captured, standalone=True) == final, "The restored live WPF state differs from its final profile")
    database_rows(final, account, media, [first_png, second_png])
    require(old["schema"] == final["schema"] and old["tables"]["sync_entries"][0] == final["tables"]["sync_entries"][0]
            and old["tables"]["sync_account_status"][0][2] < final["tables"]["sync_account_status"][0][2],
            "Rollback changed the original entry or did not advance its account")
    messages = []
    for path in sorted((files / "engine-logs").glob("*.log")):
        messages.extend(engine_lines(path.read_text(encoding="utf-8-sig")))
    require(messages.count("Folder watcher started with 1 source(s).") == 2, "Expected two real installed worker starts")
    stops = []
    for label, phase in (("original", original), ("restored", second)):
        console = (out / label / "wpf.log").read_bytes()
        before = (out / (label + "-before-quit.log")).read_bytes()
        require("fallback" not in phase and phase["mutexReleased"] and console.startswith(before)
                and sweep.encode() in before and b"Folder watcher started with 1 source(s)." in before,
                "Ordinary WPF worker life, release or output differs")
        stops.append(shutdown(phase, messages, read(out / label / "quit-menu.json"), console[len(before):].decode("utf-8")))
        require(stops[-1]["orderlyProcessExit"], "The owned job required forced cleanup")
    initial = (out / "restored-first-sweep.log").read_bytes()
    require((out / "restored-before-quit.log").read_bytes().startswith(initial) and sweep.encode() in initial,
            "Missing original zero-change startup reconciliation before the second PNG")
    return dict(**result, secondAsset=backup.NEW_ID, rowIds=[r[0] for r in final["tables"]["sync_entries"]], stops=stops)


def replay(out, live_only=False):
    report = read(out / "result.json")
    checks = verify(out, report, live_only)
    if not live_only:
        release = module("ifw_upload_package_files", INSTALLED / "run.py")
        files = release.evidence_hashes(out)
        del files["result.json"]
        require(report["status"] == "observed" and checks == report["checks"] and files == report["files"],
                "Incomplete original evidence or changed receipt")
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--live-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(replay(args.output.resolve(), args.live_only), indent=2))
