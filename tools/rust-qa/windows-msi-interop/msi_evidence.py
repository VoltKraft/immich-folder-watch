"""Independently rebuild the MSI, launcher and post-activation inventory checks."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import struct
import subprocess
from urllib.parse import unquote
from zipfile import ZipFile

from common import BEFORE, HERE, INSTALLED, QA, ROOT, TARGETS, launcher_variant, read, sha, verify_source_inputs


def independent_session(text, worker, earliest, latest):
    """Join the sparse x64 session's native snapshots to the actual two-pass challenge."""
    rows = text.splitlines()
    if (len(rows) < 8 or rows[1] != f"READY {worker} rust" or rows[3] != "MSI_DISABLE 0"
            or rows[6] != "MSI_DECODE 0 0 0"):
        raise ValueError("Missing the independent ETW session, provider disable or loss-free ETL decode")
    phases = {}
    for name, index in (("attached", 0), ("captured", 2), ("disabled", 4), ("stopped", 5)):
        match = re.fullmatch(rf"MSI_ETW {name} pid={worker} qpc=(\d+) mode=(\d+) eventsLost=0 logLost=0 "
                             r"realtimeLost=0 allocated=(\d+) written=(\d+)", rows[index])
        if not match:
            raise ValueError("Missing or lossy ETW phase: " + name)
        qpc, mode, allocated, written = map(int, match.groups())
        # Sequential file logging with EVENT_TRACE_INDEPENDENT_SESSION_MODE. The SDK may
        # report additional flags. A circular/overwriting ETL cannot attest the two passes.
        if mode & 0x08000001 != 0x08000001 or mode & (0x02 | 0x400):
            raise ValueError("The ETW session did not use independent sequential file logging")
        phases[name] = dict(qpc=qpc, mode=mode, allocated=allocated, written=written)
    if not (0 < phases["attached"]["qpc"] <= earliest < latest <= phases["captured"]["qpc"]
            <= phases["disabled"]["qpc"] <= phases["stopped"]["qpc"] and phases["stopped"]["written"] > 0):
        raise ValueError("The ETW session counters did not enclose both file reconciliations")
    return "\n".join(rows[1:2] + rows[7:]), phases


def sparse_inventory(text, worker, earliest, latest):
    rows = text.splitlines()
    if len(rows) != 205 or rows[0] != f"READY {worker} rust" or rows[-1] != "COMPLETE":
        raise ValueError("Incomplete original worker ETW decoder output")
    details = rows[1].split()
    if len(details) != 9 or details[0] != "COUNTS":
        raise ValueError("Missing native file trace counters")
    starts, ends, *errors = map(int, details[1:])
    if min(starts, ends) < 4 or any(errors):
        raise ValueError("Failed, lost, pending or duplicate file observations")
    i, previous = 2, earliest
    observations = []
    for sweep in range(2):
        for directory in range(100):
            kind, p, index, enum, count = rows[i].split()
            i += 1
            if (kind != "D" or (int(p), int(index)) != (sweep, directory)
                    or (directory == 0 and not (previous < int(enum) <= latest and int(count) == 1))
                    or (directory and (int(enum) or int(count)))):
                raise ValueError("The kernel did not observe exactly the introduced directory and file")
            if directory == 0:
                first = int(enum)
        kind, p, lo, hi, count = rows[i].split()
        i += 1
        if kind != "B" or int(p) != sweep or lo != hi or int(count) != 1 or not first <= int(lo) <= latest:
            raise ValueError("The original file identity query is missing from a reconciliation")
        previous = int(lo)
        observations.append(dict(directoryQpc=first, fileQpc=previous))
    return observations


