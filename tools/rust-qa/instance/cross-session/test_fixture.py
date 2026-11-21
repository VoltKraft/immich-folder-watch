"""Check cross-session qualification and rehearse the unchanged Rust guard on Linux."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from batch import eligible
from fixture import HOSTED, INSTANCE, MARKER, ROOT, guard_id, instance, subject_env, wait, write
import worker

RUSTC = ROOT / "artifacts/rust/toolchain/bin/rustc"


def rust_writer(exe, profile):
    return instance.Child([exe, "writer", profile, "unix", "0"], profile, os.environ)


def remote_posix(profile):
    if profile.name != "profile" or (profile / ".ifw-instance-fixture").read_bytes() != MARKER:
        raise ValueError("Expected the new POSIX rehearsal profile")
    os.setsid()
    print(f"POSIX_SESSION {os.getsid(0)}", flush=True)
    exe = profile.parent / "instance"
    with rust_writer(exe, profile) as busy:
        busy.expect("WRITER_BUSY")
        busy.success()
    print("REMOTE_REFUSED", flush=True)
    if input() != "ACQUIRE":
        raise ValueError("Unexpected original holder signal")
    with rust_writer(exe, profile) as holder:
        holder.expect("WRITER_HELD")
        if os.getsid(holder.proc.pid) != os.getsid(0):
            raise ValueError("The native holder did not inherit the peer's POSIX session")
        print("REMOTE_HELD", flush=True)
        if input() != "RELEASE":
            raise ValueError("Unexpected remote holder signal")
        holder.send("RELEASE")
        holder.expect("WRITER_RELEASED")
        holder.success()
    print("REMOTE_RELEASED", flush=True)


class FixtureTests(unittest.TestCase):
    def test_no_registration_without_existing_batch_right(self):
        bits = {"directAllow": False, "directDeny": False, "enabledGroupAllow": False, "groupDeny": False}
        self.assertFalse(eligible(bits))
        for allowed in ("directAllow", "enabledGroupAllow"):
            self.assertTrue(eligible({**bits, allowed: True}))
            for denied in ("directDeny", "groupDeny"):
                self.assertFalse(eligible({**bits, allowed: True, denied: True}))

    def test_controller_cannot_forward_other_job_identity(self):
        with self.assertRaises(ValueError):
            subject_env(Path.cwd(), {**HOSTED, "GITHUB_REF": "refs/heads/main"})

    def test_equal_sessions_different_account_and_elevation_stop_before_writers(self):
        with tempfile.TemporaryDirectory() as d:
            area = Path(d)
            write(area / "controller.json", {"sid": "synthetic", "controller": {"sessionId": 2}})
            for sid, session, elevated in (("wrong", 0, False), ("synthetic", 2, False), ("synthetic", 0, True)):
                with self.subTest(sid=sid, session=session, elevated=elevated), patch("worker.Accounts") as accounts:
                    accounts.return_value.identify.return_value = (sid, Path("app"), {"sessionId": session, "elevated": elevated})
                    result = {}
                    with self.assertRaises(RuntimeError):
                        worker.run(area, result)
                    self.assertEqual(result["worker"]["sessionId"], session)
                    self.assertFalse((area / "worker-ready.json").exists())

    def test_worker_failure_and_deadline_are_observable(self):
        with tempfile.TemporaryDirectory() as d:
            area = Path(d)
            with self.assertRaises(TimeoutError):
                wait(area, "missing.json", 0)
            write(area / "worker-done.json", {"passed": False, "reason": "synthetic"})
            with self.assertRaisesRegex(RuntimeError, "worker finished"):
                wait(area, "missing.json")

    @unittest.skipUnless(sys.platform == "linux" and RUSTC.is_file(), "native Linux Rust rehearsal")
    def test_real_guard_between_two_linux_process_sessions(self):
        with tempfile.TemporaryDirectory(prefix="ifw-session-rehearsal-") as d:
            area = Path(d)
            profile, exe = area / "profile", area / "instance"
            profile.mkdir(mode=0o700)
            (profile / ".ifw-instance-fixture").write_bytes(MARKER)
            (profile / "writer.lock").touch(mode=0o600)
            subprocess.run([RUSTC, "--edition=2024", "-Dwarnings", "-O", INSTANCE / "main.rs", "-o", exe],
                           cwd=area, check=True, timeout=90)
            original_id = guard_id(profile)
            with rust_writer(exe, profile) as first:
                first.expect("WRITER_HELD")
                self.assertEqual(os.getsid(first.proc.pid), os.getsid(0))
                with instance.Child([sys.executable, "-B", Path(__file__).resolve(), "--posix-peer", profile],
                                    profile, os.environ) as peer:
                    peer.expect(f"POSIX_SESSION {peer.proc.pid}")
                    self.assertNotEqual(os.getsid(peer.proc.pid), os.getsid(first.proc.pid))
                    peer.expect("REMOTE_REFUSED")
                    first.send("RELEASE")
                    first.expect("WRITER_RELEASED")
                    first.success()
                    peer.send("ACQUIRE")
                    peer.expect("REMOTE_HELD")
                    with rust_writer(exe, profile) as busy:
                        busy.expect("WRITER_BUSY")
                        busy.success()
                    peer.send("RELEASE")
                    peer.expect("REMOTE_RELEASED")
                    peer.success()
            with rust_writer(exe, profile) as last:
                last.expect("WRITER_HELD")
                last.send("RELEASE")
                last.expect("WRITER_RELEASED")
                last.success()
            self.assertEqual(guard_id(profile), original_id)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--posix-peer" and sys.platform == "linux":
        remote_posix(Path(sys.argv[2]).resolve())
    else:
        unittest.main()
