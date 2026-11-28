"""Bind selected source licenses, notices, assets and native input hashes to the combined graph."""
from collections import Counter
from pathlib import Path

from sources import HYPER_KEY, HYPER_ROOT, QA, ROOT, read, sha256, source_profile
import source_notices
import unix_adapter

# Exact alternatives in the reviewed GUI archives. Preserve cumulative terms and file-level additions.
GUI_BRANCH = {
    **dict.fromkeys(("MIT", "MIT OR Apache-2.0", "Apache-2.0 OR MIT", "MIT/Apache-2.0", "Apache-2.0/MIT",
                     "0BSD OR MIT OR Apache-2.0", "BSD-2-Clause OR Apache-2.0 OR MIT",
                     "MIT OR Apache-2.0 OR Zlib", "MIT OR Zlib OR Apache-2.0", "Zlib OR Apache-2.0 OR MIT",
                     "Unlicense OR MIT", "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT"), "MIT"),
    "Apache-2.0": "Apache-2.0", "Apache-2.0 OR GPL-2.0-only": "Apache-2.0",
    "Apache-2.0 AND MIT": "Apache-2.0 AND MIT", "BSD-3-Clause OR Apache-2.0": "BSD-3-Clause",
    "(MIT OR Apache-2.0) AND Unicode-3.0": "MIT AND Unicode-3.0", "ISC": "ISC",
    "BSL-1.0": "BSL-1.0", "Zlib": "Zlib",
}


def supplements(name):
    catalog = "rust/audit/notices/"
    if name in {"egui", "epaint", "eframe", "egui-winit", "egui-wgpu", "ecolor", "emath"}:
        return [catalog + "egui-MIT", catalog + "egui-Apache-2.0"]
    if name.startswith("accesskit"):
        return [catalog + filename for filename in ("accesskit-MIT", "accesskit-Apache-2.0", "accesskit-Chromium-BSD")]
    if name in {"unicode-general-category", "harfrust"}:
        return ["tools/rust-qa/legacy/licenses/Unicode-LICENSE.txt"]
    if name.startswith("vello_"):
        return [catalog + "tiny-skia-BSD"]
    return {"clipboard-win": [catalog + "clipboard-win-BSL-1.0"], "profiling": [catalog + "profiling-MIT"],
            "spirv": [catalog + "SPIRV-Headers", catalog + "rspirv-Apache-2.0"],
            "wayland-protocols-plasma": [catalog + "weston-1.5.0-COPYING"]}.get(name, [])


