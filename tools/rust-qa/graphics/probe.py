"""Run pinned graphics subjects on a disposable Linux X11 or Wayland desktop."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from inputs import GUI_SOURCES, WORKER_SOURCES, sha, source_digest


HERE = Path(__file__).resolve().parent
NAMESPACES = ("net", "mnt", "pid", "ipc", "user")
HELPER_REVISION = "9e189bf06662a2286a1cbadd2efc14ac4a8e22e4"
GRAPHICS_FREEZE = "27462474116603be88e476ed32a943b4fa1126c7"
FIRST_INTEGRATION = "8b071ab9089a87a65ae1cc23325fcbba452fe4d2"


def archived_digest(revision, name):
    return hashlib.sha256(subprocess.check_output(
        ["git", "show", f"{revision}:tools/rust-qa/graphics/{name}"], cwd=HERE)).hexdigest()


def freeze_drivers(destination):
    root = HERE.parents[2]
    files = {"graphics": ("probe.py", "scenarios.py", "inputs.py", "monitor_capture.py"),
             "performance": ("linux.py", "session.py", "x11.py", "observations.py"),
             "gui": ("native.py", "desktop_input.py", "wayland.py")}
    hashes = {}
    for area, names in files.items():
        for name in names:
            path = Path("tools/rust-qa") / area / name
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if area == "graphics":
                shutil.copyfile(root / path, target)
            else:
                # A read of a fixed local Git object also works during unrelated observer edits.
                target.write_bytes(subprocess.check_output(["git", "show", f"{HELPER_REVISION}:{path}"], cwd=root))
            hashes[path.as_posix()] = sha(target)
    return hashes


def launch(args):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", args.name):
        raise ValueError("A fresh result label is required")
    if args.case == "driver-loss" and args.driver != "mesa":
        raise ValueError("The one-shot driver-status experiment requires the isolated llvmpipe ICD")
    if args.diagnostic_mailbox and not (args.integrated and args.backend == "wayland"):
        raise ValueError("The explicit Mesa control requires the integrated private Wayland desktop")
    if args.monitor_capture and args.backend != "wayland":
        raise ValueError("Recording a private Mutter output requires Wayland")
    if args.trace_waits and not (args.monitor_capture and args.integrated):
        raise ValueError("The wait diagnostic requires a monitored private integrated Wayland case")
    artifacts = HERE.parents[2] / "artifacts/rust"
    output = artifacts / "graphics" / args.name
    output.mkdir(parents=True, exist_ok=False)
    subject = args.subject.resolve(strict=True)
    if not subject.is_relative_to(artifacts) or not (subject / "native-gui-assessment").is_file():
        raise ValueError("Select a staged native QA subject")
    hardware = None
    if args.driver in ("intel", "intel-and-mesa"):
        rid = Path("/dev/dri/renderD128")
        node = rid.stat()
        sysfs = Path("/sys/class/drm/renderD128").resolve(strict=True)
        pci = (sysfs / "device").resolve(strict=True)
        if (not stat.S_ISCHR(node.st_mode) or os.major(node.st_rdev) != 226
                or (pci / "vendor").read_text().strip() != "0x8086"):
            raise RuntimeError("Expected the single Intel DRM render-only node")
        hardware = dict(render=str(rid), sysfs=str(sysfs), pci=str(pci),
                        number=f"{os.major(node.st_rdev)}:{os.minor(node.st_rdev)}",
                        vendor=(pci / "vendor").read_text().strip(), device=(pci / "device").read_text().strip())
    gui_receipt = json.loads((subject / "native-gui-assessment.inputs.json").read_text())
    if gui_receipt["binary_sha256"] != sha(subject / "native-gui-assessment"):
        raise ValueError("GUI binary differs from the bound source receipt")
    if args.integrated:
        from stage_integrated import verify
        verify(subject)
        integrated = json.loads((subject / "integrated.inputs.json").read_text())
        files = {"gui_receipt": subject / "native-gui-assessment.inputs.json",
                 "worker_receipt": subject / "worker.inputs.json", "submit_observer": subject / "submit-observer/libvulkan.so.1",
                 "stage": HERE / "stage_integrated.py", "submit_source": HERE / "submit_loss.rs", "observer_builder": HERE / "build.py"}
        if any(integrated.get(role) != sha(path) for role, path in files.items()):
            raise ValueError("The integrated graphics measurement differs from its input receipt")
    elif args.case == "stock":
        workers = json.loads((subject / "worker.inputs.json").read_text())
        if (source_digest(gui_receipt) != GUI_SOURCES or source_digest(workers) != WORKER_SOURCES
                or workers["gui_sha256"] != gui_receipt["binary_sha256"]
                or workers["worker_sha256"] != sha(subject / "ifw-performance-worker")
                or workers["observer_sha256"] != sha(subject / "observer/libvulkan.so.1")):
            raise ValueError("The stock control requires the frozen performance subject")
    else:
        exp = json.loads((subject / "graphics.inputs.json").read_text())
        checks = {"gui": "native-gui-assessment", "worker": "ifw-performance-worker", "observer": "observer/libvulkan.so.1"}
        if args.case == "driver-loss":
            checks["submit_observer"] = "submit-observer/libvulkan.so.1"
        if any(sha(subject / path) != exp[role] for role, path in checks.items()):
            raise ValueError("Experimental subject differs from its bound sources")
        builders = ({sha(HERE / "build.py"), archived_digest(FIRST_INTEGRATION, "build.py")}
                    if exp.get("base_revision") else {archived_digest(GRAPHICS_FREEZE, "build.py")})
        if (exp["builder"] not in builders or exp["submit_source"] != archived_digest(GRAPHICS_FREEZE, "submit_loss.rs")
                or any(exp[field] != sha(HERE / name) for field, name in
               (("pins", "inputs.py"), ("patch", "supervisor.patch"),
                ("graphics", "graphics.rs")))):
            raise ValueError("Rebuild the experiment from the current observation inputs")
    with tempfile.TemporaryDirectory(prefix="ifw-rw02-graphics-", dir="/tmp") as tmp:
        work = Path(tmp) / "run"
        work.mkdir()
        snapshot = Path(tmp) / "inputs"
        sources = freeze_drivers(snapshot)
        drivers = snapshot / "tools/rust-qa"
        sys.path.insert(0, str(drivers / "performance"))
        from linux import namespace
        spec = dict(case=args.case, driver=args.driver, hardware=hardware, backend=args.backend, integrated=args.integrated,
                    diagnostic_mailbox=args.diagnostic_mailbox, monitor_capture=args.monitor_capture, trace_waits=args.trace_waits,
                    outer={k: os.readlink(f"/proc/self/ns/{k}") for k in NAMESPACES})
        (work / "spec.json").write_text(json.dumps(spec))
        command = namespace(work, subject, None, True)
        boundary = command.index("--chdir")
        extra = ["--ro-bind", str(drivers / "graphics"), "/graphics", "--ro-bind", str(drivers / "gui"), "/gui"]
        if hardware:
            extra += ["--dev-bind", hardware["render"], hardware["render"],
                      "--ro-bind", hardware["pci"], hardware["pci"],
                      "--symlink", hardware["sysfs"], "/sys/dev/char/" + hardware["number"],
                      "--symlink", hardware["sysfs"], "/sys/class/drm/renderD128"]
        icd = command.index("VK_DRIVER_FILES") + 1
        if args.driver in ("intel", "intel-and-mesa"):
            manifest = Path("/usr/share/vulkan/icd.d") / ("intel_icd." + platform.machine() + ".json")
            if not manifest.is_file():
                raise RuntimeError("Missing native Intel Vulkan ICD")
            command[icd] = str(manifest) if args.driver == "intel" else str(manifest) + ":" + command[icd]
        elif args.driver == "absent":
            bad = work / "missing-driver.json"
            bad.write_text(json.dumps({"file_format_version": "1.0.0", "ICD": {
                "library_path": "/qa/absent-driver.so", "api_version": "1.0.0"}}))
            command[icd] = "/qa/missing-driver.json"
        manifests = {p: sha(work / "missing-driver.json" if p.startswith("/qa/") else Path(p))
                     for p in command[icd].split(":")}
        command[boundary:boundary] = extra
        command[-1:] = ["/graphics/probe.py", "--inside"]
        try:
            completed = subprocess.run(command, timeout=120)
        finally:
            for file in ("subject.log", "results.json", "xserver.log", "mutter.log", "last-accessibility-tree.json",
                         "pipewire.log", "wireplumber.log", "gstreamer.log", "monitor-formats.log", "monitor-cadence.jsonl",
                         "failure.json", "client-trace.log", "main-thread-waits.jsonl", "main-thread-backtrace.log"):
                if (work / file).is_file():
                    shutil.copyfile(work / file, output / file)
        if {path: sha(snapshot / path) for path in sources} != sources:
            raise RuntimeError("Graphics observation snapshot changed during execution")
    shutil.copyfile(subject / "native-gui-assessment.inputs.json", output / "build.json")
    proof = dict(driver=sources, helper_revision=HELPER_REVISION, icd=manifests, platform=platform.machine(), kernel=platform.release(),
                 build_receipt_sha256=sha(output / "build.json"), observer_exit=completed.returncode)
    for filename in ("results.json", "failure.json"):
        if (output / filename).is_file():
            proof["observation_sha256" if filename == "results.json" else "failure_sha256"] = sha(output / filename)
    if (subject / "graphics.inputs.json").is_file():
        proof["experiment"] = json.loads((subject / "graphics.inputs.json").read_text())
    if args.integrated:
        proof["integrated"] = integrated
    (output / "inputs.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(output, flush=True)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def inside():
    sys.path[:0] = ["/driver", "/gui", "/graphics"]
    from session import fresh_profile, private_session, stop, wait_for
    from observations import Frames
    from native import X11Observer, action
    from x11 import Display
    from scenarios import TrayStatus, WaylandCommits, exercise, pixels, start_accessibility
    work = Path("/qa")
    spec = json.loads((work / "spec.json").read_text())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DISPLAY") != ":93"
            or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or any(os.readlink(f"/proc/self/ns/{k}") == v for k, v in spec["outer"].items())):
        raise RuntimeError("An isolated graphics session is required")
    os.umask(0o077)
    Path.home().mkdir()
    media = work / "files"
    media.mkdir()
    (media / "d0000").mkdir()
    with ExitStack() as stack:
        display, xserver = private_session(stack)
        if spec["backend"] == "wayland":
            from wayland import WaylandObserver
            os.environ["XDG_RUNTIME_DIR"] = "/tmp/runtime"
            if not spec["integrated"] or spec["diagnostic_mailbox"]:
                os.environ["MESA_VK_WSI_PRESENT_MODE"] = "mailbox"
            Path("/tmp/runtime").mkdir(mode=0o700)
            if spec["monitor_capture"]:
                from monitor_capture import MonitorCapture
                observer = MonitorCapture(stack, capture=True)
            else:
                observer = WaylandObserver(stack)
            damage = WaylandCommits(stack, observer.log)
            xserver = "Mutter headless virtual monitor"
        else:
            observer = X11Observer(display)
            damage = Display()
            stack.callback(damage.close, damage.display)
        frames = Frames(stack) if spec["driver"] != "intel-and-mesa" else None
        if spec["case"] not in ("stock", "unavailable"):
            start_accessibility(stack)
        env = fresh_profile(work / "profile", media)
        env.update(HOME="/tmp/home", IFW_QA_GRAPHICS=spec["case"])
        if spec["case"] == "driver-loss":
            env["RUST_BACKTRACE"] = "1"
        if spec["backend"] == "wayland":
            env["XDG_RUNTIME_DIR"] = "/tmp/runtime"
        if frames:
            directory = "/app/submit-observer" if spec["case"] == "driver-loss" else "/app/observer"
            env.update(IFW_QA_RENDER_FD=str(frames.writer), LD_LIBRARY_PATH=directory)
        spec.pop("outer")
        evidence = dict(spec, desktop_server=xserver, mesa_present_mode=env.get("MESA_VK_WSI_PRESENT_MODE"),
                        drawing_observer="XDamage" if spec["backend"] == "x11" else "Wayland buffer commit",
                        exposed_drm=sorted(p.name for p in Path("/dev/dri").glob("*")),
                        gui_sha256=sha(Path("/app/native-gui-assessment")), worker_sha256=sha(Path("/app/ifw-performance-worker")),
                        presentation_observer_sha256=sha(Path(directory) / "libvulkan.so.1") if frames else None)
        if evidence["exposed_drm"] != (["renderD128"] if spec["hardware"] else []):
            raise RuntimeError("Unexpected DRM exposure")
        log = work / "subject.log"
        tray = TrayStatus(stack) if spec["case"] in ("repeated-loss", "unavailable") else None
        output = stack.enter_context(log.open("w"))
        errors = subprocess.STDOUT
        if spec["trace_waits"]:
            env["WAYLAND_DEBUG"] = "client"
            errors = stack.enter_context((work / "client-trace.log").open("w"))
        subject = subprocess.Popen(["/app/native-gui-assessment"], env=env, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=errors, pass_fds=(frames.writer,) if frames else ())
        stack.callback(stop, subject)
        waits = None
        if spec["trace_waits"]:
            from monitor_capture import MainThreadWaits
            waits = MainThreadWaits(stack, subject)
        if spec["case"] == "stock":
            wait_for(lambda: observer.poll() or subject.poll() is not None, 20, "No window or startup failure")
            window = observer.poll()
            if window:
                if spec["backend"] == "x11":
                    evidence["frame_readback"] = wait_for(lambda: pixels(display, window), 6, "Missing drawn X11 UI")
                evidence["draws_observed"] = wait_for(damage.drain, 6, "Missing native drawing")
                if frames:
                    wait_for(lambda: frames.read() and frames.ready, 5, "Mapped without a successful Vulkan presentation")
                if spec["integrated"]:
                    try:
                        action("qa-destroy-graphics")
                    except subprocess.CalledProcessError as error:
                        if "InvalidArgs" not in error.stderr:
                            raise
                        evidence["ordinary_launch_rejected_fault_action"] = True
                    else:
                        raise RuntimeError("An ordinary GUI accepted the diagnostic device-loss action")
        else:
            try:
                evidence.update(exercise(stack, spec["case"], subject, observer, damage, frames, log, media, tray,
                                         require_queue_completion=spec["integrated"]))
            except (TimeoutError, RuntimeError) as exc:
                evidence["observation_error"] = str(exc)
                evidence["subject_exit_at_failure"] = subject.poll()
                observer.poll()
                evidence["window_events"] = observer.events
                if spec["monitor_capture"]:
                    surfaces = {e["surface"] for e in observer.events if e["event"] == "map"}
                    try:
                        evidence["monitor_output"] = observer.report(sorted(surfaces))
                    except RuntimeError as capture_error:
                        evidence["monitor_error"] = str(capture_error)
                (work / "failure.json").write_text(json.dumps(evidence, indent=2) + "\n")
                if waits:
                    waits.after_timeout()
                raise
        if subject.poll() is None:
            action("quit")
        code = subject.wait(timeout=8)
        observer.poll()
        evidence.update(exit=code, presents=frames.read() if frames else None,
                        window_events=[e["event"] for e in observer.events],
                        app_lines=log.read_text().splitlines())
        if spec["case"] == "stock" and spec["driver"] == "absent":
            if (code == 0 or evidence["presents"] or "map" in evidence["window_events"]
                    or not any("Native renderer exited before its first UI pass" in s for s in evidence["app_lines"])):
                raise RuntimeError("Missing driver unexpectedly initialized the stock native renderer")
        elif spec["case"] not in ("raw-loss", "unrelated-panic") and (code != 0 or not any(s.startswith("DRAINED passes=") for s in evidence["app_lines"])):
            raise RuntimeError("The subject did not drain its worker on Quit")
        if spec["case"] == "raw-loss" and (code != 101 or not any("Failed to create staging buffer" in l for l in evidence["app_lines"])):
            raise RuntimeError("The frozen raw-loss control did not reproduce its renderer failure")
        actual = [s.split()[2] for s in evidence["app_lines"] if s.startswith("ADAPTER Vulkan ")]
        mode = spec["case"]
        preferred = "IntegratedGpu" if spec["hardware"] else "Cpu"
        if spec["driver"] == "absent":
            expected = []
        elif mode in ("stock", "init-fallback", "raw-loss", "unrelated-panic"):
            expected = [preferred]
        else:
            expected = [preferred, "Cpu"] + ([preferred] if mode == "repeated-loss" else [])
        if actual != expected:
            raise RuntimeError(f"Observed unexpected Vulkan adapter selection {actual}, expected {expected}")
        if spec["integrated"]:
            selected = sum(" mode=Mailbox driver=llvmpipe desktop=Wayland" in line for line in evidence["app_lines"])
            if selected != (actual.count("Cpu") if spec["backend"] == "wayland" else 0):
                raise RuntimeError("The application did not select presentation for precisely the observed Wayland CPU surfaces")
        if spec["monitor_capture"]:
            surfaces = [evidence[tag]["native_window"] for tag in ("initial_graphics", "recovered_graphics", "explicit_retry")
                        if tag in evidence]
            evidence["monitor_output"] = observer.report(surfaces)
        (work / "results.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps({k: evidence[k] for k in ("case", "driver", "exit", "presents")}), flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--name", required=True)
        parser.add_argument("--case", choices=("stock", "raw-loss", "recover", "repeated-loss", "during-paint", "unrelated-panic", "driver-loss", "init-fallback", "unavailable"), default="stock")
        parser.add_argument("--driver", choices=("mesa", "intel", "intel-and-mesa", "absent"), default="mesa")
        parser.add_argument("--backend", choices=("x11", "wayland"), default="x11")
        parser.add_argument("--subject", type=Path, default=HERE.parents[2] / "artifacts/rust/performance/subjects/native-map-confirmed")
        parser.add_argument("--integrated", action="store_true", help="Run the canonical GUI with its normal presentation policy")
        parser.add_argument("--diagnostic-mailbox", action="store_true", help="Set the Mesa Wayland override for a labelled control run")
        parser.add_argument("--monitor-capture", action="store_true", help="Consume and timestamp the selected virtual monitor's PipeWire frames")
        parser.add_argument("--trace-waits", action="store_true", help="Collect private client events and main-thread waits including a timeout backtrace")
        launch(parser.parse_args())