def payload_details(payload, target):
    expected = {"windows-x64": (439, 149235325, "96711b33e8d8e72228ab213b733438a972dc4ada44f9cfbf973e13244a250940"),
                "windows-arm64": (438, 160659509, "8a0d6104742f6b3e5f448f70064afc4cdcb3e3feda1759d2b2e21652c003c8ab")}[target]
    entries = payload["entries"]
    digest = sha256()
    for name in sorted(entries):
        item = entries[name]
        if not re.fullmatch("[0-9a-f]{64}", item["sha256"]) or not isinstance(item["bytes"], int) or item["bytes"] < 0:
            raise ValueError("Invalid installed file record")
        digest.update(f"{name}\t{item['bytes']}\t{item['sha256']}\n".encode())
    if (len(entries), sum(r["bytes"] for r in entries.values()), digest.hexdigest()) != expected or (
            payload["files"], payload["bytes"], payload["sha256"]) != expected:
        raise ValueError("The installed files differ from the original shipping cabinet")
    app = entries["AppExecutableFile"]
    if app["path"] != "ImmichFolderWatch.exe":
        raise ValueError("The observed executable is not the shipping apphost")
    return app["sha256"]


def bytes_sha(data):
    return sha256(data).hexdigest()


def verify_transactions(out, recorded, operations, identity, target, *, install_only=False):
    expected = [("/i", "install.log")]
    if not install_only:
        expected.append(("/x", "uninstall.log"))
    if ([(op["operation"], op["log"]) for op in operations] != expected
            or set(recorded) != {name for _, name in expected}
            or any(op["timedOut"] or op["exitCode"] != 0 for op in operations)):
        raise ValueError("A successful install followed by an owned uninstall is required")
    package = PureWindowsPath(operations[0]["subject"])
    asset = read(INSTALLED / "release.json")["assets"][target]
    if not package.is_absolute() or package.name != asset["name"] or (not install_only and operations[1]["subject"].lower() != identity["productCode"].lower()):
        raise ValueError("The Windows Installer transaction used an unexpected package or product")
    paths = []
    for _, name in expected:
        original = out / name
        path = PureWindowsPath(recorded[name]["nativePath"])
        if not path.is_absolute() or path.name != name or not original.is_file() or sha(original) != recorded[name]["sha256"]:
            raise ValueError("Missing or unbound original MSI log: " + name)
        paths.append(path.parent)
    if len(set(paths)) != 1:
        raise ValueError("The installer logs came from different native directories")
    request = dict(identity=identity, arch=target.removeprefix("windows-"), logs=recorded)
    replay = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(HERE / "transaction-logs.ps1"),
                             "-Directory", str(out.resolve()), *(["-InstallOnly"] if install_only else [])], input=json.dumps(request), encoding="utf-8", capture_output=True)
    if replay.returncode:
        raise ValueError("Original MSI transaction replay failed: " + replay.stderr.strip())
    checks = json.loads(replay.stdout)
    if checks != {op["log"]: op["actions"] for op in operations}:
        raise ValueError("Raw Windows Installer actions differ from their native recording")
    return checks


def compiler_rows(lines):
    messages = [json.loads(line) for line in lines.splitlines()]
    if [m for m in messages if m["reason"] == "build-finished"] != [{"reason":"build-finished","success":True}] or messages[-1]["reason"] != "build-finished":
        raise ValueError("Incomplete native compiler stream")
    units = [m for m in messages if m["reason"] == "compiler-artifact"]
    rows = set()
    for unit in units:
        source, identity = unit["package_id"].rsplit("#", 1)
        name, version = identity.split("@", 1) if "@" in identity else (PurePosixPath(unquote(source)).name, identity)
        rows.add((name, version, tuple(sorted(unit["features"]))))
    gui, = [u for u in units if u["target"]["name"] == "native-gui-assessment" and u["target"]["kind"] == ["bin"]]
    if (PureWindowsPath(gui["executable"]).name != "native-gui-assessment.exe" or gui["executable"] not in gui["filenames"]
            or PureWindowsPath(gui["target"]["src_path"]).parts[-2:] != ("src", "main.rs")):
        raise ValueError("The original GUI compiler output is missing")
    return rows, units


