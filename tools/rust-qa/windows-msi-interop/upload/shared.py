"""Inputs shared by the installed Windows upload observer and its detached replay."""
from io import BytesIO
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

UPLOAD = Path(__file__).resolve().parent
sys.path.insert(0, str(UPLOAD.parent))
from common import AREA, HERE, INSTALLED, QA, ROOT, TARGETS, module, read, require, sha, write

peer = module("ifw_signed_upload_peer", INSTALLED / "interop/shipping_upload.py")
backup = module("ifw_signed_upload_snapshot", INSTALLED / "interop/installed_backup.py")


def configuration(media, endpoint):
    path = str(media).replace("'", "''")
    return (f'immich:\n  serverApiUrl: "{endpoint}/api"\n  apiKey: "{peer.TEST_KEY}"\n'
            f"  allowInsecureHttp: true\nwatch:\n  sources:\n    - path: '{path}'\n"
            '      syncMode: uploadAll\n      includeSubdirectories: true\n      deleteAfterUpload: false\n'
            '      extensions: [".png"]\nlogging:\n  target: file\n  level: Information\n  logDirectory: engine-logs\n')


def endpoint_port(endpoint):
    match = re.fullmatch(r"http://127\.0\.0\.1:([1-9]\d{0,4})", endpoint, re.ASCII)
    require(match and int(match[1]) <= 65535, "Expected the single private IPv4 loopback origin")
    return int(match[1])


def observer_sources(out, revision, *, freeze=False):
    paths = {HERE / n for n in ("common.py", "private_desktop.py", "install.ps1", "msi_evidence.py", "transaction-logs.ps1",
                                "reverse/observe.py", "reverse/quit.ps1", "reverse/quit-source.ps1",
                                "reverse/profile.ps1", "reverse/evidence.py")}
    paths.update(INSTALLED / n for n in ("windows.ps1", "release.json", "run.py", "interop/installed_backup.py",
                                         "interop/shipping_upload.py", "interop/assess.py"))
    paths.update([ROOT / "packaging/windows/Test-InstallerUpgradeContract.ps1", ROOT / "packaging/windows/Test-InstalledUpgrade.ps1",
                  QA / "observe-windows-gui.py", QA / "windows_observer.py"])
    paths.update(p for p in UPLOAD.glob("*.py") if not p.name.startswith("test_"))
    for folder, modules in {
        "windows-performance": ("run", "native", "build", "metrics"),
        "windows-inventory": ("scan", "subject"),
        "windows-desktop": ("win32", "job", "run", "worker"),
        "windows-launcher": ("observe", "named_process", "window_readback", "retained_subject", "retained_window"),
    }.items():
        paths.update(QA / folder / (name + ".py") for name in modules)
    names = sorted(p.relative_to(ROOT).as_posix() for p in paths)
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == revision,
            "Use the source revision of the original Windows observation")
    requests = "".join(f"{revision}:{name}\n" for name in names).encode()
    blobs = BytesIO(subprocess.check_output(["git", "cat-file", "--batch"], input=requests, cwd=ROOT))
    eol = subprocess.check_output(["git", "check-attr", "--cached", "-z", "eol", "--", *names], cwd=ROOT).split(b"\0")
    attributes = dict(zip((n.decode() for n in eol[:-1:3]), eol[2::3]))
    original = out / "observer-sources.zip"
    with ZipFile(original, "x" if freeze else "r", ZIP_DEFLATED) as archive:
        if not freeze:
            require(sorted(archive.namelist()) == names, "Changed observer source member set")
        for name in names:
            header = blobs.readline().split()
            require(len(header) == 3 and header[1] == b"blob", "Missing tracked observer " + name)
            data = blobs.read(int(header[2]))
            require(blobs.read(1) == b"\n", "Invalid committed source stream")
            permitted = [data]
            if attributes[name] == b"unspecified":
                permitted.append(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            local = (ROOT / name).read_bytes()
            require(local in permitted, "Changed worktree observer " + name)
            if freeze:
                archive.writestr(name, local)
            else:
                require(archive.read(name) in permitted, "Changed archived observer " + name)
    return sha(original)
