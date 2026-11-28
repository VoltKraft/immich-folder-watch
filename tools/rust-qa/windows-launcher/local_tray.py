"""Verify the original paired compiler archive for a retained local Windows tray trial."""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import socket
import subprocess
import tempfile
import uuid
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
TARGET = "x86_64-pc-windows-msvc"
GUI = "native-gui-assessment.exe"
WORKER = "ifw-performance-worker.exe"


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_compiler(stream, record):
    messages = [json.loads(line) for line in stream.splitlines()]
    if messages[-1] != {"reason": "build-finished", "success": True}:
        raise ValueError("The retained native compiler did not finish")
    units = [line for line in messages if line["reason"] == "compiler-artifact"]
    app, = [unit for unit in units if unit["target"]["name"] == "native-gui-assessment"
            and unit["target"]["kind"] == ["bin"] and unit["executable"]]
    image, manifest = PureWindowsPath(app["executable"]), PureWindowsPath(app["manifest_path"])
    if (image.name != GUI or image.parent.name != "release" or image.parent.parent.name != "build"
            or PureWindowsPath(app["target"]["src_path"]) != manifest.parent / "src/main.rs"):
        raise ValueError("The retained native application differs from the compiler stream")
    for name in ("eframe", "winit"):
        original = record[name + "Unit"]
        unit, = [row for row in units if row["target"]["name"] == name and row["target"]["kind"] == ["lib"]]
        names = [PureWindowsPath(f).relative_to(image.parent.parent).as_posix() for f in unit["filenames"]]
        if (PureWindowsPath(unit["manifest_path"]) != manifest.parent / original["manifest"]
                or PureWindowsPath(unit["target"]["src_path"]) != manifest.parent / original["crateRoot"]
                or sorted(unit["features"]) != original["features"] or sorted(names) != sorted(original["outputs"])
                or {Path(item).suffix for item in names} != {".rmeta", ".rlib"}):
            raise ValueError(f"The original {name} library differs from the retained compiler stream")


