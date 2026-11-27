"""Check the complete transport with only the ARM64 import library substituted."""

import json
import os
import shutil
import sys
import tomllib
from pathlib import Path

from formats import pe_imports
from inputs import BASE, HERE, LIBRARY, ROOT, sha

REALTIME = HERE.parent / "realtime"
NAME = "windows_aarch64_msvc"


def registry_cache(dst, lock, suite="transport"):
    caches = [BASE.parent / "realtime-cargo", BASE.parent / "realtime-assessment/cargo-home",
              BASE.parent / "assessment-cache"]
    for home in caches:
        for index in (home / "registry/index").glob("index.crates.io-*"):
            cache = home / "registry/cache" / index.name
            expected = [(cache / f"{p['name']}-{p['version']}.crate", p["checksum"])
                        for p in lock["package"] if "source" in p]
            if not all(file.is_file() for file, _ in expected):
                continue
            shutil.copytree(index, dst / "index" / index.name)
            isolated = dst / "cache" / index.name
            isolated.mkdir(parents=True)
            for file, checksum in expected:
                if sha(file) != checksum:
                    raise ValueError(f"Locked {suite} source changed: {file.name}")
                shutil.copyfile(file, isolated / file.name)
            return len(expected)
    raise ValueError(f"The {suite} (--locked) assessment must first populate its job-local registry cache")


def compare_lock(before, after, name=NAME, suite="transport"):
    for pkg in before["package"]:
        if pkg["name"] == name and pkg["version"] == "0.52.6":
            del pkg["source"]
            del pkg["checksum"]
            break
    else:
        raise ValueError("Missing original Microsoft registry package")
    if before != after:
        raise ValueError(f"Replacing the single import package changed the remaining {suite} lock")


def check_link_response(response, library):
    """Require the exact isolated path in the full-path MSVC link response."""
    raw = response.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else (
        "utf-16-le" if b"\0" in raw[:16] else "utf-8-sig")
    matches = [line.strip(' "\t') for line in raw.decode(encoding).splitlines()
               if line.strip(' "\t').lower().endswith(LIBRARY)]
    if len(matches) != 1 or not Path(matches[0]).samefile(library):
        raise ValueError("The final link response did not resolve the isolated import library")


