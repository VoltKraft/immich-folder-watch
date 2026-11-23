"""Reconstruct the native Plasma guest from Ubuntu's reviewed QA archives."""

import argparse
import concurrent.futures
import csv
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from audit import native_architecture, sha

HERE = Path(__file__).resolve().parent
ART = HERE.parents[2] / "artifacts/rust/plasma"
sys.path.insert(0, str(HERE.parent / "portal-noble"))
from inputs import fetch, snapshot_url


def namespace():
    return ["bwrap", "--unshare-all", "--uid", "0", "--gid", "0", "--die-with-parent", "--new-session",
            "--clearenv", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--setenv", "HOME", "/tmp", "--setenv", "PATH", "/usr/sbin:/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8"]


def unpack_base(base, dest):
    cmd = namespace() + ["--ro-bind", "/usr", "/usr"]
    for name in ("bin", "sbin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            cmd += ["--symlink", os.readlink(path), "/" + name]
        elif path.is_dir():
            cmd += ["--ro-bind", str(path), "/" + name]
    subprocess.run(cmd + ["--ro-bind", str(base), "/ubuntu-base.tar.gz", "--bind", str(dest), "/guest", "--",
                          "tar", "--no-same-owner", "--no-same-permissions", "--exclude=./dev/*", "--exclude=dev/*",
                          "-xzf", "/ubuntu-base.tar.gz", "-C", "/guest"], check=True)


def prepare(output, cache, acquire):
    arch = native_architecture()
    review = json.loads((HERE / f"ubuntu-{arch}.json").read_text())
    table = HERE / f"ubuntu-{arch}.tsv"
    triplet = platform.machine() + "-linux-gnu"
    if sha(table) != review["packageTableSha256"]:
        raise ValueError("The frozen Ubuntu package table differs")
    with table.open() as source:
        entries = list(csv.DictReader(source, delimiter="\t"))
    if len(entries) != review["packages"] or any(e["Architecture"] not in (arch, "all") for e in entries):
        raise ValueError("Incomplete package review")
    if output.exists() or not output.is_relative_to(ART) or not cache.is_relative_to(ART):
        raise ValueError("Select a fresh destination and a private cache under artifacts/rust/plasma")
    cache.mkdir(exist_ok=True, parents=True)
    output.parent.mkdir(exist_ok=True, parents=True)
    base_file = review["baseFile"]
    base = fetch("https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/" + base_file,
                 cache / base_file, review["baseSha256"], acquire, review["baseBytes"])

    def archive(entry):
        pool = entry["Filename"]
        if not pool.startswith(("pool/main/", "pool/universe/")) or ".." in Path(pool).parts:
            raise ValueError("Expected an Ubuntu main/universe package")
        return fetch(snapshot_url(review["snapshot"], pool), cache / Path(pool).name, entry["SHA256"], acquire, int(entry["Size"]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as workers:
        files = list(workers.map(archive, entries))
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="staging-") as scratch:
        root = Path(scratch) / "root"
        root.mkdir()
        unpack_base(base, root)
        if sha(root / "usr/share/keyrings/ubuntu-archive-keyring.gpg") != review["archiveKeyringSha256"]:
            raise ValueError("Unexpected keyring in the Ubuntu Base image")
        names = Path(scratch) / "debs"
        names.write_text("".join(p.name + "\n" for p in files))
        # Package scripts are unnecessary for this desktop. Only unpack their authenticated data.
        command = ["bwrap", "--ro-bind", str(root), "/", *namespace()[1:], "--tmpfs", "/mnt",
                   "--ro-bind", str(cache), "/mnt/archives", "--ro-bind", str(names), "/mnt/debs",
                   "--bind", str(root), "/mnt/dest", "--", "bash", "-euo", "pipefail", "-c",
                   'while read -r p; do dpkg-deb --fsys-tarfile "/mnt/archives/$p" | '
                   'tar --keep-directory-symlink --no-same-owner --no-same-permissions -xf - -C /mnt/dest; done < /mnt/debs']
        subprocess.run(command, check=True)
        for entry in entries:
            notice = (root / "usr/share/doc" / entry["Package"] / "copyright").resolve(strict=True)
            if not notice.is_relative_to(root) or sha(notice) != entry["copyrightSha256"]:
                raise ValueError(f"Changed notice for {entry['Package']}")
        for relative, expected in review["keyPayloads"].items():
            if sha(root / relative) != expected:
                raise ValueError(f"Changed native Plasma payload {relative}")
        subprocess.run(["bwrap", "--bind", str(root), "/", *namespace()[1:], "--", "bash", "-euo", "pipefail", "-c",
                        'ldconfig\nglib-compile-schemas /usr/share/glib-2.0/schemas\n'
                        f'gio-querymodules /usr/lib/{triplet}/gio/modules\n'
                        f'/usr/lib/{triplet}/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders --update-cache\n'
                        'update-mime-database /usr/share/mime\nfc-cache -f'], check=True)
        root.rename(output)
    print(f"Prepared {output} from Ubuntu Base and {len(entries)} authenticated packages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path, default=ART / "cache")
    parser.add_argument("--acquire", action="store_true", help="download missing pinned archives from Ubuntu")
    args = parser.parse_args()
    destination = args.output or (ART / f"guest-{native_architecture()}")
    prepare(destination.resolve(), args.cache.resolve(), args.acquire)