def verify_build(out, result):
    patch, after = launcher_variant(result.get("direction") == "wpf-primary")
    b = read(out / "build.json")
    if (b["source"], b["target"]) != (result["revision"], result["target"]) or (
            b["sourceArchive"], b["compiler"]) != (sha(out / "sources.zip"), sha(out / "compiler.jsonl")):
        raise ValueError("Unexpected native source or compiler stream")
    with ZipFile(out / "sources.zip") as z:
        canonical = json.loads(z.read("canonical/build.json"))
        ordinary = json.loads(z.read("ordinary/build.json"))
        raw = z.read("after/windows_launcher.rs")
        base = b["base"]
        if (bytes_sha(z.read("before/windows_launcher.rs")) != BEFORE or bytes_sha(raw) != after
                or sha(QA / "gui/src/windows_launcher.rs") != BEFORE or z.read("launcher.patch") != patch.read_bytes()
                or b["sources"] != {**ordinary["compilerInputs"], "windows_launcher.rs": after}
                or ordinary["compilerInputs"]["windows_launcher.rs"] != BEFORE
                or ordinary["revision"] != b["source"] or ordinary["target"] != b["target"]
                or canonical["target"] != b["target"] or canonical["source"] != b["source"]
                or ordinary["baseline"] != canonical["binarySha256"] or base["gui"] != ordinary["binary"]
                or b["assets"]["native-gui-assessment.exe"] == ordinary["binary"]
                or sha256(z.read("canonical/graph.json")).hexdigest() != canonical["graphSha256"]
                or canonical["graphSha256"] != ordinary["canonicalGraph"]
                or bytes_sha(z.read("Cargo.lock")) != ordinary["lock"]
                or bytes_sha(z.read("ordinary/eframe-source.zip")) != ordinary["eframeSource"]["archiveSha256"]
                or bytes_sha(z.read("ordinary/compiler.jsonl")) != ordinary["compilerEvidence"]["sha256"]
                or bytes_sha(z.read("canonical/build.json")) != ordinary["baselineReceipt"]
                or bytes_sha(z.read("ordinary/build.json")) != base["buildReceipt"]
                or any(sha(ROOT / n) != d for n, d in {**base["inventory"]["sources"], **base["observerInputs"]}.items())):
            raise ValueError("The private launcher differs from its source-bound native ordinary build")
        standard, _ = compiler_rows(z.read("ordinary/compiler.jsonl"))
    expected, units = compiler_rows((out / "compiler.jsonl").read_bytes())
    if (expected != standard or expected != {(n, v, tuple(f)) for n,v,f in b["rows"]}
            or b["units"] != dict(units=len(units), featureSets=len(expected), packages=len({i[:2] for i in expected}))
            or b["assets"] != {"native-gui-assessment.exe": b["application"]["sha256"],
                               "ifw-performance-worker.exe": base["inventory"]["worker"],
                               "file-observer.exe": base["inventory"]["fileObserver"]}):
        raise ValueError("The native compiler graph or worker/observer sources changed")
    for name, expected_digest in b["assets"].items():
        path = out / name
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Missing native PE")
            stream.seek(60)
            stream.seek(struct.unpack("<I", stream.read(4))[0])
            machine = stream.read(6)
        if machine != b"PE\0\0" + struct.pack("<H", TARGETS[b["target"]][1]) or sha(path) != expected_digest:
            raise ValueError("Wrong native executable or architecture")
    return b


