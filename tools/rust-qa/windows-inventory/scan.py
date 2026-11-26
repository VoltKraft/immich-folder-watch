"""Measure real HWND transitions within independently observed file opens on the private Windows fixture."""
from contextlib import ExitStack
from bisect import bisect_left
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

from native import hosted, synthetic_config, wpf_profile


DIRECTORIES = 100
PER_DIRECTORY = 1000
MIN_RESPONSES = 5
INTERVAL = .025


def create_fixture(top, resources, api):
    from native import pin_new_marker
    if not hosted() or top.parent.resolve() != Path(os.environ["RUNNER_TEMP"]).resolve() or not top.name.startswith("ifw-rw02-"):
        raise ValueError("Create the inventory only under the owned native runner temporary directory")
    token = uuid.uuid4().hex
    pin_new_marker(resources, api, top / "inventory.owner", token)
    media = top / "files"
    media.mkdir()
    name_set = hashlib.sha256()
    for d in range(DIRECTORIES):
        folder = media / f"d{d:04d}"
        folder.mkdir()
        for f in range(PER_DIRECTORY):
            name = f"f{f:04d}.jpg"
            (folder / name).touch(exist_ok=False)
            name_set.update(f"{folder.name}/{name}\n".encode("ascii"))
    return token, dict(directories=DIRECTORIES, files=DIRECTORIES * PER_DIRECTORY,
                       fileBytes=0, orderedPathsSha256=name_set.hexdigest())


def verify_marker(area, owner_token):
    if not isinstance(owner_token, str) or not re.fullmatch("[0-9a-f]{32}", owner_token):
        raise ValueError("Invalid original inventory owner token")
    marker = area.parent / "inventory.owner"
    info = marker.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size != 32
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("The synthetic inventory marker changed")
    with marker.open("rb") as stream:
        if stream.read(33) != owner_token.encode("ascii"):
            raise ValueError("The inventory marker differs from the originally issued token")


def environment(area, endpoint, rust, media, owner_token):
    verify_marker(area, owner_token)
    env = {**os.environ, "TEMP": str(area), "TMP": str(area), "IFW_QA_ISOLATED": "1", "WGPU_DX12_COMPILER": "Fxc",
           "HTTP_PROXY": endpoint, "HTTPS_PROXY": endpoint, "ALL_PROXY": endpoint, "NO_PROXY": "localhost,127.0.0.1,::1",
           "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    for key in ("IFW_QA_GRAPHICS", "IFW_QA_BENCHMARK", "IFW_QA_INVENTORY_ROOT", "IFW_QA_INVENTORY_TOKEN",
                "IFW_QA_INVENTORY_TRIAL", "IFW_QA_INVENTORY_PORT", "IFW_QA_DWM_TRANSITIONS"):
        env.pop(key, None)
    if rust:
        for key in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
            folder = area / key
            folder.mkdir()
            env[key] = str(folder)
        env.update(IFW_QA_BENCHMARK="1", IFW_QA_INVENTORY_ROOT=str(area.parent),
                   IFW_QA_INVENTORY_TOKEN=owner_token,
                   IFW_QA_INVENTORY_TRIAL=area.name, IFW_QA_INVENTORY_PORT=endpoint.rsplit(":", 1)[1])
        (area / "config.yaml").write_text(synthetic_config(media, endpoint), encoding="utf-8")
    return env


def owned_worker(api, proc, logfile, await_value):
    def ready():
        if proc.poll() is not None:
            raise RuntimeError("The native supervisor exited before the inventory bootstrap")
        matches = re.findall(r"^INVENTORY_WORKER pid=(\d+)$", logfile.read_text(encoding="utf-8", errors="replace"), re.M)
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Expected one comparison worker")
        pid = int(matches[0])
        parent, image = api.processes().get(pid, (0, ""))
        if parent != proc.pid or image.casefold() != "ifw-performance-worker.exe":
            raise ValueError("The reported worker is not the GUI's live native child")
        return pid
    return await_value(ready, "No owned inventory worker", timeout=30, delay=.015)


