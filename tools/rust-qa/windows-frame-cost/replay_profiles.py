"""Reconstruct the retained and frame-ready Windows inputs with the native Cargo resolver on Linux."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZipFile

import frame_ready_build as ready
from prepare import ROOT, warm


def replay(output, canonical):
    # Snapshot the retained state before prepare.stage adds diagnostic changes to its private libraries.
    retained = warm.stage(output / "retained", canonical=canonical)
    archive = output / "retained-source.zip"
    evidence = warm.eframe_source.source_bundle(retained, archive, canonical)
    env = ready.prepare.environment(output)
    graphs = {}
    for target in warm.TARGETS:
        rows = warm.feature_rows(retained / "Cargo.toml", target, env)
        canonical_env = env
        config = retained.parents[2] / ".cargo"
        if config.is_dir():
            canonical_env = {**env, "CARGO_HOME": str(config)}
        if rows != warm.feature_rows(canonical / "Cargo.toml", target, canonical_env):
            raise ValueError("The retained Windows feature selection differs from the ordinary GUI")
        graphs[target] = rows
    frame_dir = output / "frame"
    frame_dir.mkdir()
    gui, rows, diagnostic, pins = ready.stage(frame_dir, canonical=canonical)
    if archive.read_bytes() != (frame_dir / "ordinary-source.zip").read_bytes():
        raise ValueError("The independent reconstructions of the ordinary libraries differ")
    if set(rows) != set(graphs[ready.prepare.TARGET]) | {(ready.prepare.TIMING, "0.0.0", ())}:
        raise ValueError("Unexpected frame-ready Windows feature selections")
    with ZipFile(archive) as source:
        for key in ("pins", "winitPins"):
            library = evidence[key]
            if sha256(source.read(library["crate"] + ".crate")).hexdigest() != library["archiveSha256"]:
                raise ValueError("The original crate archive differs from the retained library receipt")
    return {"originals": warm.originals(canonical),
            "retained": {k: v for k, v in evidence["pins"].items() if k.endswith(("LockSha256", "ManifestSha256"))},
            "ordinarySource": evidence["archiveSha256"], "graphs": graphs,
            "diagnosticSource": diagnostic, "frameReadyMain": pins["files"]["src/main.rs"],
            "frameReadyGraph": rows, "frameReadyCompilerSources": ready.compiler_sources(gui)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--canonical", type=Path, default=warm.GUI)
    source.add_argument("--historical", action="store_true", help="reconstruct the pre-language GUI from its reviewed Git revision")
    args = parser.parse_args()
    root = ROOT / "artifacts/rust/windows-warm-window"
    root.mkdir(exist_ok=True)
    out = Path(mkdtemp(prefix="profile-replay-", dir=root))
    os.environ["CARGO_NET_OFFLINE"] = "true"
    print(out, flush=True)
    if args.historical:
        from gui.startup import qualify
        gui, _ = qualify.stage(out / "original")
    else:
        gui = args.canonical.resolve()
    report = replay(out, gui)
    (out / "profile.json").write_text(json.dumps(report, indent=2) + "\n")
