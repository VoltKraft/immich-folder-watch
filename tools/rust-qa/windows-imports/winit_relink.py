"""Relink the real x64 winit event-loop consumer with the combined profile's feature set."""

import hashlib
import json
import os
import re
import shutil
import tomllib
from pathlib import Path

from formats import pe_imports
from inputs import HERE, LIBRARY, ROOT, sha
from relink import check_link_response, compare_lock, registry_cache

GUI = HERE.parent / "gui"
COMBINED = HERE.parent / "combined-profile"
# Four sorted package/feature lines from the reviewed Windows x64 combined cargo tree.
COMBINED_TREE = "f76fad398b5896f1065a7a5455c0c84b31a010bbe9212fffeac3010923884627"
FEATURES = "1b962ddbd88695405ce6cbfce5afac27a38cf6c9bf90c90429898f5a37b7e3ae"
WITNESS = {"kernel32.dll": "GetCurrentThreadId", "user32.dll": "CreateWindowExW"}


def lock(path):
    return tomllib.loads(path.read_text("utf-8"))


def native_link(project, cargo, run, env, target, library, metadata):
    response = project / "inputs.rsp"
    link_map = project / "symbols.map"
    output = run([cargo, "rustc", "--frozen", "--release", "--target", target.triple,
                  "--message-format=json-render-diagnostics", "--", "-C", f"link-arg=/LINKREPROFULLPATHRSP:{response}",
                  "-C", f"link-arg=/MAP:{link_map}"], project, env=env, timeout=900)
    check_link_response(response, library)
    sys_id, = (p["id"] for p in metadata["packages"] if (p["name"], p["version"]) == ("windows-sys", "0.52.0"))
    units = [json.loads(line) for line in output.splitlines()]
    rlib, = (Path(p).stem for unit in units if unit["reason"] == "compiler-artifact" and unit["package_id"] == sys_id
             for p in unit["filenames"] if p.endswith(".rlib"))
    binary = Path(env["CARGO_TARGET_DIR"]) / target.triple / "release/ifw-winit-import.exe"
    imports = {dll.lower(): names for dll, names in pe_imports(binary, target.machine).items()}
    mapping = link_map.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    providers = {}
    for dll, symbol in WITNESS.items():
        if symbol not in imports.get(dll, ()):
            raise ValueError(f"The relinked winit consumer lacks {dll}!{symbol}")
        providers[symbol] = sorted({line.split()[-1] for line in mapping if f"__imp_{symbol} " in line})
    # Windows can also provide a common Kernel32 symbol via the SDK. Demand an actual
    # executed import owned by the selected library or by its windows-sys rlib member.
    if not any(provider.lower() in {f"{rlib}:{dll}".lower(), f"{Path(LIBRARY).stem}:{dll}".lower()}
               for dll, symbol in WITNESS.items() for provider in providers[symbol]):
        raise ValueError(f"No executed winit import came from the selected binding: {providers}")
    observed = {}
    for mode, expected in (("main-thread", "main-thread-created"), ("worker-thread", "worker-thread-rejected")):
        observation = run([binary, mode], project, env=env, timeout=20).decode("ascii").strip()
        if observation != expected:
            raise ValueError(f"Unexpected native winit {mode} result: {observation}")
        observed[mode] = observation
    return {"binarySha256": sha(binary), "mapSha256": sha(link_map), "responseSha256": sha(response),
            "resolvedLibrarySha256": sha(library), "providers": providers, "bindingsRlib": rlib,
            "peImports": imports, "execution": observed}


