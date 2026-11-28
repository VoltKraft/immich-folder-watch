"""Prepare the isolated, unmerged upstream caret experiment from verified original bytes."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import sys
import tempfile
import tomllib

from inputs import ART, ROOT, acquire_original, sha

HEAD = "e0bc7924dac211c5ff727d55922662ce371ec819"
BASE = "fc9d66dda742d722eedaa8684d23f86369cf8e5f"
SERVO = "580b9c6c68fdb689916017e61d5052be3ed349b5"
REQUIRED = {
    "pr-8828.diff": (f"https://github.com/ahmedhosnypro/egui/compare/{BASE}...{HEAD}.diff",
                     "6d849fed4a055ef4b9f7b198fb1d8f195d47f7c3e1ce2a1cc745953983ab569b"),
    "egui-LICENSE-MIT": (f"https://raw.githubusercontent.com/ahmedhosnypro/egui/{HEAD}/LICENSE-MIT",
                         "95ca92f5f8ea5231f1580b3a2a799e8260af3114b900e1def5355a7f44bcf60c"),
    "egui-LICENSE-APACHE": (f"https://raw.githubusercontent.com/ahmedhosnypro/egui/{HEAD}/LICENSE-APACHE",
                            "8173d5c29b4f956d532781d2b86e4e30f83e6b7878dce18c919451d6ba707c90"),
    "unicode-bidi-0.3.18.crate": ("https://static.crates.io/crates/unicode-bidi/unicode-bidi-0.3.18.crate",
                                 "5c1cb5db39152898a79168971543b1cb5020dff7fe43c8dc468b0885f5e29df5"),
    "unicode-bidi-source.tgz": (f"https://codeload.github.com/servo/unicode-bidi/tar.gz/{SERVO}",
                                "f720ab2f8acbda7ca47b09f8145afb9418119057eeba0a8aa13733d775c38020"),
    "UnicodeData.txt": ("https://www.unicode.org/Public/16.0.0/ucd/UnicodeData.txt",
                        "ff58e5823bd095166564a006e47d111130813dcf8bf234ef79fa51a870edb48f"),
    "BidiBrackets.txt": ("https://www.unicode.org/Public/16.0.0/ucd/BidiBrackets.txt",
                         "b8f32554c6f658821fb0ee742d21c5b1f2086b9bf13071fed04894b022f93d67"),
    "ucd-readme.txt": ("https://www.unicode.org/Public/16.0.0/ucd/ReadMe.txt",
                       "14cafa23788d3a20dd21d6b0cdcb8d6dab520781fcd9ad9392f3b88ea607e633"),
}

# The original feature declarations reference optional, unselected integrations.
# This path-only assessment builds the original Rust files with exactly these two features.
BIDI_MANIFEST = """[package]
name = "unicode-bidi"
version = "0.3.18"
edition = "2018"
license = "MIT OR Apache-2.0"
publish = false
[features]
default = []
hardcoded-data = []
std = []
flame_it = []
serde = []
smallvec = []
bench_it = []
unstable = []
"""

BASE_CRATES = {"egui": "bec9144f49b7a28b5f395d3147e325b4fe3e77ba686eac11d1bdf0a7da3f375f",
               "epaint": "97bac86ae3dde93fc3951e790951caea739ff39a6c89d909cdaf1d9278dbb1bd"}


def take_files(source, prefix, names, destination):
    for name in sorted(names):
        member = source.getmember(f"{prefix}/{name}")
        if not member.isfile() or ".." in Path(name).parts or Path(name).is_absolute():
            raise ValueError("Unexpected assessment source member")
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with source.extractfile(member) as data, path.open("xb") as output:
            shutil.copyfileobj(data, output)


def generated_table_digest(table, original):
    # The upstream generator writes in Python text mode. Hash the emitted Unicode
    # table in the source archive's LF encoding on both supported operating systems.
    digest = hashlib.sha256(table.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if digest != sha(original):
        raise ValueError("The published Bidi table differs from the independent Unicode 16 reconstruction")
    return digest


def reproduce_table(source, prefix, inputs, original):
    # A private directory contains every file the audited generator would otherwise fetch.
    with tempfile.TemporaryDirectory(dir=inputs) as scratch:
        work = Path(scratch)
        take_files(source, prefix, ["tools/generate.py", "tests/data/BidiTest.txt",
                                    "tests/data/BidiCharacterTest.txt"], work)
        (work / "src/char_data").mkdir(parents=True)
        data = work / "data/ucd"
        data.mkdir(parents=True)
        for name in ("UnicodeData.txt", "BidiBrackets.txt", "ReadMe.txt"):
            shutil.copyfile(inputs / ("ucd-readme.txt" if name == "ReadMe.txt" else name), data / name)
        env = dict(os.environ, PATH=str(work), HOME=str(work), PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([sys.executable, "-W", "ignore::SyntaxWarning", "tools/generate.py"],
                       cwd=work, env=env, check=True)
        return generated_table_digest(work / "src/char_data/tables.rs", original)


def prepare(gui, acquire):
    inputs = ART / "upstream"
    inputs.mkdir(exist_ok=True)
    for name, (url, digest) in REQUIRED.items():
        path = inputs / name
        if not path.is_file() and acquire:
            acquire_original(path, url, digest, 10_000_000)
        if sha(path) != digest:
            raise ValueError(f"Unexpected pinned source {name}")
    unicode_notice = gui.parent / "legacy/licenses/Unicode-LICENSE.txt"
    if sha(unicode_notice) != "e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96":
        raise ValueError("Missing verified Unicode data notice")

    overrides = gui / "overrides"
    overrides.mkdir()
    for name, pin in BASE_CRATES.items():
        matches = list((ROOT / "artifacts/rust/assessment-cache/registry/cache").glob(f"*/{name}-0.37.0.crate"))
        if len(matches) != 1 or sha(matches[0]) != pin:
            raise ValueError(f"Missing reviewed original {name} 0.37 archive")
        with tarfile.open(matches[0]) as archive:
            prefix = f"{name}-0.37.0"
            names = [m.name.removeprefix(prefix + "/") for m in archive if m.isfile()]
            take_files(archive, prefix, names, overrides / name)

    with tarfile.open(inputs / "unicode-bidi-0.3.18.crate") as dist, tarfile.open(inputs / "unicode-bidi-source.tgz") as src:
        prefix = "unicode-bidi-0.3.18"
        names = {m.name.removeprefix(prefix + "/") for m in dist if m.isfile() and "/src/" in m.name}
        names.update(("AUTHORS", "COPYRIGHT", "LICENSE-MIT", "LICENSE-APACHE", "Cargo.toml.orig"))
        for name in names:
            origin = "Cargo.toml" if name == "Cargo.toml.orig" else name
            expected = src.extractfile(f"unicode-bidi-{SERVO}/{origin}").read()
            if dist.extractfile(f"{prefix}/{name}").read() != expected:
                raise ValueError(f"Published source differs from upstream: {name}")
        take_files(dist, prefix, names, overrides / "unicode-bidi")
        table_digest = reproduce_table(src, f"unicode-bidi-{SERVO}", inputs,
                                       overrides / "unicode-bidi/src/char_data/tables.rs")
    (overrides / "unicode-bidi/Cargo.toml").write_text(BIDI_MANIFEST, encoding="utf-8", newline="\n")
    patch = (inputs / "pr-8828.diff").read_bytes()
    hunks = re.split(rb"(?m)(?=^diff --git )", patch)
    code = b"".join(h for h in hunks if re.match(rb"diff --git a/crates/(egui|epaint)/src/[\w/]+\.rs ", h))
    # Avoid resolving the parent repository. Only change copies of these two upstream crates.
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(gui))
    subprocess.run(["git", "apply", "--no-index", "-p2", "-"], input=code, cwd=overrides, env=env, check=True)
    if not (overrides / "epaint/src/text/caret.rs").is_file():
        raise ValueError("Upstream change did not apply")
    with (overrides / "epaint/Cargo.toml").open("a", encoding="utf-8", newline="\n") as manifest:
        manifest.write('\n[dependencies.unicode-bidi]\npath = "../unicode-bidi"\nversion = "=0.3.18"\n'
                       'default-features = false\nfeatures = ["hardcoded-data", "std"]\n')
    with (gui / "Cargo.toml").open("a", encoding="utf-8", newline="\n") as manifest:
        manifest.write('\n[patch.crates-io]\negui = { path = "overrides/egui" }\nepaint = { path = "overrides/epaint" }\n')
    licenses = gui / "candidate-notices"
    licenses.mkdir()
    for name in ("AUTHORS", "COPYRIGHT", "LICENSE-MIT", "LICENSE-APACHE"):
        shutil.copyfile(overrides / "unicode-bidi" / name, licenses / ("unicode-bidi-" + name))
    for name in ("egui-LICENSE-MIT", "egui-LICENSE-APACHE", "ucd-readme.txt"):
        shutil.copyfile(inputs / name, licenses / name)
    shutil.copyfile(unicode_notice, licenses / unicode_notice.name)
    return {"patchHead": HEAD, "patchBase": BASE, "originalCrates": BASE_CRATES, "recreatedUnicodeTable": table_digest,
            "inputs": {n: h for n, (_, h) in REQUIRED.items()},
            "appliedRustDiffSha256": hashlib.sha256(code).hexdigest(), "recipe": sha(Path(__file__)),
            "effectiveSources": {p.relative_to(overrides).as_posix(): sha(p) for p in sorted(overrides.rglob("*"))
                                 if p.is_file() and (p.suffix == ".rs" or p.name == "Cargo.toml")},
            "notices": {p.name: sha(p) for p in sorted(licenses.iterdir())}}


def feature_graph(manifest, target, env, cargo):
    command = [str(cargo), "tree", "--frozen", "--workspace", "--manifest-path", str(manifest), "--target", target,
               "--edges", "normal,build", "--prefix", "none", "--format", "{p}|{f}"]
    result = {}
    for line in subprocess.check_output(command, env=env, text=True).splitlines():
        if line == "[build-dependencies]":
            continue
        package, features = line.removesuffix(" (*)").split("|")
        name, version, *_ = package.split()
        result.setdefault(name + " " + version, set()).add(tuple(sorted(filter(None, features.split(",")))))
    return result


def lock(gui, env, cargo, base_graphs):
    path = gui / "Cargo.lock"
    before = tomllib.loads(path.read_text(encoding="utf-8"))["package"]
    subprocess.run([str(cargo), "metadata", "--offline", "--manifest-path", str(gui / "Cargo.toml"),
                    "--format-version", "1"], cwd=gui, env=env, stdout=subprocess.DEVNULL, check=True)
    after = tomllib.loads(path.read_text(encoding="utf-8"))["package"]
    def external(rows):
        return {(p["name"], p["version"], p["source"], p["checksum"]) for p in rows if "source" in p}
    diff = external(before) - external(after)
    if ({n: h for n, _, _, h in diff} != BASE_CRATES or external(after) - external(before)
            or {p["name"] for p in after if "source" not in p}
            != {"native-gui-assessment", "desktop-lifecycle", "epaint", "egui", "unicode-bidi"}):
        raise ValueError("Private compiled graph changed outside the audited inputs")
    inventories = {}
    for target, base in base_graphs.items():
        resolved = feature_graph(gui / "Cargo.toml", target, env, cargo)
        expected = dict(base, **{"unicode-bidi v0.3.18": {("hardcoded-data", "std")}})
        if resolved != expected:
            raise ValueError(f"Unreviewed package or feature change in {target}: "
                             f"{[key for key in set(expected) | set(resolved) if expected.get(key) != resolved.get(key)]}")
        record = {key: sorted(v) for key, v in sorted(resolved.items())}
        data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        inventories[target] = {"packages": len(record), "nativeFeatureSetsSha256": hashlib.sha256(data).hexdigest()}
    return {"sha256": sha(path), "inventories": inventories}
