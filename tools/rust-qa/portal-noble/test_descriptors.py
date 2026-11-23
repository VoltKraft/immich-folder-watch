"""Exercise the retained-directory observer with one disposable Linux child and real descriptors."""
from contextlib import contextmanager, ExitStack
import errno
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from observe import (APP, BACKING, FIXTURE, original_fds, record_grant_at_refusal, request_attempt, retained_fds,
                     retry_failed, retry_peer, revoke_grant, save)


CHILD = """
import os
from pathlib import Path
import sys
root = Path(sys.argv[1])
flags = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_RDONLY
grant = os.open(root, flags)
album = os.open(root / "album", flags)
other = os.open(root / "unreported-private-leaf", os.O_RDONLY)
print("ready", flush=True)
for line in sys.stdin:
    if line == "missing\\n":
        os.close(album)
    elif line == "regular\\n":
        os.dup2(other, album, inheritable=False)
    elif line == "temporary\\n":
        original = os.dup(album)
        os.dup2(other, album, inheritable=False)
    elif line == "restore\\n":
        os.dup2(original, album, inheritable=False)
        os.close(original)
    elif line == "replaced\\n":
        (root / "album").rename(root / "moved")
        (root / "album").mkdir()
        replacement = os.open(root / "album", flags)
        os.dup2(replacement, album, inheritable=False)
        os.close(replacement)
    elif line == "renamed\\n":
        (root / "album").rename(root / "unreported-alias")
    elif line == "stop\\n":
        break
    print("done", flush=True)
"""


