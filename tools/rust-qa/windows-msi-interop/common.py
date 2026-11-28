"""Shared source and evidence paths for the installed WPF secondary trial."""
from hashlib import file_digest, sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
INSTALLED = ROOT / "tools/RustCompatibilityOracle/installed"
AREA = ROOT / "artifacts/rust/windows-msi-interop"
TARGETS = {"x86_64-pc-windows-msvc": ("windows-x64", 0x8664),
           "aarch64-pc-windows-msvc": ("windows-arm64", 0xaa64)}
BEFORE = "67c3359dbbb352a0db36a4b9dbfa98ee7c305965e463d8cb3827cace9a987288"
AFTER = "58c04d0ea71fd89846499c79214572db3645eff933c0197e0f80034a1f526c01"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def module(name, path):
    sys.path.insert(0, str(path.parent))
    spec = spec_from_file_location(name, path)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def launcher():
    return module("ifw_installed_secondary_observer", QA / "windows-launcher/observe.py")


def launcher_variant(wpf_primary):
    if wpf_primary:
        return HERE / "reverse/launcher.patch", "7a7f5efbcddff0b17a77aed5d69ffe34cefdfda693ad020dc1a2f12154b20941"
    return HERE / "launcher.patch", AFTER


def inputs(wpf_primary=False):
    paths = [*sorted(HERE.glob("*.py")), *sorted(HERE.glob("*.ps1")), HERE / "launcher.patch",
             INSTALLED / "windows.ps1", INSTALLED / "release.json", INSTALLED / "run.py",
             ROOT / "packaging/windows/Test-InstallerUpgradeContract.ps1",
             QA / "windows-inventory/scan.py", QA / "windows-inventory/file-observer.cpp",
             QA / "windows-warm-window/build.py", QA / "windows-warm-window/compiler_units.py"]
    if wpf_primary:
        reverse = HERE / "reverse"
        paths.extend([*sorted(reverse.glob("*.py")), *sorted(reverse.glob("*.ps1")), reverse / "launcher.patch"])
        paths.extend([ROOT / "packaging/windows/Test-InstalledUpgrade.ps1", QA / "observe-windows-gui.py",
                      QA / "windows_observer.py", QA / "windows-warm-window/window_lifetime.py"])
        for folder, names in {
            "windows-desktop": ("run", "worker", "job", "win32"),
            "windows-launcher": ("observe", "named_process", "retained_subject", "retained_window", "window_readback"),
            "windows-performance": ("run", "native", "metrics", "build"),
        }.items():
            paths.extend(QA / folder / (name + ".py") for name in names)
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}


def verify_source_inputs(recorded, revision, wpf_primary=False):
    local = inputs(wpf_primary)
    if set(recorded) != set(local) or revision != subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip():
        raise ValueError("Use the exact source revision that recorded this trial")
    # These release tools have no EOL attribute. Git for Windows normally checks
    # them out as CRLF. Keep native byte digests and verify each against its Git blob.
    checkout_text = {p.relative_to(ROOT).as_posix() for p in (
        INSTALLED / "windows.ps1", INSTALLED / "release.json", INSTALLED / "run.py",
        ROOT / "packaging/windows/Test-InstallerUpgradeContract.ps1", ROOT / "packaging/windows/Test-InstalledUpgrade.ps1")}
    queries = "".join(f"{revision}:{path}\n" for path in local).encode()
    blobs = BytesIO(subprocess.check_output(["git", "cat-file", "--batch"], cwd=ROOT, input=queries))
    for path, digest in local.items():
        header = blobs.readline().split()
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError(f"Missing committed MSI observer source: {path}")
        data = blobs.read(int(header[2]))
        if blobs.read(1) != b"\n":
            raise ValueError("Incomplete committed MSI observer source")
        permitted = {sha256(data).hexdigest()}
        if path in checkout_text:
            permitted.add(sha256(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")).hexdigest())
        if digest not in permitted or recorded[path] not in permitted:
            raise ValueError(f"An MSI observer source differs from the committed bytes: {path}")
