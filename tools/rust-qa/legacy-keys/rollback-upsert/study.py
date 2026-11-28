"""Run the shipping C# rollback-upsert study on the attested, finalized Linux x64 Rust backups."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"new-entry"))
import run as base
from verify import PROFILES

ROOT, ART, WORK, DONORS = base.ROOT, base.ART, base.WORK, base.DONORS
PRIOR = ART/"new-entry-readback-f932674-offline-01"
ORIGINAL = ART/"casing-profile-verified-f538495"
PIN = "4cc86159873ef842dc8460e21f1f6dfe145b6c1d1cec231ddaec291aee5f58dd"
RAW_PIN = "1194dacc81f3abb99625276755bf2f38c9dfe2bf97ae169a2adf5063e12eeca4"
FILES = ("Rollback.cs","RollbackUpsert.csproj","check.py","study.py")
CASES = {f"{a}-{m}-{b}" for a in PROFILES for m in ("sensitive","insensitive") for b in PROFILES}
SDK = ROOT/"artifacts/flatpak-local-2.11.2/sdk"
ICU = ART/"casing-oracle-verified-e59a691/icu74"


def archived_file(directory, name):
    """Read a regular large archive member by its checked inode in a held directory."""
    if not name or Path(name).name != name or name in (".",".."):
        raise ValueError("Expected one archive member filename.")
    handle = os.open(name,os.O_PATH|os.O_NOFOLLOW,dir_fd=directory)
    try:
        info = os.fstat(handle)
        def identity(s):
            return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 32*1024*1024:
            raise ValueError("Expected a bounded single-link archive member.")
        with open(f"/proc/self/fd/{handle}","rb") as stream:
            data = stream.read(info.st_size+1)
            if len(data) != info.st_size or identity(os.fstat(stream.fileno())) != identity(info):
                raise ValueError("An original changed while it was read.")
        if identity(os.stat(name,dir_fd=directory,follow_symlinks=False)) != identity(info):
            raise ValueError("An original was replaced.")
        return data,[hashlib.sha256(data).hexdigest(),*identity(info)]
    finally:
        os.close(handle)


def originals(checkout):
    blobs, records = {}, {}
    # Keep every original attested export. Only the eight Rust cases and their
    # canonical provenance are exposed to the new native writer.
    with base.directory(checkout, PRIOR.relative_to(ROOT)) as prior:
        data,records["result.json"] = base.bounded_source(prior,"result.json")
        assert records["result.json"][0] == PIN
        receipt = json.loads(data)
        assert receipt["evidenceTarSha256"] == RAW_PIN and set(receipt["trials"]) == CASES
        blobs[DONORS/"result.json"] = data
        raw,records["evidence.tar"] = archived_file(prior,"evidence.tar")
        assert records["evidence.tar"][0] == RAW_PIN
        with base.directory(prior,Path("cases")) as case_root:
            assert set(os.listdir(case_root)) == CASES
            for name in CASES:
                with base.directory(case_root,Path(name)) as case:
                    assert set(os.listdir(case)) == {"inserted.db","receipt.json"}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for item in archive:
                path = Path(item.name)
                if not item.isreg() or path.is_absolute() or ".." in path.parts or item.name in records:
                    raise ValueError("Unexpected member in the original evidence.")
                with base.directory(prior,path.parent) as parent:
                    if item.size == 0:  # The prior native commands produced some empty success logs.
                        fd = os.open(path.name,os.O_PATH|os.O_NOFOLLOW,dir_fd=parent)
                        try:
                            s = os.fstat(fd)
                            assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size == 0
                            records[item.name] = [hashlib.sha256(b"").hexdigest(),s.st_dev,s.st_ino,0,s.st_mtime_ns,s.st_ctime_ns,1]
                        finally:
                            os.close(fd)
                        continue
                    actual,records[item.name] = archived_file(parent,path.name)
                with archive.extractfile(item) as original:
                    assert actual == original.read()
                if path.parts[0] == "cases":
                    name = path.parts[1]
                    assert name in CASES
                    if path.name == "inserted.db":
                        assert records[item.name][0] == receipt["trials"][name]["after"]
                    blobs[DONORS/Path(*path.parts[1:])] = actual
        assert len(records) == 162
    old, hashes, dirs = base.capture(checkout,ORIGINAL)
    for path,record in hashes.items():
        if base.HERE in path.parents:
            assert receipt["studySources"][str(path.relative_to(ROOT))] == record[0]
            blobs[path] = old[path]
        else:
            assert receipt["originalsBeforeAndAfter"][str(path.relative_to(base.DONORS))] == record
    assert dirs == receipt["originalDirectories"]
    with base.directory(checkout,HERE.relative_to(ROOT)) as folder:
        for name in FILES:
            blobs[HERE/name],records["study/"+name] = base.bounded_source(folder,name)
    return blobs,records


def private_stage():
    from check import verify
    for path, access in ((ROOT,"ro"),(ART,"ro"),(DONORS,"ro"),(HERE,"ro"),(base.HERE,"ro"),(WORK,"rw")):
        assert base.mount_record(path) == dict(filesystem="tmpfs",access=access)
    revision = json.loads((ART/"revision.json").read_bytes())
    network = dict(parent=revision["parentNetNamespace"],worker=os.stat("/proc/self/ns/net").st_ino,
                   interfaces=[l.split(":",1)[0].strip() for l in Path("/proc/net/dev").read_text().splitlines()[2:]],
                   ipv4Routes=Path("/proc/net/route").read_text().splitlines()[1:])
    assert network["parent"] != network["worker"] and network["interfaces"] == ["lo"] and not network["ipv4Routes"]
    prior = json.loads((DONORS/"result.json").read_bytes())
    assert base.sha(DONORS/"result.json") == PIN
    tools = base.verify_tool_inputs(json.loads((ROOT/"global.json").read_bytes())["sdk"]["version"])
    assert json.loads(json.dumps(tools)) == prior["toolArchives"]
    for name in ("home","tmp","cli","config","data","cache","feed"):
        (WORK/name).mkdir(mode=0o700)
    env = dict(PATH="/usr/bin:/bin",LANG="C.UTF-8",HOME=str(WORK/"home"),TMPDIR=str(WORK/"tmp"),
               DOTNET_ROOT=str(ART/"sdk"),DOTNET_CLI_HOME=str(WORK/"cli"),NUGET_PACKAGES=str(ART/"nuget-input"),
               XDG_CONFIG_HOME=str(WORK/"config"),XDG_DATA_HOME=str(WORK/"data"),XDG_CACHE_HOME=str(WORK/"cache"),
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",DOTNET_NOLOGO="1",DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_GENERATE_ASPNET_CERTIFICATE="false",IFW_ORACLE_EXPECT_ARCH="x64")
    def run(log, cmd, extra=None):
        with (WORK/(log+".log")).open("wb") as stdout:
            result = subprocess.run(cmd,env=env|(extra or {}),cwd=ROOT,stdout=stdout,stderr=subprocess.STDOUT,timeout=150)
        if result.returncode:
            print((WORK/(log+".log")).read_text(errors="replace")[-6000:],file=sys.stderr)
            raise ValueError(f"Failed phase: {log}")
    config = WORK/"feed/NuGet.Config"
    config.write_text('<configuration><packageSources><clear/><add key="offline" value="." /></packageSources></configuration>\n')
    assert base.mount_record(ART/"nuget-input")["access"] == "ro"
    dotnet = ART/"sdk/dotnet"
    run("sdk",[dotnet,"--version"])
    assert (WORK/"sdk.log").read_text().strip() == prior["sdk"] and base.sha(dotnet) == prior["dotnetHostSha256"]
    project = HERE/"RollbackUpsert.csproj"
    options = ["--artifacts-path",WORK/"dotnet-build","--disable-build-servers","-m:1","-p:UseSharedCompilation=false",
               "-p:RestoreDisableParallel=true","-p:EnableWindowsTargeting=false","-p:NuGetAudit=false"]
    run("restore",[dotnet,"restore",project,"--configfile",config,"--source",WORK/"feed",*options])
    run("build",[dotnet,"build",project,"-c","Release","--no-restore",*options])
    dll = WORK/"dotnet-build/bin/RollbackUpsert/release/RollbackUpsert.dll"
    for action in ("write","read"):
        cmd = []
        if action == "read":
            cmd = [*base.PRIVATE,"--bind","/","/","--proc","/proc","--dev","/dev"]
            for writer in PROFILES:
                snapshots = WORK/("write-"+writer)
                cmd += ["--ro-bind",snapshots,snapshots]
            cmd += ["--"]
        for version in PROFILES:
            extra = {"LD_LIBRARY_PATH":str(ART/"icu74"),"DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU":"74.2"} if version == PROFILES[0] else {}
            run(action+"-"+version,[*cmd,dotnet,"exec","--fx-version","10.0.12","--roll-forward","Disable",dll,action,version],extra)
    result = verify(DONORS,WORK,prior,ROOT)
    sources = {str(p.relative_to(ROOT)):base.sha(p) for p in (HERE/n for n in FILES)}
    result.update(source=revision["commit"],sourceArchiveSha256=revision["archiveSha256"],studySources=sources,
                  previousReceiptSha256=PIN,previousRawSha256=RAW_PIN,privateNetwork=network,toolArchives=tools,
                  nativeReports={d.name:base.sha(d/"result.json") for a in ("write","read") for d in WORK.glob(a+"-*") if d.is_dir()})
    assert result["probeSha256"] == base.sha(dll)
    (WORK/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    selected = [*WORK.glob("*.log"),WORK/"result.json",*(HERE/n for n in FILES),ART/"source.tar",dll,dll.parent/"ImmichFolderWatch.Core.dll"]
    selected += [p for a in ("write","read") for v in PROFILES for p in (WORK/(a+"-"+v)).iterdir()]
    with tarfile.open(fileobj=sys.stdout.buffer,mode="w|") as archive:
        for p in sorted(selected):
            name = str(p.relative_to(WORK)) if WORK in p.parents else ("study-sources/"+p.name if HERE in p.parents else p.name)
            archive.add(p,arcname=name,recursive=False)


def main():
    if not __debug__:
        raise SystemExit("Python assertions are required.")
    os.chdir(ROOT)
    os.umask(0o077)
    if sys.argv[1:] == ["--private-stage"]:
        private_stage()
        return
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output",type=Path,required=True)
    out = cli.parse_args().output.absolute()
    if out.parent != ART or out in (PRIOR,ORIGINAL):
        raise ValueError("Expected a new direct output child of artifacts/rust.")
    with ExitStack() as stack:
        checkout = os.open(".",base.DIRFLAGS)
        stack.callback(os.close,checkout)
        parent = stack.enter_context(base.directory(checkout,ART.relative_to(ROOT)))
        blobs,initial = originals(checkout)
        rev, refs = base.git_snapshot()
        blobs.update(refs)
        blobs.update({Path("/etc/passwd"):f"fixture:x:{os.getuid()}:{os.getgid()}:Synthetic:/tmp:/bin/false\n".encode(),
                      Path("/etc/group"):f"fixture:x:{os.getgid()}:\n".encode(),Path("/etc/hosts"):b"127.0.0.1 localhost\n::1 localhost\n"})
        os.mkdir(out.name,0o700,dir_fd=parent)
        dest = stack.enter_context(base.directory(parent,Path(out.name)))
        cmd = [*base.PRIVATE,"--unshare-net","--ro-bind","/usr","/usr","--symlink","usr/bin","/bin","--symlink","usr/lib","/lib",
               "--symlink","usr/lib64","/lib64","--ro-bind","/etc/ld.so.cache","/etc/ld.so.cache","--symlink","../usr/lib/os-release","/etc/os-release",
               "--proc","/proc","--dev","/dev","--tmpfs","/tmp","--tmpfs",ROOT,"--tmpfs",ART,"--tmpfs",WORK,"--tmpfs",DONORS,
               "--tmpfs",base.HERE,"--tmpfs",HERE]
        fds = []
        for name,path in {"sdk":SDK,"icu74":ICU,"nuget-input":ROOT/"artifacts/nuget-packages"}.items():
            fd = stack.enter_context(base.directory(checkout,path.relative_to(ROOT)))
            fds.append(fd)
            cmd += ["--ro-bind-fd",str(fd),ART/name]
        for name,path in base.ARCHIVES.items():
            with base.directory(checkout,path.parent.relative_to(ROOT)) as source:
                fd = os.open(path.name,os.O_PATH|os.O_NOFOLLOW,dir_fd=source)
            stack.callback(os.close,fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size < 384*1024*1024:
                raise ValueError("Invalid distribution archive.")
            fds.append(fd)
            cmd += ["--ro-bind-fd",str(fd),ART/name]
        for path,data in blobs.items():
            fd = os.memfd_create("rollback-upsert",os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
            stack.callback(os.close,fd)
            with os.fdopen(os.dup(fd),"wb") as stream:
                stream.write(data)
            os.lseek(fd,0,0)
            fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SEAL)
            fds.append(fd)
            cmd += ["--ro-bind-data",str(fd),path]
        for path in (base.HERE,HERE,DONORS,ART,ROOT):
            cmd += ["--remount-ro",path]
        cmd += ["--chdir",ROOT,"--",sys.executable,"-B",HERE/"study.py","--private-stage"]
        def new(name):
            return os.fdopen(os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=dest),"w+b")
        with new("evidence.tar") as raw, new("namespace.log") as log:
            proc = subprocess.run(cmd,env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","HOME":"/tmp"},
                                  pass_fds=tuple(fds),stdout=raw,stderr=log,timeout=240)
            if proc.returncode:
                raise RuntimeError(f"Native study failed. See {out/'namespace.log'}.")
            assert 0 < raw.tell() <= 32*1024*1024
            raw.seek(0)
            digest = hashlib.file_digest(raw,"sha256").hexdigest()
            raw.seek(0)
            with tarfile.open(fileobj=raw,mode="r:") as archive:
                result = json.load(archive.extractfile("result.json"))
                for f in FILES:
                    digest_source = hashlib.sha256(archive.extractfile("study-sources/"+f).read()).hexdigest()
                    assert initial["study/"+f][0] == result["studySources"][str((HERE/f).relative_to(ROOT))] == digest_source
        base.check_sources(rev)
        assert originals(checkout)[1] == initial and os.path.samestat(os.fstat(dest),os.stat(out.name,dir_fd=parent,follow_symlinks=False))
        result.update(evidenceTarSha256=digest,preservedPriorExportMembers=160,preservedRustCases=8,
                      originalCSharpDonorFiles=8,priorExportIdentitiesBeforeAndAfter={
                          k:initial[k] for k in sorted(initial) if not k.startswith("study/")},
                      identityFields=["sha256","device","inode","size","mtimeNs","ctimeNs","links"])
        data = (json.dumps(result,indent=2,sort_keys=True)+"\n").encode()
        with new("result.json") as summary:
            summary.write(data)
        print(hashlib.sha256(data).hexdigest(),out/"result.json")


if __name__ == "__main__":
    main()
