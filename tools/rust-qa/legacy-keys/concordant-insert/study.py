"""Run the three-profile insert and rollback comparison on fresh, offline Linux x64 copies."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "new-entry"))
import run as base

ROOT, ART, DONORS, WORK = base.ROOT, base.ART, base.DONORS, base.WORK
ORIGINAL = ART/"managed-invariant-verified-86ae038"
FILES = ("study.py", "trial.py", "insert.rs", "ConcordantStore.cs", "ConcordantStore.csproj")
MANAGED = "tools/rust-qa/legacy-invariant/managed-invariant-10.0.12.tsv"
NEW_ENTRY = "tools/rust-qa/legacy-keys/new-entry"
ROLLBACK = "tools/rust-qa/legacy-keys/rollback-upsert"
EXTRA = (MANAGED, NEW_ENTRY, ROLLBACK, "rust/tests/fixtures/legacy/linux/sqlite/sensitive.sql")
LIB = base.STORE / "src/lib.rs"


def capture(checkout):
    blobs, records = {}, {}
    def retain(folder, filename, dest, pin=None):
        data, record = base.bounded_source(folder, filename)
        if pin is not None and record[0] != pin:
            raise ValueError(f"Incorrect source digest for {filename}")
        records[str(dest.relative_to(ROOT))] = record
        blobs[dest] = data
        return data
    with base.directory(checkout, ORIGINAL.relative_to(ROOT)) as folder:
        original = json.loads(retain(folder, "evidence.json", DONORS/"writers.json",
                              "b500d9cba921ea9f94caba407087fb1bd22a8272e477e93f8c03674b7b94957f"))
        for name, receipt in original["nativeWriters"].items():
            with base.directory(folder,Path("source/artifacts/rust")/name) as writer:
                expected = receipt["files"]
                if set(os.listdir(writer)) != set(expected) or set(expected) != {"result.json","invariant-uppercase.tsv","insensitive.db","sensitive.db"}:
                    raise ValueError("The finalized original writer directory differs.")
                for filename,digest in expected.items():
                    retain(writer,filename,DONORS/name/filename,digest)
    with base.directory(checkout,Path("artifacts/rust/rollback-upsert-13e4af8-offline-01")) as folder:
        retain(folder,"result.json",DONORS/"prior-upsert.json","10f88914879023f006fb8779205fc936da984f568de7ba84e80dcb46751d1f36")
    with base.directory(checkout,Path("artifacts/rust/stored-keys-three-profile-verified")) as folder:
        retain(folder,"result.json",DONORS/"prior-readback.json","9ee4efa144f87a6e6b45f2c5e41dbf580c3d1beb883017dad2d48da9bb3268e1")
    with base.directory(checkout,HERE.relative_to(ROOT)) as folder:
        for name in FILES:
            retain(folder,name,HERE/name)
    with base.directory(checkout,LIB.parent.relative_to(ROOT)) as folder:
        retain(folder,LIB.name,LIB)
    return blobs,records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    out=parser.parse_args().output.absolute()
    if not __debug__ or out.parent!=ART:
        raise ValueError("Expected an enabled assertion interpreter and a new direct output child of artifacts/rust.")
    os.chdir(ROOT)
    os.umask(0o077)
    # Preserve the library being assessed as a separate sealed source beside the underlying Git snapshot.
    storage=base.STORE.relative_to(ROOT).as_posix()
    tracked_storage=subprocess.check_output(["git","ls-files","-z","--",storage]).decode().split("\0")
    base.TRACKED=(*[p for p in base.TRACKED if p!=storage],*EXTRA,
                  *[p for p in tracked_storage if p and p!=LIB.relative_to(ROOT).as_posix()])
    with ExitStack() as stack:
        checkout=os.open(".",base.DIRFLAGS)
        stack.callback(os.close,checkout)
        area=stack.enter_context(base.directory(checkout,ART.relative_to(ROOT)))
        blobs,initial=capture(checkout)
        rev,snapshot=base.git_snapshot()
        blobs.update(snapshot)
        blobs[base.STORE/"examples/concordant_study.rs"]=blobs[HERE/"insert.rs"]
        blobs.update({Path("/etc/passwd"):f"fixture:x:{os.getuid()}:{os.getgid()}:Synthetic:/tmp:/bin/false\n".encode(),
                      Path("/etc/group"):f"fixture:x:{os.getgid()}:\n".encode(),Path("/etc/hosts"):b"127.0.0.1 localhost\n"})
        os.mkdir(out.name,0o700,dir_fd=area)
        dest=stack.enter_context(base.directory(area,Path(out.name)))
        cmd=[*base.PRIVATE,"--unshare-net","--clearenv","--setenv","PATH","/usr/bin:/bin","--setenv","LANG","C.UTF-8","--setenv","HOME","/tmp",
             "--ro-bind","/usr","/usr","--symlink","usr/bin","/bin","--symlink","usr/lib","/lib","--symlink","usr/lib64","/lib64",
             "--ro-bind","/etc/ld.so.cache","/etc/ld.so.cache","--symlink","../usr/lib/os-release","/etc/os-release",
             "--dev","/dev","--proc","/proc","--tmpfs","/tmp","--tmpfs",ROOT,"--tmpfs",ART,"--tmpfs",DONORS,"--tmpfs",WORK]
        roots={"sdk":ROOT/"artifacts/flatpak-local-2.11.2/sdk","icu74":ART/"casing-oracle-verified-e59a691/icu74",
               "toolchain":ART/"toolchain","cargo-input":ART/"storage-assessment/cargo-home","nuget-input":ROOT/"artifacts/nuget-packages"}
        fds=[]
        for name,path in roots.items():
            fd=stack.enter_context(base.directory(checkout,path.relative_to(ROOT)))
            fds.append(fd)
            cmd += ["--ro-bind-fd",str(fd),ART/name]
        for name,path in base.ARCHIVES.items():
            with base.directory(checkout,path.parent.relative_to(ROOT)) as parent:
                fd=os.open(path.name,os.O_PATH|os.O_NOFOLLOW,dir_fd=parent)
            stack.callback(os.close,fd)
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or not 0<s.st_size<384*1024*1024:
                raise ValueError("Unexpected distribution archive.")
            fds.append(fd)
            cmd += ["--ro-bind-fd",str(fd),ART/name]
        for path,data in blobs.items():
            fd=os.memfd_create("concordant-input",os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
            stack.callback(os.close,fd)
            with os.fdopen(os.dup(fd),"wb") as file:
                file.write(data)
            os.lseek(fd,0,0)
            fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SEAL|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK)
            fds.append(fd)
            cmd += ["--ro-bind-data",str(fd),path]
        for path in (DONORS,ART,ROOT): cmd += ["--remount-ro",path]
        cmd += ["--chdir",ROOT,"--",sys.executable,"-B",HERE/"trial.py"]
        def fresh(name):
            return os.fdopen(os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=dest),"w+b")
        with fresh("evidence.tar") as raw, fresh("namespace.log") as log:
            proc=subprocess.run(cmd,env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","HOME":"/tmp"},
                                pass_fds=tuple(fds),stdout=raw,stderr=log,timeout=420)
            if proc.returncode:
                raise RuntimeError(f"Native trial failed. See {out/'namespace.log'}.")
            assert 0<raw.tell()<80*1024*1024
            raw.seek(0)
            digest=hashlib.file_digest(raw,"sha256").hexdigest()
            raw.seek(0)
            with tarfile.open(fileobj=raw,mode="r:") as archive:
                result=json.load(archive.extractfile("private-result.json"))
                for name in FILES:
                    assert hashlib.sha256(archive.extractfile("study/"+name).read()).hexdigest()==initial[str((HERE/name).relative_to(ROOT))][0]
                assert hashlib.sha256(archive.extractfile("study/storage-lib.rs").read()).hexdigest()==initial[str(LIB.relative_to(ROOT))][0]
        base.check_sources(rev)
        assert capture(checkout)[1]==initial and os.path.samestat(os.fstat(dest),os.stat(out.name,dir_fd=area,follow_symlinks=False))
        result.update(rawSha256=digest,inputsBeforeAndAfter=initial)
        data=(json.dumps(result,sort_keys=True,indent=2)+"\n").encode()
        with fresh("result.json") as report: report.write(data)
        print(hashlib.sha256(data).hexdigest(),out/"result.json")


if __name__=="__main__":
    main()
