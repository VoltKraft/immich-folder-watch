"""Check the staged-image deletion boundary and its actual Windows sharing refusal."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
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
                    self.assertEqual((path, delete), (subject, True))
                    return opened(10)
                index = [GUI, WORKER].index(path.name) + 1
                if delete:
                    self.assertTrue({10, 20 + index} <= alive)
                    self.assertTrue({11, 12}.isdisjoint(alive))
                return opened((30 if delete else 10) + index)
            def witness(path, access, sharing, security, disposition, flags, template):
                index = [GUI, WORKER].index(Path(path).name) + 1
                self.assertTrue({10, 10 + index} <= alive)
                self.assertEqual((access, sharing, disposition, flags), (0x81, 5, 3, 0x00200000))
                return opened(20 + index)
            def dispose(handle):
                if handle == 10:
                    self.assertEqual(alive, {10})
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
            api.file_info.side_effect = lambda h: (0x10 if h == 10 else 0x80, (1, h % 10))
            api.delete_handle.side_effect = dispose
            api.close.side_effect = close
            with self.assertRaisesRegex(ValueError, "actual observation"):
                with observe.staged_images(api, root, tmp / GUI, inventory, result):
                    self.assertEqual(alive, {10, 11, 12, 21, 22})
                    raise ValueError("actual observation")
            self.assertFalse(alive)
            self.assertFalse(subject.exists())
            for row in result["stagedImageCleanup"].values():
                self.assertTrue(row["absent"] and row["dispositionAccepted"])

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
                                         observe.QA / "windows-desktop/win32.py")})
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
                    raise
            api.path_handle.side_effect = acquire
            with ThreadPoolExecutor(max_workers=1) as thread:
                with observe.staged_images(api, root, build / GUI, inventory, result) as staged:
                    other = system.path_handle(staged, False)
                    def release_after_refusal():
                        try:
                            return blocked.wait(3)
                        finally:
                            observe.release_handle(system.close, "CloseHandle(test sharing control)", other)
                    released = thread.submit(release_after_refusal)
                self.assertTrue(released.result(timeout=1))
            self.assertFalse((root / "subject").exists())
            images = result["stagedImageCleanup"]
            self.assertGreaterEqual(images[GUI]["attempts"], 2)
            self.assertEqual(images[GUI]["firstSharingViolation"]["win32Error"], 32)
            self.assertTrue(all(row["absent"] and row["dispositionAccepted"] for row in images.values()))
            self.assertEqual(len({(row["volume"], row["fileId"]) for row in images.values()}), 2)
        result["fixtureRemoved"] = not root.exists() and not build.exists()
        self.assertTrue(result["fixtureRemoved"])
        result["status"] = "passed"


if __name__ == "__main__":
    unittest.main()
