"""Stage the original ARM64 executable, managed oracle and their source-bound fixture."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

PARENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PARENT))
from fixture import ROOT
from native_build import FILES, validate

TARGET = "aarch64-pc-windows-msvc"
REVISION = "1c9a7ee6388450a0bcbf9afa947ea4138a6441df"
ARTIFACT = 15229492640
DIGEST = "90df61bc32fa397958a5d91ad7a586e0dcbcba6c2544b668f295a9f4caf5680c"
DIRECTORY = ROOT / "artifacts/rust/arm64-standard-writer"


def verify(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != DIGEST:
        raise ValueError("The original Windows ARM64 writer archive digest differs")
    with ZipFile(path) as archive:
        if sorted(archive.namelist()) != sorted((*FILES, "build.json")):
            raise ValueError("Unexpected original writer archive")
        receipt = json.loads(archive.read("build.json"))
        blobs = {name: archive.read(name) for name in FILES}
    if receipt["revision"] != REVISION:
        raise ValueError("Unexpected original build revision")
    validate(receipt, TARGET, blobs)
    pe = blobs["instance.exe"]
    offset = int.from_bytes(pe[60:64], "little")
    if pe[:2] != b"MZ" or pe[offset:offset+6] != b"PE\0\0\x64\xaa":
        raise ValueError("The original executable is not an ARM64 PE image")
    return receipt


def download():
    DIRECTORY.mkdir(parents=True, exist_ok=False)
    url = f"repos/VoltKraft/immich-folder-watch/actions/artifacts/{ARTIFACT}"
    metadata = json.loads(subprocess.check_output(["gh", "api", url]))
    if (metadata["id"] != ARTIFACT or metadata["expired"] or metadata["digest"] != "sha256:" + DIGEST
            or metadata["workflow_run"]["id"] != 46062734833
            or metadata["workflow_run"]["head_sha"] != REVISION
            or metadata["name"] != f"rust-desktop-writer-{TARGET}-{REVISION}"):
        raise ValueError("Unexpected compiler archive metadata")
    archive = DIRECTORY / "writer.zip"
    with archive.open("xb") as file:
        subprocess.run(["gh", "api", url + "/zip"], stdout=file, check=True)
    verify(archive)


def stage(root):
    archive = DIRECTORY / "writer.zip"
    receipt = verify(archive)
    files = {ROOT / name for name in receipt["source_sha256"]}
    files.update(PARENT / name for name in ("fixture.py", "standard.py", "batch.py", "worker.py", "observe.py",
                 "native_build.py", "console_levels.py", "scheduler.ps1", "scheduler_cleanup.ps1"))
    files.update(Path(__file__).parent / name for name in (
        "inputs.py", "case.py", "logon.py", "run.ps1", "batch_account.py", "replay.py"))
    files.add(ROOT / ".github/workflows/rust-windows-arm64-writer.yaml")
    files.add(ROOT / "global.json")
    for source in sorted(files):
        destination = root / "source" / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(archive, root / "writer.zip")
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


if __name__ == "__main__":
    if sys.argv[1:] == ["download"]:
        download()
    elif len(sys.argv) == 3 and sys.argv[1] == "stage":
        manifest = stage(Path(sys.argv[2]))
        (DIRECTORY / "observer-sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    else:
        raise SystemExit("Expected download or stage <new isolated staging directory>")