class SubjectTree:
    def __init__(self, api, stack, job, required_handles):
        self.api, self.stack, self.job = api, stack, job
        self.expected = set(required_handles)
        self.handles = dict(required_handles)
        self.records = {}
        self.samples = []
        for pid, handle in required_handles.items():
            api.verify_job_member(job, pid, handle)

    def member_memory(self, pid):
        if pid not in self.handles:
            handle = self.api.open_job_member(self.job, pid)
            self.stack.callback(self.api.close, handle)
            self.handles[pid] = handle
        handle = self.handles[pid]
        if pid not in self.records:
            # Toolhelp supplies labels only, after the original member is pinned.
            entries = self.api.processes()
            if pid not in entries:
                raise ValueError("The process was absent from the image and parent snapshot")
            parent, image = entries[pid]
            self.records[pid] = dict(parent=parent, image=image, creation100ns=self.api.process_identity(handle))
        return self.api.working_set_bytes(handle)

    def usage(self):
        api, job = self.api, self.job
        for attempt in range(1, 9):
            initial = api.job_accounting(job)
            members = api.job_pids(job)
            if missing := self.expected - members:
                raise ValueError(f"Required trial job members disappeared: {sorted(missing)}")
            working = {}
            try:
                for pid in sorted(members):
                    working[pid] = self.member_memory(pid)
            except (OSError, ValueError) as exc:
                if pid in self.expected or pid in api.job_pids(job):
                    raise ValueError(f"Cannot measure trial job member {pid}, required={pid in self.expected}, "
                                     f"sample={len(self.samples) + 1}: {exc}") from exc
                # This optional member left during observation. Discard the entire partial working set.
                continue
            after = api.job_pids(job)
            final = api.job_accounting(job)
            if (members != after or initial.total != final.total
                    or not initial.active == final.active == len(members)):
                continue
            # The job totals include CPU from children which ran and exited between samples.
            ticks = final.times[0] + final.times[1]
            self.samples.append(dict(cpu100ns=ticks, totalProcesses=final.total, workingSetBytes=working,
                                     membershipAttempts=attempt))
            return ticks / 10_000_000, sum(working.values()) / 1_048_576
        raise ValueError(f"No stable membership for working-set sample {len(self.samples) + 1} of the trial job")


def completion_count(text, subject, media):
    # Only newline-terminated complete records can release an observation phase.
    lines = text.splitlines(keepends=True)
    lines = [row.rstrip("\r\n") for row in lines if row.endswith("\n")]
    if subject == "rust":
        found = [row for row in lines if row.startswith("INVENTORY_COMPLETE ")]
        expected = ["INVENTORY_COMPLETE files=100000 changed=100000 pass=0",
                    "INVENTORY_COMPLETE files=100000 changed=0 pass=1"]
        if found[:2] != expected[:min(2, len(found))]:
            raise ValueError("Unexpected native inventory count or pass order")
        return min(2, len(found))
    if any("Initial scan failed for source" in row for row in lines):
        raise ValueError("The WPF watcher reported an unsuccessful reconciliation")
    suffix = f"Persistent reconciliation for uploadNew queued 0 changed file(s) from {media}."
    return sum(row.endswith(": " + suffix) for row in lines)


