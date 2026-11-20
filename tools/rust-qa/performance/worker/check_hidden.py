"""Observe a fresh inventory change while the private native X11 window stays unmapped."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


def inside():
    sys.path.insert(0, "/driver")
    from observations import DirectoryReads
    from session import Subject, action, private_session, wait_for

    work = Path("/qa")
    outer = json.loads((work / "namespaces.json").read_text())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DISPLAY") != ":93"
            or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or any(os.readlink(f"/proc/self/ns/{k}") == v for k, v in outer.items())):
        raise RuntimeError("The private performance namespace is required")
    os.umask(0o077)
    Path.home().mkdir()
    media = work / "files"
    leaf = media / "d0000"
    leaf.mkdir(parents=True)
    spec = dict(managed=False, desktop_spike=True, entry="native-gui-assessment",
                start_marker="INVENTORY_STARTED", finish_marker="INVENTORY_COMPLETE")
    with ExitStack() as stack:
        display, server = private_session(stack)
        reads = DirectoryReads(stack, media)
        subject = Subject(stack, spec, work / "hidden", media, None)
        window = wait_for(lambda: subject.probe(display.visible), 30, "Missing visible window")
        wait_for(lambda: subject.probe(lambda: len(subject.inventories) >= 2), 10, "Missing initial inventories")
        if subject.inventories[:2] != [(0, 0, 0), (0, 0, 1)]:
            raise RuntimeError("Unexpected initial source state")
        action(subject, display, False)
        before = len(subject.inventories)
        hidden_start = time.monotonic()
        (leaf / "added-while-hidden.jpg").touch(exist_ok=False)

        def rediscovered():
            subject.alive()
            if display.visible():
                raise RuntimeError("The GUI became visible during a background inventory")
            return next((entry for entry in subject.inventories[before:] if entry[:2] == (1, 1)), None)

        change = wait_for(rediscovered, 12, "Hidden worker did not discover the new synthetic file")
        observed = time.monotonic()
        _, _, directories = reads.scan_bounds(hidden_start, observed)
        action(subject, display, True)
        if display.visible() != window:
            raise RuntimeError("Activation did not restore the retained X11 window")
        action(subject, display, False)
    if subject.process.returncode != 0:
        raise RuntimeError("Native supervisor did not drain its child")
    return dict(xserver=server, initial=subject.inventories[:2], while_hidden=change,
                seconds_to_rediscovery=round(observed - hidden_start, 4), directories_observed=directories,
                retained_window=window, quit_while_hidden=True, exit=subject.process.returncode)


def main(stage):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from linux import OUTPUT, namespace, sha256

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", stage):
        raise ValueError("Use a staged subject label")
    subject = OUTPUT / "subjects" / stage
    output = OUTPUT / f"{stage}-worker-hidden.json"
    if output.exists():
        raise FileExistsError(output)
    receipts = json.loads((subject / "worker.inputs.json").read_text())
    binaries = {k: sha256(subject / name) for k, name in (("gui_sha256", "native-gui-assessment"),
                                                         ("worker_sha256", "ifw-performance-worker"))}
    if any(receipts[k] != v for k, v in binaries.items()):
        raise ValueError("The staged binary hashes differ from the build receipt")
    with tempfile.TemporaryDirectory(prefix="ifw-hidden-worker-", dir="/tmp") as directory:
        work = Path(directory)
        (work / "namespaces.json").write_text(json.dumps({
            k: os.readlink(f"/proc/self/ns/{k}") for k in ("net", "mnt", "pid", "ipc", "user")}))
        command = namespace(work, subject, None, True)
        command[-1:] = ["/driver/worker/check_hidden.py", "--inside"]
        subprocess.run(command, check=True, timeout=60)
        result = json.loads((work / "hidden.json").read_text())
    result.update(binaries, observer_sha256=sha256(Path(__file__)))
    with output.open("x") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(output)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        Path("/qa/hidden.json").write_text(json.dumps(inside()))
    elif len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        sys.exit("Usage: python3 check_hidden.py STAGED_SUBJECT")
