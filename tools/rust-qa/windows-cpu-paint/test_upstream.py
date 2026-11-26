"""Exercise offline archives, exact notice bytes, corrupted input and atomic reuse."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import upstream


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"
        self.pins = self.root / "pins.json"
        self.notice = self.root / "original-license"
        self.notice.write_bytes(b"Original notice\r\n")
        self.enterContext(patch.object(upstream, "PINS", self.pins))
        self.enterContext(patch.object(upstream, "ROOT", self.root))
        self.network = self.enterContext(patch.object(upstream.ARCHIVES, "open"))
        self.name = "probe"
        self.stem = "probe-1.0.0"
        self.seed = self.cache / "archives" / (self.stem + ".crate")
        self.url = "https://static.crates.io/crates/probe/probe-1.0.0.crate"
        self.src = b"fn sample() {}\r\n"
        self.archive()

    def archive(self, extra=None):
        original = [(".cargo_vcs_info.json", b'{"git":{"sha1":"original"}}'),
                    ("src/lib.rs", self.src), ("LICENSE", b"Original MIT\r\n")]
        if extra:
            original.append(extra)
        output = BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as tar:
            for name, data in original:
                entry = tarfile.TarInfo(self.stem + "/" + name)
                entry.size = len(data)
                tar.addfile(entry, BytesIO(data))
        self.raw = output.getvalue()
        self.rows = {
            "packages": {self.name: {"version": "1.0.0", "sha256": upstream.digest(self.raw),
                         "bytes": len(self.raw), "files": len(original),
                         "unpackedBytes": sum(len(s) for _, s in original), "vcsCommit": "original"}},
            "notices": {"original": {"repositoryFile": self.notice.name,
                                     "sha256": upstream.digest(self.notice.read_bytes())},
                        "package": {"archiveMember": [self.name, "LICENSE"],
                                    "sha256": upstream.digest(b"Original MIT\r\n")}}}
        self.pins.write_text(json.dumps(self.rows), encoding="utf-8")

    def write_seed(self):
        self.seed.parent.mkdir(parents=True, exist_ok=True)
        self.seed.write_bytes(self.raw)

    def response(self, data, url):
        result = BytesIO(data)
        result.geturl = lambda: url
        self.network.return_value = result

    def test_requires_explicit_seed_and_rechecks_offline(self):
        with self.assertRaises(FileNotFoundError):
            upstream.prepare(self.cache)
        self.network.assert_not_called()
        self.response(self.raw, self.url)
        result = upstream.prepare(self.cache, fetch=True)
        self.assertEqual(self.seed.read_bytes(), self.raw)
        self.assertEqual((result.sources["probe"] / "src/lib.rs").read_bytes(), self.src)
        self.assertEqual((result.notices / "original").read_bytes(), self.notice.read_bytes())
        self.assertEqual((result.notices / "package").read_bytes(), b"Original MIT\r\n")
        self.assertEqual(json.loads(result.receipt.read_bytes())["archiveSha256"]["probe"], upstream.digest(self.raw))
        self.network.reset_mock()
        self.assertEqual(upstream.prepare(self.cache), result)
        self.network.assert_not_called()

    def test_refuses_redirect_digest_and_size_before_caching(self):
        for data, url in ((self.raw, self.url + "?elsewhere"), (b"-" * len(self.raw), self.url),
                          (self.raw + b"x", self.url)):
            with self.subTest(url=url, length=len(data)):
                self.response(data, url)
                with self.assertRaises(ValueError):
                    upstream.prepare(self.cache, fetch=True)
                self.assertFalse(self.seed.exists())
                self.assertEqual(list(self.cache.glob("prepared-*")), [])

    def test_redirect_handler_stops_before_requesting_another_url(self):
        with self.assertRaises(ValueError):
            upstream.OriginOnly().redirect_request(None, None, 302, "Found", {}, "https://example.org")

    def test_corrupt_seed_is_retained_and_never_downloaded_again(self):
        self.write_seed()
        self.seed.write_bytes(b"x" * len(self.raw))
        with self.assertRaises(ValueError):
            upstream.prepare(self.cache, fetch=True)
        self.network.assert_not_called()
        self.assertEqual(self.seed.read_bytes(), b"x" * len(self.raw))

    def test_repo_and_archive_notices_must_match_original_bytes(self):
        self.write_seed()
        self.notice.write_bytes(self.notice.read_bytes().replace(b"\r\n", b"\n"))
        with self.assertRaises(ValueError):
            upstream.prepare(self.cache)
        self.notice.write_bytes(b"Original notice\r\n")
        self.rows["notices"]["package"]["sha256"] = "0" * 64
        self.pins.write_text(json.dumps(self.rows), encoding="utf-8")
        with self.assertRaises(ValueError):
            upstream.prepare(self.cache)

    def test_archive_path_traversal_and_duplicate_are_refused(self):
        for name in ("../outside", "src/lib.rs"):
            with self.subTest(name=name):
                self.archive((name, b"extra"))
                self.write_seed()
                with self.assertRaises(ValueError):
                    upstream.prepare(self.cache)
                self.assertFalse((self.cache / "outside").exists())
                self.assertEqual(list(self.cache.glob("prepared-*")), [])

    def test_concurrent_prepare_and_existing_tree_tamper(self):
        self.write_seed()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: upstream.prepare(self.cache), range(4)))
        self.assertTrue(all(r == results[0] for r in results))
        src = results[0].sources["probe"] / "src/lib.rs"
        extra = src.with_name("extra.rs")
        extra.write_bytes(b"unreviewed")
        with self.assertRaises(ValueError):
            upstream.prepare(self.cache)
        extra.unlink()
        src.write_bytes(self.src.replace(b"sample", b"opaque"))
        with self.assertRaises(ValueError):
            upstream.prepare(self.cache)
        src.unlink()
        with self.assertRaises(ValueError):
            upstream.prepare(self.cache)
        self.network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
