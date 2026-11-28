"""Compare the two Cargo directory sources for the supplied original AccessKit archive."""
import argparse
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase

QA = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(QA), str(QA / "combined-profile")]
from sources import accesskit_source, prepare_registry, read, sha256, write
from gui.startup.vendor import verify_sources


def check(original):
    case = TestCase()
    review = read(accesskit_source.REVIEW)
    key = review["crate"]
    selected = {accesskit_source.KEY: review["archiveSha256"]}
    with TemporaryDirectory() as raw:
        work = Path(raw)
        cache = work / "original/cache/reviewed"
        cache.mkdir(parents=True)
        shutil.copyfile(original, cache / (key + ".crate"))
        stock, before = prepare_registry(work / "stock", [work / "original"], False, selected, jobs=1, stock=True)
        fixed, after = prepare_registry(work / "corrected", [work / "original"], False, selected, jobs=1)
        case.assertEqual(verify_sources(stock, selected, before), before)
        case.assertEqual(verify_sources(fixed, selected, after), after)
        upstream = read(stock / key / ".cargo-checksum.json")
        compiler = read(fixed / key / ".cargo-checksum.json")
        case.assertEqual(upstream["package"], compiler["package"])
        case.assertEqual(compiler["package"], sha256(original))
        case.assertEqual(upstream["files"].keys(), compiler["files"].keys())
        case.assertEqual(len(compiler["files"]), 28)
        changed = {p: {"before": digest, "after": compiler["files"][p]} for p, digest in upstream["files"].items()
                   if compiler["files"][p] != digest}
        case.assertEqual(changed, review["files"])
        case.assertEqual(before[key]["transformations"], [])
        case.assertEqual(after[key]["transformations"], [{"path": p, **change} for p, change in sorted(changed.items())])
        with case.assertRaisesRegex(ValueError, "compiler tree differs"):
            verify_sources(stock, selected, after)
        with case.assertRaisesRegex(ValueError, "compiler tree differs"):
            verify_sources(fixed, selected, before)
        # Even a self-consistent Cargo file manifest cannot authorize a third source change.
        extra = fixed / key / "src/lib.rs"
        with extra.open("ab") as stream:
            stream.write(b"\n")
        compiler["files"]["src/lib.rs"] = sha256(extra)
        write(fixed / key / ".cargo-checksum.json", compiler)
        with case.assertRaisesRegex(ValueError, "compiler tree differs"):
            verify_sources(fixed, selected, after)
        print("Verified the frozen original, both 28-file Cargo sources, the two changes and three rejection controls.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    check(parser.parse_args().archive)
