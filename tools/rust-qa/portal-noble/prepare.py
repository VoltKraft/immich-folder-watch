"""Extract APT-authenticated Noble development inputs into a private, sparse /usr."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import urllib.parse

from inputs import BASE, fetch, sha, snapshot_url

DEVELOPMENT = ("dpkg-dev", "patch", "gcc", "libc6-dev", "pkg-config", "gettext", "meson", "ninja-build",
               "libgdk-pixbuf-2.0-dev", "libfuse3-dev", "libglib2.0-dev", "libjson-glib-dev", "libpipewire-0.3-dev")


def guest(osroot, root, *, extra=()):
    args = ["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--clearenv",
            "--ro-bind", str(osroot / "usr"), "/noble-usr", "--ro-bind", str(root), "/usr",
            "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/run",
            "--dir", "/tmp/home", "--setenv", "HOME", "/tmp/home", "--setenv", "LANG", "C.UTF-8",
            "--setenv", "PATH", "/usr/sbin:/usr/bin:/bin", "--setenv", "PYTHONDONTWRITEBYTECODE", "1"]
    for name in ("bin", "lib", "lib64", "sbin"):
        source = osroot / name
        if source.is_symlink():
            args += ["--symlink", os.readlink(source), "/" + name]
    for name in ("alternatives", "ld.so.cache", "ld.so.conf", "ld.so.conf.d", "os-release", "debian_version",
                 "dpkg", "perl", "ssl/openssl.cnf"):
        path = osroot / "etc" / name
        if path.exists():
            args += ["--ro-bind", str(path), "/etc/" + name]
    return args + list(extra)


def package_plan(aptroot, runner):
    command = guest(aptroot, aptroot / "usr", extra=[
        "--ro-bind", str(aptroot / "etc/apt"), "/etc/apt",
        "--ro-bind", str(aptroot / "var/lib/apt/lists"), "/var/lib/apt/lists",
        "--ro-bind", str(aptroot / "var/lib/dpkg/status"), "/var/lib/dpkg/status",
        "--dir", "/var/cache/apt/archives", "--"])
    options = ["-o", "Debug::NoLocking=1", "-o", "Dir::Cache::pkgcache=/tmp/packages",
               "-o", "Dir::Cache::srcpkgcache=/tmp/sources", "-o", "APT::Get::AllowUnauthenticated=false"]
    plan = subprocess.check_output(command + ["apt-get", *options, "--yes", "--no-install-recommends",
                                               "--print-uris", "install", *DEVELOPMENT], text=True)
    (runner / "apt-plan.log").write_text(plan)
    entries = []
    for line in plan.splitlines():
        if not line.startswith("'"):
            continue
        url, _, size, _ = shlex.split(line)
        public = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        if "/pool/" not in public or not public.endswith(".deb"):
            raise ValueError("Expected an Ubuntu binary package")
        pool = "pool/" + public.split("/pool/", 1)[1]
        filename = Path(pool).name
        name, version, arch = filename[:-4].split("_")
        entries.append((pool, name, int(size)))
    origins = {}
    if entries:
        # apt-cache may return multiple pocket versions. The exact pool path binds the selected version and architecture.
        rows = subprocess.check_output(command + ["apt-cache", *options, "show", *(name for _, name, _ in entries)], text=True)
        for row in rows.split("\n\n"):
            fields = dict(l.split(": ", 1) for l in row.splitlines() if l and not l[0].isspace() and ": " in l)
            if "Filename" in fields:
                origins[fields["Filename"]] = fields
    selected = []
    for path, name, size in entries:
        data = origins[path]
        if data["Package"] != name or int(data["Size"]) != size or len(data["SHA256"]) != 64:
            raise ValueError("Unmatched APT package")
        selected.append({f: data[f] for f in ("Package", "Version", "Architecture", "Filename", "Size", "SHA256")})
    return selected


def merge(base, added, view, prefix=Path()):
    """Use the existing distribution's ordinary files read-only and overlay only extracted package paths."""
    view.mkdir()
    for name in sorted({p.name for p in base.iterdir()} | {p.name for p in added.iterdir()}):
        lower, upper, dest = base / name, added / name, view / name
        if upper.is_symlink():
            dest.symlink_to(os.readlink(upper))
        elif upper.is_dir() and lower.is_dir() and not lower.is_symlink():
            merge(lower, upper, dest, prefix / name)
        elif upper.exists():
            dest.symlink_to("/extra-usr/" + (prefix / name).as_posix())
        elif lower.is_symlink():
            dest.symlink_to(os.readlink(lower))
        else:
            dest.symlink_to("/noble-usr/" + (prefix / name).as_posix())


