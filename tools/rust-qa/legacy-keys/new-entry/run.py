"""Build and run the isolated native Linux x64 insert study from cached storage inputs."""
import argparse
import fcntl
from contextlib import ExitStack, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ART = ROOT / "artifacts/rust"
TARGET = "x86_64-unknown-linux-gnu"
RECEIPT = "2e88e22b9b885bd01bae29a9b0c8b82b75d67b28529a09d2884b32f9500e8b2d"
STORE = ROOT / "tools/rust-qa/storage"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


STUDY = ("NewEntryReadback.csproj", "Readback.cs", "insert.rs", "run.py", "verify.py")
MEMBERS = ("insensitive.db", "invariant-uppercase.tsv", "manifest.json", "sensitive.db")
DONORS, WORK = ART/"donors", ART/"work"
DIRFLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
PRIVATE = ["bwrap", "--unshare-user", "--unshare-pid", "--die-with-parent", "--new-session"]


@contextmanager
def directory(root, relative):
    """Walk only direct children of held Linux directory descriptors."""
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Expected a contained relative directory.")
    current = os.dup(root)
    try:
        for name in relative.parts:
            child = os.open(name, DIRFLAGS, dir_fd=current)
            os.close(current)
            current = child
        yield current
    finally:
        os.close(current)


def bounded_source(parent, name):
    # O_PATH inspects the inode before a device, FIFO or linked file can be read.
    if not name or name in (".", "..") or Path(name).name != name:
        raise ValueError("Expected a single input filename.")
    leaf = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        info = os.fstat(leaf)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 1024 * 1024:
            raise ValueError(f"Expected a small single-link regular input: {name}")
        with open(f"/proc/self/fd/{leaf}", "rb") as stream:
            data = stream.read(info.st_size + 1)
            after = os.fstat(stream.fileno())
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
        if (len(data) != info.st_size or identity(after) != identity(info)
                or identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity(info)):
            raise ValueError(f"Original changed while reading: {name}")
        return data, [hashlib.sha256(data).hexdigest(), *identity(info)]
    finally:
        os.close(leaf)


def capture(checkout, donor):
    blobs, records, directories = {}, {}, {}
    def identify(fd, path):
        identity = os.fstat(fd)
        directories[str(path)] = [identity.st_dev, identity.st_ino, identity.st_mtime_ns, identity.st_ctime_ns]
    def take(parent, name, target, expected=None):
        data, record = bounded_source(parent, name)
        if expected is not None and record[0] != expected:
            raise ValueError(f"Input digest differs: {target}")
        blobs[target], records[target] = data, record
        return data
    with directory(checkout, donor.relative_to(ROOT)) as root:
        identify(root, donor.relative_to(ROOT))
        receipt = json.loads(take(root, "evidence.json", DONORS/"evidence.json", RECEIPT))
        for writer in ("older", "current"):
            name = "writer-" + writer
            with directory(root, Path(name)) as handle:
                identify(handle, (donor/name).relative_to(ROOT))
                expected = receipt["writers"][writer]["filesSha256"]
                if set(os.listdir(handle)) != set(MEMBERS) or set(expected) != set(MEMBERS):
                    raise ValueError("Unexpected donor directory contents.")
                for file in MEMBERS:
                    take(handle, file, DONORS/name/file, expected[file])
    with directory(checkout, HERE.relative_to(ROOT)) as root:
        identify(root, HERE.relative_to(ROOT))
        for file in STUDY:
            take(root, file, HERE/file)
    return blobs, records, directories


def mount_record(path):
    escaped = str(path).replace("\\", "\\134").replace(" ", "\\040").replace("\t", "\\011").replace("\n", "\\012")
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ")
        fields = left.split()
        if fields[4] == escaped:
            return {"filesystem":right.split()[0], "access":fields[5].split(",")[0]}
    raise ValueError(f"Required private mount is missing: {path}")


