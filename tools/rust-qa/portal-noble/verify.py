"""Bind the four Ubuntu source archives and selected binary inputs to Ubuntu-signed indices."""
import gzip
import hashlib
import json
import lzma
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import re
import subprocess
import tempfile

from inputs import KEYRING, ORIGINALS, POOL, SIGNER, SOURCE, SOURCE_RELEASE, SOURCE_SNAPSHOT, VERSION, fetch, sha, snapshot_url


def signed_release(key, path):
    if sha(key) != KEYRING:
        raise ValueError("Unexpected Ubuntu archive keyring")
    with tempfile.TemporaryDirectory() as home:
        result = subprocess.run(["gpgv", "--homedir", home, "--status-fd", "1", "--keyring", str(key), str(path)],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not any(line.startswith("[GNUPG:] VALIDSIG " + SIGNER + " ") for line in result.stdout.splitlines()):
        raise ValueError("Unexpected Ubuntu release signer")
    text = path.read_text()
    if "Origin: Ubuntu\n" not in text or "Codename: noble\n" not in text:
        raise ValueError("The signed release does not describe Ubuntu Noble")
    rows = {}
    for line in text.split("\nSHA256:\n", 1)[1].splitlines():
        if not line.startswith(" "):
            break
        digest, size, name = line.split()
        rows[name] = (digest, int(size))
    return text, rows


def authenticate(aptroot, cache, download):
    key = aptroot / "usr/share/keyrings/ubuntu-archive-keyring.gpg"
    signed = fetch(snapshot_url(SOURCE_SNAPSHOT, "dists/noble-updates/InRelease"), cache / (SOURCE_RELEASE + ".InRelease"),
                   SOURCE_RELEASE, download, 126125)
    text, rows = signed_release(key, signed)
    if "Suite: noble-updates\n" not in text:
        raise ValueError("Expected the signed Noble Updates source index")
    entry = "main/source/Sources.xz"
    digest, size = rows[entry]
    index = fetch(snapshot_url(SOURCE_SNAPSHOT, "dists/noble-updates/" + entry), cache / (digest + ".xz"), digest, download, size)
    data = lzma.decompress(index.read_bytes()).decode()
    rows = [p for p in data.split("\n\n") if p.startswith("Package: " + SOURCE + "\n") and
            "\nVersion: " + VERSION + "\n" in p and "\nDirectory: " + POOL.rstrip("/") + "\n" in p]
    if len(rows) != 1:
        raise ValueError("The fixed Ubuntu source package is absent from this signed release")
    listed = dict((n, h) for h, _, n in re.findall(r"^ ([0-9a-f]{64}) (\d+) (\S+)$", rows[0], re.M))
    if listed != ORIGINALS:
        raise ValueError("Ubuntu-signed source archive identities differ")
    return dict(keyFingerprint=SIGNER, keyring=KEYRING, index=digest, release=sha(signed), snapshot=SOURCE_SNAPSHOT,
                date=re.search(r"^Date: (.+)$", text, re.M)[1], sourceVersion=VERSION)


def contents(path):
    if path.suffix == ".xz":
        return lzma.open(path, "rb")
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    if path.suffix == ".lz4":
        # Ubuntu runner indices normally use apt's lz4 storage format.
        if not Path("/usr/lib/apt/apt-helper").is_file():
            raise ValueError("The native apt-helper is needed for compressed Ubuntu cache files")
        return tempfile_decoded(path)
    return path.open("rb")


def tempfile_decoded(path):
    result = tempfile.TemporaryFile()
    try:
        subprocess.run(["/usr/lib/apt/apt-helper", "cat-file", str(path)], stdout=result, check=True)
        result.seek(0)
        return result
    except BaseException:
        result.close()
        raise


def signed_packages(root, arch, plan, output):
    lists = root / "var/lib/apt/lists"
    expected = {p["Filename"]: p["SHA256"] for p in plan}
    control = POOL + SOURCE + "_" + VERSION + "_" + arch + ".deb"
    wanted = {*expected, control}
    found = {}
    snapshots = {}
    signed = {}
    releases = sorted(lists.glob("*InRelease"), key=lambda p: ("noble-updates" not in p.name, p.name))
    for release in releases:
        if not re.search(r"_dists_noble(?:-updates|-security)?_InRelease$", release.name):
            continue
        # Discard unrelated configured repositories before checking the Ubuntu signature.
        if "Origin: Ubuntu\n" not in release.read_text():
            continue
        authenticated, rows = signed_release(root / "usr/share/keyrings/ubuntu-archive-keyring.gpg", release)
        issued = parsedate_to_datetime(re.search(r"^Date: (.+)$", authenticated, re.M)[1])
        snapshot = issued.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for component in ("main", "universe"):
            key = component + "/binary-" + arch + "/Packages"
            prefix = release.name.removesuffix("InRelease") + key.replace("/", "_")
            matches = [p for p in lists.glob(prefix + "*") if p.name in (prefix, prefix + ".lz4", prefix + ".gz", prefix + ".xz")]
            if len(matches) != 1:
                continue
            sha256 = hashlib.sha256()
            count = 0
            with contents(matches[0]) as source:
                block = bytearray()
                while chunk := source.read(256 * 1024):
                    sha256.update(chunk)
                    count += len(chunk)
                    block.extend(chunk)
                    records = block.split(b"\n\n")
                    block = records.pop()
                    for entry in records:
                        if b"\nFilename: " not in entry:
                            continue
                        name = entry.split(b"\nFilename: ", 1)[1].split(b"\n", 1)[0].decode()
                        if name in wanted:
                            digest = entry.split(b"\nSHA256: ", 1)[1].split(b"\n", 1)[0].decode()
                            found[name] = digest
                            snapshots[name] = snapshot
                if block.strip():
                    raise ValueError("Unterminated Ubuntu package index")
            if rows.get(key) != (sha256.hexdigest(), count):
                raise ValueError("Ubuntu binary index does not match its signed release")
            signed[matches[0].name] = {"sha256": sha256.hexdigest(), "release": sha(release)}
            if set(found) == wanted:
                break
        if set(found) == wanted:
            break
    if set(found) != wanted or any(found[n] != digest for n, digest in expected.items()):
        raise ValueError(f"The signed Noble indices do not cover the selected development/control packages: {sorted(wanted-set(found))}")
    record = dict(indices=signed, control=control, packages=found, snapshots=snapshots)
    (output / "apt-packages.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def check_control(osroot, aptroot, arch, cache, download, out):
    from prepare import guest
    signed = json.loads((out / "development/apt-packages.json").read_text())
    public = signed["control"]
    filename = Path(public).name
    digest = signed["packages"][public]
    installed = aptroot / "var/cache/apt/archives" / filename
    archive = installed if installed.is_file() and sha(installed) == digest else fetch(
        snapshot_url(signed["snapshots"][public], public), cache / filename, digest, download)
    dest = out / "distributed"
    dest.mkdir()
    cmd = guest(osroot, osroot / "usr", extra=["--ro-bind", str(archive), "/package.deb", "--bind", str(dest), "/dest", "--"])
    subprocess.run(cmd + ["dpkg-deb", "-x", "/package.deb", "/dest"], check=True)
    if subprocess.check_output(cmd + ["dpkg-deb", "-f", "/package.deb", "Version"], text=True).strip() != VERSION:
        raise ValueError("Wrong version in the authenticated control package")
    files = ("usr/libexec/xdg-document-portal", "usr/libexec/xdg-permission-store", "usr/share/doc/xdg-desktop-portal/copyright")
    actual = {p: sha(osroot / p) for p in files}
    if any(sha(dest / k) != v for k, v in actual.items()):
        raise ValueError("The actual installed service, permission store or license differs from the authenticated Ubuntu package")
    return dict(deb=filename, sha256=digest, contents=actual)
