"""Run source-bound Windows x64 realtime tests inside a local native guest."""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_sources(root, manifest):
    for name, expected in manifest.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
            raise ValueError(f"Invalid source name {name}")
        source = (root / relative).resolve(strict=True)
        if not source.is_relative_to(root) or digest(source) != expected:
            raise ValueError(f"Compiler input differs from its source archive: {name}")


def unpack_subject(archive, name, directory, expected):
    info = archive.getinfo(name)
    if not 0 < info.file_size <= 32 * 1024 * 1024:
        raise ValueError(f"Invalid size for {name}")
    output = directory / name
    output.write_bytes(archive.read(info))
    if digest(output) != expected:
        raise ValueError(f"Compiler output hash differs for {name}")
    return output


def verify_host():
    if os.name != "nt":
        raise ValueError("Windows x64 guest required")
    # IsWow64Process2 reports the native machine independently of the child environment.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    probe = kernel.IsWow64Process2
    probe.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)]
    probe.restype = ctypes.c_int
    process = ctypes.c_ushort()
    native = ctypes.c_ushort()
    if not probe(ctypes.c_void_p(-1), ctypes.byref(process), ctypes.byref(native)):
        raise ctypes.WinError(ctypes.get_last_error())
    if native.value != 0x8664 or process.value != 0:
        raise ValueError("The test driver must be a native AMD64 process on an x64 guest")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--archive-sha256", required=True, help="digest from the Actions artifact metadata")
    parser.add_argument("--head", required=True, help="full Git commit recorded by the native compiler")
    parser.add_argument("--source-root", required=True, type=Path, help="source checkout or export at that commit")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--system-proxy", action="store_true",
                        help="exercise and restore the current user's connection settings on this disposable guest")
    args = parser.parse_args()
    if not __debug__:
        raise ValueError("Python assertions must be enabled")
    verify_host()
    if not re.fullmatch("[0-9a-f]{40}", args.head):
        parser.error("--head requires the full Git commit")
    expected = args.archive_sha256.removeprefix("sha256:")
    if not re.fullmatch("[0-9a-f]{64}", expected) or digest(args.archive) != expected:
        raise ValueError("Actions archive digest mismatch")
    source = args.source_root.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty guest output directory")
    result = {"head": args.head, "host": platform.platform(), "machine": platform.machine(),
              "python": platform.python_version(), "runner": "local-guest", "archiveSha256": expected,
              "guestVerifierSha256": digest(Path(__file__)), "steps": {}}

    def step(name, command, timeout):
        with (output / (name + ".txt")).open("wb") as stream:
            status = subprocess.run(command, cwd=source, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout).returncode
        result["steps"][name] = status
        if status:
            raise RuntimeError(f"{name} failed; see {output / (name + '.txt')}")

    try:
        with zipfile.ZipFile(args.archive) as archive, tempfile.TemporaryDirectory(prefix="ifw-local-realtime-") as temp:
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError("Duplicate Actions archive members")
            receipt = archive.read("result.json")
            compiled = json.loads(receipt)
            if (compiled["head"] != args.head or compiled["target"] != "x86_64-pc-windows-msvc"
                    or not compiled["passed"] or compiled["steps"].get("build") != 0):
                raise ValueError("Invalid Windows compiler receipt")
            verify_sources(source, compiled["sourceFiles"])
            locked = digest(source / "tools/rust-qa/realtime/Cargo.lock")
            if locked != compiled["lockSha256"]:
                raise ValueError("Lockfile differs from the compiler receipt")
            result.update(compilerReceiptSha256=hashlib.sha256(receipt).hexdigest(),
                          compilerWorkflowRun=compiled["workflowRun"], verifiedSourceFiles=len(compiled["sourceFiles"]))
            native = Path(temp)
            subject = unpack_subject(archive, "ifw-realtime-probe.exe", native,
                                     compiled["outputs"]["ifw-realtime-probe.exe"])
            result["probeSha256"] = digest(subject)
            if compiled.get("mode") == "build-only":
                if (compiled["steps"].get("unit-build") != 0
                        or {"format", "clippy", "sessions", "unit"}.intersection(compiled["steps"])):
                    raise ValueError("Expected compiler-only output before executing guest tests")
                unit = unpack_subject(archive, "ifw-realtime-unit.exe", native, compiled["outputs"]["ifw-realtime-unit.exe"])
                result["unitSha256"] = digest(unit)
                step("unit", [unit], 60)
            elif "unit" in compiled["steps"] and "sessions" in compiled["steps"]:
                # Early compiler archives contain only the release executable.
                result["unitAvailability"] = "compiler archive did not include a unit executable"
            else:
                raise ValueError("Unrecognized compiler artifact")
            step("sessions", [sys.executable, source / "tools/rust-qa/realtime/verify.py",
                              "--probe", subject, "--output", output / "sessions.json"], 600)
            sessions = json.loads((output / "sessions.json").read_text(encoding="utf-8"))
            if sessions["probeSha256"] != result["probeSha256"] or sessions.get("failure") or not sessions["cases"]:
                raise ValueError("Incomplete wire result or unexpected executable")
            result["wireCases"] = len(sessions["cases"])
            if args.system_proxy:
                fixture = "tools/rust-qa/realtime/windows_system_fixture.py"
                if fixture not in compiled["sourceFiles"]:
                    raise ValueError("The compiler receipt does not include the Windows system proxy fixture")
                # Keep a second copy of the settings in the supervisor. A
                # timed-out worker may have been terminated before its finally.
                spec = importlib.util.spec_from_file_location("ifw_proxy_fixture", source / fixture)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                connection = module.Connection()
                saved = connection.settings()
                try:
                    step("system-proxy", [sys.executable, source / fixture, "--probe", subject,
                                          "--output", output / "system-proxy.json"], 240)
                finally:
                    if [v or None for v in connection.settings()] != [v or None for v in saved]:
                        connection.settings(saved)
                    result["supervisorSettingsRestored"] = [v or None for v in connection.settings()] == [v or None for v in saved]
                    if not result["supervisorSettingsRestored"]:
                        raise RuntimeError("The local supervisor could not restore the Windows proxy settings")
                system = json.loads((output / "system-proxy.json").read_text(encoding="utf-8"))
                if system["probeSha256"] != result["probeSha256"] or not system["settingsRestored"]:
                    raise ValueError("System proxy fixture could not verify the tested binary or restored settings")
                result["systemProxyCases"] = len(system["cases"])
            result["passed"] = True
    finally:
        result.setdefault("passed", False)
        result["outputs"] = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "result.json"}
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
