"""Shared source and evidence paths for the installed WPF secondary trial."""
from hashlib import file_digest
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
INSTALLED = ROOT / "tools/RustCompatibilityOracle/installed"
AREA = ROOT / "artifacts/rust/windows-msi-interop"
TARGETS = {"x86_64-pc-windows-msvc": ("windows-x64", 0x8664),
           "aarch64-pc-windows-msvc": ("windows-arm64", 0xaa64)}
BEFORE = "a4587fa61645df77f456d5e5ebe77985d835a71cca8880785bde6826d5ebdb95"
AFTER = "58c04d0ea71fd89846499c79214572db3645eff933c0197e0f80034a1f526c01"


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


def inputs():
    paths = [*sorted(HERE.glob("*.py")), *sorted(HERE.glob("*.ps1")), HERE / "launcher.patch",
             INSTALLED / "windows.ps1", INSTALLED / "release.json", INSTALLED / "run.py",
             ROOT / "packaging/windows/Test-InstallerUpgradeContract.ps1",
             QA / "windows-inventory/scan.py", QA / "windows-inventory/file-observer.cpp",
             QA / "windows-warm-window/build.py", QA / "windows-warm-window/compiler_units.py"]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