TRACKED = ("src/ImmichFolderWatch.Core", "rust/crates/ifw-legacy", "rust/Cargo.toml", "Directory.Build.props", "Directory.Build.targets",
           "global.json", "NuGet.Config", "rust/toolchain-inputs.json", "tools/rust-qa/storage",
           "tools/rust-qa/legacy/InvariantUppercaseProfile.cs", "tools/rust-qa/legacy/casing",
           "tools/rust-qa/check-toolchain.py", "rust/tests/fixtures/legacy/linux/manifest.json",
           "packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml", "tools/read-flatpak-sdk.py",
           "tools/rust-qa/plasma/ubuntu-amd64.tsv")
ARCHIVES = {"rust.tar.xz":ART/"toolchain-inputs/rust-1.100.0-x86_64-unknown-linux-gnu.tar.xz",
            "sdk.tar.gz":ROOT/"artifacts/flatpak-local-2.11.2/dotnet-sdk.tar.gz",
            "icu.deb":ART/"portal-noble/development-01/packages/libicu74_74.2-1ubuntu3.1_amd64.deb"}


def check_sources(commit):
    subprocess.run(["git", "diff", "--quiet", commit, "--", *TRACKED], check=True)
    if subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "--", *TRACKED]):
        raise ValueError("Untracked first-party input.")


def git_snapshot():
    rev = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    check_sources(rev)
    archive = subprocess.check_output(["git", "archive", "--format=tar", rev, "--", *TRACKED])
    blobs = {ART/"source.tar":archive}
    with tarfile.open(fileobj=io.BytesIO(archive),mode="r:") as source:
        for member in source:
            if member.isdir():
                continue
            path = Path(member.name)
            if not member.isreg() or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unexpected committed study input.")
            with source.extractfile(member) as file:
                blobs[ROOT/path] = file.read()
    revision = dict(commit=rev, parentNetNamespace=os.stat("/proc/self/ns/net").st_ino, archiveSha256=hashlib.sha256(archive).hexdigest(),
                    trees={p:subprocess.check_output(["git", "rev-parse", rev+":"+p],text=True).strip() for p in TRACKED})
    blobs[ART/"revision.json"] = json.dumps(revision).encode()
    return rev, blobs


def verify_tool_inputs(sdk_version):
    # These pins come from the committed distro inputs mounted in this run.
    flatpak = ROOT/"packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml"
    sdk = json.loads(subprocess.check_output([sys.executable,"-B",ROOT/"tools/read-flatpak-sdk.py","--manifest",flatpak]))
    rust = json.loads((ROOT/"rust/toolchain-inputs.json").read_bytes())["targets"][TARGET]["rust"]["sha256"]
    icu = [line.split("\t") for line in (ROOT/"tools/rust-qa/plasma/ubuntu-amd64.tsv").read_text().splitlines()
           if line.startswith("libicu74\t")]
    if sdk["version"] != sdk_version or len(icu) != 1:
        raise ValueError("Expected the pinned Linux x64 SDK and ICU package.")
    expected = {"rust.tar.xz":("sha256",rust), "sdk.tar.gz":("sha512",sdk["sources"]["linux-x64"]["sha512"]),
                "icu.deb":("sha256",icu[0][5])}
    for name,(algorithm,wanted) in expected.items():
        with (ART/name).open("rb") as stream:
            if hashlib.file_digest(stream,algorithm).hexdigest() != wanted:
                raise ValueError(f"Tool archive digest differs: {name}")
    members = {}
    def compare(archive, selected):
        found = set()
        for member in archive:
            path = str(Path(member.name))
            if path in selected:
                if not member.isreg() or path in found:
                    raise ValueError("Unexpected tool archive member.")
                with archive.extractfile(member) as data:
                    value = hashlib.file_digest(data,"sha256").hexdigest()
                if value != sha(selected[path]):
                    raise ValueError(f"Installed binary differs from its archive: {path}")
                members[path] = value
                found.add(path)
        if found != selected.keys():
            raise ValueError("Missing a pinned tool binary.")
    files = ["dotnet", f"sdk/{sdk_version}/dotnet.dll", "shared/Microsoft.NETCore.App/10.0.12/System.Private.CoreLib.dll",
             "shared/Microsoft.NETCore.App/10.0.12/libcoreclr.so"]
    with tarfile.open(ART/"sdk.tar.gz",mode="r|gz") as package:
        compare(package,{f:ART/"sdk"/f for f in files})
    names = [f"libicu{x}.so.74.2" for x in ("data","i18n","uc")]
    icu_dir = ART/"icu74"
    if ({p.name for p in icu_dir.iterdir()} != set(names) | {n.removesuffix(".2") for n in names}
            or any((icu_dir/n).is_symlink() or os.readlink(icu_dir/n.removesuffix(".2")) != n for n in names)):
        raise ValueError("ICU loader inputs differ from the three versioned libraries and their links.")
    data = subprocess.check_output(["ar","p",ART/"icu.deb","data.tar.zst"])
    with tarfile.open(fileobj=io.BytesIO(data),mode="r|zst") as package:
        compare(package,{"usr/lib/x86_64-linux-gnu/"+n:ART/"icu74"/n for n in names})
    return {"archiveDigests":dict(expected), "installedMembersSha256":members}


