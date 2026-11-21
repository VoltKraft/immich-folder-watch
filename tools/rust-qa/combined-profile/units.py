"""Check the successful compiler's actual target and build-host units against Cargo's selected graph."""
from collections import defaultdict
import json
from pathlib import PurePosixPath
from urllib.parse import unquote

from sources import read, sha256, write


def compiler_units(output, target):
    features = read(output / (target + ".json"))["features"]
    compiled, units, libs = defaultdict(set), [], {}
    finished = False
    for line in (output / "build.log").read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        reason = item["reason"]
        if reason == "build-finished":
            finished = item["success"]
        if reason not in {"compiler-artifact", "build-script-executed"}:
            continue
        origin, identity = item["package_id"].rsplit("#", 1)
        if "@" in identity:
            name, version = identity.split("@", 1)
        else:
            name, version = PurePosixPath(unquote(origin)).name, identity
        key = f"{name} v{version}"
        if reason == "build-script-executed":
            if item["linked_libs"]:
                libs[key] = sorted(item["linked_libs"])
            continue
        group = tuple(sorted(item["features"]))
        compiled[key].add(group)
        filenames = [p.replace("\\", "/") for p in item["filenames"]]
        selected = {target if f"/{target}/release/" in path else "host" for path in filenames}
        units.append({"package": key, "targetName": item["target"]["name"], "kinds": sorted(item["target"]["kind"]),
                      "features": group, "compiledFor": sorted(selected)})
    if not finished or {key: sorted(sets) for key, sets in compiled.items()} != {
            key: sorted(tuple(group) for group in sets) for key, sets in features.items()}:
        raise ValueError("Actual native compiler features/packages differ from the normal/build tree")
    if "static=sqlite3" not in libs.get("libsqlite3-sys v0.40.0", []) or not any(
            name.startswith("static=ring_core_") for name in libs.get("ring v0.17.14", [])):
        raise ValueError("Missing the native SQLite or ring link directive")
    units.sort(key=lambda unit: (unit["package"], unit["targetName"], unit["features"], unit["kinds"]))
    write(output / "compiler-units.json", {"nativeTarget": target, "compiledPackages": len(compiled),
                                           "units": units, "nativeBuildDirectives": libs})
    return {"packages": len(compiled), "units": len(units), "reportSha256": sha256(output / "compiler-units.json")}
