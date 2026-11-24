"""Check cross-session qualification and rehearse the unchanged Rust guard on Linux."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from batch import eligible
from fixture import HOSTED, INSTANCE, MARKER, ROOT, guard_id, instance, read, subject_env, wait, write
from standard import AMBIENT, STANDARD, qualifies, required_authority, restriction_flag
import observe
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
    def test_system_query_distinguishes_errors_empty_output_and_advertised_numeric_levels(self):
        output = "0x00020000 (Basic User)\r\n0x40000\r\n".encode("utf-16le")
        observed = worker.level_inventory(0, output)
        self.assertEqual(observed["levelCodes"], ["0x20000", "0x40000"])
        self.assertTrue(observed["levelListed"])
        self.assertFalse(worker.level_inventory(1, output)["levelListed"])
        self.assertEqual(worker.level_inventory(1, output)["levelQueryExit"], 1)
        self.assertEqual(worker.level_inventory(0, b"")["levelQueryBytes"], 0)
        self.assertFalse(worker.level_inventory(0, b"0x000200001")["levelListed"])
        self.assertFalse(worker.level_inventory(0, b"0x40000")["levelListed"])

    def test_restriction_flag_accepts_both_windows_token_result_widths(self):
        for width in (1, 4):
            self.assertFalse(restriction_flag(bytes(width)))
            self.assertTrue(restriction_flag((1).to_bytes(width, "little")))
        self.assertTrue(restriction_flag(bytes([0, 1, 0, 0])))
        for invalid in (b"", bytes(2), bytes(8)):
            with self.assertRaisesRegex(ValueError, "result size"):
                restriction_flag(invalid)

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

    def test_effective_membership_integrity_privileges_and_capabilities_are_required(self):
        standard = dict(elevated=False, tokenType=1, elevationType=1, enabledAdministrativeGroups=0,
                        privilegesOutsideStandard=0, enabledOutsideStandard=0, uiAccess=False,
                        capabilityCount=0, integrityRid=8192)
        self.assertTrue(qualifies(standard))
        self.assertTrue(qualifies({**standard, "elevationType": 3, "integrityRid": 4096}))
        for key, bad in (("elevated", True), ("tokenType", 2), ("elevationType", 2),
                         ("enabledAdministrativeGroups", 1), ("privilegesOutsideStandard", 1),
                         ("integrityRid", 12288), ("capabilityCount", 1), ("uiAccess", True)):
            with self.subTest(key=key):
                self.assertFalse(qualifies({**standard, key: bad}))
        self.assertFalse(qualifies({"elevated": False}))

    def test_same_session_or_wrong_account_stops_before_any_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp)
            config = {"hosted": HOSTED, "controller": {"sidSha256": "fixture", "sessionId": 2}, "expires": time.time() + 30}
            write(area / "controller.json", config)
            for digest, session in (("stranger", 0), ("fixture", 2)):
                with patch("worker.Accounts") as accounts:
                    accounts.return_value.identify.return_value = ("private", Path(sys.executable), {"sessionId": session, "sidSha256": digest})
                    with self.assertRaisesRegex(RuntimeError, "account"):
                        worker.own_identity(area, "scheduled")
            self.assertFalse((area / "scheduled-ready.json").exists())

    def test_failed_standard_launch_preserves_the_original_second_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp)
            identity = {"pid": 42, "sessionId": 0, "elevated": True, "elevationType": 1}
            with patch("worker.own_identity", return_value=({"mode": "hosted-S4U"}, None, "private", identity)), patch(
                    "worker.basic_user", side_effect=RuntimeError("Level unavailable")):
                with self.assertRaisesRegex(RuntimeError, "Level unavailable"):
                    worker.run(area, {})
            self.assertEqual(read(area / "scheduled-bootstrap.json"), identity)
            self.assertFalse((area / "scheduled-ready.json").exists())

    def test_existing_standard_sessions_never_attempt_a_trust_level_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp)
            identity = {"pid": 42, "sessionId": 3, "elevated": True}
            with patch("worker.own_identity", return_value=({"mode": "existing-standard-sessions"}, None, "private", identity)), patch(
                    "worker.basic_user") as alternative:
                with self.assertRaisesRegex(RuntimeError, "already"):
                    worker.run(area, {})
                alternative.assert_not_called()

    def test_all_five_writers_are_inspected_before_their_controller_acknowledgement(self):
        self.exercise_handover(STANDARD)

    def test_elevated_ambient_trial_independently_inspects_five_native_writers(self):
        self.exercise_handover(AMBIENT)

    def exercise_handover(self, mode, *, finish_override=None, child_override=None):
        elevated = mode == AMBIENT
        facts = dict(tokenType=1, elevationType=1 if elevated else 3, elevated=elevated, enabledAdministrativeGroups=int(elevated),
                     denyOnlyAdministrativeGroups=0, privilegeCount=4 + int(elevated), privilegesOutsideStandard=int(elevated),
                     enabledOutsideStandard=0, capabilityCount=0, uiAccess=False, hasRestrictions=False,
                     integrityRid=12288 if elevated else 8192, sidSha256="fixture")
        phase_names = [phase for phases in worker.PHASES.values() for phase, _ in phases]
        pids = {name: i + 40 for i, name in enumerate(("original", "scheduled", *phase_names))}
        identities = {}
        for name, pid in pids.items():
            session = 2 if name.startswith("original") else 0
            identities[name] = {**facts, "pid": pid, "created100ns": pid, "sessionId": session, "tokenSessionId": session,
                                "authorityInventorySha256": ("a" if session else "b") * 64}
        if child_override:
            identities["scheduled-refuse"].update(child_override)
        guard = {"fileId": "fixture", "volume": "test"}
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp)
            for filename in ("original-ready", "scheduled-ready"):
                write(area / (filename + ".json"), {"worker": identities[filename.split("-")[0]], "guard": guard})
            for role in worker.PHASES:
                write(area / (role + "-bootstrap.json"), identities[role])
                write(area / (role + "-done.json"), {"passed": True})
            for name in phase_names:
                for suffix in ("-created.json", "-held.json"):
                    write(area / (name + suffix), identities[name])
                ended = {"pid": pids[name], "created100ns": pids[name], "guard": guard, "exitCode": 0,
                         "event": "WRITER_BUSY" if name.endswith("-refuse") else "WRITER_RELEASED"}
                if name == "scheduled-refuse" and finish_override:
                    ended.update(finish_override)
                write(area / (name + "-finished.json"), ended)
            result = {"mode": mode, "controller": identities["original"], "guard": guard,
                      "build": {"rust_binary_sha256": "fixture"}}
            def inspect(_, pid, __, image, session, created):
                name = next(n for n, number in pids.items() if number == pid)
                self.assertEqual(identities[name]["sessionId"], session)
                self.assertEqual(identities[name]["created100ns"], created)
                if name in phase_names and not (area / (name + "-verified.json")).exists():
                    self.assertTrue((area / (name + "-launch.json")).is_file())
                    self.assertEqual(image.name, "instance.exe")
                return identities[name]
            with patch.object(observe, "verified_process", side_effect=inspect), patch.object(
                    observe.instance, "sha", return_value="fixture"), patch.object(observe, "guard_id", return_value=guard):
                observe.native_handover(area, object(), "private", area / "instance.exe", None, result)
            self.assertEqual(set(result["writersObservedBeforeResume"]), set(phase_names))
            self.assertEqual(result["originalReacquiredAfterScheduledRelease"], identities["original-last"])
            self.assertTrue(result["lockSequenceObserved"])
            self.assertEqual([(row["phase"], row["event"]) for row in result["observedWriterEvents"]], [
                ("original-hold", "WRITER_HELD"), ("scheduled-refuse", "WRITER_BUSY"), ("original-hold", "WRITER_RELEASED"),
                ("scheduled-hold", "WRITER_HELD"), ("original-refuse", "WRITER_BUSY"), ("scheduled-hold", "WRITER_RELEASED"),
                ("original-last", "WRITER_HELD"), ("original-last", "WRITER_RELEASED")])

    def test_ambient_trial_never_requests_an_alternative_process_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp)
            identity = {"pid": 42, "elevated": True, "elevationType": 1, "sessionId": 0}
            result = {}
            with patch("worker.own_identity", return_value=({"mode": AMBIENT}, None, "private", identity)), patch(
                    "worker.basic_user") as alternative, patch("worker.participant", return_value=True) as fixed:
                worker.run(area, result)
            alternative.assert_not_called()
            fixed.assert_called_once_with(area, "scheduled")
            self.assertEqual(read(area / "scheduled-bootstrap.json"), identity)
            self.assertEqual(result["mode"], "unchanged-bootstrap-authority")

    def test_ambient_trial_requires_the_local_parents_actual_authority(self):
        for key, changed in (("authorityInventorySha256", "a" * 64), ("elevated", False), ("integrityRid", 8192),
                             ("tokenSessionId", 3), ("privilegeCount", 3), ("authorityInventorySha256", "x" * 64)):
            with self.subTest(key=key, changed=changed), self.assertRaisesRegex(RuntimeError, "suspended native writer"):
                self.exercise_handover(AMBIENT, child_override={key: changed})
        with self.assertRaisesRegex(ValueError, "Unknown"):
            required_authority("ambiguous", {}, {})

    def test_busy_exit_code_guard_pid_and_process_creation_must_match(self):
        for key, wrong in (("event", "WRITER_HELD"), ("exitCode", 1), ("guard", {"fileId": "other"}),
                           ("pid", 98765), ("created100ns", 12345)):
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "lock response"):
                self.exercise_handover(AMBIENT, finish_override={key: wrong})

    def test_ambient_evidence_cannot_promote_the_standard_user_gate(self):
        full = {"attempted": True, "passed": True, "lockSequenceObserved": True, "temporaryProfileRemoved": True}
        ambient = {**full, "mode": AMBIENT, "ambientGuardPassed": True}
        standard = {**full, "mode": STANDARD, "standardUserGuardPassed": True}
        for a, s, expected_a, expected_s in (
                (ambient, standard, True, True), (ambient, {}, True, False), ({}, standard, False, True),
                (ambient, {**standard, "temporaryProfileRemoved": False}, True, False),
                ({**ambient, "lockSequenceObserved": False}, standard, False, True),
                (ambient, {**standard, "passed": False}, True, False),
                (ambient, {**standard, "attempted": False}, True, False),
                (ambient, {**standard, "mode": AMBIENT}, True, False)):
            result = observe.summarize(a, s)
            self.assertIs(result["ambientGuardPassed"], expected_a)
            self.assertIs(result["standardUserGuardPassed"], expected_s)
            self.assertIs(result["passed"], expected_a and expected_s)

    def test_each_trial_confirms_its_exact_task_cleanup_after_scheduler_failure(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"GITHUB_SHA": "fixture"}):
            base = Path(temp)
            output = base / "results"
            output.mkdir()
            args = SimpleNamespace(target="fixture", output=output)
            areas = []
            def scheduled(area, _args, result, _reference):
                areas.append(area)
                result["schedulerStarted"] = True
                if result["mode"] == STANDARD:
                    result.update(schedulerExit=1, cleanupExit=0)
                    write(area / "cleanup.json", {"cleanupVerified": True})
                    write(area / "original-console-helper.json", {"pid": 123, "created100ns": 456})
                    (area / "original-console-launch.claim").touch()
                raise RuntimeError("Fixture registration failed")
            with patch.object(observe, "scheduled", side_effect=scheduled), patch.object(observe, "participants_exited", return_value=0):
                ambient = observe.hosted_case(args, base, AMBIENT, object())
                standard = observe.hosted_case(args, base, STANDARD, object())
            self.assertNotEqual(*areas)
            self.assertTrue(areas[0].is_dir())
            self.assertFalse(areas[1].exists())
            self.assertFalse(ambient["temporaryProfileRemoved"])
            self.assertTrue(standard["temporaryProfileRemoved"])
            self.assertFalse(read(output / "ambient-case.json")["ambientGuardPassed"])
            self.assertFalse(read(output / "standard-case.json")["standardUserGuardPassed"])
            self.assertEqual(read(output / "original-console-helper.json"), {"pid": 123, "created100ns": 456})
            self.assertEqual(read(output / "original-console-claim.json"), {"bytes": 0, "rawBase64": ""})
            self.assertIsNone(ambient["standardUserGuardPassed"])
            self.assertIsNone(standard["ambientGuardPassed"])

    @unittest.skipUnless(sys.platform == "linux", "local filesystem link controls")
    def test_guard_identity_refuses_links(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            original, guard = area / "original", area / "writer.lock"
            original.touch()
            guard.symlink_to(original)
            with self.assertRaisesRegex(RuntimeError, "guard"):
                guard_id(area)
            guard.unlink()
            os.link(original, guard)
            with self.assertRaisesRegex(RuntimeError, "guard"):
                guard_id(area)

    def test_raw_account_errors_are_never_written_to_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "test.json"
            write(file, {"error": "S-1-5-21-123-456-789-1000 fixture failed"})
            self.assertEqual(read(file)["error"], "[account ID] fixture failed")

    def test_worker_failure_and_deadline_are_observable(self):
        with tempfile.TemporaryDirectory() as d:
            area = Path(d)
            with self.assertRaises(TimeoutError):
                wait(area, "missing.json", 0)
            write(area / "worker-done.json", {"passed": False, "reason": "synthetic"})
            with self.assertRaisesRegex(RuntimeError, "participant failed"):
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
