"""Build two private Documents daemons from the same unpacked Ubuntu source package."""
import hashlib
import json
import os
import re
import subprocess

from inputs import ART, HERE, ORIGINALS, ROOT, SOURCE, VERSION, sha
from prepare import guest

C_FILE = "document-portal/document-portal-fuse.c"
BEFORE = "aff36d56cc496e449047ad17d024139812b7160ef6d8f1e5b3eb22fbb5b76730"
AFTER = "a3cf626fa1e2971b9e3a7bfb0081c353c79603a75a30c5a2b8db82a36b432f92"
OPTIONS = ["--wrap-mode=nodownload", "--buildtype=release", "-Dpytest=disabled", "-Ddocbook-docs=disabled",
           "-Dlibportal=disabled", "-Dflatpak-interfaces=disabled", "-Dgeoclue=disabled", "-Dsystemd=disabled",
           "-Dinstalled-tests=false", "-Dman-pages=disabled", "-Dsandboxed-image-validation=true"]
LICENSES = {"COPYING": "dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551",
            "debian/copyright": "0c57db2b97ce8ec210905c7c1c415fcf184729fcf95d96be166fc9ceedf4b229",
            "libglnx/LICENSES/LGPL-2.1-or-later.txt": "dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551",
            "libglnx/LICENSES/LGPL-2.0-or-later.txt": "61778e80a2fd85955b626b29aa2bcf06144c714277bded65633e4a81479d9fb3"}
FUSE = {"include/fuse3/fuse_lowlevel.h": "665dded1d4e325c87ee16db6b059b37859cdf8bcb5a78aebb8ac377518390f3b",
        "include/fuse3/fuse_common.h": "41e5bda1724deda46a213ea237461323801d6256ec8f9756e19a0c73b20ea608",
        "share/doc/libfuse3-dev/copyright": "e3324ad43e309aae4f46501a20580d69fb3c69bf8f2fb0c7ae9e3d2408123a07"}


def inventory(src):
    return {p.relative_to(src).as_posix(): ("symlink " + os.readlink(p) if p.is_symlink() else sha(p))
            for p in sorted(src.rglob("*")) if p.is_file() or p.is_symlink()}


def pair(osroot, prepared, cache, out):
    src = out / "source"
    cmd = guest(osroot, prepared / "usr", extra=[
        "--ro-bind", str(prepared / "extra/usr"), "/extra-usr",
        "--ro-bind", str(cache), "/inputs", "--ro-bind", str(HERE), "/recipe",
        "--ro-bind", str(ROOT / "rust/crates/safe-fs/src"), "/safe-fs",
        "--ro-bind", str(ART / "toolchain"), "/toolchain", "--bind", str(out), "/work",
        "--setenv", "CFLAGS", "-D_GNU_SOURCE=1 -include sys/file.h",
        "--setenv", "SOURCE_DATE_EPOCH", "1790112000", "--chdir", "/work", "--"])
    def run(name, *args):
        with (out / (name + ".log")).open("wb") as log:
            subprocess.run(cmd + list(args), stdout=log, stderr=subprocess.STDOUT, check=True, timeout=170)
    run("unpack", "dpkg-source", "--no-check", "-x", "/inputs/" + SOURCE + "_" + VERSION + ".dsc", "/work/source")
    (src / "subprojects/libglnx").symlink_to("../libglnx")
    baseline = inventory(src)
    if sha(src / C_FILE) != BEFORE or any(baseline[k] != v for k, v in LICENSES.items()):
        raise ValueError("Unexpected fully quilt-patched Ubuntu source")
    for name, digest in FUSE.items():
        candidate = prepared / "extra/usr" / name
        if not candidate.is_file():
            candidate = osroot / "usr" / name
        if sha(candidate) != digest:
            raise ValueError("The selected FUSE header or license differs from the reviewed Ubuntu package")
    run("rustc", "/toolchain/bin/rustc", "-vV")
    run("safe-fs-build", "/toolchain/bin/rustc", "--crate-name", "safe_fs", "--edition=2024", "--crate-type=rlib",
        "-Dwarnings", "/safe-fs/lib.rs", "-o", "/work/libsafe_fs.rlib")
    run("reader-build", "/toolchain/bin/rustc", "--edition=2024", "-Dwarnings", "/recipe/read.rs", "--extern",
        "safe_fs=/work/libsafe_fs.rlib", "-o", "/work/reader")
    for name in ("unmodified", "backport"):
        if name == "backport":
            before_patch = inventory(src)
            run("flock-patch", "patch", "-d", "/work/source", "-p1", "--batch", "--fuzz=0", "-i", "/recipe/flock.patch")
            final = inventory(src)
            if [p for p in final if before_patch.get(p) != final[p]] != [C_FILE] or final.keys() != before_patch.keys() or final[C_FILE] != AFTER:
                raise ValueError("Backport must change exactly the reviewed Documents flock handler")
        run(name + "-configure", "meson", "setup", "/work/" + name, "/work/source", *OPTIONS)
        run(name + "-compile", "ninja", "-C", "/work/" + name, "-j4", "document-portal/xdg-document-portal")
        run(name + "-link", "ldd", "/work/" + name + "/document-portal/xdg-document-portal")
        if "not found" in (out / (name + "-link.log")).read_text():
            raise ValueError("A native Documents dependency failed to load")
    run("versions", "/bin/bash", "-eu", "-c",
        "cc --version; meson --version; ninja --version; dpkg-source --version; pkg-config --modversion fuse3 glib-2.0 gio-2.0 json-glib-1.0")
    runtime = guest(osroot, osroot / "usr", extra=["--ro-bind", str(out), "/work", "--"])
    linked = subprocess.check_output(runtime + ["ldd", "/work/backport/document-portal/xdg-document-portal"], text=True)
    (out / "runtime-link.log").write_text(linked)
    if "not found" in linked:
        raise ValueError("Noble runtime library unavailable")
    names = re.findall(r"(?:=> )?(/[^\s]+) \(0x[0-9a-f]+\)", linked)
    sums = subprocess.check_output(runtime + ["sha256sum", *names], text=True)
    libraries = {name: digest for digest, name in (line.split() for line in sums.splitlines())}
    return dict(originalSource=baseline[C_FILE], patchedSource=AFTER, upstreamHunk=sha(HERE / "flock.patch"),
                sourceLicenses=LICENSES, fuseBuildInputs=FUSE, runtimeLibraries=libraries,
                distroSource=ORIGINALS, patchSeries=(src / "debian/patches/series").read_text().splitlines(),
                rustSafeFs={p.name: sha(p) for p in sorted((ROOT / "rust/crates/safe-fs/src").glob("*.rs"))},
                reader=sha(out / "reader"), binaries={n: sha(out / n / "document-portal/xdg-document-portal") for n in ("unmodified", "backport")},
                sourceManifestSha256=hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest())
