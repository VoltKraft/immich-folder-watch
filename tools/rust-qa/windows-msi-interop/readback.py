"""Replay the installed WPF secondary and original Rust inventory from the native artifact."""
import argparse
import json
from pathlib import Path
from common import read, sha
from msi_evidence import verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output
    result = read(out / "result.json")
    files = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "result.json"}
    if result["status"] != "observed" or result["files"] != files or result["checks"] != verify(out, result):
        raise ValueError("The recorded installed secondary trial could not be independently verified")
    print(json.dumps(result["checks"], indent=2))
