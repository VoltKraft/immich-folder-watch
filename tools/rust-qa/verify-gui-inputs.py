"""Verify the reviewed fonts and supplemental notices used by the desktop assessment."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import HTTPRedirectHandler, build_opener


RUST = Path(__file__).resolve().parents[2] / "rust"
MAX_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify(fetch=False):
    records = json.loads((RUST / "audit/gui-inputs.json").read_text(encoding="utf-8"))["files"]
    destinations = set()
    for record in records:
        destination = (RUST / record["path"]).resolve()
        digest = record["sha256"]
        url = record["source"]
        if (destination.parent not in (RUST / "assets/fonts", RUST / "audit/notices")
                or destination in destinations or not re.fullmatch("[a-f0-9]{64}", digest)
                or not re.fullmatch(r"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/[0-9a-f]{40}/[\w./-]+", url)):
            raise ValueError(f"Unexpected GUI input declaration: {record['path']}")
        destinations.add(destination)
        if fetch and not destination.exists():
            with build_opener(NoRedirect()).open(url, timeout=30) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Unexpected upstream bytes: {record['path']}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(data)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError(f"GUI input hash mismatch: {record['path']}")
    print(f"Verified {len(records)} GUI inputs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-missing", action="store_true",
                        help="restore missing reviewed files from immutable source revisions")
    verify(parser.parse_args().fetch_missing)
