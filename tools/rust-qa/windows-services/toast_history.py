"""Observe two inbox WinRT toasts using only this disposable job's unique app identity."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from activation import ART, HERE, QA, ROOT, TARGET, hosted, module, paths, sha, write
from service_sources import service_files, verify_checkout

LINK = "IFW synthetic notification.lnk"
PROGRAMS = "a77f5d77-2e2b-44c3-a6a2-aba601054a51"
OPERATIONS = {"prepare", "register", "inspect", "post-quiet", "post-normal", "remove-quiet", "remove-normal"}
HISTORY_PHASES = ["identity", "shortcut", "history"]
READINESS_SOURCE = "tools/rust-qa/windows-services/src/toast_readiness.rs"
NOT_FOUND = 0x80070490 - (1 << 32)
MAX_NOTIFIER_ATTEMPTS = 17
REQUIRED_IMPORTS = {"RoInitialize", "RoUninitialize", "InitPropVariantFromCLSID", "SetCurrentProcessExplicitAppUserModelID",
                    "PropVariantChangeType", "GetTokenInformation"}
# Failure of one of these Windows services/capabilities is recorded as unavailable.
# Unknown HRESULTs and every ownership or cleanup error fail the fixture.
UNAVAILABLE = {0x80070005, 0x80040154, 0x80070490, 0x80070422, 0x80070424, 0x800706ba,
               0x803e0105, 0x803e0111, 0x803e0112, 0x803e0114, 0x803e0117}


def request_identity(target):
    if not hosted(target) or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch":
        raise ValueError("Use the corresponding disposable Windows runner on the rewrite branch")


def notifier_attempts(fields, phases, hresult):
    """Check the complete bounded Create/Setting sequence before content or Show."""
    raw = [key for key in fields if key.startswith("ready.")]
    observed = []
    expected_phases = ["identity", "shortcut"]
    expected_keys = []
    for number in range(1, MAX_NOTIFIER_ATTEMPTS + 1):
        calls = {}
        for stage in ("create", "setting"):
            key = f"ready.{number}.{stage}"
            value = fields.get(key, "")
            if not re.fullmatch(r"0|-[1-9][0-9]{0,9}", value) or int(value) < -(1 << 31):
                raise ValueError("Missing or invalid notifier readiness HRESULT")
            code = calls[stage] = int(value)
            expected_keys.append(key)
            expected_phases.append("notifier-" + stage)
            if code:
                break
        observed.append(calls)
        if code != NOT_FOUND or f"ready.{number + 1}.create" not in fields:
            break
    if code:
        if hresult != code or "setting" in fields or "showReturned" in fields:
            raise ValueError("Notifier readiness refusal differs from the sender result")
    elif fields.get("setting") == "0":
        expected_phases.append("content")
        if hresult is None or "show" in phases:
            expected_phases.append("show")
    elif fields.get("setting") not in ("1", "2", "3", "4") or hresult is not None:
        raise ValueError("Missing or invalid notification setting after readiness")
    if expected_keys != raw or expected_phases != phases:
        raise ValueError("Notifier readiness calls or phases differ from the native result")
    return observed


def parse_log(data, operation, token, expected_pid, session, exit_code, *, require_readiness=False):
    if not re.fullmatch(r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}", token):
        raise ValueError("Expected the trial's version 4 UUID")
    if len(data) > 8192:
        raise ValueError("Unexpected native toast log size")
    fields, phases, hresult = {}, [], None
    pending_call = None
    for line in data.decode("utf-8").splitlines():
        if hresult is not None:
            raise ValueError("The native HRESULT must terminate the native log")
        if line.startswith("Probe HRESULT "):
            if not re.fullmatch(r"Probe HRESULT -[1-9][0-9]{0,9}", line) or pending_call is not None:
                raise ValueError("Invalid native HRESULT")
            hresult = int(line.split()[-1])
            if hresult < -(1 << 31):
                raise ValueError("Invalid native HRESULT")
            continue
        key, separator, value = line.partition("=")
        if not separator or key in fields:
            raise ValueError("Malformed or duplicate native toast evidence")
        if pending_call is not None:
            if not re.fullmatch(r"ready\.[1-9][0-9]?\." + pending_call, key):
                raise ValueError("Missing immediate notifier readiness result")
            pending_call = None
        elif key.startswith("ready."):
            raise ValueError("Notifier readiness result is outside its native call phase")
        if key == "phase":
            phases.append(value)
            if value in ("notifier-create", "notifier-setting"):
                pending_call = value.removeprefix("notifier-")
        else:
            if operation == "inspect" and exit_code == 0 and key == "count" and phases != HISTORY_PHASES:
                raise ValueError("The native row count appeared outside the exact history-read phase")
            fields[key] = value
    if (fields.get("operation") != operation or fields.get("aumid") != "IFW.RustQA.Toast." + token
            or fields.get("pid") != str(expected_pid) or fields.get("session") != str(session)
            or fields.get("elevated") not in ("true", "false") or not phases or phases[0] != "identity"
            or (exit_code == 0) != (hresult is None)):
        raise ValueError("Missing native process, synthetic app identity or result")
    if operation == "inspect" and exit_code == 0 and (phases != HISTORY_PHASES or "count" not in fields):
        raise ValueError("A successful inspection did not complete the native history-read phase")
    item = dict(fields=fields, phases=phases, hresult=hresult)
    if operation in ("post-quiet", "post-normal") and (exit_code == 0 or len(phases) > 2) and (
            require_readiness or any(phase.startswith("notifier-") for phase in phases)):
        item["notifierReadiness"] = notifier_attempts(fields, phases, hresult)
    return item


def observed_rows(fields, token):
    """Read exact synthetic content, rejecting partial, duplicate or unexpected records."""
    modes = {key.split(".")[0] for key in fields if "." in key}
    if not modes <= {"quiet", "normal"} or fields.get("count") != str(len(modes)):
        raise ValueError("Native history has unexpected or incomplete rows")
    for mode in modes:
        expected = dict(group="g" + token[16:31], tag=mode[0] + token[:15],
                        title=f"IFW synthetic {mode} {token}", body=f"Rust {mode} notification history {token}")
        row = {key.removeprefix(mode + "."): value for key, value in fields.items() if key.startswith(mode + ".")}
        if row != expected:
            raise ValueError("History content differs from the original synthetic request")
    return modes


def validate_post(item, mode):
    fields = item["fields"]
    if fields.get("setting") not in ("0", "1", "2", "3", "4"):
        raise ValueError("Unknown native notification setting")
    if fields["setting"] != "0":
        if "show" in item["phases"] or "showReturned" in fields:
            raise ValueError("A disabled setting allowed a send attempt")
        return False
    if (fields.get("suppressPopup") != ("true" if mode == "quiet" else "false")
            or fields.get("mirroringDisabled") != "true" or fields.get("showReturned") != "true"
            or int(fields.get("expirationTicks", "0")) <= 0 or item["phases"][-1] != "show"):
        raise ValueError("The native sender did not confirm this request's properties and Show result")
    return True


class Unavailable(Exception):
    """The native Windows service could not provide this capability."""

    def __init__(self, message, *, show_attempted=False):
        super().__init__(message)
        self.show_attempted = show_attempted


def exchange(call, token, record, *, delay=time.sleep, clock=time.monotonic):
    def action(operation):
        item = call(operation)
        if item["hresult"] is not None:
            code = item["hresult"] & 0xffffffff
            phase = item["phases"][-1]
            if code in UNAVAILABLE and phase in ("history", "notifier", "notifier-create", "notifier-setting", "show"):
                raise Unavailable(f"{operation} returned HRESULT 0x{code:08x} during {phase}",
                                  show_attempted="show" in item["phases"])
            raise RuntimeError(f"{operation} failed during {item['phases'][-1]} with HRESULT 0x{code:08x}")
        return item

    def poll(expected, *, after_removal=False):
        deadline = clock() + 14
        while True:
            sample = action("inspect")
            rows = observed_rows(sample["fields"], token)
            if rows == expected or clock() >= deadline:
                if after_removal and rows != expected:
                    raise RuntimeError("Exact notification removal was not confirmed independently")
                return rows
            delay(.65)

    # The Start Menu index can lag behind the successful shortcut notification.
    # Recheck only the exact app's read-only query; each actual Show still runs once.
    deadline = clock() + 8
    while True:
        initial = call("inspect")
        hr = initial["hresult"]
        if hr is None:
            break
        code = hr & 0xffffffff
        if (initial["phases"][-1] == "history" and code in (0x80070490, 0x803e0102)
                and clock() < deadline):
            delay(.65)
            continue
        if initial["phases"][-1] == "history" and code in UNAVAILABLE | {0x803e0102}:
            raise Unavailable(f"The new app's history returned HRESULT 0x{code:08x}")
        raise RuntimeError(f"Initial native history failed with HRESULT 0x{code:08x}")
    if observed_rows(initial["fields"], token):
        raise ValueError("The new app identity already has notification history")
    record.update(initiallyEmpty=True, modes={}, cleanup={})
    # Record the potential tag before starting each sender. A failed or interrupted
    # Show must still get its own exact removal and an independent empty readback.
    attempted = []
    posted = set()
    problem = None
    try:
        for mode in ("quiet", "normal"):
            attempted.append(mode)
            try:
                sent = validate_post(action("post-" + mode), mode)
            except Unavailable as error:
                if not error.show_attempted:
                    attempted.pop()
                record["modes"][mode] = {"platformError": str(error)}
                continue
            if sent:
                posted.add(mode)
                found = poll(posted)
            else:
                attempted.pop()
                found = set()
            record["modes"][mode] = {"sent": sent, "observed": sorted(found)}
    except Exception as exc:
        problem = exc
    finally:
        cleanup_errors = []
        # Observe the other tag surviving a selective removal whenever both arrived.
        for mode in reversed(attempted):
            try:
                removal = action("remove-" + mode)
                if removal["fields"].get("removeReturned") != "true" or removal["phases"][-1] != "remove":
                    raise ValueError("Missing exact native removal result")
                before = record["modes"].get("normal", {}).get("observed", [])
                expected = {"quiet"} if mode == "normal" and "quiet" in before else set()
                if mode == "normal" and "quiet" not in before:
                    # The quiet toast might have arrived after its sampling deadline.
                    # Its own removal and the final empty readback still run.
                    remaining = observed_rows(action("inspect")["fields"], token)
                    if "normal" in remaining:
                        remaining = poll(remaining - {"normal"}, after_removal=True)
                else:
                    remaining = poll(expected, after_removal=True)
                record["cleanup"][mode] = sorted(remaining)
            except Exception as exc:
                cleanup_errors.append(f"{mode}: {exc}")
        try:
            poll(set(), after_removal=True)
            record["finallyEmpty"] = True
        except Exception as exc:
            cleanup_errors.append(f"final history: {exc}")
        if cleanup_errors:
            raise RuntimeError("Could not establish exact toast cleanup: " + " / ".join(cleanup_errors)) from problem
    if problem:
        raise problem
    if (record["modes"]["quiet"].get("observed") == ["quiet"]
            and record["modes"]["normal"].get("observed") == ["normal", "quiet"]
            and record["cleanup"] == {"normal": ["quiet"], "quiet": []} and record.get("finallyEmpty")):
        return "passed"
    raise Unavailable("One or both exact notification history entries were unavailable")


def validate_imports(imports):
    if not isinstance(imports, dict) or not imports or not all(
            isinstance(lib, str) and lib.lower().endswith(".dll") and isinstance(names, list) and names
            and all(isinstance(symbol, str) and symbol for symbol in names) for lib, names in imports.items()):
        raise ValueError("Invalid recorded native import table")
    if not REQUIRED_IMPORTS <= {symbol for names in imports.values() for symbol in names}:
        raise ValueError("Native executable lacks the reviewed Windows notification or identity calls")


def evidence_files(directory):
    return {p.name: sha(p) for p in sorted(directory.iterdir()) if p.name != "result.json" and p.is_file()}


def replay(directory, result):
    """Re-evaluate the native imports, desktop, original processes and history observations."""
    token = result["token"]
    journal = result["processes"]
    target = result["target"]
    machine = next(machine for name, machine in TARGET.values() if name == target)
    if not 10 <= len(journal) <= 150 or any(proc["operation"] not in OPERATIONS for proc in journal):
        raise ValueError("Invalid operation journal")
    required = {"native-build.json", "pe-imports.json", "shortcut.bin", "desktop.json"}
    required.update(f"{i:03}-{proc['operation']}.txt" for i, proc in enumerate(journal))
    files = [p for p in directory.iterdir() if p.name != "result.json"]
    if ({p.name for p in files} != required or set(result["evidenceFiles"]) != required
            or any(p.is_symlink() or not p.is_file() for p in files)
            or evidence_files(directory) != result["evidenceFiles"]):
        raise ValueError("Missing, changed or unexpected raw native evidence")
    native_report = directory / "native-build.json"
    build = json.loads(native_report.read_bytes())
    required_checks = ["compiler", "inventory", "clippy", "build", "toast-controls"]
    if READINESS_SOURCE in build["sourceFiles"]:
        required_checks.append("notifier-readiness")
    if (sha(native_report) != result["earlyResultSha256"] or build["hosted"] is not True
            or not re.fullmatch("[0-9a-f]{64}", result["binarySha256"])
            or (build["head"], build["target"], build["workflowRun"], build["workflowAttempt"], build["probeSha256"])
            != (result["head"], target, result["run"], result["attempt"], result["binarySha256"])
            or not result["observerInputs"] or build["sourceFiles"] != result["observerInputs"]
            or build["checkoutVerified"] is not True or build["canonicalGraphSha256"] != result["graphSha256"]
            or any(type(build["steps"].get(k)) is not int or build["steps"][k] != 0
                   for k in required_checks)
            or sha(directory / "pe-imports.json") != build["evidenceFiles"]["pe-imports.json"]):
        raise ValueError("The captured import table or executable identity differs from the original native build")
    validate_imports(json.loads((directory / "pe-imports.json").read_bytes()))
    context = json.loads((directory / "desktop.json").read_bytes())
    console = module("toast_console", QA / "windows-desktop/win32.py").ordinary_console
    if context != result["desktop"] or not console(context, "Default") or type(context["session"]) is not int:
        raise ValueError("The recorded desktop is not the ordinary unlocked Default input desktop")
    if (result.get("profileRemoved") is not True or result.get("ownedFolderRemoved") is not True
            or result.get("ownedFolderCreated") is not True or result["shortcut"]["knownFolder"] != PROGRAMS
            or result["shortcut"]["relative"] != f"ifw-shell-{token}/{LINK}"
            or sha(directory / "shortcut.bin") != result["shortcut"]["sha256"]):
        raise ValueError("Missing owned shortcut, profile cleanup or process evidence")
    index = 0
    identities = set()

    def archived(operation):
        nonlocal index
        if index >= len(journal):
            raise ValueError("Native observations ended before the exchange completed")
        proc = journal[index]
        filename = f"{index:03}-{operation}.txt"
        index += 1
        if (proc["log"] != filename or proc["operation"] != operation or proc["jobEmpty"] is not True
                or proc.get("forced") or type(proc["exit"]) is not int or tuple(proc["machine"]) != (machine, machine)
                or any(type(proc[k]) is not int or proc[k] <= 0 for k in ("pid", "creation100ns"))
                or sha(directory / filename) != proc["logSha256"]):
            raise ValueError("The archived process differs from the requested native observation")
        identity = (proc["pid"], proc["creation100ns"])
        if identity in identities:
            raise ValueError("A sender or observer process identity was reused")
        identities.add(identity)
        row = parse_log((directory / filename).read_bytes(), operation, token, proc["pid"],
                        result["desktop"]["session"], proc["exit"], require_readiness=READINESS_SOURCE in build["sourceFiles"])
        if row.get("notifierReadiness") != proc.get("notifierReadiness"):
            raise ValueError("The reported notifier readiness differs from the original native calls")
        if operation != "prepare" and row["fields"].get("installedLinkVerified") != "true":
            raise ValueError("Missing identity readback from the installed Start Menu shortcut")
        return row

    for operation, flag in (("prepare", "prepared"), ("register", "shellNotified")):
        row = archived(operation)
        if row["hresult"] is not None or row["fields"].get(flag) != "true":
            raise ValueError("Missing native shortcut preparation or registration")
    original = {}
    status = exchange(archived, token, original, delay=lambda _: None, clock=lambda: 0)
    if (status != "passed" or index != len(journal)
            or any(original[k] != result.get(k) for k in ("initiallyEmpty", "finallyEmpty", "modes", "cleanup"))):
        raise ValueError("The raw native history differs from the reported outcome")
    return original


def measure(target, exe, out, record):
    from notification_probe import (Desktop, Win32, child, fixture_profile, ordinary_console, owned_directory,
                                    pin_new_marker, pin_path)
    from native import known_folder
    from build import pe_machine
    api, desktop = Win32(), Desktop()
    record["desktop"] = desktop.context()
    write(out / "desktop.json", record["desktop"])
    session = record["desktop"]["session"]
    if not ordinary_console(record["desktop"], "Default"):
        raise Unavailable("The job has no unlocked ordinary input desktop")
    if any(pe_machine(path) != TARGET[os.environ["RUNNER_ARCH"]][1] for path in (exe, Path(sys.executable))):
        raise ValueError("Expected a native observer and native sender")
    token = uuid.uuid4().hex
    record.update(token=token, processes=[], presentationObserved=None, activationObserved=None)
    temp = Path(os.environ["RUNNER_TEMP"])
    with ExitStack() as outer:
        outer.enter_context(pin_path(api, exe, False))
        area = outer.enter_context(fixture_profile(api, temp, token, record))
        pin_new_marker(outer, api, area / "synthetic.fixture", token)
        env = dict(os.environ, TEMP=str(area), TMP=str(area), IFW_QA_TOAST_HISTORY="1",
                   IFW_QA_ISOLATED="1", IFW_QA_INVENTORY_TOKEN=token)

        def call(operation):
            log = out / f"{len(record['processes']):03}-{operation}.txt"
            info = dict(operation=operation, log=log.name)
            record["processes"].append(info)
            with child(api, exe, ["--hosted-toast-history", str(area), token, operation], area, env, log, info) as proc:
                proc.wait(timeout=25)
            item = parse_log(log.read_bytes(), operation, token, info["pid"], session, info["exit"], require_readiness=True)
            if "notifierReadiness" in item:
                info["notifierReadiness"] = item["notifierReadiness"]
            info["logSha256"] = sha(log)
            if operation != "prepare" and item["fields"].get("installedLinkVerified") != "true":
                raise ValueError("The native subject could not verify the installed shortcut")
            return item

        prepared = call("prepare")
        if prepared["hresult"] is not None or prepared["fields"].get("prepared") != "true":
            raise ValueError("The native shortcut template could not be created")
        staged = area / LINK
        programs = known_folder(PROGRAMS)
        directory = programs / ("ifw-shell-" + token)
        record["ownedFolderCreated"] = False
        try:
            with owned_directory(api, programs, directory.name) as folder, ExitStack() as installed:
                record["ownedFolderCreated"] = True
                installed.enter_context(pin_path(api, staged, False))
                if not 0 < staged.stat().st_size <= 32768:
                    raise ValueError("Unexpected synthetic shortcut size")
                raw = staged.read_bytes()
                link = folder / LINK
                with link.open("xb") as stream:
                    stream.write(raw)
                _, identity = installed.enter_context(pin_path(api, link, False))
                if link.read_bytes() != raw:
                    raise ValueError("Installed shortcut does not match the original COM output")
                record["shortcut"] = dict(knownFolder=PROGRAMS, relative=f"{directory.name}/{LINK}",
                                          fileIdentity=identity, sha256=hashlib.sha256(raw).hexdigest())
                (out / "shortcut.bin").write_bytes(raw)
                registered = call("register")
                if registered["hresult"] is not None or registered["fields"].get("shellNotified") != "true":
                    raise ValueError("Could not announce the owned shortcut to the Shell")
                return exchange(call, token, record)
        finally:
            record["ownedFolderRemoved"] = record["ownedFolderCreated"] and not os.path.lexists(directory)
            if record["ownedFolderCreated"] and not record["ownedFolderRemoved"]:
                raise RuntimeError("The test-owned Programs folder or shortcut remains")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=[name for name, _ in TARGET.values()])
    parser.add_argument("--replay", type=Path, help="Verify an original positive hosted artifact using only its saved files")
    args = parser.parse_args()
    target = args.target
    if args.replay:
        result = json.loads((args.replay / "result.json").read_bytes())
        if result["target"] != target or result["status"] != "passed":
            raise ValueError("Expected the complete positive artifact from this target")
        print(json.dumps(replay(args.replay, result), sort_keys=True))
        return 0
    request_identity(target)
    out = ART / ("toast-history-" + target)
    out.mkdir(exist_ok=False)
    result = dict(status="failed", target=target, head=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
                  attempt=os.environ["GITHUB_RUN_ATTEMPT"])
    try:
        from notification_probe import bind_build
        result["observerInputs"] = verify_checkout(ROOT, service_files(), result["head"], HERE)
        exe, original = paths(target)
        bind_build(target, exe, original, result)
        build = json.loads((original / "result.json").read_bytes())
        controls = original / "toast-controls.txt"
        if (type(build["steps"].get("toast-controls")) is not int or build["steps"]["toast-controls"] != 0
                or sha(controls) != build["evidenceFiles"].get(controls.name)
                or not controls.read_text(encoding="utf-8").rstrip().endswith("OK")):
            raise ValueError("The native build did not complete the history and cleanup controls")
        result["earlyEvidence"][controls.name] = sha(controls)
        readiness = original / "notifier-readiness.txt"
        if (type(build["steps"].get("notifier-readiness")) is not int or build["steps"]["notifier-readiness"] != 0
                or sha(readiness) != build["evidenceFiles"].get(readiness.name)
                or "test result: ok. 2 passed; 0 failed;" not in readiness.read_text(encoding="utf-8")):
            raise ValueError("The native build did not complete the notifier readiness controls")
        result["earlyEvidence"][readiness.name] = sha(readiness)
        pe = module("toast_pe", QA / "windows-imports/formats.py")
        imports = pe.pe_imports(exe, TARGET[os.environ["RUNNER_ARCH"]][1])
        validate_imports(imports)
        table = original / "pe-imports.json"
        if sha(table) != build["evidenceFiles"].get(table.name) or json.loads(table.read_bytes()) != imports:
            raise ValueError("The native service's import table changed since the original build")
        (out / table.name).write_bytes(table.read_bytes())
        (out / "native-build.json").write_bytes((original / "result.json").read_bytes())
        result["status"] = measure(target, exe, out, result)
        if result["status"] == "passed":
            result["evidenceFiles"] = evidence_files(out)
            replay(out, result)
    except Unavailable as exc:
        result.update(status="unavailable", reason=str(exc))
    except Exception as exc:
        result.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
    finally:
        result["evidenceFiles"] = evidence_files(out)
        write(out / "result.json", result)
    print(result["status"], result.get("error") or result.get("reason") or "")
    return {"passed": 0, "failed": 1, "unavailable": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
