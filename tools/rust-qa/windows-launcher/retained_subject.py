"""Bind a retained launch to the paired Windows build and its local eframe compiler unit."""
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
WARM = HERE.parent / "windows-warm-window"


def select(target, canonical_exe, canonical, graph_path, sha):
    subjects = runpy.run_path(str(WARM / "inputs.py"), run_name="ifw_launcher_retained_inputs")["subjects"]
    api, cold, warm, directory, paired = subjects(target)
    report = directory / "build.json"
    record = json.loads(report.read_bytes())
    pins = json.loads((WARM / "eframe-source.json").read_bytes())
    graph = json.loads(graph_path.read_bytes())
    if (cold != canonical_exe or warm == cold or record["binary"] == record["baseline"]
            or paired["revision"] != canonical["source"] or paired["target"] != target
            or paired["baseline"] != canonical["binarySha256"] or paired["buildReceipt"] != sha(report)
            or paired["binary"] != record["binary"] or paired["baseline"] != record["baseline"]
            or graph["target"] != target or sha(graph_path) != record["canonicalGraph"]
            or record["canonicalGraph"] != canonical["graphSha256"]
            or record["canonicalLock"] != canonical["lockSha256"] or graph["lockSha256"] != record["canonicalLock"]
            or record["canonicalLock"] != pins["canonicalLockSha256"] or record["lock"] != pins["retainedLockSha256"]
            or record["eframeSource"]["pins"] != pins):
        raise ValueError("The retained GUI, canonical GUI, graph and source override must belong to one paired build")
    packages = graph["packages"]
    eframe, = [p for p in packages if (p["name"], p["version"]) == ("eframe", "0.37.0")]
    unit = record["eframeUnit"]
    staged = directory / "project/tools/rust-qa/gui"
    crate = "artifacts/retained/eframe"
    compiled = {p.name: sha(p) for p in [*sorted((staged / "src").glob("*.rs")), staged / "src/tray-icon.argb"]}
    if (record["compilerInputs"] != compiled or sha(staged / "Cargo.toml") != pins["retainedManifestSha256"]
            or sha(staged / "Cargo.lock") != record["lock"] or unit["manifest"] != crate + "/Cargo.toml"
            or unit["crateRoot"] != crate + "/src/lib.rs" or eframe["archiveSha256"] != pins["archiveSha256"]
            or eframe["featureSets"] != [unit["features"]]
            or record["selectedFeatureRows"] != sum(len(p["featureSets"]) for p in packages)):
        raise ValueError("The retained compiler sources or selected eframe features differ from the native build")
    build = (directory / "build").resolve()
    outputs = unit["outputs"]
    if not any(name.endswith(".rlib") for name in outputs):
        raise ValueError("The retained eframe library is missing")
    for name, digest in outputs.items():
        path = (build / name).resolve()
        if not path.is_relative_to(build) or path.relative_to(build).as_posix() != name or sha(path) != digest:
            raise ValueError("The retained eframe compiler output changed")
    root = HERE.parents[2]
    base_fonts = {p.name: sha(p) for p in sorted((root / "rust/assets/fonts").glob("*.ttf"))}
    fallbacks = {name: asset["sha256"] for name, asset in canonical["fallbackFonts"].items()}
    if not base_fonts or not fallbacks or record["baseFonts"] != base_fonts or record["fallbackFonts"] != fallbacks:
        raise ValueError("The retained font inputs differ from the reviewed native GUI")
    evidence = {**paired, "canonicalGraph": record["canonicalGraph"], "lock": record["lock"],
                "selectedFeatureRows": record["selectedFeatureRows"], "compilerEvidence": record["compilerEvidence"],
                "eframeUnit": unit,
                "eframeSource": record["eframeSource"], "compilerInputs": compiled, "variantInputs": record["variantInputs"],
                "baseFonts": record["baseFonts"], "fallbackFonts": record["fallbackFonts"]}
    return api, warm, evidence
