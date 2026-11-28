"""Compare actual rollback stores with the historical SQL keys and full same-process casing tables."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from verify import ENTRIES, OTHER, PRIMARY, PROFILES, SPLIT, STABLE, TABLES, identity


def snapshot(data):
    assert data.startswith(b"SQLite format 3\0") and data[18:20] == b"\1\1"
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(data)
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA user_version").fetchone() == (1,)
        schema = db.execute("SELECT type,name,rootpage,sql FROM sqlite_schema ORDER BY type,name").fetchall()
        assert {n for t,n,_,_ in schema if t == "table"} == set(TABLES)
        db.row_factory = sqlite3.Row
        rows = {t:[dict(r) for r in db.execute(f'SELECT rowid,* FROM "{t}" ORDER BY rowid')] for t in TABLES}
        return schema, rows


def projected(rows, mapping):
    def listing(account, source):
        return sorted((r for r in rows["sync_entries"] if r["account_scope"] == account and
                       r["source_key"] == source.translate(mapping)), key=lambda r:r["relative_path_key"])
    tests = [(PRIMARY,STABLE,"New/Stable.jpg"),(PRIMARY,STABLE,"New/Only-ƛ.jpg"),(PRIMARY,STABLE,"New/Only-Ƛ.jpg"),
             (PRIMARY,SPLIT,"New/Source.jpg"),(PRIMARY,SPLIT.replace("ƛ","Ƛ"),"New/Source.jpg"),(OTHER,STABLE,"New/Stable.jpg")]
    lookups = []
    for account,source,name in tests:
        matches = [r for r in listing(account,source) if r["relative_path_key"] == name.translate(mapping)]
        assert len(matches) <= 1
        lookups.append(identity(matches[0]) if matches else None)
    lists = [[identity(r) for r in listing(a,s)] for a,s in
             ((PRIMARY,STABLE),(PRIMARY,SPLIT),(PRIMARY,SPLIT.replace("ƛ","Ƛ")),(OTHER,STABLE))]
    history = {r["account_scope"]:r["last_successful_sync_utc"] for r in rows["sync_account_status"]}
    return dict(lookups=lookups, lists=lists, history=history[PRIMARY], otherHistory=history[OTHER])


def expected_rows(before, mapping):
    physical = {(r["account_scope"],r["source_key"],r["relative_path_key"]):r.copy() for r in before["sync_entries"]}
    next_id = max(r["rowid"] for r in physical.values())+1
    changed, added = [], []
    for source,path,asset in ENTRIES:
        original, = [r for r in before["sync_entries"] if r["asset_id"] == asset]
        assert (original["source_path"], original["relative_path"], original["file_size"]) == (source,path,83)
        key = PRIMARY,source.translate(mapping),path.translate(mapping)
        row = physical.get(key)
        if row is None:
            row = original | {"rowid":next_id, "source_key":key[1], "relative_path_key":key[2]}
            physical[key] = row
            added.append(dict(asset=asset, historicalRowid=original["rowid"], newRowid=next_id))
            next_id += 1
        else:
            assert row["asset_id"] == asset and row["rowid"] == original["rowid"]
            changed.append(row["rowid"])
        row["file_size"] = 101
    rows = sorted(physical.values(), key=lambda r:r["rowid"])
    return before | {"sync_entries":rows}, changed, added


def verify(donors, work, prior, root):
    reports, maps = {}, {}
    for action in ("write","read"):
        for version in PROFILES:
            path = work/(action+"-"+version)
            doc = json.loads((path/"result.json").read_bytes())
            table = (path/"invariant-uppercase.tsv").read_bytes()
            assert table == (root/f"tools/rust-qa/legacy/casing/unicode-{version}.tsv").read_bytes()
            mapping = {int(a,16):int(b,16) for a,b in (r.split(b"\t") for r in table.splitlines()[1:])}
            assert doc["casingProfile"] == dict(tableSha256=sha256(table).hexdigest(), scannedScalars=1112064,
                                                changedScalars=len(mapping), contextBatchChecked=True)
            assert (doc["format"], doc["version"], doc["action"], doc["os"],doc["arch"],doc["runtime"]) == (
                "ifw-rollback-upsert-v1",version,action,"linux","x64","10.0.12")
            assert [doc["corelibSha256"],doc["corelibBuild"]] == prior["readerBuilds"][2:]
            assert doc["storeSha256"] == prior["readerBuilds"][1] and doc["baseline"] == "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
            assert len(doc["cases"]) == (8 if action == "write" else 16)
            maps[version] = mapping
            reports[action,version] = doc
    assert len({d["probeSha256"] for d in reports.values()}) == 1
    results, stages_checked, existing, added, original, fields = {}, 0, 0, 0, 0, set()
    for name, trial in prior["trials"].items():
        donor,mode,insert = name.split("-")
        base = (donors/name/"inserted.db").read_bytes()
        assert sha256(base).hexdigest() == trial["after"]
        schema, before = snapshot(base)
        for writer in PROFILES:
            entry = reports["write",writer]["cases"][name]
            mapping = maps[writer] if mode == "insensitive" else {}
            target, changed, duplicates = expected_rows(before,mapping)
            mismatch = mode == "insensitive" and writer != insert
            assert (len(changed),len(duplicates)) == ((1,2) if mismatch else (3,0))
            assert entry["stages"]["before"] == projected(before,mapping)
            for phase in ("first","repeat"):
                f = work/("write-"+writer)/(name+"."+phase+".db")
                data = f.read_bytes()
                assert sha256(data).hexdigest() == entry["hashes"][phase]
                assert snapshot(data) == (schema,target)
                assert entry["stages"][phase] == projected(target,mapping)
            stages_checked += 3
            signals = {}
            for reader in PROFILES:
                observed = reports["read",reader]["cases"][writer+"/"+name]
                assert observed["digest"] == entry["hashes"]["repeat"]
                assert observed["observation"] == projected(target,maps[reader] if mode=="insensitive" else {})
                lookups = observed["observation"]["lookups"]
                sizes = [lookups[i]["FileSize"] if lookups[i] is not None else None for i in (0,1,3)]
                expected_size = 101 if mode == "sensitive" or reader == writer else (83 if mismatch else None)
                assert sizes == [101,expected_size,expected_size]
                stable_list = observed["observation"]["lists"][0]
                sizes_b = sorted(r["FileSize"] for r in stable_list if r["AssetId"] == "Insert-Asset-B")
                assert sizes_b == ([83,101] if mismatch else [101])
                signals[reader] = dict(originalLookupSizes=sizes,relativeListingSizes=sizes_b)
                stages_checked += 1
            existing += len(changed)
            added += len(duplicates)
            original += sum(len(t) for t in before.values())
            fields.add(reports["write",writer]["storeSha256"])
            results[writer+"/"+name] = dict(historicalPhysicalRowidsUpdated=changed,addedPhysicalRows=duplicates,
                                            snapshotHashes=entry["hashes"],finalReads=signals)
    assert (len(results), stages_checked, existing, added, original, len(fields)) == (16,80,40,8,204,1)
    return dict(format="ifw-rollback-upsert-result-v1",cases=results,originalRowsAcrossCopies=original,
                distinctOldRowsUpdated=existing,firstPassRowsAdded=added,repeatRowsAdded=0,
                upsertCalls=96,nativeObservations=stages_checked,singleLookups=stages_checked*6,
                sourceLists=stages_checked*4,historyReads=stages_checked*2,
                storeSha256=fields.pop(), probeSha256=reports["write",PROFILES[0]]["probeSha256"])