def activation(row, log, etw, exe_digest, *, independent=False):
    primary, creation = row["primary"]
    worker, worker_creation = row["worker"]
    sec, root = row["secondary"], row["root"]
    client = sec["pid"]
    if (row["status"] != "observed" or min(primary, worker, client, creation, worker_creation, sec["created"], row["frequency"]) <= 0
            or len({primary,worker,client}) != 3 or (sec["exit"], sec["totalProcesses"], sec["activeAfter"]) != (0,1,0)
            or sec["sha256"] != exe_digest or sec["arguments"] != [] or not row["jobDrained"]
            or row["quit"] != {"method": "control-Q", "exitCode": 0} or row.get("cleanupConfirmed") is not True
            or not row["stagedDirectory"]["removed"] or not all(v["absent"] for v in row["stagedImageCleanup"].values())):
        raise ValueError("Wrong launch identity, exit or native process cleanup")
    for phase in ("before","after"):
        members = row[phase]["members"]
        if (set(row[phase]["pids"]) != {m["pid"] for m in members}
                or len({m["pid"] for m in members}) != len(members)
                or sum(m["role"] == "primary" for m in members) != 1
                or sum(m["role"] == "worker" for m in members) != 1
                or any(m["role"] not in ("primary","worker","systemConsoleHost") for m in members)
                or any((m["parent"] not in (primary,worker) or m["image"].lower() != "conhost.exe")
                       for m in members if m["role"] == "systemConsoleHost")):
            raise ValueError("The original job membership differs from its observed executables")
        identities = {m["role"]:m for m in members if m["role"] in ("primary","worker")}
        p, w = identities["primary"], identities["worker"]
        if (p["pid"], p["creation100ns"], w["pid"], w["creation100ns"], w["parent"]) != (
                primary, creation, worker, worker_creation, primary) or (
                p["image"], w["image"]) != ("native-gui-assessment.exe", "ifw-performance-worker.exe"):
            raise ValueError("The original Rust supervisor or worker changed")
    hwnd = root["first"]["hwnd"]
    tid = root["first"]["tid"]
    for phase in ("first", "hidden", "reopened", "afterInventory"):
        phase_root = root[phase]
        if (phase_root["hwnd"], phase_root["pid"], phase_root["tid"], phase_root["title"], phase_root["desktop"]) != (
                hwnd, primary, tid, "Desktop input probe", "Default") or min(hwnd,tid) <= 0:
            raise ValueError("The observer lost the retained original HWND")
    if ([r[:2] for r in root["lifetimeBeforeQuit"]] != [[hwnd, "create"]]
            or root["first"]["showEvent"]["event"] != "show" or root["hidden"]["hideEvent"]["event"] != "hide"
            or [(e["event"], e["hwnd"], e["root"]) for e in root["reopened"]["events"]] != [("hide",hwnd,True),("show",hwnd,True)]
            or root["afterInventory"]["events"] != root["reopened"]["events"]):
        raise ValueError("The original root did not hide and then reopen exactly once")
    show = root["msiShow"]
    event = root["reopened"]["events"][-1]
    stamp = show["earliestMs"] + ((event["winEventTimeMs"] - show["earliestMs"] + 2**31) % 2**32 - 2**31)
    if (show["showEvent"] != event or not show["distinctTicks"] or stamp != show["showMs"]
            or not 0 <= show["earliestMs"] <= show["releasedByMs"] < stamp <= show["observedMs"] <= show["earliestMs"] + 35000):
        raise ValueError("The external HWND SHOW cannot be ordered after the MSI secondary resumed")
    markers = [s for s in log.splitlines() if s.startswith(("LAUNCHER_PRIMARY ", "LAUNCHER_OPEN ", "LAUNCHER_SECONDARY ", "WINDOW_HIDDEN"))]
    if markers != [f"LAUNCHER_PRIMARY pid={primary}", "WINDOW_HIDDEN", f"LAUNCHER_OPEN client={client}"]:
        raise ValueError("The Rust listener did not acknowledge exactly the installed WPF PID")
    if re.findall(r"^INVENTORY_WORKER pid=(\d+)$", log, re.M) != [str(worker)] or not re.search(r"^DRAINED passes=[1-9]\d*$", log, re.M):
        raise ValueError("The held worker did not belong to the drained primary")
    sweeps = [(int(p),int(n),int(c)) for n,c,p in re.findall(r"^INVENTORY_COMPLETE files=(\d+) changed=(\d+) pass=(\d+)$", log, re.M)]
    first = next((i for i,(_,n,_) in enumerate(sweeps) if n), 0)
    if (first < 2 or len(sweeps) < first + 2 or [p for p,_,_ in sweeps] != list(range(len(sweeps)))
            or any(n or c for _,n,c in sweeps[:first]) or sweeps[first][1:] != (1,1)
            or any((n,c) != (1,0) for _,n,c in sweeps[first+1:])):
        raise ValueError("The newly introduced file was not reconciled twice after reopening")
    challenge = row["challenge"]
    if (not 0 < sec["releasedAfterQpc"] <= row["reopenedByQpc"] <= challenge["introducedAfterQpc"] < challenge["observedByQpc"]
            or challenge["etlBytes"] <= 0 or not all(re.fullmatch(r"[0-9a-f]{64}", challenge[k]) for k in ("etlSha256","sha256"))):
        raise ValueError("Incomplete post-activation challenge")
    earliest, latest = challenge["introducedAfterQpc"], challenge["observedByQpc"]
    result = dict(primary=primary, secondary=client, hwnd=hwnd, worker=worker, workerCreation100ns=worker_creation)
    if challenge.get("traceExit") != 0:
        raise ValueError("The original worker file observer did not exit successfully")
    if independent:
        etw, result["fileTracePhases"] = independent_session(etw, worker, earliest, latest)
    result["kernelFileQueries"] = sparse_inventory(etw, worker, earliest, latest)
    return result


