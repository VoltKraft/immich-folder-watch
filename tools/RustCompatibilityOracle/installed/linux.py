"""Observe the shipping Flatpak installation, offline repair and ordinary uninstall."""

import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from run import HERE, ROOT, RELEASE, check, database_state, digest, native_target, write_json


APP = "io.github.voltkraft.immich-folder-watch"
COMMAND = "immich-folder-watch"
METAINFO = Path("share/metainfo") / f"{APP}.metainfo.xml"
QA = Path("/qa")
PACKAGE = Path("/package.flatpak")
SEED = Path("/seed")
PROFILE = Path("/tmp/home/.var/app") / APP / "config" / COMMAND
INSTALLATION = Path("/tmp/installation")
REPOSITORY = Path("/tmp/release-source")
ORIGINAL = Path("/tmp/original")
NAMES = ("config.yaml", "sync-state.db")
NAMESPACES = ("user", "mnt", "net", "ipc", "pid")
ENV = {
    "HOME": "/tmp/home", "TMPDIR": "/tmp", "XDG_CONFIG_HOME": "/tmp/home/.config",
    "XDG_DATA_HOME": "/tmp/home/.local/share", "XDG_CACHE_HOME": "/tmp/home/.cache",
    "XDG_STATE_HOME": "/tmp/home/.local/state", "XDG_RUNTIME_DIR": "/tmp/run",
    "GNUPGHOME": "/tmp/gnupg", "FLATPAK_USER_DIR": str(INSTALLATION),
    "FLATPAK_SYSTEM_DIR": "/tmp/empty-system", "FLATPAK_CONFIG_DIR": "/tmp/empty-flatpak-config",
}


def namespace_ids():
    return {name: os.readlink(f"/proc/self/ns/{name}") for name in NAMESPACES}


def verified_package(path):
    target = native_target()
    check(target in ("linux-x64", "linux-arm64"), "A native Linux x64 or ARM64 host is required")
    asset = RELEASE["assets"][target]
    info = path.lstat()
    check(stat.S_ISREG(info.st_mode) and info.st_size == asset["bytes"] and digest(path) == asset["sha256"],
          f"The bundle must match the original {asset['name']} bytes and SHA-256")
    return asset


def profile_hashes(directory):
    hashes = {}
    for name in NAMES:
        path = directory / name
        profile_file_id(path)
        hashes[name] = digest(path)
    return hashes


def profile_file_id(path):
    info = path.lstat()
    check(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 16 * 1024 * 1024,
          f"Expected a regular synthetic {path.name} file")
    return [info.st_dev, info.st_ino]


def command(*arguments):
    argv = [str(argument) for argument in arguments]
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    with (QA / "commands.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": argv, "exit": completed.returncode,
                              "stdout": completed.stdout, "stderr": completed.stderr}) + "\n")
    completed.check_returncode()
    return completed.stdout.strip()


def user_flatpak(*arguments):
    return command("flatpak", "--user", *arguments)


def keyfile(contents):
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.optionxform = str
    parsed.read_string(contents)
    return {section: dict(parsed[section]) for section in parsed.sections()}


def payload(root):
    entries = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        name = path.relative_to(root).as_posix()
        if stat.S_ISLNK(mode):
            entries[name] = {"link": os.readlink(path)}
        elif stat.S_ISDIR(mode):
            entries[name] = {"directory": True}
        else:
            check(stat.S_ISREG(mode), f"Unsupported package member {name}")
            entries[name] = {"sha256": digest(path), "executableBits": mode & 0o111}
    return entries


