"""Run the fixed guard exercise from two already logged-on standard sessions on an isolated test VM."""

import argparse
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
import uuid

from fixture import Accounts, HERE, ROOT, bind, checked, instance, read, validate_area, wait, write, participants_exited
from observe import TARGETS, finish_process, native_handover, original, prepare
from standard import EXISTING, qualifies
import worker

VM_MARKER = b"Immich Folder Watch isolated Windows test VM; synthetic data only\n"


def vm_root(root):
    if not root.is_absolute() or not root.drive or root.drive.startswith("\\\\") or root == Path(root.anchor):
        raise ValueError("A dedicated local test VM scratch directory is required")
    marker = root / ".ifw-existing-session-test"
    for item in [marker, root, *root.parents]:
        if getattr(item.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("The test VM marker and its path must be free of reparse points")
    if not marker.is_file() or marker.stat().st_size != len(VM_MARKER) or marker.read_bytes() != VM_MARKER:
        raise ValueError("The disposable VM root must have the explicit synthetic-data marker")
    return root


def interactive(identity):
    if not qualifies(identity) or not identity["sessionId"]:
        raise RuntimeError("Use the existing, non-elevated standard user in a nonzero session")
    lib = c.WinDLL("wtsapi32", use_last_error=True)
    query = bind(lib, "WTSQuerySessionInformationW", w.BOOL, w.HANDLE, w.DWORD, c.c_int,
                 c.POINTER(c.c_void_p), c.POINTER(w.DWORD))
    free = bind(lib, "WTSFreeMemory", None, c.c_void_p)
    def value(kind, typ):
        pointer, size = c.c_void_p(), w.DWORD()
        checked(query(None, identity["sessionId"], kind, c.byref(pointer), c.byref(size)), "WTSQuerySessionInformationW")
        try:
            if not pointer.value or size.value < c.sizeof(typ):
                raise ValueError("Incomplete WTS session observation")
            return c.cast(pointer, c.POINTER(typ)).contents.value
        finally:
            free(pointer)
    state, protocol = value(8, w.DWORD), value(16, w.USHORT)
    if state not in (0, 1, 4) or protocol not in (0, 2):
        raise RuntimeError("An existing console or Remote Desktop session must own this participant")
    return {"connectionState": state, "clientProtocol": protocol, "sessionId": identity["sessionId"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("controller", "peer"))
    parser.add_argument("target", choices=TARGETS.values())
    parser.add_argument("path", type=Path, help="Marked VM root for controller, its printed unique directory for peer")
    parser.add_argument("--native-archive", type=Path, help="original Actions ZIP containing the tested native writer")
    parser.add_argument("--archive-sha256", help="SHA-256 from the corresponding Actions artifact")
    args = parser.parse_args()
    if bool(args.native_archive) != bool(args.archive_sha256) or (args.native_archive and args.role != "controller"):
        parser.error("The controller takes the native archive and its Actions SHA-256 together")
    native = {"AMD64": "x86_64-pc-windows-msvc", "X86_64": "x86_64-pc-windows-msvc",
              "ARM64": "aarch64-pc-windows-msvc", "AARCH64": "aarch64-pc-windows-msvc"}
    if os.name != "nt" or native.get(platform.machine().upper()) != args.target:
        parser.error("Use the matching native desktop architecture")
    who = Accounts()
    _, _, identity = who.identify(os.getpid())
    desktop = interactive(identity)
    if args.role == "peer":
        area = args.path
        vm_root(area.parent)
        validate_area(area)
        config = read(area / "controller.json")
        if (config["mode"] != EXISTING or identity["sidSha256"] != config["controller"]["sidSha256"]
                or identity["sessionId"] == config["controller"]["sessionId"]):
            raise RuntimeError("Use the same local account in its second existing standard session")
        write(area / "peer-desktop.json", desktop)
        result = {"passed": False}
        try:
            worker.run(area, result, "scheduled")
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        write(area / "worker-done.json", result)
        return 0 if result["passed"] else 1
    root = vm_root(args.path)
    area = root / ("IfwQaCross_" + uuid.uuid4().hex)
    area.mkdir(mode=0o700)
    output = ROOT / "artifacts/rust/instance-native" / args.target / ("existing-" + area.name)
    output.mkdir(parents=True, exist_ok=False)
    result = {"passed": False, "mode": EXISTING, "target": args.target, "attempted": True,
              "ambientGuardPassed": None, "standardUserGuardPassed": False, "lockSequenceObserved": False,
              "controllerDesktop": desktop, "sources": {p.name: instance.sha(p) for p in sorted(HERE.glob("*.py"))}}
    local = None
    try:
        env, accounts, sid, exe = prepare(area, args, result, result["mode"])
        print("Run the peer from the second standard session using this unique directory:", str(area), flush=True)
        local = original(area, env)
        native_handover(area, accounts, sid, exe, None, result)
        result["peerDesktop"] = read(area / "peer-desktop.json")
        if (result["peerDesktop"] != interactive(result["scheduledWorkerObservedByController"])
                or not wait(area, "worker-done.json")["passed"] or not wait(area, "original-bootstrap-done.json")["passed"]):
            raise RuntimeError("A genuine second standard session or completion record is missing")
        result["passed"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if not result["passed"]:
            (area / "abort").touch()
        if local:
            finish_process(local)
        for name in ("worker-done.json", "original-bootstrap-done.json", "scheduled-attempt.json", "original-attempt.json",
                     "original-done.json", "scheduled-done.json"):
            if (area / name).is_file():
                shutil.copyfile(area / name, output / name)
        try:
            result["participantExitsVerified"] = participants_exited(area)
            shutil.rmtree(area)
            result["temporaryProfileRemoved"] = not area.exists()
        except (OSError, RuntimeError) as exc:
            result.update(passed=False, temporaryProfileRemoved=False, cleanupError=f"{type(exc).__name__}: {exc}")
        result["standardUserGuardPassed"] = bool(result["passed"] and result["lockSequenceObserved"] and result["temporaryProfileRemoved"])
        result["passed"] = result["standardUserGuardPassed"]
        write(output / "result.json", result)
        (output / "evidence.sha256").write_text("".join(f"{instance.sha(p)}  {p.name}\n" for p in sorted(output.glob("*.json"))))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