def stage(archive, digest, destination):
    if not re.fullmatch("[0-9a-f]{64}", digest) or file_sha(archive) != digest:
        raise ValueError("The tray archive differs from the original Actions SHA-256")
    with ZipFile(archive) as kit:
        members = kit.infolist()
        if len(members) > 512 or sum(item.file_size for item in members) > 512 * 1024**2:
            raise ValueError("Unexpected size of the native tray compiler kit")
        index = json.loads(kit.read("tray-build.json"))
        files = index["files"]
        if sorted(kit.namelist()) != sorted(["tray-build.json", *files]):
            raise ValueError("The tray kit's members differ from its manifest")
        for name, sha in files.items():
            with kit.open(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                    raise ValueError(f"Unexpected compiler kit member: {name}")
        normal = json.loads(kit.read("canonical/build.json"))
        warm = json.loads(kit.read("retained/build.json"))
        graph = json.loads(kit.read("canonical/graph.json"))
        inventory = index["inventory"]
        policy = json.loads((ROOT / "rust/audit/gui-profile.json").read_bytes())
        pins = json.loads((QA / "windows-warm-window/eframe-source.json").read_bytes())
        winit_pins = json.loads((QA / "windows-warm-window/winit-source.json").read_bytes())
        if (index["target"] != TARGET or normal["target"] != TARGET or warm["target"] != TARGET
                or not re.fullmatch("[0-9a-f]{40}", index["revision"])
                or normal["source"] != index["revision"] or warm["revision"] != index["revision"]
                or warm["baselineReceipt"] != files["canonical/build.json"]
                or normal["binarySha256"] != files["canonical/" + GUI] or warm["baseline"] != normal["binarySha256"]
                or warm["binary"] != inventory["gui"] or warm["binary"] != files[GUI] or warm["binary"] == warm["baseline"]
                or inventory["worker"] != files[WORKER] or warm["buildHost"] != "github-hosted"
                or normal["lockSha256"] != policy["lockSha256"] or warm["canonicalLock"] != normal["lockSha256"]
                or normal["graphSha256"] != policy["targetReportSha256"][TARGET]
                or graph["target"] != TARGET or graph["lockSha256"] != warm["canonicalLock"]
                or warm["canonicalGraph"] != normal["graphSha256"] or files["canonical/graph.json"] != warm["canonicalGraph"]
                or files["retained/compiler.jsonl"] != warm["compilerEvidence"]["sha256"]
                or warm["compilerEvidence"]["application"] != dict(target="native-gui-assessment", crateRoot="src/main.rs",
                                                                   output=GUI, sha256=files[GUI])
                or files["retained/eframe-source.zip"] != warm["eframeSource"]["archiveSha256"]
                or warm["eframeSource"]["pins"] != pins or warm["eframeSource"]["winitPins"] != winit_pins
                or warm["lock"] != pins["retainedLockSha256"] or warm["lock"] != files["retained/project/Cargo.lock"]
                or files["retained/project/Cargo.toml"] != pins["retainedManifestSha256"]):
            raise ValueError("The local tray binaries differ from the paired original compiler receipts")
        compiler_files = {k.removeprefix("retained/project/src/"): v for k, v in files.items() if k.startswith("retained/project/src/")}
        if compiler_files != warm["compilerInputs"]:
            raise ValueError("Different staged GUI sources")
        for name in ("eframe", "winit"):
            if any(files["retained/build/" + path] != v for path, v in warm[name + "Unit"]["outputs"].items()):
                raise ValueError("Different retained library files")
        check_compiler(kit.read("retained/compiler.jsonl"), warm)
        for paths, root in [(normal["compilerSources"], ROOT), (inventory["sources"], ROOT),
                            (warm["variantInputs"], QA / "windows-warm-window")]:
            for relative, expected in paths.items():
                source = (root / relative).resolve()
                if not source.is_relative_to(root) or file_sha(source) != expected:
                    raise ValueError(f"The checked-out tray build source differs: {relative}")
        for name in (GUI, WORKER):
            with kit.open(name) as src, (destination / name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
    return index, warm


@contextmanager
def subject(launcher, archive, digest, result, observer_inputs):
    if (os.name != "nt" or os.getenv("GITHUB_ACTIONS") or os.getenv("RUNNER_ENVIRONMENT")
            or socket.gethostname().casefold() != "ifw-qa25" or ctypes.windll.shell32.IsUserAnAdmin()):
        raise ValueError("Use the dedicated local non-elevated Windows Server x64 console")
    api, desk = launcher.recorder.Win32(), launcher.Desktop()
    context = desk.context()
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    identity = json.loads(subprocess.check_output([powershell, "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "@{user=[Security.Principal.WindowsIdentity]::GetCurrent().Name;"
        "vm=(Get-CimInstance Win32_ComputerSystem).HypervisorPresent} | ConvertTo-Json -Compress"], encoding="utf-8"))
    if (identity["user"].casefold() != r"ifw-qa25\ifw-test" or identity["vm"] is not True
            or api.machine(-1) != (0x8664, 0x8664) or not launcher.ordinary_console(context, "Default")):
        raise ValueError("The original input desktop, native target or standard QA account differs")
    result.update(host="local-vm", hostContext=context, hostIdentity=identity, archiveSha256=digest,
                  observerRevision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  observerInputs={path.relative_to(ROOT).as_posix(): file_sha(path) for path in observer_inputs})
    with launcher.profile_resources(api, Path(tempfile.gettempdir()), uuid.uuid4().hex, result) as (build, stack):
        index, warm = stage(archive, digest, build)
        result.update(revision=index["revision"], compilerRun=index["run"], compilerAttempt=index["attempt"],
                      buildReceipt=index["files"]["retained/build.json"], gui=warm["binary"], inventory=index["inventory"],
                      graph=warm["canonicalGraph"], lock=warm["lock"], peMachines={})
        for name in (GUI, WORKER):
            image = build / name
            stack.enter_context(launcher.recorder.pin_path(api, image, False))
            result["peMachines"][name] = launcher.recorder.pe_machine(image)
            if result["peMachines"][name] != 0x8664:
                raise ValueError("The pinned tray binaries must both be native x64")
        yield api, desk, build / GUI, index["inventory"], index["revision"]