def private_stage():
    from verify import PROFILES, verify
    sys.path.insert(0, str(STORE))
    from evidence import external_lock, target_graph, verify_sources
    out, corp = WORK, DONORS
    mounts = {str(p.relative_to(ROOT)):mount_record(p) for p in (ROOT, ART, WORK, DONORS, HERE, ART/"cargo-input", ART/"nuget-input")}
    for p, access in ((WORK, "rw"), (DONORS, "ro"), (HERE, "ro")):
        if mount_record(p) != {"filesystem":"tmpfs", "access":access}:
            raise ValueError("Execute the study through its private namespace driver.")
    for p in (ROOT, ART):
        if mount_record(p) != {"filesystem":"tmpfs", "access":"ro"}:
            raise ValueError("Expected a read-only reconstructed checkout.")
    if any(mount_record(ART/p)["access"] != "ro" for p in ("cargo-input", "nuget-input")):
        raise ValueError("Expected read-only package inputs.")
    for name in ("home", "cli", "config", "data", "cache", "tmp", "feed", "cases", "study-sources"):
        (out/name).mkdir(mode=0o700)
    for name in STUDY:
        shutil.copyfile(HERE/name, out/"study-sources"/name)
    (out/"new-entry-study.marker").write_text("ifw-rw02-new-entry-study-v1\n", encoding="ascii")
    rust_bin, dotnet = ART/"toolchain/bin", ART/"sdk/dotnet"
    cargo = out/"cargo-home"
    registry = ART/"cargo-input/registry"
    if any(p.is_symlink() for p in registry.rglob("*")):
        raise ValueError("The reviewed offline Cargo registry must contain regular files and directories.")
    shutil.copytree(registry, cargo/"registry", symlinks=True)
    if any(p.is_symlink() for p in (cargo/"registry").rglob("*")):
        raise ValueError("Linked member in the private registry copy.")
    sdk_spec = json.loads((ROOT/"global.json").read_bytes())["sdk"]["version"]
    reviewed = json.loads((STORE/"inputs.json").read_bytes())
    assert sha(STORE/"Cargo.lock") == reviewed["lock_sha256"]
    env = dict(PATH=os.pathsep.join([str(rust_bin), "/usr/bin", "/bin"]), LANG="C.UTF-8", HOME=str(out/"home"),
               TMPDIR=str(out/"tmp"), DOTNET_ROOT=str(dotnet.parent), DOTNET_CLI_HOME=str(out/"cli"),
               XDG_CONFIG_HOME=str(out/"config"), XDG_DATA_HOME=str(out/"data"), XDG_CACHE_HOME=str(out/"cache"),
               DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", DOTNET_NOLOGO="1", IFW_ORACLE_EXPECT_ARCH="x64",
               CARGO_HOME=str(cargo), CARGO_TARGET_DIR=str(out/"cargo-build"),
               NUGET_PACKAGES=str(ART/"nuget-input"), LIBSQLITE3_FLAGS=reviewed["sqlite"]["flags"],
               LIBSQLITE3_SYS_USE_PKG_CONFIG="0")
    def run(log, command, extra=None, ok=True):
        print(f"Running {log}", file=sys.stderr, flush=True)
        with (out/(log+".log")).open("wb") as stream:
            proc = subprocess.run(command, cwd=ROOT, env=env | (extra or {}), stdout=stream,
                                  stderr=subprocess.STDOUT, timeout=600, check=False)
        if ok != (proc.returncode == 0):
            print((out/(log+".log")).read_text(errors="replace")[-10000:], file=sys.stderr)
            raise RuntimeError(f"{log} returned {proc.returncode}.")

    shutil.copyfile(ART/"source.tar", out/"source.tar")
    revision = json.loads((ART/"revision.json").read_bytes())
    rev = revision["commit"]
    network = {"parent":revision["parentNetNamespace"], "worker":os.stat("/proc/self/ns/net").st_ino,
               "interfaces":[line.split(":",1)[0].strip() for line in Path("/proc/net/dev").read_text().splitlines()[2:]],
               "ipv4Routes":Path("/proc/net/route").read_text().splitlines()[1:]}
    if network["parent"] == network["worker"] or network["interfaces"] != ["lo"] or network["ipv4Routes"]:
        raise ValueError("Expected a separate offline network namespace with only loopback and no external route.")
    archives = verify_tool_inputs(sdk_spec)
    run("toolchain", [sys.executable, "-B", ROOT/"tools/rust-qa/check-toolchain.py", TARGET])
    run("sdk", [dotnet, "--version"])
    assert (out/"sdk.log").read_text().strip() == sdk_spec
    # Reuse the assessment's exact lock and bundled SQLite. rustc receives only
    # Cargo's four reported library artifacts, without changing a shipping manifest.
    if external_lock(STORE/"Cargo.lock") != {(p["name"],p["version"]):p["archive_sha256"] for p in reviewed["packages"]}:
        raise ValueError("Reviewed archives differ from the storage lockfile.")
    metadata_cmd = [rust_bin/"cargo", "metadata", "--manifest-path", STORE/"Cargo.toml", "--frozen", "--format-version", "1"]
    run("metadata", metadata_cmd)
    run("native-graph", [*metadata_cmd, "--filter-platform", TARGET])
    metadata = json.loads((out/"metadata.log").read_bytes())
    if target_graph(json.loads((out/"native-graph.log").read_bytes())) != reviewed["target_graphs"][TARGET]:
        raise ValueError("Resolved Rust dependency features differ.")
    counts = verify_sources(metadata, reviewed, cargo, out/"cargo-evidence")
    run("cargo", [rust_bin/"cargo", "build", "--manifest-path", STORE/"Cargo.toml", "--lib", "--release",
                  "--frozen", "--target", TARGET, "--message-format=json"])
    libs, search_dirs, compiled = {}, set(), set()
    for line in (out/"cargo.log").read_bytes().splitlines():
        if line.startswith(b"{"):
            msg = json.loads(line)
            if msg["reason"] == "compiler-artifact":
                if msg["package_id"].startswith("registry+"):
                    compiled.add(msg["package_id"].split("#", 1)[1])
                for filename in msg["filenames"]:
                    p = Path(filename)
                    if p.suffix == ".rlib":
                        search_dirs.add("dependency=" + str(p.parent))
                        if msg["target"]["name"] in ("ifw_legacy", "ifw_sqlite_assessment", "rusqlite", "serde_json"):
                            libs[msg["target"]["name"]] = p
            elif msg["reason"] == "build-script-executed":
                search_dirs.update(msg["linked_paths"])
    assert len(libs) == 4
    writer = out/"insert"
    command = [rust_bin/"rustc", HERE/"insert.rs", "--edition=2024", "-Dwarnings", "-O", "--target", TARGET, "-o", writer]
    for path in sorted(search_dirs):
        command += ["-L", path]
    for name, path in sorted(libs.items()):
        command += ["--extern", name+"="+str(path)]
    run("rustc", command)
    project = HERE/"NewEntryReadback.csproj"
    config = out/"feed/NuGet.Config"
    config.write_text('<configuration><packageSources><clear/><add key="offline" value="." /></packageSources></configuration>\n')
    build = ["--artifacts-path", out/"dotnet-build", "--disable-build-servers", "-m:1",
             "-p:UseSharedCompilation=false", "-p:RestoreDisableParallel=true", "-p:EnableWindowsTargeting=false", "-p:NuGetAudit=false"]
    run("restore", [dotnet, "restore", project, "--configfile", config, "--source", out/"feed", *build])
    run("build", [dotnet, "build", project, "--no-restore", "-c", "Release", *build])
    dll = out/"dotnet-build/bin/NewEntryReadback/release/NewEntryReadback.dll"
    for donor, bucket in zip(PROFILES, ("older", "current"), strict=True):
        for mode in ("sensitive", "insensitive"):
            for form in PROFILES:
                name = f"{donor}-{mode}-{form}"
                run("insert-"+name, [writer, corp/("writer-"+bucket), mode, form, out/"cases"/name])
    first = out/"cases"/"15.1.0-sensitive-15.1.0"
    before = sha(first/"inserted.db")
    run("refuse-existing", [writer, corp/"writer-older", "sensitive", PROFILES[0], first], ok=False)
    assert sha(first/"inserted.db") == before and "AlreadyExists" in (out/"refuse-existing.log").read_text()
    refused = out/"cases"/"unused"
    run("refuse-unknown-profile", [writer, corp/"writer-older", "insensitive", "unknown", refused], ok=False)
    assert not refused.exists() and "unqualified insertion profile" in (out/"refuse-unknown-profile.log").read_text()
    icu = ART/"icu74"
    for index, name in enumerate(PROFILES):
        profile_env = dict(LD_LIBRARY_PATH=str(icu), DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU="74.2") if index == 0 else {}
        run("csharp-"+name, [*PRIVATE, "--bind", "/", "/", "--ro-bind", out/"cases", out/"cases", "--proc", "/proc", "--dev", "/dev", "--", dotnet, "exec", "--fx-version", "10.0.12", "--roll-forward", "Disable",
                             dll, out/"cases", out/("reader-"+name)], profile_env)
    if verify_sources(metadata, reviewed, cargo, out/"cargo-evidence") != counts:
        raise ValueError("Cargo source verification differs after both native readers.")
    summary = verify(corp, out)
    host_hash = sha(dotnet)
    attested = json.loads((corp/"evidence.json").read_bytes())
    corelib = "shared/Microsoft.NETCore.App/10.0.12/System.Private.CoreLib.dll"
    if host_hash != attested["dotnetBinarySha256"] or summary["readerBuilds"][2] != archives["installedMembersSha256"][corelib]:
        raise ValueError("The native reader differs from its attested host or the archived runtime.")
    summary.update(source=rev, studySources={str((HERE/n).relative_to(ROOT)):sha(out/"study-sources"/n) for n in STUDY},
                   historicalReceipt=RECEIPT, privateMounts=mounts, privateNetwork=network, sqliteSourceId=reviewed["sqlite"]["source_id"],
                   cargoSources={"lockSha256":reviewed["lock_sha256"], "archiveFilesCompared":counts,
                                "verifiedBeforeAndAfter":True,"archiveCount":len(counts),"sourceFileCount":sum(counts.values()),"compiled":sorted(compiled),
                                "lockedTargetGraph":reviewed["target_graphs"][TARGET]},
                   rustcSha256=sha(rust_bin/"rustc"), rustLibraries={k:sha(v) for k,v in libs.items()},
                   rustWriterSha256=sha(writer), readerDllSha256=sha(dll), sdk=sdk_spec, dotnetHostSha256=host_hash,
                   olderIcu={p.name:sha(p) for p in sorted(icu.glob("libicu*.so.74.2"))},
                   readerReports={p:sha(out/("reader-"+p)/"result.json") for p in PROFILES},
                   sourceTrees=revision["trees"], sourceArchiveSha256=revision["archiveSha256"], toolArchives=archives)
    (out/"private-result.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    # Only these raw observations, original study sources and compiled subjects leave the namespace.
    selected = [*out.glob("*.log"), out/"private-result.json", out/"insert", out/"new-entry-study.marker", out/"source.tar",
                *[p for d in ("cases", "reader-15.1.0", "reader-17.0.0", "study-sources", "cargo-evidence")
                  for p in (out/d).rglob("*") if p.is_file()], dll, dll.parent/"ImmichFolderWatch.Core.dll"]
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
        for path in sorted(selected):
            archive.add(path, arcname=str(path.relative_to(out)), recursive=False)


def main():
    if not __debug__:
        raise SystemExit("Run with Python assertions enabled.")
    os.chdir(ROOT)
    os.umask(0o077)
    if sys.argv[1:] == ["--private-stage"]:
        private_stage()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dotnet", "icu74", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--donors", type=Path, default=ART/"casing-profile-verified-f538495")
    args = parser.parse_args()
    donor, out = args.donors.absolute(), args.output.absolute()
    if (out.parent != ART or not out.name or ".." in donor.parts or ART not in donor.parents
            or donor == out or out in donor.parents or donor in out.parents):
        raise ValueError("Expected independent synthetic donors and a new direct output child of artifacts/rust.")
    sdk = args.dotnet.absolute()
    if sdk.name != "dotnet":
        raise ValueError("Expected the cached SDK dotnet executable.")
    # Every package source is mounted read-only; only the new private cargo-home receives Cargo bookkeeping.
    roots = {"sdk":sdk.parent, "icu74":args.icu74.absolute(), "toolchain":ART/"toolchain",
             "cargo-input":ART/"storage-assessment/cargo-home", "nuget-input":ROOT/"artifacts/nuget-packages"}
    if any(".." in p.parts or p == donor or donor in p.parents or p in donor.parents or
           p == out or out in p.parents or p in out.parents for p in roots.values()):
        raise ValueError("Study inputs must be independent of the donor and fresh output.")
    with ExitStack() as stack:
        checkout = os.open(".", DIRFLAGS)
        stack.callback(os.close, checkout)
        area = stack.enter_context(directory(checkout, ART.relative_to(ROOT)))
        blobs, initial, identities = capture(checkout, donor)
        rev, source_blobs = git_snapshot()
        blobs.update(source_blobs)
        blobs.update({Path("/etc/passwd"):f"fixture:x:{os.getuid()}:{os.getgid()}:Synthetic:/tmp:/bin/false\n".encode(),
                      Path("/etc/group"):f"fixture:x:{os.getgid()}:\n".encode(),
                      Path("/etc/hosts"):b"127.0.0.1 localhost\n::1 localhost\n"})
        os.mkdir(out.name, 0o700, dir_fd=area)
        dest = stack.enter_context(directory(area, Path(out.name)))
        cmd = [*PRIVATE, "--unshare-net", "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
               "--symlink", "usr/lib64", "/lib64", "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
               "--symlink", "../usr/lib/os-release", "/etc/os-release", "--dev", "/dev", "--proc", "/proc",
               "--tmpfs", "/tmp", "--tmpfs", ROOT, "--tmpfs", ART, "--tmpfs", DONORS, "--dir", DONORS/"writer-older", "--dir", DONORS/"writer-current",
               "--tmpfs", WORK, "--tmpfs", HERE]
        fds = []
        for name, source in roots.items():
            fd = stack.enter_context(directory(checkout, source.relative_to(ROOT)))
            fds.append(fd)
            cmd += ["--ro-bind-fd", str(fd), ART/name]
        for name, source in ARCHIVES.items():
            with directory(checkout, source.parent.relative_to(ROOT)) as parent:
                fd = os.open(source.name, os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=parent)
            stack.callback(os.close, fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size < 384*1024*1024:
                raise ValueError("Expected a regular pinned distribution archive.")
            fds.append(fd)
            cmd += ["--ro-bind-fd", str(fd), ART/name]
        for path, data in blobs.items():
            fd = os.memfd_create("ifw-study-input", os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
            stack.callback(os.close, fd)
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(data)
            os.lseek(fd, 0, os.SEEK_SET)
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_SEAL|fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW)
            fds.append(fd)
            cmd += ["--ro-bind-data", str(fd), path]
        cmd += ["--remount-ro", DONORS, "--remount-ro", HERE, "--remount-ro", ART, "--remount-ro", ROOT, "--chdir", ROOT, "--", sys.executable, "-B", HERE/"run.py", "--private-stage"]
        def exclusive(parent, name):
            return os.open(name, os.O_RDWR|os.O_CLOEXEC|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(exclusive(dest, "evidence.tar"), "w+b") as raw, os.fdopen(exclusive(dest, "namespace.log"), "wb") as log:
            proc = subprocess.run(cmd, env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","HOME":"/tmp"}, pass_fds=tuple(fds),
                                  stdout=raw, stderr=log, timeout=600, check=False)
            if proc.returncode:
                raise RuntimeError(f"Private study exited {proc.returncode}. See {out / 'namespace.log'}.")
            if raw.tell() > 128*1024*1024:
                raise ValueError("Unexpected raw evidence size.")
            raw.seek(0)
            archive_hash = hashlib.file_digest(raw, "sha256").hexdigest()
            raw.seek(0)
            directories = {Path("."):dest}
            summary = None
            with tarfile.open(fileobj=raw, mode="r:") as archive:
                for member in archive:
                    path = Path(member.name)
                    if not member.isreg() or path.is_absolute() or ".." in path.parts or not path.name:
                        raise ValueError("Unexpected raw evidence member.")
                    parent = Path(".")
                    for component in path.parts[:-1]:
                        new = parent/component
                        if new not in directories:
                            os.mkdir(component, 0o700, dir_fd=directories[parent])
                            directories[new] = stack.enter_context(directory(directories[parent], Path(component)))
                        parent = new
                    with archive.extractfile(member) as source, os.fdopen(exclusive(directories[parent], path.name), "wb") as dst:
                        if path == Path("private-result.json"):
                            data = source.read()
                            summary = json.loads(data)
                            dst.write(data)
                        else:
                            shutil.copyfileobj(source, dst)
                        if path == Path("insert") and member.mode & 0o100:
                            os.fchmod(dst.fileno(), 0o700)
        if not os.path.samestat(os.fstat(dest), os.stat(out.name, dir_fd=area, follow_symlinks=False)):
            raise ValueError("Output directory changed.")
        check_sources(rev)
        if capture(checkout, donor)[1:] != (initial, identities):
            raise ValueError("An original or study source changed during the native trial.")
        if summary is None or summary["studySources"] != {str((HERE/n).relative_to(ROOT)):initial[HERE/n][0] for n in STUDY}:
            raise ValueError("Archived and executed study source identities differ.")
        summary.update(evidenceTarSha256=archive_hash, originalDirectories=identities, sealedInputFiles=len(blobs),
            originalDirectoryFields=["device","inode","mtimeNs","ctimeNs"], originalsBeforeAndAfter={
            str(path.relative_to(DONORS)):record for path,record in initial.items() if DONORS in path.parents},
            originalFileFields=["sha256","device","inode","size","mtimeNs","ctimeNs","links"])
        data = (json.dumps(summary, indent=2, sort_keys=True)+"\n").encode()
        with os.fdopen(exclusive(dest, "result.json"), "wb") as stream:
            stream.write(data)
        print(hashlib.sha256(data).hexdigest(), out/"result.json")


if __name__ == "__main__":
    main()
