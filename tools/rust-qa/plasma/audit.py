"""Record the verified Noble QA archives and exact license notices used by this guest."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive_indices(apt):
    """Verify every frozen pool path against an index named by an authenticated Ubuntu InRelease."""
    sys.path.insert(0, str(HERE.parent / "portal-noble"))
    from verify import signed_release
    review = json.loads((HERE / "ubuntu-amd64.json").read_text())
    table = HERE / "ubuntu-amd64.tsv"
    if sha(table) != review["packageTableSha256"]:
        raise ValueError("Changed package table")
    with table.open() as stream:
        wanted = {e["Filename"]: e for e in csv.DictReader(stream, delimiter="\t")}
    found = set()
    lists = apt / "var/lib/apt/lists"
    key = apt / "usr/share/keyrings/ubuntu-archive-keyring.gpg"
    for filename, digest in review["signedAptInputs"].items():
        if sha(lists / filename) != digest:
            raise ValueError(f"Changed archived index input {filename}")
        if not filename.endswith("_InRelease"):
            continue
        _, signed = signed_release(key, lists / filename)
        for component in ("main", "universe"):
            relative = component + "/binary-amd64/Packages"
            path = lists / (filename.removesuffix("InRelease") + relative.replace("/", "_"))
            if not path.exists():
                continue
            if (sha(path), path.stat().st_size) != signed[relative]:
                raise ValueError("The package index is not the one signed by Ubuntu")
            for paragraph in path.read_text().split("\n\n"):
                row = dict(l.split(": ", 1) for l in paragraph.splitlines() if l and not l[0].isspace() and ": " in l)
                pool = row.get("Filename")
                if pool in wanted:
                    if any(row[k] != wanted[pool][k] for k in ("Package", "Version", "Architecture", "Size", "SHA256")):
                        raise ValueError(f"Signed package metadata disagrees for {pool}")
                    found.add(pool)
    if set(wanted) != found or len(found) != review["packages"]:
        raise ValueError("Some package archives were not present in the signed Ubuntu indexes")
    print(f"Signed Ubuntu indexes confirm every field of all {len(found)} selected binary archives")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-indices", type=Path, help="original authenticated APT root with unpacked Noble indexes")
    parser.add_argument("--userspace", type=Path)
    parser.add_argument("--packages", type=Path, help="APT records authenticated against signed Noble indexes")
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.frozen_indices:
        return verify_archive_indices(args.frozen_indices)
    if not all((args.userspace, args.packages, args.archives, args.output)):
        parser.error("supply all four package/notice review paths or --frozen-indices")
    guest = args.userspace.resolve(strict=True)
    if guest == Path("/") or "VERSION_CODENAME=noble" not in (guest / "usr/lib/os-release").read_text().splitlines():
        raise ValueError("Expected a separate Ubuntu Noble QA userspace")
    entries = json.loads(args.packages.read_text())
    rows = []
    for name, row in sorted(entries.items()):
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", row["Package"]) or Path(row["Filename"]).name != name:
            raise ValueError("Invalid package record")
        archive = args.archives / name
        if archive.stat().st_size != int(row["Size"]) or sha(archive) != row["SHA256"]:
            raise ValueError(f"Package differs from the signed archive index: {name}")
        notice = (guest / "usr/share/doc" / row["Package"] / "copyright").resolve(strict=True)
        if not notice.is_relative_to(guest / "usr/share/doc"):
            raise ValueError("Package notice must resolve inside the reviewed guest")
        document = notice.read_text(encoding="utf-8", errors="replace")
        if len(document.strip()) < 80:
            raise ValueError(f"Incomplete package notice for {name}")
        rows.append({**row, "copyrightSha256": sha(notice),
                     "licenseFields": sorted(set(re.findall(r"^License:\s*([^\r\n]+)", document, re.MULTILINE)))})
    with args.output.open("x") as output:
        json.dump({"packages": rows}, output, indent=2)
        output.write("\n")
    print(f"Verified {len(rows)} package archives and distribution notices")


if __name__ == "__main__":
    main()
