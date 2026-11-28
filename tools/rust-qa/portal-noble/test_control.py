"""Regression checks for authenticated Ubuntu archive transfers, package selection and lock results."""
import errno
from email.utils import formatdate
import hashlib
from http.client import RemoteDisconnected
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError
from urllib.response import addinfourl

from inputs import POOL, SOURCE, VERSION, fetch, snapshot_url
from observe import require_result
from run import compare_services
from verify import signed_packages


class ArchiveTransfers(unittest.TestCase):
    url = "https://archive.ubuntu.com/ubuntu/pool/main/f/fixture/fixture.deb"
    body = b"checked archive bytes"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "fixture.deb"
        self.digest = hashlib.sha256(self.body).hexdigest()

    def acquire(self, download=True):
        return fetch(self.url, self.path, self.digest, download, len(self.body))

    def response(self, body, url=None):
        return addinfourl(BytesIO(body), {}, url or self.url, 200)

    def test_snapshot_uses_the_dated_signed_pool_path(self):
        stamp = "20261121T181410Z"
        self.assertEqual(snapshot_url(stamp, "pool/main/f/fixture/fixture+test~1_amd64.deb"),
                         "https://snapshot.ubuntu.com/ubuntu/20261121T181410Z/pool/main/f/fixture/fixture+test~1_amd64.deb")
        for timestamp, path in (("latest", "pool/main/f/source"), (stamp, "https://example.invalid/input"),
                                (stamp, "pool/main/../elsewhere")):
            with self.assertRaises(ValueError):
                snapshot_url(timestamp, path)

    def test_pre_header_disconnects_retry_the_same_input_then_reuse_verified_bytes(self):
        responses = [RemoteDisconnected(), RemoteDisconnected(), self.response(self.body)]
        with (
            patch("inputs.urllib.request.urlopen", side_effect=responses) as opening,
            patch("inputs.time.sleep") as delay,
            patch("inputs.tempfile.NamedTemporaryFile", wraps=tempfile.NamedTemporaryFile) as temp,
        ):
            self.assertEqual(self.acquire(), self.path)
            self.assertEqual(self.path.read_bytes(), self.body)
            self.assertEqual(self.acquire(download=False), self.path)
            self.assertEqual(self.acquire(), self.path)
            self.assertEqual(opening.call_args_list, [call(self.url, timeout=60)] * 3)
            self.assertEqual(delay.call_args_list, [call(1), call(2)])
            temp.assert_called_once_with(dir=self.path.parent)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_persistent_pre_header_disconnect_names_the_input_and_leaves_an_empty_cache(self):
        with (
            patch("inputs.urllib.request.urlopen", side_effect=RemoteDisconnected) as opening,
            patch("inputs.time.sleep") as delay,
        ):
            with self.assertRaisesRegex(RemoteDisconnected, r"fixture\.deb on all 3 attempts") as failed:
                self.acquire()
        self.assertIsInstance(failed.exception.__cause__, RemoteDisconnected)
        self.assertEqual(opening.call_count, 3)
        self.assertEqual(delay.call_count, 2)
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_snapshot_503_shares_the_disconnect_budget_and_honors_retry_after(self):
        for header, seconds in ((None, 2), ("invalid", 2), ("1", 2), ("8", 8),
                                (formatdate(1_800_000_009, usegmt=True), 9)):
            with self.subTest(header=header):
                body = BytesIO(b"temporary error page")
                error = HTTPError(self.url, 503, "Service Unavailable", {"Retry-After": header} if header else {}, body)
                with (
                    patch("inputs.urllib.request.urlopen", side_effect=[RemoteDisconnected(), error, self.response(self.body)]) as opening,
                    patch("inputs.time.time", return_value=1_800_000_000),
                    patch("inputs.time.sleep") as delay,
                ):
                    self.assertEqual(self.acquire().read_bytes(), self.body)
                    self.assertEqual(opening.call_args_list, [call(self.url, timeout=60)] * 3)
                    self.assertEqual(delay.call_args_list, [call(1), call(seconds)])
                self.assertTrue(body.closed)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])
                self.path.unlink()

    def test_persistent_503_closes_every_response_and_returns_last_status_without_creating_a_file(self):
        bodies = [BytesIO(b"service unavailable") for _ in range(3)]
        errors = [HTTPError(self.url, 503, "Service Unavailable", {}, body) for body in bodies]
        with (
            patch("inputs.urllib.request.urlopen", side_effect=errors) as opening,
            patch("inputs.time.sleep") as delay,
        ):
            with self.assertRaises(HTTPError) as failed:
                self.acquire()
            self.assertIs(failed.exception, errors[-1])
            self.assertIn("Ubuntu archive input: " + self.url, failed.exception.__notes__)
            self.assertEqual(opening.call_count, 3)
            self.assertEqual(delay.call_args_list, [call(1), call(2)])
        self.assertTrue(all(body.closed for body in bodies))
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_rejected_responses_and_body_failures_are_terminal(self):
        disconnected_body = self.response(self.body)
        disconnected_body.read = Mock(side_effect=RemoteDisconnected("body disconnected"))
        cases = (
            (HTTPError(self.url, 404, "missing", {}, None), HTTPError, "404"),
            (HTTPError(self.url, 403, "forbidden", {}, None), HTTPError, "403"),
            (HTTPError(self.url, 503, "busy", {"Retry-After": "3600"}, None), HTTPError, "503"),
            (HTTPError("https://example.invalid/input", 503, "busy", {}, None), HTTPError, "503"),
            (self.response(self.body, "https://example.invalid/fixture.deb"), ValueError, "redirect"),
            (self.response(self.body, self.url.replace("https:", "http:")), ValueError, "redirect"),
            (self.response(body=self.body + b"!"), ValueError, "Oversize"),
            (self.response(body=b"changed"), ValueError, "Unexpected Ubuntu input"),
            (disconnected_body, RemoteDisconnected, "body disconnected"),
        )
        for response, error, message in cases:
            with (
                self.subTest(message=message),
                patch("inputs.urllib.request.urlopen", side_effect=[response]) as opening,
                patch("inputs.time.sleep") as delay,
            ):
                with self.assertRaisesRegex(error, message) as failed:
                    self.acquire()
                if error is HTTPError:
                    self.assertIn("Ubuntu archive input: " + self.url, failed.exception.__notes__)
                opening.assert_called_once_with(self.url, timeout=60)
                delay.assert_not_called()
                self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_changed_cache_is_preserved_and_rejected_before_network_access(self):
        self.path.write_bytes(b"changed cache")
        with patch("inputs.urllib.request.urlopen") as opening:
            with self.assertRaisesRegex(ValueError, "Missing or changed checked input"):
                self.acquire()
            opening.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b"changed cache")


