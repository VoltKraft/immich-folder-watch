"""Capture the live shipping WAL and restore only the exact standalone return."""
from contextlib import closing
from pathlib import Path
import os
import shutil
import sqlite3
import stat
import subprocess
from tempfile import TemporaryDirectory, mkdtemp

from shared import backup, require, sha


def run_helper(work, out, profile, marker, port, build, stem, *, headless=False):
    helper = work / "installed_upload_backup.exe"
    config = sha(profile / "config.yaml")
    require(sha(helper) == build["sha256"], "The pinned Windows backup helper changed")
    flags = subprocess.CREATE_NO_WINDOW if headless else 0
    result = subprocess.run([helper, str(port), config, marker, work], cwd=work, capture_output=True, timeout=20,
                            creationflags=flags)
    for name in ("stdout", "stderr"):
        (out / (stem + "." + name)).write_bytes(getattr(result, name))
    return result.returncode


def replay_pair(folder, stem):
    # Never open the retained two-file original for SQLite recovery in place.
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "copy.db"
        shutil.copyfile(folder / stem, path)
        wal = folder / (stem + "-wal")
        if wal.exists():
            shutil.copyfile(wal, path.with_name("copy.db-wal"))
        return backup.snapshot(path)


def main_rows(file):
    with closing(sqlite3.connect(file.absolute().as_uri() + "?mode=ro&immutable=1", uri=True)) as main:
        if main.execute("SELECT count(*) FROM sqlite_schema WHERE name='sync_entries'").fetchone() == (0,):
            return 0
        return main.execute("SELECT count(*) FROM sync_entries").fetchone()[0]


def live_backup(database, work, out, reader, run):
    before = backup.snapshot(database)
    require(len(before["tables"]["sync_account_status"]) == 1 and len(before["tables"]["sync_entries"]) == 1
            and reader.execute("SELECT count(*) FROM sync_entries").fetchone() == (0,),
            "The old read view and the newly committed upload are unavailable")
    originals = {}
    for suffix in ("", "-wal"):
        path = database.with_name(database.name + suffix)
        require(0 < path.stat().st_size <= 16 * 1024 * 1024, "Missing or oversized live SQLite original")
        archived = out / ("live-source.db" + suffix)
        shutil.copyfile(path, archived)
        originals[suffix] = sha(archived)
    require(run("rust-live-upload") == 0, "The live Rust backup failed")
    require(all(sha(database.with_name(database.name + s)) == h for s,h in originals.items())
            and main_rows(out / "live-source.db") == 0 and replay_pair(out, "live-source.db") == before
            and backup.snapshot(database) == before, "The original main and WAL do not reconstruct the committed upload")
    returned = work / "installed-returned.db"
    require(not list(work.glob("installed-returned.db-*")) and backup.snapshot(returned, standalone=True) == before,
            "The standalone Rust return differs from the committed original")
    shutil.copyfile(returned, out / returned.name)
    require(sha(returned) == sha(out / returned.name), "The archived Rust return changed")
    return dict(main=originals[""], wal=originals["-wal"], returned=sha(returned), pinnedRows=0)


def restore(profile, out):
    database = profile / "sync-state.db"
    preserved = out / "original-after-quit"
    preserved.mkdir()
    originals = {}
    # Archive and compare the complete ordinary post-Quit state before touching the profile.
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = profile / (database.name + suffix)
        if os.path.lexists(path):
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
                    and info.st_size <= 16 * 1024 * 1024, "Unexpected original SQLite companion")
            shutil.copyfile(path, preserved / path.name)
            originals[path.name] = sha(path)
            require(sha(preserved / path.name) == originals[path.name], "The post-Quit archive differs")
    returned = out / "installed-returned.db"
    require(database.name in originals and replay_pair(preserved, database.name) == backup.snapshot(returned, standalone=True),
            "Old WPF exited at a different state")
    candidate = Path(mkdtemp(dir=profile, prefix="restore-"))
    prepared = candidate / "returned"
    moved = []
    clean = True
    try:
        with returned.open("rb") as src, prepared.open("xb") as dest:
            shutil.copyfileobj(src, dest)
            dest.flush()
            os.fsync(dest.fileno())
        require(sha(prepared) == sha(returned) and all(sha(profile / n) == h for n,h in originals.items()),
                "The prepared return or an original changed before restoration")
        installed = False
        try:
            for name in originals:
                (profile / name).rename(candidate / name)
                moved.append(name)
            prepared.rename(database)
            installed = True
            require(sha(database) == sha(returned) and not any(profile.glob("sync-state.db-*")),
                    "The restored database differs from the Rust return")
        except BaseException:
            # If rollback itself fails, leave the same-volume originals as well as the archived copies.
            clean = False
            if installed:
                database.rename(prepared)
            for name in reversed(moved):
                (candidate / name).rename(profile / name)
            clean = True
            raise
        return originals
    finally:
        if clean:
            shutil.rmtree(candidate)
