"""Verify the first-party Windows service and observer sources used by a hosted build."""
import hashlib
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]


def service_files():
    local = [p for p in HERE.iterdir() if p.is_file()]
    local.extend(p for p in (HERE / "src").rglob("*") if p.is_file())
    return local + [QA / name for name in (
        "gui/src/tray-icon.argb", "gui/src/windows_tray_shell.rs", "audit-graph.py", "check-toolchain.py",
        "storage/evidence.py", "windows-desktop/job.py", "windows-desktop/win32.py", "windows-imports/formats.py",
        "windows-launcher/named_process.py",
        "windows-performance/native.py", "windows-performance/build.py", "windows_observer.py")] + [
            ROOT / "rust/toolchain-inputs.json", ROOT / ".gitattributes"]


def verify_checkout(root, files, head, source_dir=None):
    paths = sorted({path.relative_to(root).as_posix() for path in files})
    if not re.fullmatch("[0-9a-f]{40}", head) or not paths or any("\n" in path or "\r" in path for path in paths):
        raise ValueError("Expected a full Git commit and bounded checkout file names")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode("ascii").strip()
    if head != current:
        raise ValueError("The requested revision differs from the native runner checkout")
    selection = [*paths, source_dir.relative_to(root).as_posix()] if source_dir else paths
    listing = subprocess.check_output(["git", "ls-tree", "-rz", "--full-tree", head, "--", *selection], cwd=root)
    tracked = {}
    for row in listing.decode("utf-8").split("\0")[:-1]:
        modes, path = row.split("\t", 1)
        mode, kind, oid = modes.split()
        if kind != "blob" or mode not in ("100644", "100755") or (root / path).is_symlink():
            raise ValueError(f"Expected a regular tracked fixture input: {path}")
        tracked[path] = oid
    if set(paths) != set(tracked):
        raise ValueError("A native build or observer input is missing from its recorded revision")
    # Apply this checkout's Git filters (including Windows eol) and compare actual file bytes against HEAD blobs.
    actual = subprocess.check_output(["git", "hash-object", "--stdin-paths"], cwd=root,
                                     input=("\n".join(paths) + "\n").encode("utf-8")).decode("ascii").splitlines()
    if actual != [tracked[path] for path in paths]:
        raise ValueError("The native service or observer working files differ from their recorded Git revision")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}