class Controls(unittest.TestCase):
    def test_failed_comparisons_preserve_their_own_evidence_and_allow_the_remaining_services(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            def probe(osroot, case, executable, reader, expected, name):
                calls.append((name, expected))
                self.assertEqual(case, root / name)
                case.mkdir()
                (case / "input.json").write_text(name)
                if name == "packaged":
                    (case / "probe.log").write_text("partial observation")
                    raise subprocess.CalledProcessError(20, ["private-observer"])
                if name == "unmodified":
                    raise subprocess.TimeoutExpired(["private-observer"], 170)
                return {"operations": 46}

            facts = {"status": "running", "results": {}}
            with patch("run.run_probe", side_effect=probe):
                with self.assertRaisesRegex(RuntimeError, "packaged, unmodified"):
                    compare_services(root, root, facts)
            self.assertEqual(calls, [("packaged", "enosys"), ("unmodified", "enosys"), ("backport", "supported")])
            saved = json.loads((root / "result.json").read_bytes())["results"]
            self.assertEqual(saved, facts["results"])
            self.assertEqual(saved["packaged"]["exitCode"], 20)
            self.assertEqual(saved["packaged"]["files"], {
                "input.json": hashlib.sha256(b"packaged").hexdigest(),
                "probe.log": hashlib.sha256(b"partial observation").hexdigest(),
            })
            self.assertEqual(saved["unmodified"]["timeoutSeconds"], 170)
            self.assertEqual(saved["unmodified"]["status"], "failed")
            self.assertEqual(saved["backport"], {"operations": 46, "status": "passed"})

    def test_refusal_and_real_conflict_are_distinct(self):
        unsupported = "REFUSED errno=38 operation=ReadLease outcome=UnsupportedFileLock action=CheckPortalFileLockSupport"
        busy = "REFUSED kind=WouldBlock operation=ReadLease outcome=FileBusy action=RetryAfterWriterRelease"
        require_result(unsupported, errno.ENOSYS, "rust")
        require_result(busy, errno.EAGAIN, "rust")
        require_result("REFUSED errno=11 runtime=10", errno.EAGAIN, "dotnet")
        for line, reason, kind in (("REFUSED errno=38", errno.EAGAIN, "dotnet"),
                ("REFUSED errno=11", errno.ENOSYS, "exclusive"), ("REFUSED errno=38", None, "rust"),
                ("REFUSED kind=WouldBlock", errno.ENOSYS, "rust"), ("REFUSED kind=WouldBlock", errno.EAGAIN, "shared"),
                ("ACQUIRED identity=1", errno.ENOSYS, "rust"), (unsupported, errno.EAGAIN, "rust"),
                (busy, errno.ENOSYS, "rust"), ("REFUSED errno=38", errno.ENOSYS, "rust"),
                ("REFUSED kind=WouldBlock", errno.EAGAIN, "rust")):
            with self.assertRaises(ValueError):
                require_result(line, reason, kind)

    def test_native_reason_must_match_the_reported_outcome_and_action(self):
        cases = ((errno.ENOSYS, "UnsupportedFileLock", "CheckPortalFileLockSupport"),
                 (errno.EOPNOTSUPP, "UnsupportedFileLock", "CheckPortalFileLockSupport"),
                 (errno.EAGAIN, "FileBusy", "RetryAfterWriterRelease"),
                 (errno.EACCES, "AccessDenied", "RestoreAuthorizedAccess"),
                 (errno.EPERM, "AccessDenied", "RestoreAuthorizedAccess"),
                 (errno.EIO, "ReadLeaseUnavailable", "InspectNativeError"))
        for number, outcome, action in cases:
            report = f"REFUSED errno={number} operation=ReadLease outcome={outcome} action={action}"
            require_result(report, number, "rust")
            for wrong in (report.replace(outcome, "Success"), report.replace(action, "IgnoreLock"),
                          report.replace("ReadLease", "RootSetup"), report + " outcome=FileBusy"):
                with self.assertRaises(ValueError):
                    require_result(wrong, number, "rust")

    def test_unsigned_bytes_or_unsigned_package_selection_cannot_supply_a_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lists = root / "var/lib/apt/lists"
            lists.mkdir(parents=True)
            prefix = "mirror_dists_noble-updates_"
            (lists / (prefix + "InRelease")).write_text("Origin: Ubuntu\n")
            control = POOL + SOURCE + "_" + VERSION + "_amd64.deb"
            item = "pool/main/t/test/test_1_amd64.deb"
            digest = "0" * 64
            content = "".join(f"Package: example\nFilename: {p}\nSHA256: {digest}\n\n" for p in (control, item)).encode()
            index = lists / (prefix + "main_binary-amd64_Packages")
            index.write_bytes(content)
            rows = {"main/binary-amd64/Packages": (hashlib.sha256(content).hexdigest(), len(content))}
            plan = [{"Filename": item, "SHA256": digest}]
            with patch("verify.signed_release", return_value=("Date: Sat, 21 Nov 2026 18:14:10 UTC\n", rows)):
                report = signed_packages(root, "amd64", plan, root)
                self.assertEqual(report["packages"][control], digest)
                self.assertEqual(report["snapshots"], {name: "20261121T181410Z" for name in (control, item)})
                with self.assertRaisesRegex(ValueError, "do not cover"):
                    signed_packages(root, "amd64", [{"Filename": item, "SHA256": "1" * 64}], root)
                index.write_bytes(content.replace(digest.encode(), b"2" * 64))
                with self.assertRaisesRegex(ValueError, "does not match"):
                    signed_packages(root, "amd64", plan, root)


if __name__ == "__main__":
    unittest.main()
