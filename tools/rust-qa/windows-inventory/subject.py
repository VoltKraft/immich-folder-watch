"""Stage a native Windows worker from the frozen inventory source and the audited YAML subset."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = HERE.parents[2]
ORIGINAL = QA / "performance/worker"
SOURCE_HASH = "edee4a245a8aee38963ce1ee54ce05ad78d5a12f3b4b34deeb73eba2cdbf1a68"
LOCK_HASH = "6d1876027b3c8d55ce479471e51a5c4d0f356e00597c393abeb7b16a1a270905"
MANIFEST_HASH = "dbc101945286359d703e79fdb3bedab24429964ecffb0991985cd2e3a059bfa6"
WORKER_PROFILE = QA / "performance/worker-inputs.json"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("The frozen comparison source no longer has the expected platform boundary")
    return source.replace(old, new)


def stage_workspace(project):
    entry = ORIGINAL / "src/main.rs"
    if any(sha(path) != digest for path, digest in
           ((entry, SOURCE_HASH), (ORIGINAL / "Cargo.lock", LOCK_HASH), (ORIGINAL / "Cargo.toml", MANIFEST_HASH))):
        raise ValueError("Windows inventory requires the approved worker source, manifest and lock")
    crate = ROOT / "rust/crates/safe-fs"
    approved = [ROOT / "rust/Cargo.toml", crate / "Cargo.toml", *sorted((crate / "src").glob("*.rs"))]
    review = json.loads(WORKER_PROFILE.read_text(encoding="utf-8"))
    reviewed_fs = {name: digest for name, digest in review.items() if name.startswith("rust/")}
    if {path.relative_to(ROOT).as_posix(): sha(path) for path in approved} != reviewed_fs:
        raise ValueError("The handle-bound native filesystem source differs from the reviewed worker profile")
    worker = project / "tools/rust-qa/performance/worker"
    (worker / "src").mkdir(parents=True)
    for name in ("Cargo.lock", "Cargo.toml"):
        shutil.copyfile(ORIGINAL / name, worker / name)
    common = entry.read_text(encoding="utf-8")
    start = common.index('    if std::env::var("IFW_QA_ISOLATED")')
    end = common.index("        .take((MAX_CONFIG + 1) as u64)", start)
    common = common[:start] + "    let input = windows_input()?;\n    let mut text = String::new();\n    input.config\n" + common[end:]
    common = replace_once(common, 'config.immich.server_api_url != "http://127.0.0.1:9/api"', "config.immich.server_api_url != input.api_url")
    common = replace_once(common, '!matches!(source.path.to_str(), Some("/qa/files" | "/qa/empty"))', "source.path != input.media_path")
    common = replace_once(common, "Ok(Directory::open_root(&source.path)?)", "Ok(input.media)")
    common = replace_once(common, "let address = SocketAddr::from((Ipv4Addr::LOCALHOST, 9));",
                          'let address = *WINDOWS_ENDPOINT.get().ok_or_else(|| io::Error::other("Missing private endpoint"))?;')
    common = replace_once(common, "Err(error) if error.kind() == io::ErrorKind::ConnectionRefused => Ok(()),",
                          "Err(error) if matches!(error.kind(), io::ErrorKind::ConnectionRefused | io::ErrorKind::TimedOut) => Ok(()),")
    common = replace_once(common, "    let root = configuration()?;", "    let root = configuration()?;\n    inventory_release()?;")
    (worker / "src/main.rs").write_text(common + '\ninclude!("windows_profile.rs");\n', encoding="utf-8", newline="\n")
    shutil.copyfile(HERE / "windows_profile.rs", worker / "src/windows_profile.rs")
    shutil.copyfile(QA / "gui/src/windows_qa_host.rs", worker / "src/windows_qa_host.rs")
    (project / "rust").mkdir()
    shutil.copyfile(ROOT / "rust/Cargo.toml", project / "rust/Cargo.toml")
    shutil.copytree(ROOT / "rust/crates/safe-fs", project / "rust/crates/safe-fs")
    return worker


def vendor_sources(archive, destination, review):
    if sha(archive) != review["filtered_bundle_sha256"]:
        raise ValueError("The native YAML filtered source archive has changed")
    with tarfile.open(archive) as members:
        for member in members:
            if member.name == "source-filter.json" and member.isfile():
                continue
            if (not (member.isfile() or member.isdir()) or member.name.startswith(("/", "\\"))
                    or "\\" in member.name or any(p in ("", ".", "..") or ":" in p for p in member.name.split("/"))
                    or member.name.split("/")[0] != "vendor"):
                raise ValueError("Unexpected member in filtered YAML source archive")
            members.extract(member, path=destination, filter="data")
    return destination / "vendor"


def validate_graph(metadata, review, target):
    allowed = {(p["name"], p["version"]): set(p["features"]) for p in review["target_graphs"][target]}
    packages = {p["id"]: p for p in metadata["packages"]}
    selected = []
    for node in metadata["resolve"]["nodes"]:
        package = packages[node["id"]]
        if not package["source"]:
            if package["name"] not in ("safe-fs", "ifw-performance-worker"):
                raise ValueError("Unexpected first-party inventory input")
            continue
        key = package["name"], package["version"]
        if key not in allowed or not set(node["features"]) <= allowed[key]:
            raise ValueError(f"Unreviewed inventory package/feature selection for {key}")
        selected.append(dict(name=key[0], version=key[1], features=sorted(node["features"])))
    return sorted(selected, key=lambda x: (x["name"], x["version"]))


def build_subject(area, output, gui, target, pe_machine, *, compile_only=False):
    if os.name != "nt" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted" or os.getenv("GITHUB_ACTIONS") != "true":
        raise ValueError("The Windows comparison needs an isolated native hosted build")
    machine = {"aarch64-pc-windows-msvc": 0xaa64, "x86_64-pc-windows-msvc": 0x8664}[target]
    stage = area / "inventory-build"
    stage.mkdir()
    worker = stage_workspace(stage)
    review_path = QA / "yaml/inputs.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    archive = ROOT / "artifacts/rust/yaml-assessment/runs" / target / "filtered-sources.tar"
    vendor = vendor_sources(archive, stage, review)
    config = stage / "offline.toml"
    config.write_text('[source.crates-io]\nreplace-with = "reviewed"\n[source.reviewed]\ndirectory = '
                      + json.dumps(vendor.as_posix()) + "\n", encoding="utf-8")
    env = dict(os.environ, CARGO_HOME=str(stage / "cargo-home"), CARGO_TARGET_DIR=str(stage / "target"))
    subprocess.run([sys.executable, str(QA / "check-toolchain.py"), target], env=env, check=True)
    base = ["--frozen", "--config", str(config), "--manifest-path", str(worker / "Cargo.toml")]
    metadata = json.loads(subprocess.check_output(["cargo", "metadata", *base, "--format-version", "1", "--filter-platform", target],
                                                 env=env, cwd=worker))
    packages = validate_graph(metadata, review, target)
    with (output / "inventory-build.log").open("wb") as log:
        if not compile_only:
            subprocess.run(["cargo", "clippy", *base, "--target", target, "--all-targets", "--", "-D", "warnings"],
                           cwd=worker, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(["cargo", "build", *base, "--target", target, "--release"],
                       cwd=worker, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    subject = area / "subject"
    subject.mkdir()
    rust = subject / gui.name
    shutil.copyfile(gui, rust)
    executable = subject / "ifw-performance-worker.exe"
    shutil.copyfile(stage / "target" / target / "release" / executable.name, executable)
    trace = None
    if not compile_only:
        with (output / "file-observer-build.log").open("wb") as log:
            built = subprocess.run(["cl.exe", "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/O2", "/utf-8", "/DUNICODE", "/D_UNICODE",
                                    str(HERE / "file-observer.cpp"), "/link", "advapi32.lib", "tdh.lib"], cwd=stage, stdout=log, stderr=subprocess.STDOUT)
        if built.returncode == 0:
            trace = stage / "file-observer.exe"
    if any(pe_machine(p) != machine for p in (rust, executable, trace) if p is not None):
        raise ValueError("The staged native inventory subject or observer has an unexpected architecture")
    files = [QA / "gui/src/windows_qa_host.rs", *sorted(HERE.glob("*.rs")), *sorted(HERE.glob("*.py")), HERE / "file-observer.cpp",
             HERE.parent / "windows-performance/etw-owned.h", review_path, WORKER_PROFILE,
             ORIGINAL / "src/main.rs", ORIGINAL / "Cargo.toml", ORIGINAL / "Cargo.lock", ROOT / "rust/Cargo.toml",
             ROOT / "rust/crates/safe-fs/Cargo.toml", *sorted((ROOT / "rust/crates/safe-fs/src").glob("*.rs"))]
    facts = dict(gui=sha(rust), worker=sha(executable), fileObserver=sha(trace) if trace else None, compiledEntry=sha(worker / "src/main.rs"),
                 approvedBundle=sha(archive), packages=packages, sources={p.relative_to(ROOT).as_posix(): sha(p) for p in files})
    return rust, trace, facts