def variant(work, source, rebuilt, compiler, target, run, env, native, result):
    folder = work / "variant"
    project = folder / "tools/rust-qa/realtime"
    project.mkdir(parents=True)
    for path in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(REALTIME / path, project / path)
    shutil.copytree(REALTIME / "src", project / "src")
    crate_dir = folder / "rust/crates/ifw-immich"
    crate_dir.mkdir(parents=True)
    shutil.copyfile(ROOT / "rust/Cargo.toml", folder / "rust/Cargo.toml")
    shutil.copyfile(ROOT / "rust/crates/ifw-immich/Cargo.toml", crate_dir / "Cargo.toml")
    shutil.copytree(ROOT / "rust/crates/ifw-immich/src", crate_dir / "src")
    source_inputs = [p for p in folder.rglob("*") if p.is_file()]
    result["sourceFiles"] = {p.relative_to(folder).as_posix(): sha(p) for p in source_inputs}
    override = folder / "imports"
    shutil.copytree(source, override)
    shutil.copyfile(rebuilt, override / "lib" / LIBRARY)
    changed = [path.relative_to(source).as_posix() for path in source.rglob("*")
               if path.is_file() and sha(path) != sha(override / path.relative_to(source))]
    if changed != ["lib/" + LIBRARY]:
        raise ValueError(f"Unexpected changes in private transport input: {changed}")
    with (project / "Cargo.toml").open("a", encoding="ascii", newline="\n") as file:
        file.write('\n[patch.crates-io]\nwindows_aarch64_msvc = { path = "../../../imports" }\n')
    original = tomllib.loads((project / "Cargo.lock").read_text("utf-8"))
    home = work / "cargo"
    result["lockedRegistryArchives"] = registry_cache(home / "registry", original)
    env = {k: v for k, v in env.items() if not (k.startswith(("CARGO_", "RUSTC_", "RUSTDOC", "RING_"))
           or k in ("RUSTFLAGS", "RUSTC", "CFLAGS", "LDFLAGS", "CPPFLAGS", "CXXFLAGS"))}
    env.update(CARGO_HOME=str(home), CARGO_TARGET_DIR=str(work / "target"), RUSTC=str(compiler),
               CARGO_NET_OFFLINE="true", PATH=str(compiler.parent) + os.pathsep + env["PATH"])
    cargo = compiler.with_name("cargo" + compiler.suffix)
    run([cargo, "update", "--offline", "-p", NAME, "--precise", "0.52.6"], project, env=env)
    compare_lock(original, tomllib.loads((project / "Cargo.lock").read_text("utf-8")))
    metadata = json.loads(run([cargo, "metadata", "--frozen", "--format-version=1",
                               "--filter-platform", target], project, env=env))
    package, = (p for p in metadata["packages"] if p["name"] == NAME)
    if package["source"] is not None or Path(package["manifest_path"]).resolve().parent != override:
        raise ValueError("Cargo did not select the private rebuilt input")
    result.update(changedInput=changed[0], librarySha256=sha(rebuilt), isolatedLockSha256=sha(project / "Cargo.lock"))
    if not native:
        return
    # The full-path response file lists resolved inputs loaded by the final MSVC link.
    response = work / "transport-link.rsp"
    link_map = work / "transport.map"
    run([cargo, "rustc", "--release", "--frozen", "--", "-C", f"link-arg=/LINKREPROFULLPATHRSP:{response}",
         "-C", f"link-arg=/MAP:{link_map}"],
        project, env=env, timeout=1500)
    check_link_response(response, override / "lib" / LIBRARY)
    result["linkerConfirmedIsolatedLibrary"] = True
    result["featureMapProviders"] = sorted({line.split()[-1] for line in
           link_map.read_text(encoding="utf-8-sig", errors="replace").splitlines()
           if "IsProcessorFeaturePresent" in line})
    original_exe = BASE.parent / "realtime-build" / target / "release/ifw-realtime-probe.exe"
    reference = BASE.parent / "realtime-native" / target
    receipt = json.loads((reference / "result.json").read_bytes())
    original_sessions = json.loads((reference / "sessions.json").read_bytes())
    if (receipt.get("passed") is not True or sha(reference / "sessions.json") != receipt["outputs"]["sessions.json"]
            or sha(original_exe) != original_sessions["probeSha256"]):
        raise ValueError("Original transport executable differs from its passing native session evidence")
    result["originalRunSha256"] = sha(reference / "result.json")
    candidate = work / "target/release/ifw-realtime-probe.exe"
    original_imports, candidate_imports = pe_imports(original_exe), pe_imports(candidate)
    if original_imports != candidate_imports or not any(
            "IsProcessorFeaturePresent" in symbols for dll, symbols in candidate_imports.items()
            if dll.lower() == "kernel32.dll"):
        raise ValueError("The original and relinked transport's OS imports differ or omit the CPU feature query")
    sessions = work / "sessions.json"
    run([sys.executable, REALTIME / "verify.py", "--probe", candidate, "--output", sessions],
        project, env=env, timeout=240)
    observations = json.loads(sessions.read_bytes())
    cases = observations["cases"]
    if (len(cases) != 27 or cases.keys() != original_sessions["cases"].keys()
            or not {"wrong-host-tls", "stop-before-ack", "close-timeout", "ack-after-upgrade", "stalled-probe",
                    "escaped-namespace", "escaped-root-api", "server-disconnect-poll", "server-disconnect-ws",
                    "server-disconnect-then-close", "engine-close-poll", "engine-close-ws"} <= cases.keys()
            or observations["redirectTargetRequests"] != 0 or observations["redirectTargetCredentials"] != 0):
        raise ValueError("Native transport observations are incomplete")
    result.update(probeSha256=sha(candidate), originalProbeSha256=sha(original_exe),
                  peerSourceSha256=sha(REALTIME / "verify.py"), peImportCount=sum(map(len, candidate_imports.values())),
                  sessions=observations, sessionsSha256=sha(sessions))