def verify(out, result):
    verify_source_inputs(result["inputs"], result["revision"], result.get("direction") == "wpf-primary")
    release = read(INSTALLED / "release.json")
    target, machine = TARGETS[result["target"]]
    b = verify_build(out, result)
    state, end = read(out / "installed.json"), read(out / "msi-result.json")
    digest = payload_details(read(out / "payload-installed.json"), target)
    if (state["exeSha256"] != digest or state["payloadSha256"] != read(out / "payload-installed.json")["sha256"]
            or state["peMachine"]["ImmichFolderWatch.exe"] != machine or state["state"]["appProcesses"] != 0
            or not state["state"]["installDirectory"] or state["configSha256"] != result["wpfProfile"]["configSha256"]
            or state["state"] != end["checkpoints"]["installed"] or not result["wpfProfile"]["removed"] or not result["scratchRemoved"]
            or state["format"] != "ifw-installed-msi-interop-v1" or end["format"] != "ifw-msi-interop-operations-v1"
            or state["identity"] != end["identity"] or state["identity"]["packageCode"] != state["state"]["packageCode"]
            or state["identity"]["packageCode"] != end["cleanup"]["packageCode"]
            or end["status"] != "passed" or not end["cleanup"]["msiRemoved"]
            or any(x["target"] != result["target"] or str(x["workflowRun"]) != result["run"] or x["sourceCommit"] != result["revision"]
                   or x["releaseCommit"] != release["commit"] or x["package"] != release["assets"][target] for x in (state,end))
            or any(end["checkpoints"][k]["installDirectory"] or end["checkpoints"][k]["appProcesses"] or
                   end["checkpoints"][k]["registered"] or end["checkpoints"][k]["relatedProducts"] for k in ("before","after"))
            or len(end["operations"]) != 2 or any(op["timedOut"] or op["exitCode"] for op in end["operations"])):
        raise ValueError("Wrong shipping MSI, profile, install state or cleanup")
    verify_transactions(out, result["msiTransactions"], end["operations"], state["identity"], target)
    if result.get("direction") == "wpf-primary":
        from reverse.evidence import verify_activation
        return verify_activation(out, result, b, state)
    row = read(out / "activation.json")
    if (sha(out / "challenge.jpg") != row["challenge"]["sha256"] or (out / "challenge.jpg").stat().st_size != 16
            or row["secondary"]["executable"] != state["exe"] or row["stagedProfile"]["gui"] != b["application"]["sha256"]
            or row["stagedProfile"]["worker"] != b["assets"]["ifw-performance-worker.exe"]):
        raise ValueError("Observed image bindings differ from the installed or compiled programs")
    return activation(row, (out / "primary.log").read_text(encoding="utf-8"),
                      (out / "files.log").read_text(encoding="ascii"), digest,
                      independent=result["target"] == "x86_64-pc-windows-msvc")
