"""Reconstruct the verified CPU renderer and replay the three native desktop samples offline."""
import argparse
import json
from pathlib import Path

import fixture_build
from evidence import check


def verify(cpu):
    out = cpu / "handoff"
    record = fixture_build.read(out / "result.json")
    build = fixture_build.read(cpu / "cpu-build.json")
    # A finished CPU build suffices even if a separate resource measurement failed later.
    base = dict(build, cpuBuild=fixture_build.sha(cpu / "cpu-build.json"), buildReceipt=build["ordinaryBuild"],
                pairedBinary=build["ordinaryBinary"], binary=build["application"]["sha256"])
    fixture_build.cpu_build.verify(cpu, base)
    fixture_build.verify(cpu, record)
    from inputs import recorder
    raw = {n: fixture_build.sha(out / n) for n in ("subject.log", "presents.log", "present-build.log")}
    if (record["status"] != "passed" or raw != record["raw"] or fixture_build.sha(out / "present.exe") != record["presentObserver"]
            or recorder.pe_machine(out / "present.exe") != 0x8664
            or fixture_build.observer_sources(record["revision"]) != record["sources"]):
        raise ValueError("Incomplete or unrelated original observation, source revision or native ETW helper")
    observed = check(out, record)
    if observed != record["verified"]:
        raise ValueError("Detached native readback disagrees with the retained result")
    return observed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpu_paint", type=Path)
    print(json.dumps(verify(parser.parse_args().cpu_paint.resolve()), indent=2))