@contextmanager
def child(root):
    (root / "album").mkdir()
    (root / "unreported-private-leaf").write_bytes(FIXTURE)
    with subprocess.Popen([sys.executable, "-B", "-c", CHILD, root], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as proc:
        try:
            if proc.stdout.readline() != "ready\n":
                raise RuntimeError("Synthetic peer did not start")
            yield proc
        finally:
            if proc.poll() is None:
                proc.stdin.write("stop\n")
                proc.stdin.flush()
                proc.wait(timeout=5)


@unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux procfs")
class Descriptors(unittest.TestCase):
    def test_name_and_permission_diagnostics_preserve_a_failed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            grant = root / "grant"
            grant.mkdir()
            (grant / "album").mkdir()
            file = root / "result.json"
            phase = "verify directories before attempt 2"
            result = {"retryObservation": {"phase": phase}}
            lookup = Mock(return_value=(os.fsencode(BACKING) + b"\0", {APP: ["read", "write"], "other-app": ["delete"]}))
            with record_grant_at_refusal(grant, lookup, result, file):
                pass
            lookup.assert_not_called()
            self.assertFalse(file.exists())
            original = ValueError("original descriptor name changed")
            with self.assertRaises(ValueError) as caught:
                with record_grant_at_refusal(grant, lookup, result, file):
                    raise original
            self.assertIs(caught.exception, original)
            lookup.assert_called_once_with()
            receipt = json.loads(file.read_bytes())["retryObservation"]["grantAtRefusal"]
            self.assertEqual(receipt["phase"], phase)
            for role, path in (("grant", grant), ("album", grant / "album")):
                item = path.lstat()
                self.assertEqual(receipt["names"][role], dict(typeBits=stat.S_IFDIR, device=item.st_dev, inode=item.st_ino))
            self.assertEqual(receipt["documentInfo"], {"expectedBacking": True, "read": True, "write": True})
            self.assertNotIn(b"other-app", file.read_bytes())

    def test_missing_names_and_permission_read_failures_are_recorded_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            grant = root / "missing"
            file = root / "result.json"
            result = {"retryObservation": {"phase": "verify directories after attempts"}}
            lookup = Mock(side_effect=PermissionError("private detail"))
            with self.assertRaisesRegex(ValueError, "original observation"):
                with record_grant_at_refusal(grant, lookup, result, file):
                    raise ValueError("original observation")
            lookup.assert_called_once_with()
            receipt = json.loads(file.read_bytes())["retryObservation"]["grantAtRefusal"]
            self.assertEqual(receipt["names"], {"grant": {"errno": errno.ENOENT}, "album": {"parentUnavailable": True}})
            self.assertEqual(receipt["documentInfo"]["errorType"], "PermissionError")
            self.assertNotIn(b"private detail", file.read_bytes())
            grant.mkdir()
            (grant / "album").symlink_to(root)
            with self.assertRaisesRegex(ValueError, "original observation"):
                with record_grant_at_refusal(grant, lambda: (b"/unreported-origin", {}), result, file):
                    raise ValueError("original observation")
            receipt = json.loads(file.read_bytes())["retryObservation"]["grantAtRefusal"]
            self.assertEqual(receipt["names"]["album"]["typeBits"], stat.S_IFLNK)
            self.assertEqual(receipt["documentInfo"], {"expectedBacking": False, "read": False, "write": False})
            self.assertNotIn(b"unreported-origin", file.read_bytes())

    def setUp(self):
        with open(sys.executable, "rb") as executable:
            self.sha = hashlib.file_digest(executable, "sha256").hexdigest()

    def test_real_directory_slots_survive_and_the_failure_stage_keeps_original_evidence(self):
        for change in (None, "missing", "regular", "replaced", "renamed"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                file = root / "observation.json"
                paths = {"grant": root, "album": root / "album"}
                trace = {"before": {}, "after": {}, "phase": "verify directories after attempts", "lastVerified": "attempt 3"}
                result = {"retryObservation": trace}
                with child(root) as proc, retry_peer(proc.pid, proc, self.sha) as peer:
                    before = retained_fds(peer, paths, trace["before"])
                    for role, path in paths.items():
                        row, = trace["before"]["named"][role]
                        self.assertEqual((row["fd"], row["link"], row["fileType"], row["device"], row["inode"]),
                                         (before[str(path)]["fd"], role, "directory", path.stat().st_dev, path.stat().st_ino))
                        info = (peer / "fdinfo" / str(row["fd"])).read_text().splitlines()
                        mount = [line.split()[1] for line in info if line.startswith("mnt_id:")]
                        self.assertEqual(row.get("mountId"), int(mount[0]) if mount else None)
                        self.assertTrue(all(row["openFlags"].values()))
                        required = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
                        self.assertEqual(int(row["flags"], 8) & required, required)
                    trace["beforeAttempts"] = [{"attempt": n, "originals": original_fds(peer, paths, before)} for n in (1, 2, 3)]
                    save(file, result)
                    old = json.loads(file.read_bytes())["retryObservation"]
                    if change is None:
                        self.assertEqual(retained_fds(peer, paths, trace["after"], before), before)
                        continue
                    proc.stdin.write(change + "\n")
                    proc.stdin.flush()
                    self.assertEqual(proc.stdout.readline(), "done\n")
                    with self.assertRaises(ValueError) as failure:
                        retained_fds(peer, paths, trace["after"], before)
                    retry_failed(file, result, failure.exception, peer, paths, before)
                    saved = json.loads(file.read_bytes())
                    self.assertEqual(saved["status"], "failed")
                    actual = saved["retryObservation"]
                    self.assertEqual(actual["before"], old["before"])
                    self.assertEqual(actual["beforeAttempts"], old["beforeAttempts"])
                    self.assertEqual((actual["failure"]["phase"], actual["failure"]["lastVerified"]),
                                     ("verify directories after attempts", "attempt 3"))
                    self.assertEqual(actual["failure"]["originals"], actual["after"]["originals"])
                    after = actual["after"]["originals"]["album"]
                    original, = old["before"]["named"]["album"]
                    self.assertEqual(after["fd"], original["fd"])
                    if change == "missing":
                        self.assertEqual(after, {"fd": original["fd"], "linkErrno": errno.ENOENT, "statErrno": errno.ENOENT,
                                                "fdinfoErrno": errno.ENOENT})
                    elif change == "regular":
                        self.assertEqual((after["fileType"], after["link"]), ("regular", "other"))
                    elif change == "replaced":
                        self.assertEqual(after["link"], "album")
                        self.assertNotEqual(after["inode"], original["inode"])
                    else:
                        self.assertEqual((after["link"], after["inode"]), ("other", original["inode"]))
                    self.assertNotIn("unreported-", file.read_text())

    def test_transient_substitution_fails_before_request_even_when_the_final_slot_is_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "observation.json"
            paths = {"grant": root, "album": root / "album"}
            trace = {"before": {}, "beforeAttempts": [], "lastVerified": "verify original directories"}
            result = {"retryObservation": trace}
            with child(root) as proc, retry_peer(proc.pid, proc, self.sha) as peer:
                before = retained_fds(peer, paths, trace["before"])
                pipe = Mock(wraps=proc.stdin)
                request_attempt(pipe, 1, peer, paths, before, result, file)
                self.assertEqual(proc.stdout.readline(), "done\n")
                trace["lastVerified"] = "attempt 1"
                proc.stdin.write("temporary\n")
                proc.stdin.flush()
                self.assertEqual(proc.stdout.readline(), "done\n")
                pipe.reset_mock()
                with self.assertRaisesRegex(ValueError, "changed before a retry") as failure:
                    request_attempt(pipe, 2, peer, paths, before, result, file)
                pipe.write.assert_not_called()
                pipe.flush.assert_not_called()
                saved = json.loads(file.read_bytes())["retryObservation"]
                self.assertEqual(saved["phase"], "verify directories before attempt 2")
                self.assertEqual(saved["lastVerified"], "attempt 1")
                first, second = saved["beforeAttempts"]
                self.assertEqual(first["originals"]["album"]["fileType"], "directory")
                self.assertEqual(second["originals"]["album"]["fileType"], "regular")
                retry_failed(file, result, failure.exception, peer, paths, before)
                proc.stdin.write("restore\n")
                proc.stdin.flush()
                self.assertEqual(proc.stdout.readline(), "done\n")
                self.assertEqual(retained_fds(peer, paths, {}, before), before)
                self.assertEqual(json.loads(file.read_bytes())["status"], "failed")

    def test_only_the_launched_peer_with_both_private_pipes_and_its_original_image_qualifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "first").mkdir()
            (root / "second").mkdir()
            with child(root / "first") as first, child(root / "second") as second:
                with self.assertRaisesRegex(ValueError, "control pipes"), retry_peer(first.pid, second, self.sha):
                    self.fail("Accepted another pipe")
                with self.assertRaisesRegex(ValueError, "selected Rust reader"), retry_peer(first.pid, first, "0" * 64):
                    self.fail("Accepted another image")

    def test_each_pre_attempt_slot_identity_and_flag_is_required_before_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "observation.json"
            paths = {"grant": root, "album": root / "album"}
            with child(root) as proc, retry_peer(proc.pid, proc, self.sha) as peer:
                before = retained_fds(peer, paths, {})
                slots = original_fds(peer, paths, before)
                for key, wrong in (("fd", -1), ("device", -1), ("inode", -1), ("flags", "0"),
                                   ("fileType", "regular"), ("link", "album")):
                    bad = {**slots, "grant": {**slots["grant"], key: wrong}}
                    trace = {"lastVerified": "attempt 1", "beforeAttempts": []}
                    pipe = Mock()
                    with (self.subTest(key=key), patch("observe.original_fds", return_value=bad),
                          self.assertRaisesRegex(ValueError, "changed before a retry")):
                        request_attempt(pipe, 2, peer, paths, before, {"retryObservation": trace}, file)
                    checked, = json.loads(file.read_bytes())["retryObservation"]["beforeAttempts"]
                    self.assertEqual(checked["originals"]["grant"][key], wrong)
                    pipe.write.assert_not_called()

    def test_explicit_revocation_records_cleanup_after_a_failed_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            grant, backing, report = root / "grant", root / "backing", root / "observation.json"
            grant.mkdir()
            backing.write_bytes(FIXTURE)
            result = {"status": "failed", "retryObservation": {"failure": {"phase": "verify directories after attempts"}}}
            calls = []
            def call(method, args):
                self.assertEqual(args, ("token", "app", ["read", "write"]))
                calls.append(method)
                grant.rmdir()
            with self.assertRaisesRegex(ValueError, "original failure"), ExitStack() as stack:
                stack.callback(calls.append, "Delete")
                stack.push(partial(revoke_grant, call, ("token", "app", ["read", "write"]), grant, backing, result, report))
                raise ValueError("original failure")
            self.assertEqual(calls, ["RevokePermissions", "Delete"])
            saved = json.loads(report.read_bytes())
            self.assertTrue(saved["revoked"] and saved["contentUnchanged"])
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["retryObservation"], result["retryObservation"])
            grant.mkdir()
            unconfirmed = {}
            with self.assertRaisesRegex(ValueError, "readback"):
                revoke_grant(lambda *_: None, (), grant, backing, unconfirmed, report, None, None, None)
            self.assertFalse(json.loads(report.read_bytes())["revocation"]["grantAbsent"])
            self.assertEqual(unconfirmed["status"], "failed")
            self.assertNotIn("revoked", unconfirmed)

    def test_combined_failure_preserves_the_primary_exception_and_independent_cleanup_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backing, grant, file = root / "backing", root / "grant", root / "observation.json"
            backing.write_bytes(FIXTURE)
            grant.mkdir()
            result = {"retryObservation": {"phase": "verify directories before attempt 2"}}
            primary = RuntimeError("Original reader failure")
            refused = Mock(side_effect=PermissionError(errno.EACCES, "Refused synthetic revocation"))
            with self.assertRaises(RuntimeError) as captured, ExitStack() as stack:
                stack.push(partial(revoke_grant, refused, (), grant, backing, result, file))
                raise primary
            self.assertIs(captured.exception, primary)
            saved = json.loads(file.read_bytes())
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["primaryFailure"]["type"], "RuntimeError")
            self.assertEqual(saved["primaryFailure"]["phase"], result["retryObservation"]["phase"])
            cleanup = saved["revocation"]
            self.assertEqual(cleanup["failures"]["callReturned"]["errno"], errno.EACCES)
            self.assertIn("grantAbsent", cleanup["failures"])
            self.assertFalse(cleanup["callReturned"] or cleanup["grantAbsent"])
            self.assertTrue(cleanup["backingRead"] and cleanup["backingUnchanged"])
            self.assertNotIn("revoked", saved)

    def test_late_backing_read_failure_leaves_both_completed_revocation_checks_on_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            grant, file = root / "grant", root / "observation.json"
            grant.mkdir()
            result = {}
            def revoke(*_):
                grant.rmdir()
            def unavailable():
                saved = json.loads(file.read_bytes())["revocation"]
                self.assertTrue(saved["callReturned"] and saved["grantAbsent"])
                self.assertFalse(saved["backingRead"])
                raise FileNotFoundError(errno.ENOENT, "Missing synthetic backing")
            backing = Mock(read_bytes=unavailable)
            with self.assertRaises(FileNotFoundError):
                revoke_grant(revoke, (), grant, backing, result, file, None, None, None)
            saved = json.loads(file.read_bytes())
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["revocation"]["failures"]["backingUnchanged"]["errno"], errno.ENOENT)
            self.assertIsNone(saved["revocation"]["backingUnchanged"])
            self.assertNotIn("revoked", saved)


if __name__ == "__main__":
    unittest.main()
