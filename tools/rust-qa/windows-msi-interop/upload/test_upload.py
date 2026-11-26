"""Portable checks of the installed WPF upload evidence and interrupted restore."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import shutil
import socket
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch

from shared import ROOT, backup, configuration, endpoint_port, peer
from database import main_rows, replay_pair, restore
from upload.readback import asset_history, database_rows
from owners import decode_connection, select_connection


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.out, self.profile = self.area / "archive", self.area / "profile"
        self.out.mkdir()
        self.profile.mkdir()
        self.db = self.profile / "sync-state.db"

    def start_store(self):
        store = sqlite3.connect(self.db)
        self.addCleanup(store.close)
        sql = (ROOT / "rust/tests/fixtures/legacy/windows/sqlite/sensitive.sql").read_text(encoding="utf-8")
        store.executescript(sql.split("INSERT INTO")[0] + "PRAGMA user_version=1; COMMIT;")
        store.execute("PRAGMA journal_mode=WAL")
        return store

    def insert(self, store):
        values = ("account", "source", "SOURCE", peer.FILENAME, peer.FILENAME.upper(), peer.ASSET_ID, "",
                  len(peer.IMAGE), "2026-01-01", 0, 0, "2026-01-02", None)
        store.execute("INSERT INTO sync_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        store.execute("INSERT INTO sync_account_status VALUES (?,?)", ("account", "2026-01-02"))
        store.commit()

    def returned(self, store):
        with closing(sqlite3.connect(self.out / "installed-returned.db")) as output:
            store.backup(output)
            self.assertEqual(output.execute("PRAGMA journal_mode=DELETE").fetchone(), ("delete",))

    def test_original_wal_and_rust_shape(self):
        store = self.start_store()
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as reader:
            reader.execute("BEGIN")
            self.assertEqual(reader.execute("SELECT count(*) FROM sync_entries").fetchone(), (0,))
            self.insert(store)
            self.returned(store)
            for suffix in ("", "-wal"):
                shutil.copyfile(self.profile / ("sync-state.db" + suffix), self.out / ("source.db" + suffix))
            self.assertEqual(main_rows(self.out / "source.db"), 0)
            whole = replay_pair(self.out, "source.db")
            self.assertEqual(whole, backup.snapshot(self.out / "installed-returned.db", standalone=True))
            database_rows(whole, "account", "source", [(peer.FILENAME, peer.ASSET_ID, peer.IMAGE)])
            with self.assertRaises(ValueError):
                database_rows(whole, "account", "wrong source", [(peer.FILENAME, peer.ASSET_ID, peer.IMAGE)])

    def test_failed_profile_commit_restores_every_original(self):
        store = self.start_store()
        self.insert(store)
        self.returned(store)
        store.close()
        # Keep a second, well-defined SQLite companion to exercise partial progress.
        (self.profile / "sync-state.db-journal").write_bytes(b"")
        initial = {p.name: p.read_bytes() for p in self.profile.iterdir()}
        rename = Path.rename
        def fail_final(path, target):
            if path.name == "returned":
                raise OSError("injected final rename failure")
            return rename(path, target)
        with patch.object(Path, "rename", fail_final), self.assertRaisesRegex(OSError, "injected"):
            restore(self.profile, self.out)
        self.assertEqual({p.name: p.read_bytes() for p in self.profile.iterdir()}, initial)
        self.assertEqual({p.name: p.read_bytes() for p in (self.out / "original-after-quit").iterdir()}, initial)

    def test_archive_failure_leaves_original_files_untouched(self):
        store = self.start_store()
        self.insert(store)
        self.returned(store)
        store.close()
        (self.profile / "sync-state.db-journal").write_bytes(b"")
        original = {p.name: p.read_bytes() for p in self.profile.iterdir()}
        copier = shutil.copyfile
        def fail_companion(src, dest):
            if src.name.endswith("-journal"):
                raise OSError("injected copy failure")
            return copier(src, dest)
        with patch.object(shutil, "copyfile", fail_companion), self.assertRaisesRegex(OSError, "injected"):
            restore(self.profile, self.out)
        self.assertEqual({p.name: p.read_bytes() for p in self.profile.iterdir()}, original)

    def test_completed_profile_restore_uses_standalone_bytes(self):
        store = self.start_store()
        self.insert(store)
        self.returned(store)
        store.close()
        originals = restore(self.profile, self.out)
        self.assertIn("sync-state.db", originals)
        self.assertEqual(self.db.read_bytes(), (self.out / "installed-returned.db").read_bytes())
        self.assertEqual(list(self.profile.iterdir()), [self.db])

    def test_peer_connection_and_body_are_bound_to_process(self):
        mime = "multipart/form-data; boundary=ifw"
        name = peer.FILENAME
        body = (f'--ifw\r\nContent-Disposition: form-data; name="assetData"; filename="{name}"\r\n'
                'Content-Type: image/png\r\n\r\n').encode() + peer.IMAGE + b'\r\n--ifw--\r\n'
        digest = sha256(body).hexdigest()
        (self.out / "asset-post-1.body").write_bytes(body)
        (self.out / name).write_bytes(peer.IMAGE)
        address = int.from_bytes(socket.inet_aton("127.0.0.1"), "little")
        row = dict(primary=dict(pid=42), introducedNs=1, sampleNs=3, connection=struct.pack("<6I", 5, address, 0xcafe0000 | socket.htons(42001), address,
                   socket.htons(3321), 42).hex(), upload=dict(client=["127.0.0.1", 42001], server=["127.0.0.1", 3321],
                   filename=name, requestNs=2, responseNs=4, bodySha256=digest, contentType=mime))
        posts = [dict(phase="original", status=201, kind="matched-image", filename=name, bodyFile="asset-post-1.body",
                      declaredBytes=len(body), bytesRead=len(body), bodySha256=digest, client=row["upload"]["client"],
                      entryNs=1, answeredNs=5, contentType=mime)]
        def check(subject):
            asset_history(self.out, posts, [("original", name, peer.IMAGE, subject)], 3321)
        check(row)
        alternate = deepcopy(row)
        mapped = bytes.fromhex("00000000000000000000ffff7f000001")
        alternate["connection"] = struct.pack("<16sII16sIIII", mapped, 0, socket.htons(42001),
                                              mapped, 0, socket.htons(3321), 5, 42).hex()
        check(alternate)
        for key, invalid in (("sampleNs", 6), ("primary", {"pid": 43})):
            alternate = deepcopy(row)
            alternate[key] = invalid
            with self.assertRaises(ValueError):
                check(alternate)
        with self.assertRaises(ValueError):
            asset_history(self.out, posts * 2, [("original", name, peer.IMAGE, row)], 3321)
        (self.out / "asset-post-1.body").write_bytes(body[:-1])
        with self.assertRaises(ValueError):
            check(row)

    def test_native_tcp4_and_mapped_tcp6_return_the_same_held_connection(self):
        # SDK network-order addresses and ports. The upper half of each port
        # DWORD is deliberately nonzero, while the state and PID are little-endian.
        mapped = bytes.fromhex("00000000000000000000ffff7f000001")
        port1, port2 = bytes.fromhex("c000abcd"), bytes.fromhex("1f90eeff")
        state, owner = bytes.fromhex("05000000"), bytes.fromhex("56341200")
        raw4 = state + bytes.fromhex("7f000001") + port1 + bytes.fromhex("7f000001") + port2 + owner
        raw6 = mapped + bytes(4) + port1 + mapped + bytes(4) + port2 + state + owner
        accepted = dict(client=["127.0.0.1", 49152], server=["127.0.0.1", 8080])
        expected = dict(**accepted, state=5, pid=0x123456)
        self.assertEqual(decode_connection(raw4), expected)
        self.assertEqual(decode_connection(raw6), expected)
        def table(*rows):
            return struct.pack("<I", len(rows)) + b"".join(rows)
        def pick(v4, v6):
            return select_connection({socket.AF_INET: v4, socket.AF_INET6: v6}, expected["pid"], accepted)
        self.assertEqual(pick(table(raw4), None), raw4.hex())
        self.assertEqual(pick(table(), table(raw6)), raw6.hex())
        self.assertEqual(pick(table(raw4), table(raw6)), raw4.hex())
        with self.assertRaisesRegex(ValueError, "owned-hits=2"):
            pick(table(), table(raw6, raw6))
        foreign = raw6[:-4] + bytes.fromhex("65000000")
        with self.assertRaisesRegex(ValueError, "tuple-hits=1 owned-hits=0") as error:
            pick(table(raw4), table(foreign))
        self.assertNotIn("101", str(error.exception))
        with self.assertRaisesRegex(ValueError, "Truncated native"):
            pick(table(), table(raw6[:-1]))
        for start, stop, value in ((0, 16, bytes.fromhex("00000000000000000000000000000001")),
                                    (24, 40, bytes.fromhex("00000000000000000000000000000001")),
                                    (16, 20, bytes.fromhex("00000007")), (40, 44, bytes.fromhex("00000008")),
                                    (20, 24, port2), (44, 48, port1), (48, 52, bytes.fromhex("08000000"))):
            changed = raw6[:start] + value + raw6[stop:]
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "owned-hits=0"):
                pick(table(), table(changed))
        self.assertTrue(decode_connection(raw6[:16] + bytes.fromhex("00000007") + raw6[20:])["client"][0].endswith("%7"))
        with self.assertRaisesRegex(ValueError, "complete native"):
            decode_connection(raw6[:-1])

    def test_upload_profile_uses_only_loopback(self):
        self.assertEqual(endpoint_port("http://127.0.0.1:57321"), 57321)
        for bad in ("http://127.0.0.1:65536", "https://127.0.0.1:443", "http://192.0.2.1:8000"):
            with self.assertRaises(ValueError):
                endpoint_port(bad)
        self.assertIn("path: 'C:\\one''s folder'", configuration(r"C:\one's folder", "http://127.0.0.1:3211"))


if __name__ == "__main__":
    unittest.main()
