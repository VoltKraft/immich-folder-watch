"""Exercise the new Rust writer and the three shipping rollback stores in the private namespace."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "new-entry"))
import run as base
sys.path.insert(0, str(HERE.parent / "rollback-upsert"))
from check import snapshot
sys.path.insert(0, str(base.STORE))
from evidence import external_lock, target_graph, verify_sources

PROFILES = {"older": "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f",
            "managed": "51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4",
            "current": "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e"}
MODES = ("insensitive", "sensitive")
ACCOUNT = "ifw-managed-invariant-study"
STABLE = "/IfwSynthetic/Insert-ASCII"
HISTORICAL = "/IfwSynthetic/Archive-S-Ƛ"
STAMP = "2024-02-29T03:04:05.1234567+00:00"
ROOT, WORK, DONORS, ART = base.ROOT, base.WORK, base.DONORS, base.ART


def entry(source, relative, asset):
    return dict(account=ACCOUNT, source=source, relative=relative, asset=asset)


NEW = [entry(STABLE, "New/Stable.jpg", "Insert-Asset-A"), entry("/IfwSynthetic/Child/../Insert-ASCII/", "New/Café-ß.jpg", "Insert-Asset-Café"),
       entry(STABLE, "New/Only-ƛ.jpg", "Insert-Asset-B"), entry("/IfwSynthetic/Case-ƛ", "New/Source.jpg", "Insert-Asset-C"),
       entry(STABLE, "New/Only-ſ.jpg", "Insert-Asset-D"), entry("/IfwSynthetic/Case-ſ", "New/Source.jpg", "Insert-Asset-E")]
ACCEPTED = {"insensitive": NEW[:2], "sensitive": NEW}


def batches(writer, mode):
    marker = entry(STABLE, "New/Never-committed.jpg", "Atomic-control")
    cases = [("eligible", ACCEPTED[mode], "inserted"), ("retry", ACCEPTED[mode], "existing"),
             ("same-batch", [marker, marker], "existing")]
    if mode == "insensitive":
        cases += [(row["asset"], [marker, row], "absent-profile-dependent") for row in NEW[2:]]
        if writer in ("older", "managed"):
            relative = "stroke-Ƛ.jpg" if writer == "older" else "long-s-S.jpg"
            cases.append(("historical-ambiguity", [marker, entry(HISTORICAL, relative, "Alias-control")], "ambiguous"))
    return cases


def verify(cases, hashes):
    results, native = {}, {}
    for profile, table_hash in PROFILES.items():
        d = WORK / ("csharp-" + profile)
        doc = json.loads((d/"result.json").read_bytes())
        table = (d/"invariant-uppercase.tsv").read_bytes()
        assert hashlib.sha256(table).hexdigest() == doc["casingProfile"]["tableSha256"] == table_hash
        assert doc["casingProfile"]["scannedScalars"] == 1112064 and doc["casingProfile"]["contextBatchChecked"] is True
        assert doc["runtime"] == "10.0.12" and doc["baseline"] == "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
        # A different build path changes this deterministic assembly's source paths. The current
        # fixture and the historical upsert study used the same private paths and source tree.
        assert doc["storeSha256"] == hashes["storeSha256"]
        lines = table.decode().splitlines()
        assert lines[0] == "IFW-INVARIANT-UPPERCASE-V1"
        native[profile] = dict(report=doc, mapping={int(a,16):int(b,16) for a,b in
                               (line.split("\t") for line in lines[1:])})
    counts = dict(rustRowsInserted=0, refusedTransactions=0, csharpUpserts=0, csharpAddedRows=0, nativeCases=0)
    for name, (writer,mode,requests) in cases.items():
        donor = (DONORS/writer/(mode+".db")).read_bytes()
        before_schema, before = snapshot(donor)
        out = WORK/"cases"/name
        receipt = json.loads((out/"receipt.json").read_bytes())
        assert receipt["profiles"] == list(PROFILES.values()) and receipt["writerReceipt"] == base.sha(DONORS/writer/"result.json")
        assert receipt["donor"] == hashlib.sha256(donor).hexdigest() and receipt["after"] == base.sha(out/"after.db")
        chain = receipt["donor"]
        for step,(label,entries,wanted) in zip(receipt["batches"],requests,strict=True):
            decision = step["decision"]
            assert step["name"] == label and step["before"] == chain
            if wanted == "inserted":
                assert decision == {"status":"inserted","rowsCommitted":len(entries)} and step["after"] != chain
                counts["rustRowsInserted"] += len(entries)
            else:
                assert decision["status"] == "refused" and decision["decision"]["status"] == wanted and decision["rowsCommitted"] == 0
                assert decision["blockedIndex"] == (0 if label=="retry" else 1) and step["after"] == chain
                counts["refusedTransactions"] += 1
            chain = step["after"]
        assert chain == receipt["after"]
        schema, rust = snapshot((out/"after.db").read_bytes())
        assert schema == before_schema
        added = []
        for index,row in enumerate(ACCEPTED[mode],1):
            display_source = os.path.normpath(row["source"])
            forms = {(display_source.translate(v["mapping"]),row["relative"].translate(v["mapping"])) for v in native.values()}
            if mode == "sensitive":
                source,relative=display_source,row["relative"]
            else:
                assert len(forms)==1
                source,relative=forms.pop()
            added.append(dict(rowid=before["sync_entries"][-1]["rowid"]+index,account_scope=ACCOUNT,source_path=display_source,
                              source_key=source,relative_path=row["relative"],relative_path_key=relative,asset_id=row["asset"],
                              album_name="Synthetic insert",file_size=83,last_write_time_utc=STAMP,direction=1,status=0,
                              last_synchronized_at_utc=STAMP,tombstone_expires_at_utc=None))
        assert rust == before | {"sync_entries":before["sync_entries"]+added}
        target = before | {"sync_entries":before["sync_entries"]+[row | {"file_size":101} for row in added]}
        saved = {}
        for profile, info in native.items():
            rounds = info["report"]["cases"][name]
            assert rounds["before"]["sha256"] == receipt["after"]
            for phase in ("before","first","repeat"):
                observations = [dict(AccountScope=ACCOUNT,SourcePath=os.path.normpath(row["source"]),RelativePath=row["relative"],
                                AssetId=row["asset"],FileSize=83 if phase=="before" else 101) for row in ACCEPTED[mode]]
                assert rounds[phase]["observations"] == observations
                if phase != "before":
                    path = WORK/("csharp-"+profile)/(name+"."+phase+".db")
                    assert base.sha(path) == rounds[phase]["sha256"] and snapshot(path.read_bytes()) == (schema,target)
                    counts["csharpUpserts"] += len(added)
            assert rounds["first"]["sha256"] == rounds["repeat"]["sha256"]
            counts["nativeCases"] += 1
            saved[profile] = rounds["repeat"]["sha256"]
        results[name] = dict(rust=receipt,updatedRowids=[row["rowid"] for row in added],shippingBackups=saved)
    assert counts == dict(rustRowsInserted=24, refusedTransactions=26, csharpUpserts=144, csharpAddedRows=0, nativeCases=18)
    return dict(counts=counts,cases=results,nativeReports={p:base.sha(WORK/("csharp-"+p)/"result.json") for p in PROFILES})


def main():
    for path,access in ((ROOT,"ro"),(ART,"ro"),(DONORS,"ro"),(WORK,"rw")):
        assert base.mount_record(path)=={"filesystem":"tmpfs","access":access}
    revision = json.loads((ART/"revision.json").read_bytes())
    net = {"parent":revision["parentNetNamespace"],"worker":os.stat("/proc/self/ns/net").st_ino,
           "interfaces":[s.split(":")[0].strip() for s in Path("/proc/net/dev").read_text().splitlines()[2:]],
           "ipv4Routes":Path("/proc/net/route").read_text().splitlines()[1:]}
    assert net["parent"] != net["worker"] and net["interfaces"]==["lo"] and not net["ipv4Routes"]
    for name in ("home","tmp","feed","logs","cases","config","data","cache"):
        (WORK/name).mkdir(mode=0o700)
    inputs=json.loads((base.STORE/"inputs.json").read_bytes())
    sdk=json.loads((ROOT/"global.json").read_bytes())["sdk"]["version"]
    archives=base.verify_tool_inputs(sdk)
    cargo=WORK/"cargo-home"
    registry=ART/"cargo-input/registry"
    assert base.mount_record(ART/"cargo-input")["access"] == base.mount_record(ART/"nuget-input")["access"] == "ro"
    if any(p.is_symlink() for p in registry.rglob("*")):
        raise ValueError("Unexpected link in offline registry.")
    shutil.copytree(registry,cargo/"registry",symlinks=True)
    env=dict(PATH=str(ART/"toolchain/bin")+":/usr/bin:/bin",LANG="C.UTF-8",HOME=str(WORK/"home"),TMPDIR=str(WORK/"tmp"),
             XDG_CONFIG_HOME=str(WORK/"config"),XDG_DATA_HOME=str(WORK/"data"),XDG_CACHE_HOME=str(WORK/"cache"),CARGO_HOME=str(cargo),
             CARGO_TARGET_DIR=str(WORK/"target"),LIBSQLITE3_FLAGS=inputs["sqlite"]["flags"],LIBSQLITE3_SYS_USE_PKG_CONFIG="0",
             DOTNET_ROOT=str(ART/"sdk"),DOTNET_CLI_HOME=str(WORK/"home"),NUGET_PACKAGES=str(ART/"nuget-input"),DOTNET_NOLOGO="1",
             DOTNET_CLI_TELEMETRY_OPTOUT="1",DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
             IFW_ORACLE_EXPECT_ARCH="x64")
    def run(name,command,request=None,extra=None,refusal=None):
        print(name,file=sys.stderr,flush=True)
        log=WORK/"logs"/(name+".log")
        with log.open("xb") as stream:
            proc=subprocess.run(command,cwd=ROOT,env=env|(extra or {}),stdout=stream,stderr=subprocess.STDOUT,
                                input=None if request is None else json.dumps(request).encode(),timeout=240)
        if (proc.returncode==0)!=(refusal is None) or (refusal and refusal not in log.read_text()):
            raise RuntimeError(log.read_text(errors="replace")[-5000:])
        return log
    run("toolchain",[sys.executable,"-B",ROOT/"tools/rust-qa/check-toolchain.py",base.TARGET])
    assert run("sdk",[ART/"sdk/dotnet","--version"]).read_text().strip()==sdk
    manifest=["--manifest-path",base.STORE/"Cargo.toml","--frozen"]
    assert base.sha(base.STORE/"Cargo.lock") == inputs["lock_sha256"]
    assert external_lock(base.STORE/"Cargo.lock")=={(r["name"],r["version"]):r["archive_sha256"] for r in inputs["packages"]}
    metadata=json.loads(run("metadata",["cargo","metadata",*manifest,"--format-version","1"]).read_bytes())
    target=json.loads(run("target-graph",["cargo","metadata",*manifest,"--format-version","1","--filter-platform",base.TARGET]).read_bytes())
    assert target_graph(target)==inputs["target_graphs"][base.TARGET]
    sources=verify_sources(metadata,inputs,cargo,WORK/"cargo-evidence")
    run("build-rust",["cargo","build",*manifest,"--release","--target",base.TARGET,
                      "--example","concordant_study","--example","inspect_stored_keys"])
    run("clippy",["cargo","clippy",*manifest,"--target",base.TARGET,"--all-targets","--","-D","warnings"])
    binary=WORK/"target"/base.TARGET/"release/examples/concordant_study"
    cases={}
    policy=list(PROFILES.values())
    historical=json.loads((DONORS/"prior-readback.json").read_bytes())["runs"]
    historical_count=0
    for writer in PROFILES:
        for mode in MODES:
            name=writer+"-"+mode
            donor_hash=base.sha(DONORS/writer/(mode+".db"))
            old=historical[{"older":"icu15","managed":"managed16","current":"icu17"}[writer]][mode]
            lookups=[q["query"] for q in old["queries"]]
            observed=run("historical-"+name,[binary.with_name("inspect_stored_keys"),"--three-profile-study",DONORS/writer,mode,donor_hash],lookups)
            assert json.loads(observed.read_bytes())==old["receipt"]
            historical_count += len(lookups)
            cmd=[binary,writer,mode,donor_hash]
            if not cases:
                for label,selection in (("unknown",[*policy,"unknown"]),("subset",policy[:2]),("duplicate",[policy[0]]*3)):
                    run("policy-"+label,cmd,{"rollbackProfiles":selection},refusal="unqualified rollback profile set")
                    assert not (WORK/"cases"/name).exists()
            requested=batches(writer,mode)
            run("rust-"+name,cmd,{"rollbackProfiles":policy,"batches":[dict(name=n,entries=e) for n,e,_ in requested]})
            cases[name]=(writer,mode,requested)
    (WORK/"cases/accepted.json").write_text(json.dumps(ACCEPTED)+"\n")
    project=HERE/"ConcordantStore.csproj"
    config=WORK/"feed/NuGet.Config"
    config.write_text('<configuration><packageSources><clear/><add key="offline" value="."/></packageSources></configuration>')
    options=["--artifacts-path",WORK/"dotnet-build","--disable-build-servers","-m:1","-p:UseSharedCompilation=false",
             "-p:RestoreDisableParallel=true","-p:EnableWindowsTargeting=false","-p:NuGetAudit=false"]
    dotnet=ART/"sdk/dotnet"
    run("restore",[dotnet,"restore",project,"--configfile",config,"--source",WORK/"feed",*options])
    run("build-csharp",[dotnet,"build",project,"-c","Release","--no-restore",*options])
    dll=WORK/"dotnet-build/bin/ConcordantStore/release/ConcordantStore.dll"
    for profile in PROFILES:
        extra={"older":{"LD_LIBRARY_PATH":str(ART/"icu74"),"DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU":"74.2"},
               "managed":{"DOTNET_SYSTEM_GLOBALIZATION_INVARIANT":"1"},"current":{}}[profile]
        run("upsert-"+profile,[*base.PRIVATE,"--bind","/","/","--ro-bind",WORK/"cases",WORK/"cases","--proc","/proc",
            "--dev","/dev","--",dotnet,"exec","--fx-version","10.0.12","--roll-forward","Disable",dll,profile],extra=extra)
    assert verify_sources(metadata,inputs,cargo,WORK/"cargo-evidence")==sources
    report=verify(cases,json.loads((DONORS/"prior-upsert.json").read_bytes()))
    report.update(format="ifw-qualified-new-entry-study-v1",source=revision,network=net,toolArchives=archives,
                  compiledWriter=base.sha(binary),nativeProbe=base.sha(dll),cargoArchives=len(sources),cargoFiles=sum(sources.values()),
                  historicalQueriesUnchanged=historical_count)
    (WORK/"private-result.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    files=[(p,str(p.relative_to(WORK))) for folder in [WORK/"logs",WORK/"cases",*(WORK/("csharp-"+v) for v in PROFILES)]
           for p in folder.rglob("*") if p.is_file()]
    files.extend((p,"study/"+p.name) for p in HERE.iterdir() if p.is_file())
    files.append((base.STORE/"src/lib.rs","study/storage-lib.rs"))
    files.extend([(ART/"source.tar","source.tar"),(binary,"concordant_study"),(dll,dll.name),(WORK/"private-result.json","private-result.json")])
    with tarfile.open(fileobj=sys.stdout.buffer,mode="w|") as output:
        for path,name in sorted(files): output.add(path,arcname=name,recursive=False)


if __name__=="__main__":
    main()
