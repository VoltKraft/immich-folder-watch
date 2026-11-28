"""Verify a native WinRT sender, both physical Shell label hits and the captured popup pixels."""

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path, PureWindowsPath
import struct
import tempfile
import time

from activation import ART, HERE, TARGET, paths, sha, write
import toast_history
from notification_probe import CleanupUnconfirmed, ordinary_console


def check_venue(native, captured):
    if native.get("host") == "isolated-vm":
        if native["target"] == TARGET["X64"][0] and "host" not in captured and captured.get("target", native["target"]) == native["target"]:
            return
    elif "host" not in native and native["target"] == TARGET["ARM64"][0] and captured.get("host") == "github-hosted":
        if (all(native[key] and native[key] == captured[key] for key in ("target", "head", "run", "attempt"))
                and captured["scriptSha256"] == native["observerInputs"]["tools/rust-qa/windows-services/toast_console.ps1"]):
            return
    raise ValueError("The native sender and physical observer must belong to the same supported desktop trial")


def corroborates_labels(banner, popup):
    if banner.get("status") != "visible":
        return False
    match = banner["presentation"]["match"]
    return (all(match["host"][k] == popup[k] for k in ("pid", "hwnd", "session"))
            and all(match[key]["runtimeId"] == label["runtimeId"]
                    for key, label in zip(("title", "body"), popup["labels"])))