def observe_split_python(osroot, prepared, output):
    """Exercise the hosted package split using the byte-identical lower Python in a fresh local merged view."""
    lower, upper = osroot / "usr", prepared / "extra/usr"
    view = prepared / "usr/bin"
    name = os.readlink(lower / "bin/python3")
    if not re.fullmatch(r"python3\.\d+", name):
        raise ValueError("Expected a versioned Python executable in the Noble runtime")
    relative = "bin/" + name
    target = view / name
    module = "lib/python3/dist-packages/mesonbuild/mesonmain.py"
    if (view.is_symlink() or os.readlink(view / "python3") != name or os.readlink(target) != "/extra-usr/" + relative
            or not (upper / module).is_file() or (lower / module).exists()
            or sha(lower / relative) != sha(upper / relative)):
        raise ValueError("The local fixture requires identical Python executables and upper-layer-only Meson")
    # Only this generated link inside the fresh private compiler view changes. Both distributions stay read-only.
    target.unlink()
    target.symlink_to("/noble-usr/" + relative)
    cmd = guest(osroot, prepared / "usr", extra=["--ro-bind", str(upper), "/extra-usr", "--"])
    inspect = ("import importlib.util, json, os, sys; "
               "print(json.dumps(dict(prefix=sys.prefix, executable=os.readlink('/proc/self/exe'), "
               "searchPath=sys.path, mesonFound=importlib.util.find_spec('mesonbuild') is not None)))")
    before = json.loads(subprocess.check_output(cmd + ["/usr/bin/python3", "-c", inspect], text=True, timeout=15))
    result = subprocess.run(cmd + ["/usr/bin/meson", "--version"], capture_output=True, text=True, timeout=15)
    before.update(mesonExit=result.returncode, mesonError=result.stderr, interpreterSha256=sha(lower / relative))
    (output / "split-python-control.log").write_text(json.dumps(before, indent=2) + "\n")
    if (before["prefix"] != "/noble-usr" or before["executable"] != "/noble-usr/" + relative or before["mesonFound"]
            or result.returncode != 1 or "ModuleNotFoundError: No module named 'mesonbuild'" not in result.stderr):
        raise ValueError("The original namespace did not reproduce the hosted missing Meson module")
    return before


def prepare(osroot, aptroot, output, arch, download):
    from verify import signed_packages
    packages = package_plan(aptroot, output)
    signed = signed_packages(aptroot, arch, packages, output)
    cache = BASE / "cache/debs"
    cache.mkdir(parents=True, exist_ok=True)
    layer = output / "extra"
    layer.mkdir()
    (layer / "usr").mkdir()
    raw = output / "packages"
    raw.mkdir()
    def load(item):
        filename, digest = Path(item["Filename"]).name, item["SHA256"]
        for pool in ("archives", "compiler"):
            cached = aptroot / "var/cache/apt" / pool / filename
            if cached.is_file() and sha(cached) == digest:
                shutil.copyfile(cached, raw / filename)
                return
        url = snapshot_url(signed["snapshots"][item["Filename"]], item["Filename"])
        archive = fetch(url, cache / filename, digest, download, int(item["Size"]))
        shutil.copyfile(archive, raw / filename)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(load, packages))
    if packages:
        cmd = guest(osroot, osroot / "usr", extra=["--ro-bind", str(raw), "/packages",
                    "--bind", str(layer), "/dest", "--", "/bin/bash", "-euo", "pipefail", "-c",
                    'for p in /packages/*.deb; do dpkg-deb --fsys-tarfile "$p" | tar --no-same-owner --no-same-permissions -xf - -C /dest; done'])
        subprocess.run(cmd, check=True, timeout=150)
    view = output / "usr"
    merge(osroot / "usr", layer / "usr", view)
    names = sorted(set(DEVELOPMENT) | {p["Package"] for p in packages})
    inputs = ["/usr/share/doc/" + name + "/copyright" for name in names]
    sums = subprocess.check_output(guest(osroot, view, extra=["--ro-bind", str(layer / "usr"), "/extra-usr", "--",
                                   "sha256sum", *inputs]), text=True)
    notices = {path.split("/")[-2]: digest for digest, path in (row.split() for row in sums.splitlines())}
    (output / "package-notices.json").write_text(json.dumps(notices, indent=2) + "\n")
    (output / "build-packages.json").write_text(json.dumps(packages, indent=2) + "\n")
    return view
