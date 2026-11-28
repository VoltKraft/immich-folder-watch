"""Verify the reviewed fonts and supplemental notices used by the desktop assessment."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from urllib.request import HTTPRedirectHandler, build_opener


RUST = Path(__file__).resolve().parents[2] / "rust"
MAX_BYTES = 2 * 1024 * 1024
WESTON_RELEASE = "https://wayland.freedesktop.org/releases/weston-1.5.0.tar.xz"


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
        archive = url == WESTON_RELEASE and record.get("archiveMember") == "weston-1.5.0/COPYING"
        immutable_git = re.fullmatch(r"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/[0-9a-f]{40}/[\w./-]+", url)
        if (destination.parent not in (RUST / "assets/fonts", RUST / "audit/notices")
                or destination in destinations or not re.fullmatch("[a-f0-9]{64}", digest)
                or not (immutable_git or archive)
                or (archive and not re.fullmatch("[a-f0-9]{64}", record["archiveSha256"]))):
            raise ValueError(f"Unexpected GUI input declaration: {record['path']}")
        destinations.add(destination)
        if fetch and not destination.exists():
            with build_opener(NoRedirect()).open(url, timeout=30) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError(f"GUI input exceeds its download limit: {record['path']}")
            if archive:
                if hashlib.sha256(data).hexdigest() != record["archiveSha256"]:
                    raise ValueError("Unexpected Weston release archive")
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as release:
                    member = release.getmember(record["archiveMember"])
                    if not member.isfile() or member.size > MAX_BYTES:
                        raise ValueError("Unexpected Weston notice member")
                    with release.extractfile(member) as notice:
                        data = notice.read()
            if hashlib.sha256(data).hexdigest() != digest:
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
