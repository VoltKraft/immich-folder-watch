"""Stage and replay the native SQLite helper used by the installed WPF worker trial."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, TARGETS, sha

STORAGE = "tools/rust-qa/storage/"
EXE = "installed_upload_backup.exe"
ARCHIVE = "installed-backup-build.zip"
RECEIPTS = {"result.json", "evidence-hashes.json", "first-party-source-hashes.json",
            "native-graph.json", "native-compiler.log", "installed-backup-build.log"}
CHECKOUT_TEXT = {"rust/toolchain-inputs.json", "tools/rust-qa/check-toolchain.py"}


def sources(revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected the measured Git revision")
    legacy = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision, "--", "rust/crates/ifw-legacy"], cwd=ROOT)
    return {*CHECKOUT_TEXT, "rust/Cargo.toml", *legacy.decode().splitlines(),
            *(STORAGE + n for n in ("Cargo.toml", "Cargo.lock", "inputs.json", "evidence.py", "run.py",
                                    "src/lib.rs", "src/main.rs", "examples/installed_upload_backup.rs",
                                    "examples/installed_upload_backup/windows.rs"))}


def image_receipt(exe):
    with exe.open("rb") as original:
        dos = original.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError("Missing the native executable's DOS header")
        offset, = struct.unpack_from("<I", dos, 60)
        original.seek(offset)
        return dict(dosMagic=dos[:2].hex(), peOffset=offset, peAndCoff=original.read(24).hex(),
                    bytes=exe.stat().st_size, sha256=sha(exe))


def verify_image(image, target, expected):
    coff = bytes.fromhex(image["peAndCoff"])
    if (image["dosMagic"] != "4d5a" or len(coff) != 24 or coff[:4] != b"PE\0\0"
            or not 64 <= image["peOffset"] <= image["bytes"] - 24
            or struct.unpack_from("<H", coff, 4)[0] != TARGETS[target][1] or image["sha256"] != expected):
        raise ValueError("The measured PE header or native helper digest differs")


def verify_archived_build(out: Path, target: str, revision: str) -> dict:
    archive = out / ARCHIVE
    required_sources = sources(revision)
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        native = {n for n in names if n.startswith("native-build-logs/")}
        expected = RECEIPTS | native | {"helper-image.json"} | {"first-party-sources/" + s for s in required_sources}
        if len(names) != len(z.infolist()) or names != expected:
            raise ValueError("Incomplete or duplicate backup build inputs")
        index = json.loads(z.read("evidence-hashes.json"))
        for name in names - {"evidence-hashes.json", "helper-image.json"}:
            if index[name] != hashlib.sha256(z.read(name)).hexdigest():
                raise ValueError(f"Native storage evidence changed: {name}")
        hashes = json.loads(z.read("first-party-source-hashes.json"))
        for name in required_sources:
            raw = z.read("first-party-sources/" + name)
            blob = subprocess.check_output(["git", "show", revision + ":" + name], cwd=ROOT)
            if (hashes[name] != index["first-party-sources/" + name]
                    or (raw != blob and not (name in CHECKOUT_TEXT and raw == blob.replace(b"\n", b"\r\n")))):
                raise ValueError(f"Storage source differs from the native checkout: {name}")
        source = "first-party-sources/"
        inputs = json.loads(z.read(source + STORAGE + "inputs.json"))
        compiler = json.loads(z.read(source + "rust/toolchain-inputs.json"))
        rustc = z.read("native-compiler.log").decode().splitlines()
        result = json.loads(z.read("result.json"))
        verify_image(json.loads(z.read("helper-image.json")), target, index[EXE])
        if (result["format"] != "ifw-rw02-storage-native-v1" or result["status"] != "passed"
                or result["source"] != revision or result["target"] != target or result["modifiedSources"]
                or result["offline"] is not True or result["lockSha256"] != inputs["lock_sha256"]
                or result["rust"]["Os"] != "windows" or result["rust"]["Arch"] != target.split("-")[0]
                or result["rust"]["SQLiteSourceId"] != inputs["sqlite"]["source_id"]
                or json.loads(z.read("native-graph.json")) != inputs["target_graphs"][target]
                or result["verifiedArchives"] != len(inputs["packages"]) or result["nativeBuildLogs"] != 2
                or f"commit-hash: {compiler['commit']}" not in rustc or f"host: {target}" not in rustc
                or result["installedUploadBackup"] != index[EXE]):
            raise ValueError("Native SQLite helper, architecture, compiler or audited graph differs")
        step = result["steps"]["installed-backup-build"]
        if (step["exitCode"] != 0 or step["log"] != "installed-backup-build.log"
                or step["command"][:3] != ["cargo", "build", "--manifest-path"]
                or step["command"][4:] != ["--frozen", "--release", "--target", target, "--example", "installed_upload_backup"]):
            raise ValueError("Missing the frozen native build of the installed upload helper")
        for profile in ("debug", "release"):
            pattern = rf"native-build-logs/{re.escape(target)}/{profile}/build/libsqlite3-sys/[0-9a-f]+/run/stdout"
            logs = [n for n in native if re.fullmatch(pattern, n)]
            if (len(native) != 4 or len(logs) != 1 or logs[0][:-6] + "stderr" not in native
                    or not all(f.encode() in z.read(logs[0]) for f in inputs["sqlite"]["flags"].split())):
                raise ValueError("Missing the native SQLite compiler and extension restrictions")
    return dict(sha256=index[EXE], sqlite=inputs["sqlite"]["source_id"], target=target, archiveSha256=sha(archive))


def stage_backup(build: Path, work: Path, out: Path, target: str, revision: str) -> dict:
    build = build.absolute()
    if build != build.resolve(strict=True) or build.parent != ROOT / "artifacts/rust/storage-native":
        raise ValueError("Expected a completed native storage assessment in this checkout")
    logs = {p.relative_to(build).as_posix() for p in (build / "native-build-logs").rglob("std*") if p.is_file()}
    selected = RECEIPTS | logs | {"first-party-sources/" + name for name in sources(revision)}
    exe = build / EXE
    if exe != exe.resolve(strict=True) or not exe.is_file():
        raise ValueError("Missing the measured Windows backup executable")
    with zipfile.ZipFile(out / ARCHIVE, "x", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("helper-image.json", json.dumps(image_receipt(exe)))
        for name in sorted(selected):
            path = build / name
            if path != path.resolve(strict=True) or not path.is_file():
                raise ValueError("Missing or indirect storage build output")
            archive.write(path, name)
    receipt = verify_archived_build(out, target, revision)
    with (build / EXE).open("rb") as original, (work / EXE).open("xb") as staged:
        shutil.copyfileobj(original, staged)
    if sha(work / EXE) != receipt["sha256"]:
        raise ValueError("The staged executable differs from the archived native build")
    return receipt
