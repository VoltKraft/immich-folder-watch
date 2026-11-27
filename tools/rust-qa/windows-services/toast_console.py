"""Verify the original VM sender, both physical Shell label hits and the captured popup pixels."""

import argparse
import json
from pathlib import Path, PureWindowsPath
import struct

from activation import TARGET, sha
import toast_history


def verify(directory, frames):
    native = json.loads((directory / "result.json").read_bytes())
    if native["status"] != "passed" or native.get("host") != "isolated-vm" or native["target"] != TARGET["X64"][0]:
        raise ValueError("Expected a complete isolated Windows x64 sender observation")
    toast_history.replay(directory, native)
    captured = json.loads((frames / "physical.json").read_text(encoding="utf-8-sig"))
    token = native["token"]
    if captured["status"] != "observed" or captured["token"] != token:
        raise ValueError("The physical observation did not match the native test identity")
    normal = [p for p in native["processes"] if p["operation"] == "post-normal"]
    if len(normal) != 1:
        raise ValueError("Expected one timed ordinary sender")
    proc = normal[0]
    row = toast_history.parse_log((directory / proc["log"]).read_bytes(), "post-normal", token, proc["pid"],
                                  native["desktop"]["session"], proc["exit"], require_readiness=True, direct_show=True)
    frequency, _, end = toast_history.toast_banner.show_timing(row)
    if (row["fields"]["showHresult"] != "0" or row["fields"]["suppressPopup"] != "false"
            or captured["frequency"] != frequency or not end <= captured["beginQpc"] <= captured["endQpc"] <= end + frequency * 10):
        raise ValueError("The screen capture was outside the original successful Show interval and its observation window")
    popup = captured["popup"]
    normal_index = native["processes"].index(proc)
    raw = json.loads((directory / f"{normal_index:03}-normal-popup.json").read_bytes())
    root = PureWindowsPath(raw["windowsDirectory"])
    expected = root / "SystemApps/ShellExperienceHost_cw5n1h2txyewy/ShellExperienceHost.exe"
    if (PureWindowsPath(popup["image"]) != expected or popup["session"] != native["desktop"]["session"]
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
    return dict(status="passed", token=token, senderPid=proc["pid"], senderSha256=native["binarySha256"],
                shellPid=popup["pid"], hwnd=popup["hwnd"], imageSha256=sha(image),
                afterShowMs=round((captured["beginQpc"] - end) * 1000 / frequency, 3))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("frames", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.native, args.frames), indent=2))