def winit_consumer(work, original, rebuilt, compiler, target, run, env, sysroot, native, result):
    combined_lock = COMBINED / "Cargo.lock"
    review = json.loads((COMBINED / "review.json").read_bytes())
    gui_review = json.loads((ROOT / "rust/audit/gui-profile.json").read_bytes())
    if sha(combined_lock) != review["lockSha256"] or sha(GUI / "Cargo.lock") != gui_review["lockSha256"]:
        raise ValueError("The original GUI or combined lock differs from its reviewed identity")
    if review["targets"][target.triple]["treeSha256"] != COMBINED_TREE:
        raise ValueError("Review the four winit/binding feature sets against the changed combined x64 tree")
    home = work / "winit-cargo"
    result["guiRegistryArchivesVerified"] = registry_cache(home / "registry", lock(GUI / "Cargo.lock"), "GUI")
    result["combinedTreeSha256"] = COMBINED_TREE
    allowed = {(p["name"], p["version"]): p["checksum"] for p in lock(combined_lock)["package"] if "source" in p}
    cargo = compiler.with_name("cargo" + compiler.suffix)
    env = {k: v for k, v in env.items() if not k.upper().startswith(("CARGO_", "RUSTC", "RUSTDOC", "RUSTFLAGS"))}
    env.update(CARGO_HOME=str(home), CARGO_NET_OFFLINE="true", RUSTC=str(compiler),
               PATH=str(compiler.parent) + os.pathsep + env["PATH"])
    if sysroot:
        env["CARGO_ENCODED_RUSTFLAGS"] = "--sysroot\x1f" + str(sysroot)
    project = work / "winit-published"
    project.mkdir()
    shutil.copyfile(HERE / "winit.rs", project / "winit.rs")
    shutil.copyfile(combined_lock, project / "Cargo.lock")
    shutil.copyfile(HERE / "winit.toml", project / "Cargo.toml")
    base = json.loads(run([cargo, "metadata", "--offline", "--format-version=1", "--filter-platform", target.triple],
                          project, env=env))
    registry = [p for p in lock(project / "Cargo.lock")["package"] if "source" in p]
    if any(p["source"] != "registry+https://github.com/rust-lang/crates.io-index" or
           allowed.get((p["name"], p["version"])) != p["checksum"] for p in registry):
        raise ValueError("The minimized winit consumer resolved an input outside the combined lock")
    tree = run([cargo, "tree", "--frozen", "--target", target.triple, "-e", "normal,build", "--prefix", "none",
                "--format", "{p}|{f}"], project, env=env).decode("utf-8")
    names = ("winit v0.30.13|", "windows-sys v0.52.0|", "windows-targets v0.52.6|", "windows_x86_64_msvc v0.52.6|")
    rows = sorted({line.removesuffix(" (*)") for line in tree.splitlines() if line.startswith(names)})
    if hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest() != FEATURES:
        raise ValueError(f"The minimized winit/binding feature sets differ from the combined profile: {rows}")
    package, = (p for p in base["packages"] if p["name"] == "winit")
    winit = Path(package["manifest_path"]).parent
    notice = sha(winit / "LICENSE")
    if package["license"] != "Apache-2.0" or notice != "6dc0e068dcf3a5bc8e054205b85b7720e1d49265bbc64bf515d2cf79197df69a":
        raise ValueError("The selected winit source lacks its original Apache-2.0 notice")
    result.update(features=rows, sourceLicense=package["license"], sourceArchiveSha256=allowed["winit", "0.30.13"],
                  winitLicenseSha256=notice, eventLoopSourceSha256=sha(winit / "src/platform_impl/windows/event_loop.rs"))
    changed = work / "winit-llvm"
    shutil.copytree(project, changed)
    override = work / "winit-import-package"
    shutil.copytree(original, override)
    shutil.copyfile(rebuilt, override / "lib" / LIBRARY)
    with (changed / "Cargo.toml").open("a", encoding="ascii", newline="\n") as file:
        file.write(f'\n[patch.crates-io]\n{target.crate} = {{ path = "../winit-import-package" }}\n')
    after = json.loads(run([cargo, "metadata", "--offline", "--format-version=1", "--filter-platform", target.triple],
                           changed, env=env))
    compare_lock(lock(project / "Cargo.lock"), lock(changed / "Cargo.lock"), target.crate, "winit")
    package, = (p for p in after["packages"] if p["name"] == target.crate)
    published, = (p for p in base["packages"] if p["name"] == target.crate)
    if package["source"] is not None or Path(package["manifest_path"]).parent != override:
        raise ValueError("Cargo did not select the reconstructed x64 import package")
    libraries = {"published": Path(published["manifest_path"]).parent / "lib" / LIBRARY, "llvm": override / "lib" / LIBRARY}
    if sha(libraries["published"]) != target.library_sha256:
        raise ValueError("Cargo expanded a different published x64 library")
    for label, folder, metadata in (("published", project, base), ("llvm", changed, after)):
        build = work / ("winit-build-" + label)
        env["CARGO_TARGET_DIR"] = str(build)
        entry = result[label] = {"lockSha256": sha(folder / "Cargo.lock"), "librarySha256": sha(libraries[label])}
        if native:
            entry.update(native_link(folder, cargo, run, env, target, libraries[label], metadata))
        else:
            common = ["--release", "--target", target.triple, "--frozen"]
            run([cargo, "check", *common], folder, env=env, timeout=600)
            ir = build / "winit.ll"
            run([cargo, "rustc", "-p", "winit", "--lib", *common, "--", "-C", "codegen-units=1", f"--emit=llvm-ir={ir}"],
                folder, env=env, timeout=600)
            content = ir.read_text("utf-8")
            calls = {symbol: len(re.findall(r"\bcall\b[^\n]*@" + symbol + r"\(", content))
                     for symbol in WITNESS.values()}
            if not all(calls.values()):
                raise ValueError(f"Missing Windows calls in target-compiled winit: {calls}")
            entry.update(crossCompiled=True, calls=calls, llvmIrSha256=sha(ir))
    if native and result["published"]["peImports"] != result["llvm"]["peImports"]:
        raise ValueError("Reconstructing the x64 import library changed the native winit PE imports")
