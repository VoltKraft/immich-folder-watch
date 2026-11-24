"""Project actual C# reads from immutable SQLite rows and the two complete scalar tables."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3


PROFILES = ("15.1.0", "17.0.0")
TABLES = ("sync_entries", "sync_timestamp_repairs", "sync_account_status", "owned_albums")
PRIMARY, OTHER = "ifw-casing-primary", "ifw-casing-other"
STABLE, SPLIT = "/IfwSynthetic/Insert-ASCII", "/IfwSynthetic/Case-ƛ"
ENTRIES = ((STABLE, "New/Stable.jpg", "Insert-Asset-A"), (STABLE, "New/Only-ƛ.jpg", "Insert-Asset-B"),
           (SPLIT, "New/Source.jpg", "Insert-Asset-C"))
STAMP = "2024-02-29T03:04:05.1234567+00:00"


def snapshot(file):
    assert file.is_file() and not file.is_symlink() and not any(
        Path(str(file)+suffix).exists() for suffix in ("-shm","-wal","-journal"))
    with closing(sqlite3.connect(file.as_uri()+"?mode=ro&immutable=1", uri=True)) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA user_version").fetchone() == (1,)
        schema = db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY type,name").fetchall()
        assert {name for kind,name,_ in schema if kind=="table"} == set(TABLES)
        db.row_factory = sqlite3.Row
        tables = {t: [dict(r) for r in db.execute(f'SELECT * FROM "{t}" ORDER BY rowid')] for t in TABLES}
        return schema, tables


def identity(row):
    return {dotnet:row[physical] for dotnet,physical in (
        ("AccountScope","account_scope"),("SourcePath","source_path"),("RelativePath","relative_path"),
        ("AssetId","asset_id"),("FileSize","file_size"))}


def verify(corpus, out):
    root = Path(__file__).resolve().parents[4]
    maps, reads, builds = {}, {}, set()
    for profile in PROFILES:
        path = out/("reader-"+profile)
        tab = (root/f"tools/rust-qa/legacy/casing/unicode-{profile}.tsv").read_bytes()
        assert (path/"invariant-uppercase.tsv").read_bytes() == tab
        scalar = {int(a,16):int(b,16) for a,b in (r.split(b"\t") for r in tab.splitlines()[1:])}
        doc = json.loads((path/"result.json").read_bytes())
        assert doc["format"] == "ifw-study-insert-readback-v1" and (doc["runtime"],doc["os"],doc["arch"]) == (
            "10.0.12","linux","x64")
        assert doc["corelibBuild"].endswith("+95017c711e6afc1085133d440e42b4bd78155701")
        for key, access, mount in (("readOnlyCasesMount","ro",out/"cases"),("privateWorkMount","rw",out)):
            left, right = doc[key].split(" - ")
            escaped = str(mount).replace("\\", "\\134").replace(" ", "\\040").replace("\t", "\\011").replace("\n", "\\012")
            assert left.split()[4] == escaped and left.split()[5].split(",")[0] == access and right.startswith("tmpfs ")
        assert doc["baseline"] == "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
        assert doc["casingProfile"] == dict(tableSha256=sha256(tab).hexdigest(),scannedScalars=1112064,
                                            changedScalars=len(scalar),contextBatchChecked=True)
        assert len(doc["cases"]) == 8
        case_sources = json.loads((corpus/"writer-older/manifest.json").read_bytes())["sources"]
        assert doc["sources"] == case_sources
        builds.add(tuple(doc[k] for k in ("readerSha256","storeSha256","corelibSha256","corelibBuild")))
        maps[profile], reads[profile] = scalar, doc["cases"]
    assert len(builds) == 1
    signals, donors, newrows, lookups, listings, history = {}, {}, 0, 0, 0, 0
    for donor, bucket in zip(PROFILES, ("older","current"), strict=True):
        for mode in ("sensitive","insensitive"):
            file = corpus/("writer-"+bucket)/(mode+".db")
            schema, previous = snapshot(file)
            for chosen in PROFILES:
                name = f"{donor}-{mode}-{chosen}"
                db = out/"cases"/name/"inserted.db"
                receipt = json.loads((db.parent/"receipt.json").read_bytes())
                checksum = sha256(db.read_bytes()).hexdigest()
                assert receipt["after"] == checksum and receipt["before"] == sha256(file.read_bytes()).hexdigest()
                assert receipt["mode"] == mode and receipt["chosenProfile"] == chosen
                structure, tables = snapshot(db)
                assert structure == schema
                chosen_map = maps[chosen] if mode=="insensitive" else {}
                expected = [dict(account_scope=PRIMARY,source_path=s,source_key=s.translate(chosen_map),relative_path=r,
                            relative_path_key=r.translate(chosen_map),asset_id=a,album_name="Synthetic insert",
                            file_size=83,last_write_time_utc=STAMP,direction=1,status=0,last_synchronized_at_utc=STAMP,
                            tombstone_expires_at_utc=None) for s,r,a in ENTRIES]
                assert all(not row["relative_path"].startswith("New/") for row in previous["sync_entries"])
                assert tables == previous | {"sync_entries":previous["sync_entries"] + expected}
                newrows += len(expected)
                donors[name] = {"before":receipt["before"],"after":checksum,
                                "storedKeys":[[r["source_key"],r["relative_path_key"],r["asset_id"]] for r in expected]}
                for reader, cmap in maps.items():
                    if mode == "sensitive":
                        cmap = {}
                    actual = reads[reader][name]
                    copy = out/("reader-"+reader)/(name+".db")
                    assert actual["digest"] == checksum and actual["readerCopySha256"] == sha256(copy.read_bytes()).hexdigest()
                    assert snapshot(copy) == (structure,tables)
                    with closing(sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1", uri=True)) as sql:
                        sql.row_factory = sqlite3.Row
                        queries = [(PRIMARY,s,r) for s,r in ((STABLE,"New/Stable.jpg"),(STABLE,"New/Only-ƛ.jpg"),
                            (STABLE,"New/Only-Ƛ.jpg"),(SPLIT,"New/Source.jpg"),(SPLIT.replace("ƛ","Ƛ"),"New/Source.jpg"))]
                        queries.append((OTHER,STABLE,"New/Stable.jpg"))
                        responses = []
                        for account, source, relative in queries:
                            rows = sql.execute("SELECT * FROM sync_entries WHERE account_scope=? AND source_key=? "
                                "AND relative_path_key=?", (account,source.translate(cmap),relative.translate(cmap))).fetchall()
                            assert len(rows) <= 1
                            responses.append(identity(rows[0]) if rows else None)
                        assert actual["lookups"] == responses
                        lists = []
                        for account, source in ((PRIMARY,STABLE),(PRIMARY,SPLIT),(PRIMARY,SPLIT.replace("ƛ","Ƛ")),(OTHER,STABLE)):
                            rows = sql.execute("SELECT * FROM sync_entries WHERE account_scope=? AND source_key=? "
                                "ORDER BY relative_path_key", (account,source.translate(cmap)))
                            lists.append([identity(row) for row in rows])
                        assert actual["lists"] == lists
                        for key,account in (("history",PRIMARY),("otherHistory",OTHER)):
                            assert actual[key] == sql.execute("SELECT last_successful_sync_utc FROM sync_account_status "
                                                            "WHERE account_scope=?", (account,)).fetchone()[0]
                    lookups += 6
                    listings += 4
                    history += 2
                    signal = {"originalStable":responses[0] is not None,"originalRelative":responses[1] is not None,
                              "alternateRelative":responses[2] is not None,"originalSource":responses[3] is not None,
                              "alternateSource":responses[4] is not None,"otherAccount":responses[5] is not None,
                              "relativeListedAtOriginalSource":any(r["AssetId"]=="Insert-Asset-B" for r in lists[0]),
                              "sourceListedAtOriginalSource":any(r["AssetId"]=="Insert-Asset-C" for r in lists[1])}
                    signal_key = f"{mode}-{chosen}-{reader}"
                    assert signals.setdefault(signal_key, signal) == signal
                    same = mode=="sensitive" or reader==chosen
                    assert signal["originalStable"] and not signal["otherAccount"] and signal["relativeListedAtOriginalSource"]
                    assert signal["originalRelative"] == signal["originalSource"] == signal["sourceListedAtOriginalSource"] == same
                    assert signal["alternateRelative"] == signal["alternateSource"] == (mode=="insensitive" and chosen=="17.0.0")
    return {"format":"ifw-new-entry-differential-v1","trials":donors,"observed":signals,"rustInsertedRows":newrows,
            "csharpLookupsCompared":lookups,"csharpListsCompared":listings,"csharpHistoryCompared":history,
            "readerBuilds":list(next(iter(builds)))}