def verify(directory, frames):
    native = json.loads((directory / "result.json").read_bytes())
    if native["status"] != "passed":
        raise ValueError("Expected a complete native sender and independent notification history")
    history = toast_history.replay(directory, native)
    captured = json.loads((frames / "physical.json").read_text(encoding="utf-8-sig"))
    if captured["status"] != "observed":
        raise ValueError(f"Physical observation {captured['status']}: {captured.get('reason') or captured.get('error')}")
    check_venue(native, captured)
    if captured.get("host") == "github-hosted":
        observer = json.loads((frames / "observer.json").read_bytes())
        machine = TARGET["ARM64"][1]
        view = captured["popup"]["normalView"]
        if view["automationId"] not in ("NormalToastView", "Normal Toast View") or not view["runtimeId"]:
            raise ValueError("Expected both labels in the Shell's ordinary popup view")
        if (observer["armedBeforeSender"] is not True or observer["jobEmpty"] is not True or observer.get("forced")
                or observer["exit"] != 0 or observer["pid"] != captured["observerPid"] or observer["creation100ns"] <= 0
                or observer["machine"] != [machine, machine]
                or any(not ordinary_console(context, "Default") or context["session"] != native["desktop"]["session"]
                       for context in (observer["desktopBefore"], observer["desktopAfter"]))):
            raise ValueError("The native physical observer did not complete on the sender's original console")
    token = native["token"]
    if captured["token"] != token:
        raise ValueError("The physical observation did not match the native test identity")
    issued = []
    for proc in native["processes"]:
        if proc["operation"] == "post-normal":
            row = toast_history.parse_log((directory / proc["log"]).read_bytes(), "post-normal", token, proc["pid"],
                                          native["desktop"]["session"], proc["exit"], require_readiness=True, direct_show=True)
            if "show" in row["phases"]:
                issued.append((proc, row))
    if len(issued) != 1:
        raise ValueError("Expected one timed ordinary Show call")
    proc, row = issued[0]
    frequency, _, end = toast_history.toast_banner.show_timing(row)
    if (row["fields"]["showHresult"] != "0" or row["fields"]["suppressPopup"] != "false"
            or captured["frequency"] != frequency or not end <= captured["beginQpc"] <= captured["endQpc"] <= end + frequency * 10):
        raise ValueError("The screen capture was outside the original successful Show interval and its observation window")
    popup = captured["popup"]
    normal_index = native["processes"].index(proc)
    raw = json.loads((directory / f"{normal_index:03}-normal-popup.json").read_bytes())
    root = PureWindowsPath(raw["windowsDirectory"])
    images = {root / "SystemApps" / package / "ShellExperienceHost.exe" for package in
              ("ShellExperienceHost_cw5n1h2txyewy", "Microsoft.Windows.ShellExperienceHost_cw5n1h2txyewy")}
    if (PureWindowsPath(popup["image"]) not in images or popup["session"] != native["desktop"]["session"]
            or popup["pid"] <= 0 or popup["hwnd"] <= 0 or popup["windowClass"] != "Windows.UI.Core.CoreWindow"
            or not popup["createdUtc"] or len(popup["labels"]) != 2):
        raise ValueError("The physical HWND does not identify the ordinary session's toast host")
    left, top, width, height = popup["capture"]
    image = frames / "popup.png"
    with image.open("rb") as stream:
        header = stream.read(24)
    if (header[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" or struct.unpack(">II", header[16:]) != (width, height)
            or sha(image) != popup["imageSha256"]):
        raise ValueError("The original screen crop differs from the physical popup observation")
    title, body = popup["labels"]
    if title["runtimeId"] == body["runtimeId"] or title["bounds"][3] > body["bounds"][1]:
        raise ValueError("The two visible Shell text rectangles must be distinct")
    for label, text in zip((title, body), ("IFW synthetic normal " + token, "Rust normal notification history " + token)):
        x, y = label["point"]
        x0, y0, x1, y1 = label["bounds"]
        if (label["text"] != text or not label["runtimeId"] or label["physicalHwnd"] != popup["hwnd"]
                or not left <= x0 <= x < x1 <= left + width or not top <= y0 <= y < y1 <= top + height):
            raise ValueError("A captured label or physical hit was outside the matching Shell popup")
    provider_match = any(corroborates_labels(banner, popup) for banner in history["normalBanners"])
    return dict(status="capture-verified", presentation="visible" if provider_match else "review-screen-crop",
                token=token, senderPid=proc["pid"], senderSha256=native["binarySha256"],
                shellPid=popup["pid"], hwnd=popup["hwnd"], imageSha256=sha(image),
                afterShowMs=round((captured["beginQpc"] - end) * 1000 / frequency, 3))


@contextmanager
def armed_screen(child_context, frames, receipt):
    with ExitStack() as stack:
        try:
            proc = stack.enter_context(child_context)
        except (OSError, RuntimeError, ValueError) as exc:
            if CleanupUnconfirmed.in_chain(exc) or ("pid" in receipt and receipt.get("jobEmpty") is not True):
                raise
            frames.mkdir(exist_ok=True)
            write(frames / "physical.json", dict(status="unavailable", reason=f"Observer launch failed: {exc}"))
            receipt["armedBeforeSender"] = False
        else:
            deadline = time.monotonic() + 30
            while not (frames / "ready").is_file() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(.1)
            receipt["armedBeforeSender"] = (frames / "ready").is_file()
        yield


def observe_arm64():
    target, machine = TARGET["ARM64"]
    toast_history.request_identity(target)
    from notification_probe import Desktop, Win32, child, pe_machine, select_powershell

    directory = ART / ("toast-history-" + target)
    frames = ART / ("toast-physical-" + target)
    if directory.exists() or frames.exists():
        raise ValueError("The sender and physical observer require two fresh output directories")
    exe, original = paths(target)
    api, desk = Win32(), Desktop()
    with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"], prefix="ifw-toast-screen-") as temp:
        area = Path(temp)
        host, attempts = select_powershell(area, "accessibility")
        context = desk.context()
        if not (host and pe_machine(Path(host)) == machine and ordinary_console(context, "Default")):
            frames.mkdir()
            write(frames / "physical.json", dict(status="unavailable", reason="No native observer on the unlocked console",
                                                 hosts=attempts, desktop=context))
            return toast_history.observe_sender(target, exe, original, None, None)
        args = ["-NoProfile", "-NoLogo", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass", "-File",
                str(HERE / "toast_console.ps1"), "-HostedArm64", "-NativeDirectory", str(directory),
                "-OutputDirectory", str(frames)]
        receipt = dict(desktopBefore=context, hosts=attempts)
        log = area / "observer.log"
        try:
            physical = child(api, Path(host), args, area, dict(os.environ), log, receipt)
            with armed_screen(physical, frames, receipt):
                return toast_history.observe_sender(target, exe, original, None, None)
        finally:
            frames.mkdir(exist_ok=True)
            receipt["desktopAfter"] = desk.context()
            write(frames / "observer.json", receipt)
            if log.is_file():
                (frames / log.name).write_bytes(log.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe-arm64", action="store_true", help="Observe the existing sender in its native rewrite job")
    parser.add_argument("--require-visible", action="store_true", help="require independent confirmation of both visible labels")
    parser.add_argument("native", type=Path, nargs="?")
    parser.add_argument("frames", type=Path, nargs="?")
    args = parser.parse_args()
    if args.observe_arm64 and not (args.native or args.frames or args.require_visible):
        raise SystemExit(observe_arm64())
    if args.observe_arm64 or not (args.native and args.frames):
        parser.error("Select --observe-arm64 or supply both native and physical evidence directories")
    result = verify(args.native, args.frames)
    print(json.dumps(result, indent=2))
    if args.require_visible and result["presentation"] != "visible":
        raise SystemExit(2)
