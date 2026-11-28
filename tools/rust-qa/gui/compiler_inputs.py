"""Verify native Cargo compiler units against the audited GUI package and feature choices."""
import json
from pathlib import Path
from urllib.parse import unquote


def verify_gui_units(log, expected):
    units = [json.loads(line) for line in log.read_text().splitlines()]
    features = {}
    local = {"native-gui-assessment": "tools/rust-qa/gui", "ifw-yaml-assessment": "tools/rust-qa/yaml",
             "desktop-lifecycle": "rust/crates/desktop-lifecycle",
             **{name: "tools/rust-qa/gui/artifacts/text/" + name for name in ("egui", "epaint", "unicode-bidi")}}
    for item in units:
        if item["reason"] != "compiler-artifact":
            continue
        source, identity = item["package_id"].rsplit("#", 1)
        name, version = (identity.split("@", 1) if "@" in identity else
                         (Path(unquote(source)).name, identity))
        manifest = Path(item["manifest_path"])
        if name in local:
            directory = Path("/project") / local[name]
            correct = source.startswith("path+file:")
        else:
            directory = Path("/vendor") / (name + "-" + version)
            correct = source == "registry+https://github.com/rust-lang/crates.io-index"
        if not correct or manifest != directory / "Cargo.toml":
            raise ValueError(f"Unexpected compiler source for {name} {version}")
        features.setdefault(name + " v" + version, set()).add(tuple(sorted(item["features"])))
    app = [i for i in units if i.get("executable") == "/build/release/native-gui-assessment"]
    if (not units or units[-1] != {"reason": "build-finished", "success": True} or len(app) != 1
            or {k: sorted(v) for k, v in features.items()} != {k: sorted(map(tuple, v)) for k, v in expected.items()}
            or app[0]["target"]["src_path"] != "/project/tools/rust-qa/gui/src/main.rs"):
        raise ValueError("The linked native application and its dependency graph differ from the qualified inputs")
    return sum(item["reason"] == "compiler-artifact" for item in units)