def coverage(text, requests, first_complete, second_complete, frequency, target, subject):
    lines = text.splitlines()
    if not lines or lines[0] != f"READY {target} {subject}" or lines[-1] != "COMPLETE":
        raise ValueError("The private PID-bound file ETW recording or decoding failed")
    if not (frequency > 0 and 0 < first_complete <= second_complete):
        raise ValueError("Invalid scan completion clocks")
    directories, batches, counts = [{}, {}], [[], []], []
    for line in lines[1:-1]:
        row = line.split()
        if row[:1] == ["COUNTS"] and len(row) == 9:
            counts.append(tuple(map(int, row[1:])))
            continue
        if len(row) != 5 or row[0] not in ("D", "B") or row[1] not in ("0", "1"):
            raise ValueError("Unexpected native file-observer record")
        sweep = int(row[1])
        a, b, c = map(int, row[2:])
        if row[0] == "B":
            batches[sweep].append((a, b, c))
        elif a not in directories[sweep]:
            directories[sweep][a] = (b, c)
        else:
            raise ValueError("Duplicate file-observer directory")
    total = DIRECTORIES * PER_DIRECTORY
    if (len(counts) != 1 or min(counts[0][:2]) < 2 * total or any(counts[0][2:])):
        raise ValueError("Incomplete or ambiguous native operation completions")
    results = []
    for idx, upper in enumerate((first_complete, second_complete)):
        rows, groups = directories[idx], batches[idx]
        if (set(rows) != set(range(DIRECTORIES)) or any(stamp <= 0 or files != PER_DIRECTORY for stamp, files in rows.values())
                or sum(size for _, _, size in groups) != total or not groups
                or any(not (0 < start <= end <= upper and 0 < size <= 32) for start, end, size in groups)
                or any(right[0] < left[1] for left, right in zip(groups, groups[1:]))):
            raise ValueError(f"The OS observer could not prove the 100,000 distinct successful fingerprint leases in pass {idx}")
        first_enum = min(stamp for stamp, _ in rows.values())
        if first_enum > groups[0][0] or max(stamp for stamp, _ in rows.values()) > groups[-1][1]:
            raise ValueError("Directory enumeration falls outside its own scan")
        if idx and first_enum <= results[0]["lastFileQpc"]:
            raise ValueError("The second real directory enumeration overlaps the first inventory")
        results.append(dict(passIndex=idx, directoriesEnumerated=len(rows), distinctFiles=total,
                            firstDirectoryCompletedQpc=first_enum, firstFileQpc=groups[0][0], lastFileQpc=groups[-1][1],
                            observedCompleteQpc=upper, recordedBatches=len(groups)))
    groups = batches[0]
    ends = [end for _, end, _ in groups]
    def near_work(stamp):
        if not results[0]["firstFileQpc"] <= stamp <= ends[-1]:
            return False
        i = bisect_left(ends, stamp)
        start, end, _ = groups[i]
        before = start if start <= stamp else ends[i-1]
        return stamp - before <= frequency / 2 and end - stamp <= frequency / 2

    accepted = []
    last_response = 0
    for action in requests:
        when, response = action["issuedQpc"], action["responseQpc"]
        if (action["action"] not in ("close", "reopen") or action["hwnd"] <= 0
                or when <= last_response or response < when):
            raise ValueError("Invalid request or response in the native HWND timeline")
        last_response = response
        if near_work(when) and near_work(response):
            accepted.append(action)
    for name in ("close", "reopen"):
        if sum(o["action"] == name for o in accepted) < MIN_RESPONSES:
            raise ValueError(f"Fewer than five native {name} responses during actual inventory work")
    return dict(passes=results, distinctFilesPerPass=total, nativeCreateStarts=counts[0][0],
                nativeOperationEnds=counts[0][1], eligibleResponses=accepted)


