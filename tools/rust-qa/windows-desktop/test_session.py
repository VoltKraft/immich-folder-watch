"""Guard the choice of input desktop using independent, revision-bound evidence."""

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from session import TIMEOUTS, command, digest, obstruction, paths, placement, write
from test_desktop import active


def original():
    point = {"subject": {"pid": 26}, "fieldPoint": {"owned": False,
             "root": {"pid": 45, "hwnd": "0xaca", "executable": "WWAHost.exe"}}}
    return {"context": active(), "status": "observed", "subjectPid": 26,
            "before": point, "raised": copy.deepcopy(point)}


class SessionTests(unittest.TestCase):
    def test_stable_foreign_root_is_required_in_both_observations(self):
        sample = original()
        self.assertEqual(obstruction(active(), sample)["pid"], 45)
        for change in ("unlocked", "owner", "identity", "phase", "proof", "subject"):
            data = copy.deepcopy(sample)
            if change == "unlocked":
                data["context"]["wts"]["lockFlags"] = 0
            elif change == "owner":
                data["raised"]["fieldPoint"]["owned"] = True
            elif change == "identity":
                data["raised"]["fieldPoint"]["root"]["hwnd"] = "0xef"
            elif change == "phase":
                data.pop("raised")
            elif change == "proof":
                data["status"] = "failed"
            else:
                data["before"]["subject"]["pid"] = 124
            with self.subTest(change=change):
                self.assertIsNone(obstruction(active(), data))

    def test_archived_placement_cannot_be_replayed_across_jobs_or_inputs(self):
        build = {"source": "revision", "binarySha256": "binary"}
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                os.environ, GITHUB_RUN_ID="391", GITHUB_RUN_ATTEMPT="2"):
            folder = Path(temp)
            root = folder / "windows-desktop"
            (root / "original").mkdir(parents=True)
            result = dict(build, run="391", attempt="2", original={"workerExit": 0})
            write(root / "results.json", result)
            write(root / "original/observation.json", original())
            files = ("results.json", "original/observation.json")
            (root / "evidence.sha256").write_text("".join(
                f"{digest(root / name)}  {name}\n" for name in files), encoding="utf-8")
            self.assertEqual(placement(folder, build, active(), {})["executable"], "WWAHost.exe")
            with patch.dict(os.environ, GITHUB_RUN_ATTEMPT="3"):
                self.assertIsNone(placement(folder, build, active(), {}))
            self.assertIsNone(placement(folder, dict(build, binarySha256="another"), active(), {}))
            changed = original()
            changed["raised"]["fieldPoint"]["root"]["pid"] = 100
            write(root / "original/observation.json", changed)
            self.assertIsNone(placement(folder, build, active(), {}))

    def test_retained_filename_has_a_separate_placement_and_driver(self):
        target = "x86_64-pc-windows-msvc"
        canonical, retained = (command(target, case) for case in ("text", "retained-text"))
        self.assertEqual([p[-1] for p in (canonical, retained)], [target, target])
        self.assertEqual((canonical[0].parent.name, canonical[0].name), ("windows-text", "run.py"))
        self.assertEqual((retained[0].parent.name, retained[0].name), ("windows-warm-window", "filename.py"))
        self.assertNotEqual(paths(target, "text")[1], paths(target, "retained-text")[1])

    def test_only_the_reviewed_commands_are_available(self):
        for case in TIMEOUTS:
            with self.subTest(case=case):
                self.assertTrue(command("aarch64-pc-windows-msvc", case)[0].is_file())
        with self.assertRaises(ValueError):
            command("aarch64-pc-windows-msvc", "unrecognized")


if __name__ == "__main__":
    unittest.main()
