"""Check the staged-image deletion boundary and its actual Windows sharing refusal."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import ctypes as c
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

import observe


GUI = "native-gui-assessment.exe"
WORKER = "ifw-performance-worker.exe"
IDENTITY = (73, 89)


def refusal(code):
    error = OSError(f"control error {code}")
    error.winerror = code
    return error


class StagedImages(unittest.TestCase):
    def test_only_sharing_on_open_is_retried_with_the_same_file_id(self):
        api = Mock()
        api.path_handle.side_effect = [refusal(32), 41]
        api.file_info.return_value = (0x80, IDENTITY)
        record = {}
        path = Path("subject") / GUI
        with patch.object(observe.time, "sleep"):
            observe.delete_staged_image(api, path, IDENTITY, record)
        self.assertEqual(record["attempts"], 2)
        self.assertEqual(record["firstSharingViolation"]["win32Error"], 32)
        self.assertIn("subject/" + GUI, record["firstSharingViolation"]["notes"][0])
        self.assertTrue(record["dispositionAccepted"])
        for call in api.path_handle.call_args_list:
            self.assertEqual((call.args, call.kwargs), ((path, False), {"delete": True}))
        api.delete_handle.assert_called_once_with(41)
        api.close.assert_called_once_with(41)

    def test_timeout_unexpected_error_reparse_replacement_and_disposition_are_terminal(self):
        for code in (2, 3, 5, 33):
            api = Mock()
            error = refusal(code)
            api.path_handle.side_effect = error
            with self.subTest(code=code), self.assertRaises(OSError) as caught:
                observe.delete_staged_image(api, Path("subject") / GUI, IDENTITY, {})
            self.assertIs(caught.exception, error)
            self.assertEqual(api.path_handle.call_count, 1)
            api.delete_handle.assert_not_called()
        api, record = Mock(), {}
        api.path_handle.side_effect = refusal(32)
        with (patch.object(observe.time, "monotonic", side_effect=[10., 14.99, 15.]),
              patch.object(observe.time, "sleep"), self.assertRaises(OSError) as caught):
            observe.delete_staged_image(api, Path("subject") / GUI, IDENTITY, record)
        self.assertEqual((caught.exception.winerror, record["attempts"]), (32, 1))
        for attrs, identity in ((0x80, (73, 99)), (stat.FILE_ATTRIBUTE_REPARSE_POINT, IDENTITY), (0x10, IDENTITY)):
            api = Mock()
            api.file_info.return_value = (attrs, identity)
            with self.subTest(attrs=attrs, identity=identity), self.assertRaises(observe.CleanupUnconfirmed):
                observe.delete_staged_image(api, Path("subject") / GUI, IDENTITY, {})
            api.delete_handle.assert_not_called()
            api.close.assert_called_once()
        api = Mock()
        api.file_info.return_value = (0x80, IDENTITY)
        api.delete_handle.side_effect = refusal(32)
        with self.assertRaises(OSError):
            observe.delete_staged_image(api, Path("subject") / GUI, IDENTITY, {})
        self.assertEqual(api.path_handle.call_count, 1)
        api.close.assert_called_once()

    def test_uncertain_process_cleanup_closes_pins_without_touching_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / ("ifw-rw02-" + uuid.uuid4().hex)
            root.mkdir()
            for name in (GUI, WORKER):
                (tmp / name).write_bytes(name.encode())
            inventory = {key: observe.recorder.sha(tmp / name) for key, name in (("gui", GUI), ("worker", WORKER))}
            api, result = Mock(), {"directoryDispositionWaits": []}
            api.path_handle.side_effect = [10, 11, 12]
            api.create_file.side_effect = [21, 22]
            api.file_info.side_effect = lambda h: (0x10, (1, 2)) if h == 10 else (0x80, (1, h % 10))
            with self.assertRaisesRegex(observe.CleanupUnconfirmed, "worker still active"):
                with observe.staged_images(api, root, tmp / GUI, inventory, result) as path:
                    self.assertEqual(path, root / "subject" / GUI)
                    api.close.assert_not_called()
                    raise observe.CleanupUnconfirmed("worker still active")
            api.delete_handle.assert_not_called()
            self.assertCountEqual([call.args[0] for call in api.close.call_args_list], [10, 11, 12, 21, 22])
            self.assertEqual(sorted(p.name for p in (root / "subject").iterdir()), sorted((GUI, WORKER)))
            self.assertFalse(any(row["absent"] for row in result["stagedImageCleanup"].values()))

    def test_readback_requires_exact_missing_name_and_leaves_a_replacement_alone(self):
        path = Path("subject") / GUI
        api = Mock()
        api.path_handle.side_effect = [refusal(2), refusal(3), refusal(5), 41]
        observe.require_absence(api, path)
        for code in (3, 5):
            with self.assertRaises(OSError) as caught:
                observe.require_absence(api, path)
            self.assertEqual(caught.exception.winerror, code)
        with self.assertRaisesRegex(observe.CleanupUnconfirmed, "still exists"):
            observe.require_absence(api, path)
        api.close.assert_called_once_with(41)
        api.delete_handle.assert_not_called()

    def test_staged_name_readback_retries_access_denied_and_requires_file_not_found(self):
        api, record = Mock(), {"attempts": 1}
        path = Path("subject") / GUI
        api.path_handle.side_effect = [refusal(5), refusal(5), refusal(2)]
        with patch.object(observe.time, "sleep") as sleep:
            observe.wait_for_staged_image_absence(api, path, record)
        self.assertEqual(record["attempts"], 1)
        self.assertEqual(record["nameReadback"], dict(attempts=3, timeoutMs=5000, firstWin32Error=5, lastWin32Error=2))
        self.assertEqual(sleep.call_count, 2)
        for request in api.path_handle.call_args_list:
            self.assertEqual((request.args, request.kwargs), ((path, False), {}))
        api.delete_handle.assert_not_called()

    def test_staged_name_readback_expires_and_stops_on_any_open_name_or_other_error(self):
        for outcome in (refusal(5), refusal(3), refusal(32), 41):
            with self.subTest(outcome=outcome):
                api, record = Mock(), {}
                api.path_handle.side_effect = [refusal(5), outcome]
                with (patch.object(observe.time, "monotonic", side_effect=[10., 14.98, 14.99, 15.]),
                      patch.object(observe.time, "sleep") as sleep,
                      self.assertRaises((OSError, observe.CleanupUnconfirmed)) as caught):
                    observe.wait_for_staged_image_absence(api, Path("subject") / GUI, record)
                sleep.assert_called_once()
                self.assertEqual(record["nameReadback"]["attempts"], 2)
                if isinstance(outcome, OSError):
                    self.assertIs(caught.exception, outcome)
                    self.assertEqual(record["nameReadback"]["lastWin32Error"], outcome.winerror)
                else:
                    self.assertIsInstance(caught.exception, observe.CleanupUnconfirmed)
                    api.close.assert_called_once_with(outcome)
                api.delete_handle.assert_not_called()

    def test_oversleep_does_not_allow_a_late_positive_readback(self):
        api, record = Mock(), {}
        api.path_handle.side_effect = [refusal(5), refusal(2)]
        with (patch.object(observe.time, "monotonic", side_effect=[10., 14.99, 15.1]),
              patch.object(observe.time, "sleep"), self.assertRaises(OSError) as caught):
            observe.wait_for_staged_image_absence(api, Path("subject") / GUI, record)
        self.assertEqual(caught.exception.winerror, 5)
        self.assertEqual(record["nameReadback"]["lastWin32Error"], 5)
        api.path_handle.assert_called_once()
        api.delete_handle.assert_not_called()

    def test_full_transition_retains_original_identity_until_disposition_and_requires_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / ("ifw-rw02-" + uuid.uuid4().hex)
            root.mkdir()
            for name in (GUI, WORKER):
                (tmp / name).write_bytes(name.encode())
            inventory = {key: observe.recorder.sha(tmp / name) for key, name in (("gui", GUI), ("worker", WORKER))}
            api, result = Mock(), {"directoryDispositionWaits": []}
            alive = set()
            subject = root / "subject"
            def opened(handle):
                alive.add(handle)
                return handle
            def by_name(path, directory, *, delete=False):
                if not path.exists():
                    raise refusal(2)
                if directory:
                    self.assertEqual(path, subject)
                    if delete:
                        self.assertEqual(alive, {20})
                    return opened(30 if delete else 10)
                index = [GUI, WORKER].index(path.name) + 1
                if delete:
                    self.assertTrue({10, 20 + index} <= alive)
                    self.assertTrue({11, 12}.isdisjoint(alive))
                return opened((30 if delete else 10) + index)
            def witness(path, access, sharing, security, disposition, flags, template):
                if Path(path) == subject:
                    self.assertEqual(alive, {10})
                    self.assertEqual((access, sharing, disposition, flags), (0x81, 7, 3, 0x02200000))
                    return opened(20)
                index = [GUI, WORKER].index(Path(path).name) + 1
                self.assertTrue({10, 10 + index} <= alive)
                self.assertEqual((access, sharing, disposition, flags), (0x81, 5, 3, 0x00200000))
                return opened(20 + index)
            def dispose(handle):
                if handle == 30:
                    self.assertEqual(alive, {20, 30})
                    subject.rmdir()
                else:
                    index = handle - 30
                    self.assertTrue({10, 20 + index, handle} <= alive)
                    (subject / [GUI, WORKER][index - 1]).unlink()
            def close(handle):
                alive.remove(handle)
                return True
            api.path_handle.side_effect = by_name
            api.create_file.side_effect = witness
            api.file_info.side_effect = lambda h: (0x10 if h in (10, 20, 30) else 0x80, (1, 100 + h % 10))
            api.delete_handle.side_effect = dispose
            api.close.side_effect = close
            with self.assertRaisesRegex(ValueError, "actual observation"):
                with observe.staged_images(api, root, tmp / GUI, inventory, result):
                    self.assertEqual(alive, {10, 11, 12, 21, 22})
                    raise ValueError("actual observation")
            self.assertFalse(alive)
            self.assertFalse(subject.exists())
            self.assertEqual(result["stagedDirectory"], dict(volume=1, fileId=100, removed=True))
            for row in result["stagedImageCleanup"].values():
                self.assertTrue(row["absent"] and row["dispositionAccepted"])

    def test_directory_disposition_refuses_a_replacement_or_reparse_point_during_transfer(self):
        for invalid in ((0x10, (73, 90)), (0x80, IDENTITY), (0x410, IDENTITY)):
            for changed_handle in (20, 30):
                with self.subTest(invalid=invalid, changed_handle=changed_handle):
                    api, runtime = Mock(), Mock()
                    api.create_file.return_value = 20
                    api.path_handle.return_value = 30
                    api.file_info.side_effect = lambda h: invalid if h == changed_handle else (0x10, IDENTITY)
                    with self.assertRaises(observe.CleanupUnconfirmed):
                        observe.remove_staged_directory(api, Path("subject"), IDENTITY, runtime, [])
                    if changed_handle == 20:
                        runtime.close.assert_not_called()
                        api.path_handle.assert_not_called()
                    else:
                        runtime.close.assert_called_once()
                        api.path_handle.assert_called_once_with(Path("subject"), True, delete=True)
                    self.assertCountEqual([call.args[0] for call in api.close.call_args_list],
                                          [20] if changed_handle == 20 else [20, 30])
                    api.delete_handle.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "requires native Windows file sharing and disposition")
    def test_windows_releases_real_deny_delete_handle_before_removing_staged_image(self):
        system = observe.recorder.Win32()
        machine, native = system.machine(-1)
        self.assertEqual(machine, native)
        target, = (name for name, code in observe.TARGETS.items() if code == machine)
        temp = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()).resolve(strict=True)
        profile, source = ("ifw-rw02-" + uuid.uuid4().hex for _ in range(2))
        result = dict(directoryDispositionWaits=[], target=target, status="failed", fixtureRemoved=False,
                      sources={p.relative_to(observe.ROOT).as_posix(): observe.recorder.sha(p)
                               for p in (Path(__file__).resolve(), Path(observe.__file__).resolve(),
                                         observe.QA / "windows-performance/native.py",
                                         observe.QA / "windows-performance/run.py",
                                         observe.QA / "windows-performance/build.py",
                                         observe.QA / "windows-desktop/win32.py",
                                         observe.QA / "gui/src/windows_worker.rs")})
        if observe.recorder.hosted():
            self.assertEqual(os.environ["NATIVE_TARGET"], target)
            result.update(source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
                          attempt=os.environ["GITHUB_RUN_ATTEMPT"])
            def archive():
                out = observe.ROOT / "artifacts/rust/windows-launcher-staging" / target
                out.mkdir(parents=True, exist_ok=True)
                with (out / "result.json").open("x", encoding="utf-8") as dest:
                    json.dump(result, dest, indent=2)
                    dest.write("\n")
            self.addCleanup(archive)
        with ExitStack() as stack:
            build = stack.enter_context(observe.recorder.owned_directory(system, temp, source))
            root = stack.enter_context(observe.recorder.owned_directory(system, temp, profile))
            # Match windows_worker.rs: GENERIC_READ, FILE_SHARE_READ | WRITE, OPEN_EXISTING,
            # FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT.
            flags = 0x02200000
            def worker_open(directory):
                handle = system.create_file(str(directory), 0x80000000, 3, None, 3, flags, None)
                if handle == c.c_void_p(-1).value:
                    raise c.WinError(c.get_last_error())
                return handle

            def sharing_refusal(open_handle):
                try:
                    handle = open_handle()
                except OSError as error:
                    self.assertEqual(error.winerror, 32)
                    return error.winerror
                observe.release_handle(system.close, "CloseHandle(unexpected sharing control)", handle)
                self.fail("Expected an actual sharing violation on CreateFileW")

            historical = root / "historical-stage"
            historical.mkdir()
            with ExitStack() as control:
                original = system.path_handle(historical, True, delete=True)
                control.callback(observe.release_handle, system.close, "CloseHandle(historical stage)", original)
                historical_id = observe.directory_identity(system, original)
                try:
                    refused = sharing_refusal(lambda: worker_open(historical))
                    result["historicalDirectory"] = dict(volume=historical_id[0], fileId=historical_id[1],
                        fixtureAccess=0x10080, fixtureShare=3, workerAccess=0x80000000, workerShare=3,
                        workerOpenWin32Error=refused)
                finally:
                    self.assertEqual(observe.directory_identity(system, original), historical_id)
                    observe.dispose_empty_directory(system, original, "historical-stage", historical_id,
                                                    result["directoryDispositionWaits"])
            observe.require_absence(system, historical)
            result["historicalDirectory"]["removed"] = True
            for name in (GUI, WORKER):
                shutil.copyfile(sys.executable, build / name)
            digest = observe.recorder.sha(sys.executable)
            result["sha256"] = digest
            inventory = {"gui": digest, "worker": digest}
            gui = root / "subject" / GUI
            blocked = threading.Event()
            api = Mock(wraps=system)
            def acquire(path, directory, **opts):
                try:
                    return system.path_handle(path, directory, **opts)
                except OSError as error:
                    if path == gui and opts.get("delete") and error.winerror == 32:
                        blocked.set()
                    elif path == gui and not opts and error.winerror == 5:
                        pending_lease.close()
                    raise
            api.path_handle.side_effect = acquire
            with ExitStack() as pending_lease, ThreadPoolExecutor(max_workers=1) as thread:
                with observe.staged_images(api, root, build / GUI, inventory, result) as staged:
                    child_pin = worker_open(staged.parent)
                    try:
                        attrs, identity = system.file_info(child_pin)
                        self.assertTrue(attrs & 0x10)
                        self.assertFalse(attrs & (stat.FILE_ATTRIBUTE_REPARSE_POINT | 0x40))
                        result["workerDirectoryPin"] = dict(access=0x80000000, share=3, flags=flags,
                                                           volume=identity[0], fileId=identity[1])
                    finally:
                        observe.release_handle(system.close, "CloseHandle(test worker directory pin)", child_pin)
                    result["fixtureDeleteOpenWin32Error"] = sharing_refusal(
                        lambda: system.path_handle(staged.parent, True, delete=True))
                    # Keep one real share-delete handle until the first read of the pending name.
                    pending = system.create_file(str(staged), 0x81, 5, None, 3, 0x00200000, None)
                    if pending == c.c_void_p(-1).value:
                        raise c.WinError(c.get_last_error())
                    pending_lease.callback(observe.release_handle, system.close, "CloseHandle(test pending image)", pending)
                    self.assertEqual(system.file_info(pending)[1], (
                        result["stagedImageCleanup"][GUI]["volume"], result["stagedImageCleanup"][GUI]["fileId"]))
                    other = system.path_handle(staged, False)
                    def release_after_refusal():
                        try:
                            return blocked.wait(3)
                        finally:
                            observe.release_handle(system.close, "CloseHandle(test sharing control)", other)
                    released = thread.submit(release_after_refusal)
                self.assertTrue(released.result(timeout=1))
            self.assertFalse((root / "subject").exists())
            self.assertEqual(result["stagedDirectory"], dict(volume=identity[0], fileId=identity[1], removed=True))
            images = result["stagedImageCleanup"]
            self.assertGreaterEqual(images[GUI]["attempts"], 2)
            self.assertEqual(images[GUI]["firstSharingViolation"]["win32Error"], 32)
            readback = images[GUI]["nameReadback"]
            self.assertGreaterEqual(readback["attempts"], 2)
            self.assertEqual((readback["firstWin32Error"], readback["lastWin32Error"]), (5, 2))
            self.assertTrue(all(row["absent"] and row["dispositionAccepted"] for row in images.values()))
            self.assertEqual(len({(row["volume"], row["fileId"]) for row in images.values()}), 2)
        result["fixtureRemoved"] = not root.exists() and not build.exists()
        self.assertTrue(result["fixtureRemoved"])
        result["status"] = "passed"


if __name__ == "__main__":
    unittest.main()
