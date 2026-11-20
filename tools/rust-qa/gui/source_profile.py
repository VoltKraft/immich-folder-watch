"""Reconstruct and authenticate the selected native text engine without editing the Cargo registry."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REVIEW = ROOT / "rust/audit/gui-text-inputs.json"
ASSETS = ROOT / "rust/assets/fonts"
BUILD_INPUTS = HERE / "artifacts"
SOURCES = BUILD_INPUTS / "text"
FONTS = BUILD_INPUTS / "fonts"
CACHE = ROOT / "artifacts/rust/gui-source-inputs"
REPLAY_REVISION = "6c953e32c0b2710bfe06b19805214946653480af"
REPLAY_MANIFESTS = {
    "tools/rust-qa/gui/Cargo.toml": "41e0bf2c09e9401d3743ecc05dfab9e7308f2e2bd4f8f4d6a455146cbed971f4",
    "tools/rust-qa/gui/Cargo.lock": "3d266972f104fae3eb992e8198d25eace401f5c9fe1ed282aa180612fe12cc4a",
    "rust/Cargo.toml": "7f4c1489640d1351a8d0fdeaea2df72fc17ad98ae3df5946fca34fa643e4e96a",
    "rust/crates/desktop-lifecycle/Cargo.toml": "b36dd12119a0d6894f15ffb44d552c077332ece9d996487fdab879e73eb72396",
}
sys.path.insert(0, str(HERE.parent))
from storage.evidence import relative_member, sha256 as sha


def profile():
    reviewed = json.loads(REVIEW.read_text(encoding="utf-8"))
    if set(reviewed["trees"]) != {"egui", "epaint", "unicode-bidi"}:
        raise ValueError("Incomplete GUI source review")
    return reviewed


def replay_manifest(name, destination):
    digest = REPLAY_MANIFESTS[name]
    if destination.is_file() and sha(destination) == digest:
        return
    source = ROOT / name
    data = source.read_bytes() if source.is_file() else b""
    if hashlib.sha256(data).hexdigest() != digest:
        data = subprocess.check_output(["git", "show", f"{REPLAY_REVISION}:{name}"], cwd=ROOT)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Changed historical GUI input {name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        path = Path(scratch) / destination.name
        path.write_bytes(data)
        path.replace(destination)


def fetch_replay_registry(env):
    """Let Cargo populate the original locked index and archives for the independent offline controls."""
    with tempfile.TemporaryDirectory(dir=CACHE) as scratch:
        project = Path(scratch)
        for name in REPLAY_MANIFESTS:
            replay_manifest(name, project / name)
        # Cargo fetch requires targets to discover the two local packages. It compiles neither file.
        for name in ("tools/rust-qa/gui/src/main.rs", "rust/crates/desktop-lifecycle/src/lib.rs"):
            path = project / name
            path.parent.mkdir(parents=True)
            path.touch()
        subprocess.run(["cargo", "fetch", "--locked", "--manifest-path", str(project / "tools/rust-qa/gui/Cargo.toml")],
                       cwd=project, env=env, check=True)


def verify_native_graph(target, env, output=None):
    reviewed = json.loads((REVIEW.parent / "gui-profile.json").read_text(encoding="utf-8"))
    lock = sha(HERE / "Cargo.lock")
    if lock != reviewed["lockSha256"]:
        raise ValueError("The GUI lock differs from its reviewed native profile")
    with tempfile.TemporaryDirectory(dir=CACHE) as scratch:
        report = Path(scratch) / "graph.json"
        subprocess.run([sys.executable, str(HERE.parent / "audit-graph.py"), str(HERE / "Cargo.toml"), target,
                        str(report), "--verify-unpacked"], env=env, check=True)
        digest = sha(report)
        if digest != reviewed["targetReportSha256"][target]:
            raise ValueError(f"Resolved GUI inputs differ from the reviewed {target} graph: {digest}")
        if output is not None:
            report.replace(output)
    return lock, digest


def take_files(source, prefix, names, destination):
    for name in sorted(names):
        relative = relative_member(name)
        member = source.getmember(f"{prefix}/{name}")
        if not member.isfile():
            raise ValueError("Unsupported archive member")
        path = destination.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with source.extractfile(member) as data, path.open("xb") as output:
            shutil.copyfileobj(data, output)


def acquire_original(path, url, digest, limit):
    for attempt in range(3):
        try:
            with tempfile.TemporaryDirectory(dir=CACHE) as scratch:
                tmp = Path(scratch) / path.name
                with urllib.request.urlopen(url, timeout=90) as data, tmp.open("xb") as output:
                    while block := data.read(256 * 1024):
                        if output.tell() + len(block) > limit:
                            raise ValueError(f"Oversize public input {path.name}")
                        output.write(block)
                if sha(tmp) != digest:
                    raise ValueError(f"Wrong published bytes for {path.name}")
                tmp.replace(path)
            return
        except (OSError, urllib.error.URLError) as error:
            if attempt == 2 or (isinstance(error, urllib.error.HTTPError) and error.code < 500 and error.code != 429):
                raise
            time.sleep(2 ** attempt)


def tree_info(root):
    digest = hashlib.sha256()
    count = 0
    if root.is_symlink() or not root.is_dir() or (hasattr(root, "is_junction") and root.is_junction()):
        raise ValueError(f"Missing or linked private source tree {root}")
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError(f"Linked private source member {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"Unexpected private source member {path}")
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(sha(path)))
        count += 1
    return {"files": count, "sha256": digest.hexdigest()}


def cached(name, url, expected, fallback, fetch, limit):
    path = CACHE / name
    if not path.exists():
        local = next((p for p in fallback if p.is_file() and sha(p) == expected), None)
        if local:
            with tempfile.TemporaryDirectory(dir=CACHE) as work:
                copy = Path(work) / name
                shutil.copyfile(local, copy)
                if sha(copy) != expected:
                    raise ValueError(f"Changed source while copying {name}")
                copy.replace(path)
        elif fetch:
            acquire_original(path, url, expected, limit)
        else:
            raise ValueError(f"First acquire the reviewed input {name} with build-gui-probe.py")
    if path.is_symlink() or sha(path) != expected:
        raise ValueError(f"Changed cached original {name}")
    return path


def reproduce_table(src, work, prefix):
    take_files(src, prefix, ["tools/generate.py", "tests/data/BidiTest.txt",
                                   "tests/data/BidiCharacterTest.txt"], work)
    data = work / "data/ucd"
    data.mkdir(parents=True)
    (work / "src/char_data").mkdir(parents=True)
    for name in ("UnicodeData.txt", "BidiBrackets.txt", "ReadMe.txt"):
        shutil.copyfile(CACHE / ("ucd-readme.txt" if name == "ReadMe.txt" else name), data / name)
    env = dict(os.environ, PATH=str(work), HOME=str(work), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-X", "utf8", "-W", "ignore::SyntaxWarning", "tools/generate.py"],
                   cwd=work, env=env, check=True)
    generated = (work / "src/char_data/tables.rs").read_bytes()
    if os.name == "nt":
        # The unmodified upstream generator uses native text-mode line endings.
        generated = generated.replace(b"\r\n", b"\n")
    return hashlib.sha256(generated).hexdigest()


def construct(sources, scratch, approved):
    for name, digest in approved["baseCrates"].items():
        prefix = f"{name}-0.37.0"
        archive = CACHE / (prefix + ".crate")
        if sha(archive) != digest:
            raise ValueError(f"Changed original crate {name}")
        with tarfile.open(archive) as contents:
            names = [m.name.removeprefix(prefix + "/") for m in contents if m.isfile()]
            take_files(contents, prefix, names, sources / name)
    with tarfile.open(CACHE / "unicode-bidi-0.3.18.crate") as dist, tarfile.open(CACHE / "unicode-bidi-source.tgz") as src:
        prefix = "unicode-bidi-0.3.18"
        names = {m.name.removeprefix(prefix + "/") for m in dist if m.isfile() and "/src/" in m.name}
        names.update(("AUTHORS", "COPYRIGHT", "LICENSE-MIT", "LICENSE-APACHE", "Cargo.toml.orig"))
        for name in names:
            original = "Cargo.toml" if name == "Cargo.toml.orig" else name
            with src.extractfile(f"unicode-bidi-{approved['unicodeBidiRevision']}/{original}") as a, dist.extractfile(f"{prefix}/{name}") as b:
                if a.read() != b.read():
                    raise ValueError(f"Original and published unicode-bidi source differ at {name}")
        take_files(dist, prefix, names, sources / "unicode-bidi")
        table = approved["reconstructedTableSha256"]
        if reproduce_table(src, scratch / "generator", "unicode-bidi-" + approved["unicodeBidiRevision"]) != table or sha(sources / "unicode-bidi/src/char_data/tables.rs") != table:
            raise ValueError("Original Unicode source data failed to reproduce the compiled table")
    shutil.copyfile(REVIEW.parent / "gui-unicode-bidi.toml", sources / "unicode-bidi/Cargo.toml")
    parts = re.split(rb"(?m)(?=^diff --git )", (CACHE / "pr-8828.diff").read_bytes())
    rust = b"".join(p for p in parts if re.match(rb"diff --git a/crates/(egui|epaint)/src/[\w/]+\.rs ", p))
    if hashlib.sha256(rust).hexdigest() != approved["appliedRustDiffSha256"]:
        raise ValueError("Selected upstream Rust diff changed")
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(scratch))
    subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "apply", "--no-index", "-p2", "-"], cwd=sources, input=rust, env=env, check=True)
    with (sources / "epaint/Cargo.toml").open("a", encoding="utf-8", newline="\n") as manifest:
        manifest.write('\n[dependencies.unicode-bidi]\npath = "../unicode-bidi"\nversion = "=0.3.18"\n'
                       'default-features = false\nfeatures = ["hardcoded-data", "std"]\n')


def prepare(fetch=False, registry=None):
    approved = profile()
    CACHE.mkdir(parents=True, exist_ok=True)
    BUILD_INPUTS.mkdir(parents=True, exist_ok=True)
    FONTS.mkdir(exist_ok=True)
    history = ROOT / "artifacts/rust/font-coverage"
    registry = registry or ROOT / "artifacts/rust/assessment-cache/registry"
    for name, original in approved["originals"].items():
        cached(name, original["url"], original["sha256"], [history / "upstream" / name], fetch, 10_000_000)
    for name, digest in approved["baseCrates"].items():
        basename = f"{name}-0.37.0.crate"
        cached(basename, f"https://static.crates.io/crates/{name}/{basename}", digest,
               (registry / "cache").glob("*/" + basename), fetch, 5_000_000)
    for name, asset in approved["fonts"].items():
        path = cached(name, asset["url"], asset["sha256"], [history / "inputs" / name], fetch, 20_000_000)
        if not (FONTS / name).exists():
            with tempfile.TemporaryDirectory(dir=FONTS) as work:
                fresh = Path(work) / name
                shutil.copyfile(path, fresh)
                fresh.replace(FONTS / name)
        if (FONTS / name).is_symlink() or sha(FONTS / name) != asset["sha256"]:
            raise ValueError(f"Changed extracted font {name}")
    for relative, digest in approved["noticeFiles"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"Changed reviewed notice {relative}")
    if not SOURCES.exists():
        with tempfile.TemporaryDirectory(dir=BUILD_INPUTS) as temporary:
            work = Path(temporary)
            sources = work / "sources"
            sources.mkdir()
            construct(sources, work, approved)
            for name, digest in approved["trees"].items():
                if tree_info(sources / name) != digest:
                    raise ValueError(f"Reconstructed source differs from the review for {name}")
            try:
                sources.rename(SOURCES)
            except OSError:
                if not SOURCES.is_dir():
                    raise
    return validate()


def validate():
    approved = profile()
    if SOURCES.is_symlink() or (hasattr(SOURCES, "is_junction") and SOURCES.is_junction()):
        raise ValueError("Linked GUI compiler source root")
    if {p.name for p in SOURCES.iterdir()} != set(approved["trees"]):
        raise ValueError("Private GUI source root differs from the reviewed package set")
    if FONTS.is_symlink() or (hasattr(FONTS, "is_junction") and FONTS.is_junction()):
        raise ValueError("Linked GUI font directory")
    for name, digest in approved["trees"].items():
        if tree_info(SOURCES / name) != digest:
            raise ValueError(f"Private GUI compiler input differs from review for {name}")
    for name, asset in approved["fonts"].items():
        if (FONTS / name).is_symlink() or sha(FONTS / name) != asset["sha256"]:
            raise ValueError(f"Changed GUI font before compilation: {name}")
    for relative, digest in approved["noticeFiles"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"Changed GUI notice before compilation: {relative}")
    return approved
