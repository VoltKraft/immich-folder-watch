"""Controls for separating Cargo's Windows compile output from local execution."""

import json
from pathlib import Path
import runpy
import unittest


RUNNER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "rust-qa/windows-local/workspace.py"))


class WorkspaceTransferTests(unittest.TestCase):
    def test_only_executable_test_targets_are_transferred(self):
        artifact = {"reason": "compiler-artifact", "package_id": "safe-fs", "profile": {"test": True},
                    "target": {"name": "handles", "kind": ["test"]}, "executable": r"D:\build\handles-abc.exe"}
        messages = [{"reason": "build-finished", "success": True}, dict(artifact, executable=None),
                    dict(artifact, profile={"test": False}), artifact]
        stream = "\n".join(map(json.dumps, messages))
        self.assertEqual(list(RUNNER["harnesses"](stream)), ["handles-abc.exe"])
        with self.assertRaises(ValueError):
            RUNNER["harnesses"](stream + "\n" + json.dumps(artifact))

    def test_guest_requires_an_actual_libtest_summary(self):
        line = b"test result: ok. 11 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.1s\r\n"
        self.assertEqual(RUNNER["test_counts"](line), {"passed": 11, "failed": 0, "ignored": 1, "measured": 0, "filtered": 0})
        self.assertIsNone(RUNNER["test_counts"](b""))
        self.assertIsNone(RUNNER["test_counts"](line + line))
