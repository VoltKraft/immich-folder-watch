"""Reconstruct the Windows ARM64 import surface from pinned Microsoft metadata."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections import defaultdict
from pathlib import Path

from formats import import_headers, pe_imports
from inputs import BASE, BASELINES, HERE, LIBRARY, ROOT, SOURCE_TAR, crates, sha, source_bundle, target_std, upstream
from relink import variant

TARGET = "aarch64-pc-windows-msvc"
RUST_REVISION = "0ef1bc386059596dada8fb65b50425aab2ea637a"
EXE = ".exe" if os.name == "nt" else ""
REQUIRED_IMPORT = {"kernel32.dll": ["IsProcessorFeaturePresent"]}


def run(command, directory, *, env=None, timeout=180):
    process = subprocess.run(command, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if process.returncode:
        raise RuntimeError(f"{Path(command[0]).name} returned {process.returncode}\n"
                           + (process.stdout + process.stderr).decode(errors="replace")[-4000:])
    return process.stdout


def rust_tools(work):
    compiler = ROOT / "artifacts/rust/toolchain/bin" / ("rustc" + EXE)
    info = run([compiler, "-vV"], work).decode("ascii")
    if f"commit-hash: {RUST_REVISION}" not in info:
        raise ValueError("Pinned Rust 1.100.0 compiler required")
    host = next(line.removeprefix("host: ") for line in info.splitlines() if line.startswith("host: "))
    sysroot = Path(run([compiler, "--print", "sysroot"], work).decode().strip())
    linker = sysroot / "lib/rustlib" / host / "bin" / ("rust-lld" + EXE)
    return compiler, [linker, "-flavor", "link"], host


def read_metadata(compiler, source, work):
    reader = source / "crates/libs/metadata/src/lib.rs"
    reader_rlib = work / "libmetadata.rlib"
    run([compiler, "--edition=2021", "--crate-name", "metadata", "--crate-type=rlib",
         "-O", reader, "-o", reader_rlib], work)
    lib = source / "crates/tools/lib/src/lib.rs"
    # The unreferenced workspace-directory scanner is the sole consumer of regex.
    # Keep the exact original file for distribution. Compile the metadata half alongside it.
    common, unused = lib.read_bytes().split(b"pub fn crates<P: AsRef<Path>>", 1)
    if b"Regex::new" not in unused:
        raise ValueError("Upstream scanner boundary changed")
    subset = common.replace(b"use regex::Regex;\n", b"").replace(b"use std::path::Path;\n", b"")
    clean = lib.with_name("import_libraries.rs")
    clean.write_bytes(subset)
    common_rlib = work / "libcommon.rlib"
    run([compiler, "--edition=2021", "--crate-name", "lib", "--crate-type=rlib", "-O",
         "--extern", f"metadata={reader_rlib}", clean, "-o", common_rlib], work)
    helper = work / ("print-signatures" + EXE)
    args = ["--edition=2021", "-O", "-L", work, "--extern", f"lib={common_rlib}"]
    run([compiler, *args, HERE / "metadata.rs", "-o", helper], work)
    rows = run([helper], work)
    (work / "signatures.tsv").write_bytes(rows)
    tables = defaultdict(dict)
    for line in rows.decode("ascii").splitlines():
        dll, func, size = line.split("\t")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", dll) or not re.fullmatch(r"[A-Za-z0-9_]+", func):
            raise ValueError("Unrecognized WinMD import spelling")
        if func in tables[dll]:
            raise ValueError(f"Duplicate metadata function {dll}!{func}")
        tables[dll][func] = size
    if len(tables) != 371 or sum(map(len, tables.values())) != 20551:
        raise ValueError("Wrong WinMD signature count")
    for dll, exports in tables.items():
        declarations = []
        for name, convention in exports.items():
            if convention == "cdecl":
                declaration = f"void __cdecl {name}() {{}}"
            else:
                count, remainder = divmod(int(convention), 4)
                if remainder:
                    raise ValueError(f"Unexpected stdcall byte count for {dll}!{name}")
                params = ", ".join(f"int p{i}" for i in range(count))
                declaration = f"void __stdcall {name}({params}) {{}}"
            declarations.append(declaration)
        expected = (source / BASELINES / (dll + ".c")).read_bytes()
        if ("\n".join(declarations) + "\n").encode("ascii") != expected:
            raise ValueError(f"WinMD signatures differ from Microsoft's C baseline for {dll}")
    return dict(tables), args


def llvm_library(linker, tables, directory):
    directory.mkdir()
    libraries = []
    for dll, imports in tables.items():
        definition = dll + ".def"
        # Microsoft indexes names lexicographically within each module. An explicit
        # index preserves its optional loader hint. Omitting NONAME retains named imports.
        entries = [f"{symbol} @{hint}" for hint, symbol in enumerate(sorted(imports))]
        (directory / definition).write_bytes(
            (f"LIBRARY {dll}\nEXPORTS\n" + "\n".join(entries) + "\n").encode("ascii"))
        filename = dll + ".lib"
        run([*linker, "/lib", "/machine:arm64", f"/def:{definition}", f"/out:{filename}"], directory)
        libraries.append(filename)
    run([*linker, "/lib", f"/out:{LIBRARY}", *libraries], directory)
    return directory / LIBRARY


def compiler_environment(work):
    """Choose the installed Microsoft ARM64 compiler and librarian for the upstream tool."""
    finder = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    path = Path(run([finder, "-utf8", "-latest", "-products", "*", "-property", "installationPath"],
                    work).decode("utf-8-sig").strip())
    setup = path / "Common7/Tools/VsDevCmd.bat"
    if not setup.is_absolute() or not setup.is_file():
        raise ValueError("Visual Studio ARM64 C++ tools were not found")

    def selected(values, host):
        env = {k.upper(): v for k, v in values.items()}
        programs = [shutil.which(name, path=env["PATH"]) for name in ("cl.exe", "lib.exe")]
        if all(x and Path(x).resolve().is_relative_to(path.resolve()) and
               Path(x).parent.name.lower() == "arm64" for x in programs):
            return env, {"compiler": sha(Path(programs[0])), "librarian": sha(Path(programs[1])),
                         "version": env.get("VCTOOLSVERSION"), "hostArch": host,
                         "binDirectory": Path(programs[0]).parent.relative_to(path).as_posix()}
        return None

    active = selected(os.environ, os.environ.get("VSCMD_ARG_HOST_ARCH", "active-shell"))
    if active:
        return active
    # subprocess list quoting escapes embedded quotes for a C argv parser. cmd.exe
    # parses its /c argument differently. Invoke a fixed local batch basename so
    # paths such as Program Files are quoted only by the batch language itself.
    if any(character in str(setup) for character in '"%\r\n'):
        raise ValueError("Unsupported Visual Studio setup path")
    activate = work / "ifw-arm64-tools.cmd"
    attempts = []
    for host in ("arm64", "amd64"):
        activate.write_bytes((f'@call "{setup}" -no_logo -arch=arm64 -host_arch={host} >nul\r\n'
                              '@if errorlevel 1 exit /b 1\r\n@set\r\n').encode('mbcs'))
        process = subprocess.run([os.environ["COMSPEC"], "/d", "/u", "/c", activate.name], cwd=work,
                                 stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        attempts.append(f"{host} returned {process.returncode}")
        if process.returncode:
            continue
        values = dict(line.split("=", 1) for line in process.stdout.decode("utf-16-le").splitlines()
                      if "=" in line and not line.startswith("="))
        found = selected({**os.environ, **values}, host)
        if found:
            return found
    raise ValueError("Could not locate the ARM64 compiler and librarian after setup: " + ", ".join(attempts))


def original_generator(compiler, source, args, work, env):
    version = tomllib.loads((source / "crates/tools/msvc/Cargo.toml").read_text("utf-8"))["package"]["version"]
    env = {**env, "PLATFORM": "arm64", "CARGO_PKG_VERSION": version}
    program = work / "microsoft-import-generator.exe"
    run([compiler, *args, source / "crates/tools/msvc/src/main.rs", "-o", program], work, env=env)
    folder = work / "msvc"
    dest = folder / "crates/targets/aarch64_msvc/lib"
    dest.mkdir(parents=True)
    run([program], folder, env=env, timeout=1200)
    return dest / LIBRARY


def compile_binding(compiler, cargo, work, sysroot):
    args = [compiler, "--target", TARGET, "--edition=2021", "--crate-type=lib", "-O"]
    if sysroot:
        args.extend(["--sysroot", sysroot])
    targets = work / "libwindows_targets.rmeta"
    bindings = work / "libwindows_sys.rmeta"
    run([*args, "--emit=metadata", "--crate-name", "windows_targets",
         cargo / "windows-targets/src/lib.rs", "-o", targets], work)
    features = [value for feature in ("Win32", "Win32_Foundation", "Win32_System", "Win32_System_Threading")
                for value in ("--cfg", f'feature="{feature}"')]
    run([*args, "--emit=metadata", "--crate-name", "windows_sys", *features,
         "--extern", f"windows_targets={targets}", cargo / "windows-sys/src/lib.rs", "-o", bindings], work)
    obj = work / "binding.obj"
    run([*args, "--emit=obj", "-L", work, "--extern", f"windows_sys={bindings}",
         HERE / "probe.rs", "-o", obj], work)
    return obj


def link_probe(linker, obj, lib, directory):
    directory.mkdir()
    out = directory / "kernel-probe.dll"
    run([*linker, "/dll", "/noentry", "/nodefaultlib", "/machine:arm64", "/timestamp:0",
         "/export:ifw_feature", "/export:ifw_ring_feature", "/out:kernel-probe.dll", obj, lib], directory)
    imports = pe_imports(out)
    if imports != REQUIRED_IMPORT:
        raise ValueError(f"Probe linked unexpected imports {imports}")
    return out


def assess(options, result):
    work = Path(tempfile.mkdtemp(prefix="build-", dir=BASE))
    source = work / "source"
    cargo = work / "crates"
    result["upstream"] = upstream(source, options.acquire, options.source_tar)
    bundle = work / "corresponding-source.tar"
    source_bundle(source, bundle)
    result["upstream"]["sourceTarSha256"] = sha(bundle)
    if sha(bundle) != SOURCE_TAR:
        raise ValueError("Generated source tar differs from the reviewed identity")
    records, original = crates(cargo, options.acquire)
    result["crateInputs"] = records
    compiler, linker, host = rust_tools(work)
    result["compiler"] = {"host": host, "commit": RUST_REVISION,
                          "linker": run([*linker, "--version"], work).decode().strip()}
    if options.native and (host != TARGET or os.name != "nt"):
        raise ValueError("Native ARM64 Windows Rust is required for --native")
    tables, rust_args = read_metadata(compiler, source, work)
    result["metadata"] = {"dlls": len(tables), "signatures": sum(map(len, tables.values())),
                          "cdecl": sum(c == "cdecl" for dll in tables.values() for c in dll.values()),
                          "signatureSha256": sha(work / "signatures.tsv")}
    libs = {"published": original, "llvm": llvm_library(linker, tables, work / "llvm")}
    repeat = llvm_library(linker, tables, work / "repeat")
    if repeat.read_bytes() != libs["llvm"].read_bytes():
        raise ValueError("Repeated LLVM rebuilds differ")
    result["llvmRepeatSha256"] = sha(repeat)
    original_imports, _ = import_headers(original)
    sysroot = None
    if host != TARGET:
        sysroot, result["crossTargetStd"] = target_std(TARGET, work, options.target_std, options.acquire)
    obj = compile_binding(compiler, cargo, work, sysroot)
    result["bindingObjectSha256"] = sha(obj)
    library_results = result["libraries"] = {}

    def verify(name, library):
        imports, coff = import_headers(library)
        if coff != 3 * len(tables):
            raise ValueError(f"{name} differs from the three ARM64 descriptor objects per module")
        if {k: set(v) for k, v in imports.items()} != {k: set(v) for k, v in tables.items()}:
            raise ValueError(f"{name} differs from the WinMD named function surface")
        differences = sum(hint != original_imports[dll][symbol] for dll, symbols in imports.items()
                          for symbol, hint in symbols.items())
        if differences:
            raise ValueError(f"{name} differs from the published lookup hints")
        probe = link_probe(linker, obj, library, work / ("pe-" + name))
        library_results[name] = {
            "sha256": sha(library), "exactPublishedBytes": library.read_bytes() == original.read_bytes(),
            "descriptorObjects": coff, "hintDifferences": differences, "peSha256": sha(probe),
            "peImports": pe_imports(probe),
        }
        if options.native:
            library_results[name]["execution"] = json.loads(run([observer, probe], work))
    env = os.environ.copy()
    if options.native:
        env, result["microsoftTools"] = compiler_environment(work)
        observer = work / "native-observer.exe"
        run([compiler, "--edition=2021", "-O", HERE / "native.rs", "-o", observer], work, env=env)
    for name, library in libs.items():
        verify(name, library)
    if options.transport:
        result["transport"] = {}
        variant(work, cargo / "windows_aarch64_msvc", libs["llvm"], compiler, TARGET, run, env,
                options.native, result["transport"])
    if options.native:
        verify("msvc", original_generator(compiler, source, rust_args, work, env))
    if len({lib["peSha256"] for lib in library_results.values()}) != 1:
        raise ValueError("The linked ARM64 probe differs between import libraries")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true", help="fetch missing pinned public source inputs")
    parser.add_argument("--native", action="store_true", help="also rebuild with MSVC and execute native ARM64 probes")
    parser.add_argument("--target-std", type=Path, help="official Rust 1.100.0 ARM64 MSVC std tar.xz")
    parser.add_argument("--source-tar", type=Path, help="read the verified filtered source tar offline")
    parser.add_argument("--transport", action="store_true",
                        help="resolve the isolated transport override and run the full relink on native Windows")
    options = parser.parse_args()
    runs = BASE / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="arm64-", dir=runs))
    first_party = {p.name: sha(p) for p in HERE.iterdir() if p.is_file()}
    result = {"nativeExecutionRequested": options.native, "sourceFiles": first_party,
              "transportInventorySha256": sha(HERE.parent / "realtime/inputs.json"),
              "toolchainInputsSha256": sha(ROOT / "rust/toolchain-inputs.json"),
              "workflowRun": os.environ.get("GITHUB_RUN_ID"), "workflowCommit": os.environ.get("GITHUB_SHA")}
    try:
        assess(options, result)
        result["passed"] = True
    except Exception as exc:
        result.update(passed=False, error=str(exc))
        raise
    finally:
        (directory / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                               encoding="utf-8")
        print(directory.relative_to(ROOT))


if __name__ == "__main__":
    main()
