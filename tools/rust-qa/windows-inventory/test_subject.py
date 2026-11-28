"""Rebuild the Windows worker inputs from their shared review before native compilation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import subject


class WorkerStagingTests(unittest.TestCase):
    def test_reviewed_worker_stages_with_windows_adapter(self):
        with TemporaryDirectory() as temporary:
            worker = subject.stage_workspace(Path(temporary))
            original = subject.ORIGINAL
            for name in ("Cargo.toml", "Cargo.lock"):
                self.assertEqual((worker / name).read_bytes(), (original / name).read_bytes())
            self.assertEqual((worker / "src/windows_profile.rs").read_bytes(),
                             (subject.HERE / "windows_profile.rs").read_bytes())
            entry = (worker / "src/main.rs").read_text(encoding="utf-8")
            self.assertIn("let input = windows_input()?;", entry)
            self.assertIn("inventory_release()?;", entry)

    def test_each_required_worker_input_remains_pinned(self):
        with TemporaryDirectory() as temporary:
            area = Path(temporary)
            profile = area / "review.json"
            review = json.loads(subject.WORKER_PROFILE.read_bytes())
            for name in ("src/main.rs", "Cargo.lock", "Cargo.toml"):
                key = (subject.ORIGINAL / name).relative_to(subject.ROOT).as_posix()
                for changed in ({**review, key: "0" * 64}, {k: v for k, v in review.items() if k != key}):
                    with self.subTest(name=name, missing=key not in changed), patch.object(subject, "WORKER_PROFILE", profile):
                        profile.write_text(json.dumps(changed), encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, "approved worker source"):
                            subject.stage_workspace(area)
                        self.assertFalse((area / "tools").exists())


if __name__ == "__main__":
    unittest.main()
