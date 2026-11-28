"""Launch a fresh, offline Plasma display with a source-bound native Rust GUI."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import uuid

from audit import native_architecture, sha, verify_elf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / "artifacts/rust/plasma"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--userspace", type=Path, help="private, audited Ubuntu Noble guest root")
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--blank-control", action="store_true", help="replay the frozen pre-IconPixmap native binary")
    parser.add_argument("--worker", type=Path, help="run the three native menu commands with the paired inventory worker")
    parser.add_argument("--restart-watcher", action="store_true", help="reload KDED's watcher before the menu selections")
    parser.add_argument("--output", type=Path, default=ART / "runs")
    args = parser.parse_args()
    if args.restart_watcher and not args.worker:
        parser.error("--restart-watcher requires the menu trial and its worker")
    arch = native_architecture()
    guest = (args.userspace or ART / f"guest-{arch}").resolve(strict=True)
    if not guest.is_relative_to(ART) or "VERSION_CODENAME=noble" not in (guest / "usr/lib/os-release").read_text().splitlines():
        parser.error("Supply a separate, prepared Ubuntu Noble userspace")
    binary = args.binary.resolve(strict=True)
    if not binary.is_relative_to(ROOT / "artifacts/rust") or not args.output.resolve().is_relative_to(ART):
        parser.error("Use the private assessment artifact directories")
    review_file = HERE / f"ubuntu-{arch}.json"
    review = json.loads(review_file.read_text())
    for relative, expected in review["keyPayloads"].items():
        path = (guest / relative).resolve(strict=True)
        if not path.is_relative_to(guest) or sha(path) != expected:
            raise ValueError(f"The native Plasma payload differs from the {arch} review: {relative}")
        if path.suffix != ".qml":
            verify_elf(path, arch)
    verify_elf(guest / "usr/bin/python3", arch)
    verify_elf(binary, arch)
    manifest = binary.with_suffix(".inputs.json")
    build = json.loads(manifest.read_text())
    if platform.system() != "Linux" or build["target"] != f"{platform.machine()}-unknown-linux-gnu" or sha(binary) != build["binary_sha256"]:
        raise ValueError("The executable does not match its native build receipt")
    icon = HERE.parent / "gui/src/tray-icon.argb"
    if sha(icon) != review["iconSha256"]:
        raise ValueError("Regenerate and review the project tray artwork")
    if args.blank_control:
        if (sha(manifest) != "a1a82918a225e2a8aa9d507644d9ba1022d045207d24068f59e1f9af2905f135"
                or build["binary_sha256"] != "a94b3ffa95450f1ac343c9fbba3148e0443b87baeebb42f67ef8347a6e5815be"):
            raise ValueError("Unexpected historical control build")
    elif build["sources"].get(icon.relative_to(ROOT).as_posix()) != sha(icon) or any(sha(ROOT / p) != v for p, v in build["sources"].items()):
        raise ValueError("Rebuild the matching native GUI from the current audited source")
    menu_inputs = None
    if args.worker:
        worker = args.worker.resolve(strict=True)
        if args.blank_control or worker != binary.with_name("ifw-performance-worker"):
            parser.error("Supply the worker beside its paired current GUI")
        verify_elf(worker, arch)
        receipt = worker.with_name("worker.inputs.json")
        pair = json.loads(receipt.read_bytes())
        if (sha(worker) != pair["worker_sha256"] or sha(binary) != pair["gui_sha256"]
                or any(sha(ROOT / path) != digest for path, digest in pair["sources"].items())):
            raise ValueError("The worker, GUI or reviewed worker sources differ from the paired build")
        menu_inputs = {"worker": sha(worker), "receipt": sha(receipt), "restartWatcher": args.restart_watcher}
    args.output.mkdir(exist_ok=True, parents=True)
    run = Path(tempfile.mkdtemp(prefix="plasma-", dir=args.output)).resolve()
    (run / "machine-id").write_text(uuid.uuid4().hex + "\n")
    (run / "passwd").write_text(f"root:x:0:0:Root:/root:/bin/false\nfixture:x:{os.getuid()}:{os.getgid()}:Fixture:/tmp/home:/bin/false\n")
    (run / "group").write_text(f"root:x:0:\nfixture:x:{os.getgid()}:\n")
    namespaces = {n: os.readlink(f"/proc/self/ns/{n}") for n in ("user", "mnt", "pid", "net", "ipc", "uts")}
    (run / "inputs.json").write_text(json.dumps({"binary": build["binary_sha256"], "target": build["target"],
        "build": sha(manifest), "blankControl": args.blank_control, "menu": menu_inputs, "icon": sha(icon), "ubuntuReview": sha(review_file),
        "brandingSvg": sha(ROOT / "assets/branding/logo.svg"),
        "drivers": {p.name: sha(p) for p in (Path(__file__), HERE / "prepare.py", HERE / "audit.py", HERE / "observe.py", HERE / "menu.py", HERE / "brand.py",
                                              HERE.parent / "performance/session.py", HERE.parent / "performance/x11.py")},
        "namespaces": namespaces}, indent=2) + "\n")
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
    for name in ("usr", "etc", "var"):
        command += ["--ro-bind", str(guest / name), "/" + name]
    for name in ("bin", "lib", "lib64", "sbin"):
        if (guest / name).is_symlink():
            command += ["--symlink", os.readlink(guest / name), "/" + name]
    command += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--dir", "/run", "--dir", "/home", "--dir", "/root",
               "--ro-bind", str(run / "machine-id"), "/etc/machine-id",
               "--ro-bind", str(run / "passwd"), "/etc/passwd", "--ro-bind", str(run / "group"), "/etc/group",
               "--ro-bind", str(binary), "/app/native-gui-assessment", "--ro-bind", str(icon), "/app/tray-icon.argb",
               "--ro-bind", str(ROOT / "assets/branding/logo.svg"), "/app/logo.svg",
               "--ro-bind", str(HERE), "/app/fixture",
               "--ro-bind", str(ROOT / "tools/rust-qa/performance"), "/app/performance", "--bind", str(run), "/qa"]
    environment = {"HOME": "/tmp/home", "PATH": "/usr/sbin:/usr/bin:/bin", "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1", "XDG_RUNTIME_DIR": "/tmp/runtime", "DISPLAY": ":93",
        "XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11",
        "KDE_FULL_SESSION": "true", "KDE_SESSION_VERSION": "5", "QT_QPA_PLATFORM": "xcb",
        "QT_QUICK_BACKEND": "software", "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1", "LIBGL_ALWAYS_SOFTWARE": "1",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/session-bus", "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/tmp/system-bus",
        "GSETTINGS_BACKEND": "memory", "IFW_QA_ISOLATED": "1", "VK_DRIVER_FILES": "/usr/share/vulkan/icd.d/lvp_icd.json"}
    for key, value in environment.items():
        command += ["--setenv", key, value]
    if menu_inputs:
        command += ["--ro-bind", str(worker), "/app/ifw-performance-worker", "--setenv", "LP_NUM_THREADS", "2"]
    print(run, flush=True)
    subprocess.run([*command, "--chdir", "/qa", "--", "/usr/bin/python3", "/app/fixture/observe.py"], check=True)


if __name__ == "__main__":
    main()
