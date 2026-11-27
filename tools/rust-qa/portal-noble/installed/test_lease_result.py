"""Regression checks for mixing another installed app or losing a failed rollback."""
import json
from pathlib import Path
import tempfile
import unittest

from lease_result import backing_receipt, collect, original_backing


class InstalledLeaseResult(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.seed = self.root / "payload"
        self.seed.mkdir()
        self.out = self.root / "observations"
        self.out.mkdir()
        self.trial, self.app, self.runtime, self.reader = "a" * 32, "b" * 64, "c" * 64, "d" * 64
        (self.root / "stage").write_text("lease\n")
        (self.root / "trial-id").write_text(self.trial)
        (self.seed / "inputs.json").write_text(json.dumps({"runtime": {"commit": self.runtime}, "reader": self.reader}))
        for phase in ["stock", "candidate", "restored"]:
            backing = self.root / ("ifw-portal-" + phase) / "source/album/original.jpg"
            backing.parent.mkdir(parents=True)
            backing.write_bytes(b"Synthetic upload fixture\n")
            self.write(phase, {"status": "passed", "phase": phase, "trial": self.trial,
                               "originalBacking": original_backing(self.root, phase),
                               "app": {"id": "org.example.IfwPortalLease//test", "readerSha256": self.reader,
                                       "commit": self.app, "runtimeCommit": self.runtime}})

    def write(self, phase, value):
        (self.out / (phase + ".json")).write_text(json.dumps(value))

    def collect(self, candidate=0, restored=0):
        collect(self.seed, self.out, self.app, self.runtime, candidate, restored,
                "install ok installed 1.18.4-1ubuntu2.24.04.3", self.root)

    def result(self):
        return json.loads((self.out / "lease-result.json").read_text())

    def test_checks_every_phase_against_its_original_runtime_and_reader(self):
        self.collect()
        self.assertEqual(self.result()["status"], "passed")
        path = self.out / "candidate.json"
        original = path.read_bytes()
        for field in ("readerSha256", "commit", "runtimeCommit", "id", "phase", "trial"):
            record = json.loads(original)
            target = record if field in ("phase", "trial") else record["app"]
            target[field] = "another-source"
            self.write("candidate", record)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.collect()
            self.assertEqual(self.result()["status"], "failed")

    def test_preserves_independent_install_and_rollback_outcomes(self):
        for candidate, restored in ((1, 0), (0, 1), (1, 1)):
            with self.subTest(exits=(candidate, restored)), self.assertRaises(ValueError):
                self.collect(candidate, restored)
            result = self.result()
            self.assertEqual((result["candidateExit"], result["restoreExit"]), (candidate, restored))
            self.assertEqual(set(result["phases"]), {"stock", "candidate", "restored"})

    def test_requires_restored_observation_on_full_trial(self):
        (self.out / "restored.json").unlink()
        with self.assertRaises(ValueError):
            self.collect()
        self.assertEqual(self.result()["status"], "failed")

    def test_detects_a_replaced_original_even_with_the_same_contents(self):
        path = self.root / "ifw-portal-stock/source/album/original.jpg"
        replacement = path.with_name("replacement.jpg")
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        with self.assertRaises(ValueError):
            self.collect()
        self.assertIn("stock", self.result()["errors"])
        self.assertIn("restored", self.result()["phases"])

    def test_download_receipt_requires_the_staged_inode_after_publication(self):
        inputs = json.loads((self.seed / "inputs.json").read_text())
        inputs["downloadOperations"] = True
        (self.seed / "inputs.json").write_text(json.dumps(inputs))
        payload = b"Synthetic download fixture\n"
        for phase in ["stock", "candidate", "restored"]:
            path = self.root / ("ifw-portal-" + phase) / "source/album/download.jpg"
            path.write_bytes(payload)
            record = json.loads((self.out / (phase + ".json")).read_text())
            record["publishedBacking"] = {**backing_receipt(self.root, phase, "download.jpg", payload),
                                          "privateDirectoryMode": "0700"}
            self.write(phase, record)
        self.collect()
        self.assertEqual(set(self.result()["finalDownloads"]), {"stock", "candidate", "restored"})
        replacement = path.with_name("another.jpg")
        replacement.write_bytes(payload)
        replacement.replace(path)
        with self.assertRaises(ValueError):
            self.collect()
        self.assertIn("restored", self.result()["errors"])


if __name__ == "__main__":
    unittest.main()
