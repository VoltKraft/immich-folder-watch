"""Verify the installed Noble speech inputs and the two retained native audio observations."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARCH = {"x86_64-unknown-linux-gnu": ("amd64", "x86_64-linux-gnu"),
        "aarch64-unknown-linux-gnu": ("arm64", "aarch64-linux-gnu")}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def packages(sysroot, target):
    arch, multiarch = ARCH[target]
    os_release = (sysroot / "usr/lib/os-release").read_text(encoding="utf-8").splitlines()
    if "ID=ubuntu" not in os_release or "VERSION_CODENAME=noble" not in os_release:
        raise ValueError("Expected an Ubuntu Noble QA userspace")
    result = {}
    for name, spec in read(HERE / "packages.json")["packages"].items():
        pkg_arch = "all" if "all" in spec["debSha256"] else arch
        if sysroot == Path("/"):
            version = subprocess.check_output(["dpkg-query", "-W", "-f", "${Version} ${Architecture} ${db:Status-Status}", name],
                                              text=True).strip()
            if version != f"{spec['version']} {pkg_arch} installed":
                raise ValueError(f"Unexpected installed package {name}: {version}")
        if sha(sysroot / "usr/share/doc" / name / "copyright") != spec["noticeSha256"]:
            raise ValueError(f"Changed Ubuntu package notice for {name}")
        for relative, expected in spec["files"].items():
            if sha(sysroot / relative.format(multiarch=multiarch)) != expected[pkg_arch]:
                raise ValueError(f"Changed Ubuntu payload {relative} for {name}")
        result[name] = {"version": spec["version"], "architecture": pkg_arch, "debSha256": spec["debSha256"][pkg_arch]}
    return result


def native(run, target, binary_sha):
    data = read(run / "results.json")
    build, driver = read(run / "build.json"), read(run / "driver.json")
    if (build.get("target") != target or build.get("binary_sha256") != binary_sha or data["binary_sha256"] != binary_sha
            or data["arch"] != target.split("-")[0] or data.get("build") != build or data.get("driver") != driver):
        raise ValueError("Source, renderer observation or native executable binding differs")
    for name in ("native.py", "screen_reader.py", "desktop_input.py", "wayland.py"):
        path = HERE.parent / "gui" / name
        if driver[path.relative_to(ROOT).as_posix()] != sha(path):
            raise ValueError(f"The retained run used a different GUI observer {name}")
    result = data["input"]
    speech = result["screen_reader"]
    backend = data["backend"]
    if (backend not in ("x11", "wayland") or result["backend"] != backend or data["mesa_present_mode_override"] is not None
            or speech["orcaVersion"].split()[-1] != "46.1"
            or speech["orcaModifierDisplay"] != (":93" if backend == "wayland" else None)
            or result["password_accessible_text"] != "•••" or len(data["runs"]) != 4):
        raise ValueError("Unexpected backend, renderer, Orca version or protected field")
    # Compare the measured interval with the original native speech trace, including key events.
    lines = (run / "orca-debug.log").read_text(encoding="utf-8", errors="replace").splitlines()
    sent = [m[1] for line in lines if (m := re.search(r"SPEECH DISPATCHER: Speaking '(.*?)' as (?:string|char|key)\b", line))]
    spoken = speech["spoken"]
    if not spoken or not any(sent[i:i+len(spoken)] == spoken for i in range(len(sent))):
        raise ValueError("The measured speech interval differs from the Orca trace")
    expected = ("Dateiname entry", "Kennwort password text", "English push button", "Filename entry")
    cursor = 0
    indices = []
    for name in expected:
        matches = [i for i in range(cursor, len(spoken)) if re.match(re.escape(name) + r"(?:[.\s]|$)", spoken[i])]
        if not matches:
            raise ValueError(f"Missing native focus announcement: {name}")
        indices.append(matches[0])
        cursor = matches[0]+1
    masked = spoken[indices[1]+1:indices[2]]
    if (masked != speech["protectedFieldSpeech"] or masked.count("•") != 3
            or any(re.search(r"\b[xyz]+\b", s, re.I) for s in masked)):
        raise ValueError("Incorrect mask or spoken password character")
    dispatcher = (run / "speechd.log").read_text(encoding="utf-8", errors="replace")
    if ("Module espeak-ng started successfully" not in dispatcher or "Initialized for server audio for espeak-ng" not in dispatcher):
        raise ValueError("The native eSpeak NG module did not initialize server audio")
    raw = (run / "orca-audio.raw").read_bytes()
    start, end = speech["audioStartOfTraversal"], speech["audioBytesObserved"]
    if (not 0 <= start < end <= len(raw) or end-start <= 8192 or not any(raw[start:end])
            or hashlib.sha256(raw[:end]).hexdigest() != speech["audioPrefixSha256"]):
        raise ValueError("Private ALSA samples are silent, incomplete or different")
    files = ["results.json", "build.json", "driver.json", "namespace.json", "orca-debug.log", "orca-audio.raw",
             "speechd.log", "input-app.log", "mutter.log" if backend == "wayland" else "xserver.log"]
    return backend, {"directory": run.name, "spokenFields": [spoken[i] for i in indices], "protected": masked,
                     "measuredAudioBytes": end-start, "sources": {p: sha(run / p) for p in files}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=ARCH)
    parser.add_argument("--userspace", default=Path("/"), type=Path, help="audited unpacked local Noble userspace")
    parser.add_argument("--binary", type=Path, default=ROOT / "artifacts/rust/gui-build/release/native-gui-assessment")
    parser.add_argument("--runs", type=Path, nargs=2, help="two explicit source-bound observations from a local userspace")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != args.target.split("-")[0]:
        parser.error("A matching native Linux architecture is required")
    pkg = packages(args.userspace.resolve(strict=True), args.target)
    binary_sha = sha(args.binary)
    runs = args.runs or [p.parent for p in sorted((ROOT / "artifacts/rust/gui-run").glob("*/results.json"))
                         if read(p).get("input", {}).get("screen_reader")]
    if len(runs) != 2:
        raise ValueError("Expected one fresh native speech result per backend")
    observed = dict(native(run, args.target, binary_sha) for run in runs)
    if set(observed) != {"x11", "wayland"}:
        raise ValueError("Both native display backends are required")
    output = args.output or ROOT / "artifacts/rust/gui-native" / args.target / "ubuntu-reader.json"
    with output.open("x", encoding="utf-8") as out:
        json.dump({"target": args.target, "source": os.environ.get("GITHUB_SHA"), "binarySha256": binary_sha,
                   "reviewSha256": sha(HERE / "packages.json"), "verifierSha256": sha(Path(__file__)),
                   "packages": pkg, "observations": observed}, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print(output)


if __name__ == "__main__":
    main()
