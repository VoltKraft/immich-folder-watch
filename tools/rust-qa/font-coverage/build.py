"""Construct a private font experiment from frozen original GUI sources and licensed fonts."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from inputs import ART, HERE, PINS, ROOT, sha, verify

RUST = ROOT / "artifacts/rust"
PATCHES = [
    ("#![forbid(unsafe_code)]", "#![forbid(unsafe_code)]\n\nmod font_probe;"),
    ("        creation.egui_ctx.set_fonts(fonts);",
     "        font_probe::register(&mut fonts);\n        creation.egui_ctx.set_fonts(fonts);"),
    ('filename: "Grüße – Sommer.jpg".to_owned(),', 'filename: font_probe::filename(),'),
    ("ui.text_edit_singleline(&mut model.filename)\n                .labelled_by(label.id);",
     "font_probe::filename_edit(ui, &mut model.filename, label.id);"),
]


def build(args):
    assets = verify(args.acquire)
    target = ART / ("build-target-bidi" if args.bidi_candidate else "build-target")
    target.mkdir(exist_ok=True)
    variant = "-bidi" if args.bidi_candidate else ""
    subject = ART / "subjects" / (args.target + variant)
    subject.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="project-", dir=ART) as scratch:
        project = Path(scratch)
        gui = project / "tools/rust-qa/gui"
        for name, digest in (PINS["sources"] | PINS["supportSources"]).items():
            source = ROOT / name
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_file() and sha(source) == digest:
                shutil.copyfile(source, destination)
            else:
                data = subprocess.check_output(["git", "show", f"{PINS['guiRevision']}:{name}"], cwd=ROOT)
                destination.write_bytes(data)
            if sha(destination) != digest:
                raise ValueError(f"Changed base input {name}")
        main = gui / "src/main.rs"
        original = main.read_text(encoding="utf-8")
        for before, after in PATCHES:
            if original.count(before) != 1:
                raise ValueError("Frozen supervisor instrumentation anchor changed")
            original = original.replace(before, after)
        main.write_text(original, encoding="utf-8", newline="\n")
        shutil.copyfile(HERE / "font_probe.rs", gui / "src/font_probe.rs")
        fonts = gui / "fonts"
        fonts.mkdir()
        for name in assets:
            shutil.copyfile(ART / "inputs" / name, fonts / name)
        frozen_qa = gui.parent
        subprocess.run([sys.executable, str(frozen_qa / "verify-gui-inputs.py")], check=True)
        env = dict(os.environ, CARGO_HOME=str(RUST / "assessment-cache"), CARGO_TARGET_DIR=str(target),
                   IFW_QA_FONT_DIR=str(project / "rust/assets/fonts"))
        cargo_env = dict(env)
        cargo_bin = "cargo"
        if os.name != "nt":
            cargo_env["PATH"] = str(RUST / "toolchain/bin") + os.pathsep + cargo_env["PATH"]
            cargo_bin = RUST / "toolchain/bin/cargo"
        profile = json.loads((project / "rust/audit/gui-profile.json").read_text(encoding="utf-8"))
        graph = project / "baseline-graph.json"
        subprocess.run([sys.executable, str(frozen_qa / "audit-graph.py"), str(gui / "Cargo.toml"),
                        args.target, str(graph), "--verify-unpacked"], env=cargo_env, check=True)
        if sha(graph) != profile["targetReportSha256"][args.target]:
            raise ValueError("Native dependency graph differs from the reviewed assessment")
        candidate = None
        if args.bidi_candidate:
            import bidi_candidate
            base_graphs = {triple: bidi_candidate.feature_graph(gui / "Cargo.toml", triple, cargo_env, cargo_bin)
                           for triple in sorted(profile["targetReportSha256"])}
            candidate = bidi_candidate.prepare(gui, args.acquire)
            candidate["lockedGraph"] = bidi_candidate.lock(gui, cargo_env, cargo_bin, base_graphs)
        if os.name == "nt":
            version = subprocess.check_output([sys.executable, str(frozen_qa / "check-toolchain.py"), args.target], text=True)
            subprocess.run(["cargo", "fmt", "--manifest-path", str(gui / "Cargo.toml"), "--", "--check"], env=env, check=True)
            subprocess.run(["cargo", "clippy", "--manifest-path", str(gui / "Cargo.toml"), "--frozen",
                            "--all-targets", "--", "-D", "warnings"], env=env, check=True)
            subprocess.run(["cargo", "build", "--manifest-path", str(gui / "Cargo.toml"), "--release", "--frozen"],
                           env=env, check=True)
            binary = target / "release/native-gui-assessment.exe"
        else:
            linux_builder = gui / "build.py"
            build_path = project / "artifacts/rust/gui-build"
            build_path.parent.mkdir(parents=True)
            build_path.symlink_to(target, target_is_directory=True)
            toolchain = RUST / "toolchain"
            version = subprocess.check_output([sys.executable, str(frozen_qa / "check-toolchain.py"), args.target,
                                               "--rustc", str(toolchain / "bin/rustc")], text=True)
            subprocess.run([str(toolchain / "bin/rustfmt"), "--check", "--edition", "2024", str(main)], check=True)
            command = [sys.executable, str(linux_builder), "--toolchain", str(toolchain),
                       "--registry", str(RUST / "assessment-cache/registry")]
            subprocess.run([*command, "--clippy"], check=True)
            subprocess.run(command, check=True)
            binary = target / "release/native-gui-assessment"
        subject.mkdir(exist_ok=True)
        shutil.copy2(binary, subject / binary.name)
        for name in ("noto-OFL.txt", "cjk-OFL.txt"):
            shutil.copyfile(fonts / name, subject / name)
        record = {"target": args.target, "compiler": version.strip(), "guiRevision": PINS["guiRevision"],
                  "graphSha256": sha(graph), "baseSources": PINS["sources"], "supportSources": PINS["supportSources"], "inputManifest": sha(HERE / "inputs.json"),
                  "builder": sha(HERE / "build.py"), "auditor": sha(HERE / "inputs.py"),
                  "probe": sha(gui / "src/font_probe.rs"), "mainWithProbe": sha(main),
                  "assets": assets, "binary": binary.name, "binarySha256": sha(binary)}
        if candidate is not None:
            record["bidiCandidate"] = candidate
            shutil.copytree(gui / "candidate-notices", subject / "candidate-notices", dirs_exist_ok=True)
        (subject / "subject.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(subject)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--acquire", action="store_true", help="fetch missing pinned public fonts and full licenses")
    parser.add_argument("--bidi-candidate", action="store_true", help="test the isolated pinned upstream caret patch")
    build(parser.parse_args())