def packaged_desktop(files, arch):
    bin_dir = files / "lib" / COMMAND
    check(os.readlink(files / "bin" / COMMAND) == f"/app/lib/{COMMAND}/{COMMAND}", "Unexpected apphost link")
    elf = {}
    for name in (COMMAND, "libcoreclr.so", "libhostfxr.so", "libhostpolicy.so"):
        with (bin_dir / name).open("rb") as executable:
            header = executable.read(20)
        check(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01", f"Expected little-endian ELF64 for {name}")
        elf[name] = int.from_bytes(header[18:20], "little")
        check(elf[name] == {"x86_64": 62, "aarch64": 183}[arch], f"Unexpected ELF architecture for {name}")
    check(bool((bin_dir / COMMAND).stat().st_mode & 0o111), "The shipping apphost has no executable bits")
    runtime = json.loads((bin_dir / f"{COMMAND}.runtimeconfig.json").read_bytes())["runtimeOptions"]
    check(runtime["tfm"] == "net10.0" and len(runtime["includedFrameworks"]) == 1 and
          runtime["includedFrameworks"][0]["name"] == "Microsoft.NETCore.App" and
          re.fullmatch(r"10\.0\.\d+", runtime["includedFrameworks"][0]["version"]), "Unexpected self-contained .NET runtime")
    check((bin_dir / f"{COMMAND}.dll").is_file() and (bin_dir / f"{COMMAND}.deps.json").is_file(),
          "Managed application files are missing")
    appstream = ET.parse(files / METAINFO).getroot()
    release = appstream.find("releases/release")
    check(appstream.tag == "component" and appstream.get("type") == "desktop-application" and
          appstream.findtext("id") == APP and appstream.findtext("launchable") == APP + ".desktop" and
          release is not None and release.get("version") == RELEASE["version"], "Unexpected installed AppStream identity")
    return {"elfMachine": elf, "dotnet": runtime["includedFrameworks"][0], "appstreamVersion": release.get("version")}


def private_inputs():
    check(all(os.environ.get(key) == value for key, value in ENV.items()), "The private shipping Flatpak environment is required")
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields, filesystem = line.split(" - ", 1)
        mountpoint, options = fields.split()[4:6]
        mounts[mountpoint] = (options.split(","), filesystem.split()[0])
    read_only = ["/app", "/driver", str(PACKAGE), *(str(SEED / name) for name in NAMES)]
    check(all("ro" in mounts.get(path, ((), ""))[0] for path in read_only) and
          "rw" in mounts.get(str(QA), ((), ""))[0] and mounts.get("/tmp", ((), ""))[1] == "tmpfs" and
          not Path("/home").exists() and not Path("/var/lib/flatpak").exists() and
          not Path("/run/dbus/system_bus_socket").exists() and not Path("/proc/net/route").read_text().splitlines()[1:],
          "The private shipping Flatpak mounts are required")
    inputs = json.loads(Path("/app/inputs.json").read_bytes())
    ids = namespace_ids()
    check(all(ids[name] != inputs["outerNamespaces"][name] for name in NAMESPACES), "Missing private namespace")
    check({name: profile_file_id(SEED / name) for name in NAMES} == inputs["seedFileIds"],
          "The read-only mounts differ from the generated synthetic seed files")
    return inputs, ids


def run_inside():
    inputs, ids = private_inputs()
    for path in ENV.values():
        Path(path).mkdir(mode=0o700, parents=True, exist_ok=True)
    check(verified_package(PACKAGE) == inputs["asset"], "Unexpected package in the isolated mount")
    seed = profile_hashes(SEED)
    check(seed == inputs["seed"], "Seed bytes differ from the caller's inputs")
    PROFILE.mkdir(mode=0o700, parents=True)
    for name in NAMES:
        shutil.copyfile(SEED / name, PROFILE / name)

    arch = platform.machine()
    check(command("flatpak", "--default-arch") == arch, "Native Flatpak architecture differs")
    ref = f"app/{APP}/{arch}/master"
    check(not user_flatpak("list", "--columns=ref") and not user_flatpak("remotes", "--show-disabled", "--columns=name"),
          "The private installation must start empty")
    repo_option = f"--repo={REPOSITORY}"
    command("ostree", repo_option, "init", "--mode=archive-z2")
    command("flatpak", "build-import-bundle", REPOSITORY, PACKAGE)
    command("flatpak", "build-update-repo", REPOSITORY)
    commit = command("ostree", repo_option, "rev-parse", ref)
    check(re.fullmatch(r"[0-9a-f]{64}", commit), "Missing native release commit")
    command("ostree", repo_option, "checkout", "--user-mode", commit, ORIGINAL)
    original = payload(ORIGINAL / "files")
    write_json(QA / "bundle-payload.json", original)

    profile = {}

    def observe_profile(stage):
        check({file.name for file in PROFILE.iterdir()} == set(NAMES), f"Unexpected profile files at {stage}")
        profile[stage] = profile_hashes(PROFILE)
        check(profile[stage] == seed, f"Shipping package changed the synthetic profile at {stage}")

    observe_profile("beforeInstall")
    user_flatpak("install", "--noninteractive", "--no-related", "--no-deps", "--bundle", PACKAGE)
    observe_profile("afterInstall")
    info = {key: user_flatpak("info", "--show-" + key, ref)
            for key in ("ref", "origin", "commit", "location", "runtime", "metadata", "permissions")}
    location = INSTALLATION / ref / commit
    check(info["ref"] == ref and info["commit"] == commit and Path(info["location"]) == location and
          location.resolve(strict=True) == location and info["origin"] == "immich-folder-watch-origin",
          "Unexpected deployment identity or location")
    metadata = keyfile(info["metadata"])
    runtime = f"org.freedesktop.Platform/{arch}/26.08"
    check(metadata == keyfile((ORIGINAL / "metadata").read_text()) and metadata["Application"] == {
        "name": APP, "runtime": runtime, "sdk": f"org.freedesktop.Sdk/{arch}/26.08", "command": COMMAND,
    } and info["runtime"] == runtime, "Unexpected deployed application metadata")
    permissions = {"Context": {"shared": "ipc;network;", "sockets": "x11;", "devices": "dri;"},
                   "Session Bus Policy": {"org.kde.StatusNotifierWatcher": "talk"}}
    check(keyfile(info["permissions"]) == permissions, "Unexpected effective sandbox permissions")
    check(user_flatpak("list", "--columns=ref") == ref.removeprefix("app/"), "Unexpected installed refs")
    files = location / "files"
    installed = payload(files)
    write_json(QA / "installed-payload.json", installed)
    # Flatpak adds the empty .ref lock file to an active deployment's files directory.
    lock = {"sha256": hashlib.sha256(b"").hexdigest(), "executableBits": 0}
    check(".ref" not in original and installed == original | {".ref": lock},
          "Installed payload or deployment lock differs from the original commit")
    desktop = packaged_desktop(files, arch)

    # Give the private installation a fully offline source for the real Flatpak reinstallation.
    user_flatpak("remote-modify", "--url=" + REPOSITORY.as_uri(), info["origin"])
    check(command("ostree", f"--repo={INSTALLATION}/repo", "remote", "show-url", info["origin"]) == REPOSITORY.as_uri(),
          "The repair source must resolve to the private release repository")
    canary = files / METAINFO
    check(canary.resolve(strict=True) == canary and canary.is_file(), "The repair subject must be a local regular file")
    canary.unlink()
    check(not canary.exists(), "The repair subject must be missing before repair")
    user_flatpak("repair", "--reinstall-all")
    repaired = payload(files)
    write_json(QA / "repaired-payload.json", repaired)
    check(repaired == installed and user_flatpak("info", "--show-commit", ref) == commit,
          "Flatpak repair did not restore the original payload and commit")
    observe_profile("afterRepair")
    user_flatpak("uninstall", "--noninteractive", "--no-related", ref)
    check(not user_flatpak("list", "--columns=ref") and not location.exists() and not files.exists(),
          "The deployment survived ordinary uninstall")
    observe_profile("afterUninstall")
    retained = QA / "retained"
    retained.mkdir(mode=0o700)
    for name in NAMES:
        shutil.copyfile(PROFILE / name, retained / name)
    result = {"ref": ref, "commit": commit, "origin": info["origin"], "runtime": runtime,
              "permissions": permissions, "desktop": desktop, "payloadEntries": len(original), "flatpakDeploymentLock": lock,
              "repair": {"source": REPOSITORY.as_uri(), "removed": METAINFO.as_posix(),
                         "restoredSha256": repaired[METAINFO.as_posix()]["sha256"]},
              "profileHashes": profile, "retainedRows": database_state(retained / "sync-state.db"),
              "namespaces": ids, "deployedRefsAfterUninstall": [], "tools": {}}
    for tool in ("bwrap", "flatpak", "ostree"):
        result["tools"][tool] = {"version": command(tool, "--version"), "sha256": digest(Path(shutil.which(tool)))}
    write_json(QA / "observations.json", result)


def run_native(package, evidence, seed_info):
    asset = verified_package(package)
    check(evidence.name == "native", "The shipping runner must supply its native evidence directory")
    seed = evidence.parent / "seed"
    check(stat.S_ISDIR(seed.lstat().st_mode), "The generated seed directory must be local")
    expected = {"config.yaml": seed_info["configSha256"], "sync-state.db": seed_info["databaseSha256"]}
    evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
    os_release = platform.freedesktop_os_release()
    receipt = {"status": "failed", "target": native_target(), "asset": asset,
               "host": {"distribution": os_release["PRETTY_NAME"], "kernel": platform.release()}}
    try:
        inputs = {"asset": asset, "seed": expected, "outerNamespaces": namespace_ids(),
                  "seedFileIds": {name: profile_file_id(seed / name) for name in NAMES}}
        write_json(evidence / "inputs.json", inputs)
        harness = ROOT / "tools/rust-qa/performance/linux.py"
        paths = [HERE / name for name in ("linux.py", "run.py", "release.json")]
        sources = {str(path.relative_to(ROOT)): digest(path) for path in [harness, *paths]}
        with tempfile.TemporaryDirectory(prefix="ifw-shipping-flatpak-", dir="/tmp") as staging:
            scripts = Path(staging) / HERE.relative_to(ROOT)
            scripts.mkdir(parents=True)
            write_json(Path(staging) / "inputs.json", inputs)
            for path in paths:
                shutil.copyfile(path, scripts / path.name)
                check(digest(scripts / path.name) == sources[str(path.relative_to(ROOT))], "Fixture source changed")
            command_line = runpy.run_path(str(harness))["namespace"](evidence, Path(staging), None)
            command_line = command_line[:command_line.index("--chdir")]
            command_line += ["--dir", "/var/tmp", "--ro-bind", str(package.absolute()), str(PACKAGE), "--dir", str(SEED)]
            for name in NAMES:
                command_line += ["--ro-bind", str((seed / name).absolute()), str(SEED / name)]
            for key, value in ENV.items():
                command_line += ["--setenv", key, value]
            command_line += ["--chdir", "/qa", "--", "/usr/bin/python3", "-B",
                             str(Path("/app") / HERE.relative_to(ROOT) / "linux.py"), "--inside"]
            with (evidence / "namespace.log").open("wb") as log:
                child = subprocess.run(command_line, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            check(child.returncode == 0, f"Private Flatpak run exited with {child.returncode}, see namespace.log and commands.jsonl")
        check(sources == {str(path.relative_to(ROOT)): digest(path) for path in [harness, *paths]},
              "Fixture sources changed during the run")
        check(profile_hashes(evidence / "retained") == expected, "Retained files differ outside the namespace")
        receipt.update(json.loads((evidence / "observations.json").read_bytes()),
                       status="passed", fixtureSha256=sources, privateNamespaceExited=True)
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        write_json(evidence / "result.json", receipt)


if __name__ == "__main__":
    if sys.argv[1:] != ["--inside"]:
        sys.exit("Use run.py to test the shipping installer with a generated synthetic profile.")
    run_inside()