def measure(api, fixture, subject, exe, observer, area, endpoint, user_sid, output, await_value, stop_subject, p95, owner_token,
            *, presentation_trace=None, visibility_witness=None, dwm_transitions=None, after_inventory=None):
    from native import CleanupUnconfirmed, finish_owned_trace, start_owned_subject
    rust = subject == "rust"
    area.mkdir()
    media = area.parent / "files"
    env = environment(area, endpoint, rust, media, owner_token)
    if dwm_transitions is not None:
        if not rust or dwm_transitions not in ("ordinary", "disabled") or after_inventory is None:
            raise ValueError("The DWM comparison requires a Rust scan and post-scan editor observer")
        env["IFW_QA_DWM_TRANSITIONS"] = dwm_transitions
    target_log = output / (area.name + ".log")
    observer_log = output / (area.name + "-files.log")
    input_log = output / (area.name + "-requests.json")
    with ExitStack() as stack:
        if not rust:
            api.ensure_no_primary(user_sid)
        profile = None if rust else stack.enter_context(wpf_profile(media, endpoint))
        log = stack.enter_context(target_log.open("wb"))
        proc = start_owned_subject(stack, api, exe, area, env, log, rust, stop_subject)
        if rust:
            api.resume_owned_process(proc.pid)
        if rust:
            target = owned_worker(api, proc, target_log, await_value)
            target_handle = api.open_job_member(proc.benchmark_job, target)
            stack.callback(api.close, target_handle)
        else:
            target, target_handle = proc.pid, int(proc._handle)
            api.verify_job_member(proc.benchmark_job, target, target_handle)
        identity = api.process_identity(target_handle)
        presentation = presentation_trace(stack, proc, area, output) if presentation_trace else None
        stream = stack.enter_context(observer_log.open("wb", buffering=0))
        etl = area / "files.etl"
        session = "IFW-Files-" + uuid.uuid4().hex
        helper = subprocess.Popen([observer, str(target), session, etl, media, subject],
                                  cwd=area, stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        stopped = False

        def finish_trace():
            nonlocal stopped
            try:
                finish_owned_trace(helper, observer, area, etl, session, 240)
            except CleanupUnconfirmed:
                raise
            except subprocess.TimeoutExpired:
                # The shared finalizer confirmed logger removal after killing the stuck decoder.
                stopped = True
                raise
            stopped = True

        def remove_trace():
            if stopped:
                try:
                    etl.unlink(missing_ok=True)
                except OSError as exc:
                    raise CleanupUnconfirmed("Could not remove the private raw file trace") from exc

        stack.callback(remove_trace)
        cleanup = stack.enter_context(ExitStack())
        cleanup.callback(finish_trace)
        ready = f"READY {target} {subject}".encode()
        await_value(lambda: helper.poll() is not None or ready in observer_log.read_bytes().splitlines(),
                    "The native file-I/O observer did not start", timeout=25, delay=.01)
        if helper.poll() is not None:
            raise RuntimeError("Could not start PID-filtered file ETW")
        fixture.TITLE = "Desktop input probe" if rust else "Immich Folder Watch"
        windows = fixture.Windows(proc.pid)
        stack.callback(windows.close)
        if rust:
            proc.stdin.write(b"T")
            proc.stdin.flush()
        else:
            api.resume_owned_process(proc.pid)

        def check():
            if (code := proc.poll()) is not None:
                raise RuntimeError(f"{target_log.name}: measured GUI exited during its scan with 0x{code & 0xffffffff:08X}")

        def completed(passes):
            check()
            if rust:
                lines = target_log.read_text(encoding="utf-8", errors="replace")
            else:
                logs = sorted((profile / "engine-logs").glob("*.log"))
                lines = "".join(path.read_text(encoding="utf-8", errors="replace") for path in logs)
            return completion_count(lines, subject, media) >= passes

        def visible(want):
            def observed():
                check()
                hwnd = windows.visible()
                return hwnd if want else not hwnd
            return await_value(observed, "No independently observed HWND transition during the scan")

        window = visible(True)
        requests = []
        closed = False
        deadline = time.monotonic() + 480
        while not completed(1):
            if time.monotonic() > deadline or len(requests) >= 16000:
                raise TimeoutError("The first real inventory exceeded the observation budget")
            action = "reopen" if closed else "close"
            if visibility_witness is not None:
                visibility_witness("before", action, int(window), proc.pid)
            issued = api.clock()
            if closed:
                if rust:
                    proc.stdin.write(b"O")
                    proc.stdin.flush()
                else:
                    api.activate_wpf(user_sid, proc.pid)
                window = visible(True)
            else:
                windows.close_window(window)
                visible(False)
            requests.append(dict(action=action, issuedQpc=issued, responseQpc=api.clock(), hwnd=int(window)))
            if visibility_witness is not None:
                visibility_witness("after", action, int(window), proc.pid)
            closed = not closed
            time.sleep(INTERVAL)
        first_complete = api.clock()
        await_value(lambda: completed(2), "The second complete reconciliation is missing", timeout=480, delay=.025)
        second_complete = api.clock()
        input_log.write_text(json.dumps(dict(guiPid=proc.pid, inventoryPid=target, firstCompleteQpc=first_complete,
                                             secondCompleteQpc=second_complete, frequency=api.frequency,
                                             requests=requests), indent=2) + "\n", encoding="utf-8")
        cleanup.close()
        if helper.returncode:
            raise RuntimeError("The private file-I/O trace lost events or could not decode them")
        observed = coverage(observer_log.read_text(encoding="ascii"), requests, first_complete, second_complete,
                            api.frequency, target, subject)
        with etl.open("rb") as stream:
            observed["decodedEtlSha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        observed["decodedEtlBytes"] = etl.stat().st_size
        if api.process_identity(target_handle) != identity or (rust and api.processes().get(target, (0, ""))[0] != proc.pid):
            raise ValueError("The inventory process changed during close/reopen")
        windows.pump()
        known = {r["hwnd"] for r in requests}
        events = {event: sum(item["event"] == event and item["hwnd"] in known for item in windows.events)
                  for event in ("show", "hide")}
        if min(events.values()) < MIN_RESPONSES:
            raise ValueError("Independent Windows show/hide events failed the active input control")
        if presentation:
            observed["presentation"] = presentation(observed)
        metrics = {}
        for action in ("close", "reopen"):
            values = [(q["responseQpc"] - q["issuedQpc"]) * 1000 / api.frequency
                      for q in observed["eligibleResponses"] if q["action"] == action]
            metrics["scan_" + action + "_p95_ms"] = p95(values)
        if after_inventory is not None:
            observed["editor"] = after_inventory(windows, proc, area, env, target_log, int(window))
        observed["termination"] = stop_subject(proc, rust, drain_log=target_log)
        observed.update(guiPid=proc.pid, inventoryPid=target, inventoryCreation100ns=identity, unchangedWorker=True,
                        completedPasses=2, rootWindowEvents=events, allRequests=requests, metrics=metrics)
        return observed