def inventory(rows, vendor, staged, text):
    prior = {}
    for spike in ("yaml", "storage", "realtime"):
        for sample in read(QA / spike / "inputs.json")["packages"]:
            key = sample["name"], sample["version"]
            prior.setdefault(key, []).append(sample)
    font_manifest = {f["path"]: f for f in read(ROOT / "rust/audit/gui-inputs.json")["files"]
                     if Path(f["path"]).suffix in {".ttf", ".otf"}}
    fonts = {Path(k).name: {"sha256": f["sha256"], "source": f["source"]} for k, f in font_manifest.items()}
    fonts.update({name: {"sha256": row["sha256"], "source": row["url"]} for name, row in text["fonts"].items()})
    if len(fonts) != 5:
        raise ValueError("The reviewed desktop profile must contain five explicit font inputs")
    for row in rows:
        name, version = row["name"], row["version"]
        prefix = name + "-" + version
        files = read(vendor / prefix / ".cargo-checksum.json")["files"] if row["source"] else None
        compiler_root = HYPER_ROOT if (name, version) == HYPER_KEY else source_profile.SOURCES / name
        originals = prior.get((name, version), [])
        selects = set()
        for sample in originals:
            if sample.get("archiveSha256", sample.get("archive_sha256")) != row["archiveSha256"]:
                raise ValueError(f"Unreviewed archive {prefix}")
            supplied = sample["notices"]
            if isinstance(supplied, list):
                supplied = {item["path"]: item["sha256"] for item in supplied}
            for path, checksum in supplied.items():
                actual = files.get(path) if files is not None else sha256(compiler_root / path)
                if actual != checksum or row["notices"].setdefault(path, checksum) != checksum:
                    raise ValueError(f"Changed source notice in {prefix}/{path}")
            selects.add(sample.get("selected", sample.get("license_selected")))
        if originals and len(selects) != 1:
            raise ValueError(f"Conflicting prior license selection in {prefix}")
        row["selected"] = next(iter(selects)) if selects else GUI_BRANCH[row["declared"]]
        row["supplementalNotices"] = {path: sha256(ROOT / path) for path in supplements(name)}
        if not row["notices"] and not row["supplementalNotices"]:
            raise ValueError(f"Missing original or supplemental notice for {prefix}")
        if name in text["trees"]:
            row["compilerTree"] = text["trees"][name]
        else:
            row["originalCrate"] = f"https://static.crates.io/crates/{name}/{prefix}.crate"
            row["compilerTree"] = staged[prefix]
        if prefix == unix_adapter.CRATE:
            row["registryCorrection"] = unix_adapter.correction(row["compilerTree"], row["supplementalNotices"])
        for field in ("native", "shaders", "fonts"):
            row[field] = {p: files[p] if files is not None else sha256(compiler_root / p) for p in row[field]}
        if row["fonts"]:
            raise ValueError(f"Unexpected font payload in selected source {prefix}")
        for sample in originals:
            if "assets" in sample:
                row["reviewedArchiveAssets"] = sample["assets"]
        if name == "md-5":
            # The selector dispatches only LoongArch to its assembly module.
            # On both reviewed Linux targets the regular Rust compression module is compiled.
            selected = {"src/compress.rs": "8df5241a891c79944a2da03d1ade5a3065d8028d5ea2f959977726b8c00f68c0",
                        "src/compress/soft.rs": "6f1a40ee3c35d867cef9104f1e913b32547ef3d080f4a92dec513ef63f3af9c0"}
            vcs = read(vendor / prefix / ".cargo_vcs_info.json")
            if (version != "0.11.0" or any(files[path] != digest for path, digest in selected.items())
                    or vcs != {"git": {"sha1": "b5051e5a5e7dc86a6c27c1ec7a390744ebcfb97a"}, "path_in_vcs": "md5"}):
                raise ValueError("Changed md-5 compression dispatch or upstream revision requires review")
            row["compressionSourceByTarget"] = {target: {"files": selected, "upstream": vcs} for target in
                                                ("aarch64-unknown-linux-gnu", "x86_64-unknown-linux-gnu")}
    record = {"packages": rows, "fonts": fonts, "originalNoticeFiles": {
            **{"rust/" + f["path"]: f["sha256"] for f in read(ROOT / "rust/audit/gui-inputs.json")["files"]
               if Path(f["path"]).suffix not in {".ttf", ".otf"}},
            **text["noticeFiles"]}}
    source_notices.complete_inventory(record, [vendor.parent.parent / "cache" / vendor.name])
    adapter = next(row for row in rows if "registryCorrection" in row)
    for change in adapter["compilerTree"]["transformations"]:
        name = change["path"]
        original = adapter["sourceAttributions"][name]
        data = (vendor / unix_adapter.CRATE / name).read_bytes()
        if (original["sha256"] != change["before"] or source_notices.sha(data) != change["after"]
                or source_notices.ranges(data, ".rs") != original["ranges"]):
            raise ValueError(f"Changed source attribution in {unix_adapter.CRATE}/{name}")
    return record


def totals(record):
    rows = record["packages"]
    native = {name: sum(len(p[name]) for p in rows) for name in ("native", "shaders", "notices", "protocols")
              if name != "protocols"}
    native["protocols"] = sum(len(p.get("protocols", {})) for p in rows)
    native["sourceAttributionFiles"] = sum(len(p.get("sourceAttributions", {})) for p in rows)
    native["sourceAttributionBlocks"] = len({b["sha256"] for p in rows for f in p.get("sourceAttributions", {}).values()
                                            for b in f["ranges"]})
    by_name = Counter(p["name"] for p in rows)
    return {"activeExternalPackages": len(rows), "registryPackages": sum(bool(p["source"]) for p in rows),
            "buildScriptOrMacroPackages": sum(bool(p["buildScriptsAndMacros"]) for p in rows),
            "multiVersion": {name: sorted(p["version"] for p in rows if p["name"] == name)
                             for name, count in sorted(by_name.items()) if count > 1},
            "fonts": len(record["fonts"]), "supplementalNoticeFiles": len(record["originalNoticeFiles"]), **native}
