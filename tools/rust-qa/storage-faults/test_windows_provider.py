"""Portable controls; these do not claim a native FAT mount or adapter pass."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import windows_provider as provider
import run as runner

ROOT = Path(__file__).resolve().parents[3]


def observation(changed=False):
    return {"format": "ifw-safe-fs-fat-provider-v1", **dict.fromkeys(provider.CHECKS, True),
            "acquired_identity": "FileIdentity { volume: 42, file: 123 }",
            "reopened_identity": f"FileIdentity {{ volume: 42, file: {124 if changed else 123} }}",
            "identity_changed_on_reopen": changed}


def child_result(code=0, changed=False):
    return {"exit_code": code, "timed_out": False, "wait_completed": True,
            "stdout": json.dumps(observation(changed)), "stderr": "synthetic test double"}


def pe_header(machine):
    data = bytearray(128)
    data[:2] = b"MZ"
    data[60:64] = (80).to_bytes(4, "little")
    data[80:84] = b"PE\0\0"
    data[84:86] = machine.to_bytes(2, "little")
    return data


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="provider-control-", dir=ROOT / "artifacts/rust/storage-faults")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.output = self.workspace / "evidence"
        self.output.mkdir(parents=True)
        self.scratch = self.root / "runner-temp"
        self.scratch.mkdir()
        self.env = {"GITHUB_WORKSPACE": str(self.workspace), "RUNNER_TEMP": str(self.scratch)}
        self.volume = self.root / "volume"
        self.volume.mkdir()
        (self.volume / "state.db").write_bytes(b"synthetic preserved SQLite marker")
        self.recovery = self.output / "recovery.json"
        self.checkpoint = {"format": "ifw-before-provider-recovery-v1", "status": "passed", "target": "x86_64-pc-windows-msvc",
                           "completed_cases": 8, "csharp_assertions": 208, "original_snapshot_checks": 8}
        runner.durable_json(self.recovery, self.checkpoint)

    def test_gate_refuses_incomplete_recovery_before_mount_setup(self):
        for key, value in (("status", "failed"), ("completed_cases", 7), ("csharp_assertions", 207),
                           ("original_snapshot_checks", 7)):
            with self.subTest(key=key):
                data = json.loads(self.recovery.read_text())
                data[key] = value
                bad = self.root / (key + ".json")
                runner.durable_json(bad, data)
                with patch.object(provider, "Mount") as mount:
                    result = provider.run(Path("unused"), {}, None, str(self.volume), self.root,
                                          lambda: {}, bad)
                self.assertEqual(result["status"], "failed")
                mount.assert_not_called()
        self.assertEqual({p.name for p in self.volume.iterdir()}, {"state.db"})

    def test_durable_receipt_is_exclusive_and_source_inventory_is_exact(self):
        before = self.recovery.read_bytes()
        with self.assertRaises(FileExistsError):
            runner.durable_json(self.recovery, {"status": "replacement"})
        self.assertEqual(self.recovery.read_bytes(), before)
        files = runner.provider_sources()
        self.assertEqual(len(files), len(set(files)))
        self.assertIn(ROOT / "rust/crates/safe-fs/src/windows.rs", files)
        self.assertIn(ROOT / "rust/Cargo.toml", files)
        self.assertTrue(all(path.is_file() and path.is_relative_to(ROOT) for path in files))
        output = self.root / "bound-sources"
        output.mkdir()
        hashes = runner.export_source_snapshot(ROOT, output, files)
        locations = json.loads((output / "first-party-source-paths.json").read_text())
        self.assertEqual(set(hashes), {path.relative_to(ROOT).as_posix() for path in files})
        for path in files:
            logical = path.relative_to(ROOT).as_posix()
            self.assertEqual((output / locations[logical]).read_bytes(), path.read_bytes())
            self.assertEqual(runner.sha256(output / locations[logical]), hashes[logical])

    def test_native_machine_check_rejects_the_other_architecture_and_non_pe(self):
        binary = self.root / "probe.exe"
        for machine, target, other in ((0x8664, "x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc"),
                                       (0xaa64, "aarch64-pc-windows-msvc", "x86_64-pc-windows-msvc")):
            binary.write_bytes(pe_header(machine))
            provider.require_native_pe(binary, target)
            with self.assertRaisesRegex(ValueError, "machine"):
                provider.require_native_pe(binary, other)
        binary.write_bytes(b"not an executable")
        with self.assertRaisesRegex(ValueError, "not PE"):
            provider.require_native_pe(binary, "x86_64-pc-windows-msvc")

    def test_default_recovery_can_start_without_the_provider_module_or_sources(self):
        result = subprocess.run([sys.executable, "-B", "-c",
            "import sys\nsys.modules['windows_provider'] = None\nimport run\n"
            "sources = set(run.recovery_sources(run.ROOT / 'rust/tests/fixtures/legacy/linux'))\n"
            "assert run.ROOT / 'rust/Cargo.toml' in sources\n"
            "assert sources.isdisjoint(run.PROVIDER_FILES)\n"
            "assert sources.isdisjoint((run.ROOT / 'rust/crates/safe-fs/src').glob('*.rs'))"],
            cwd=runner.HERE, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_provider_source_load_waits_for_successful_fsync(self):
        with patch.object(runner.os, "fsync", side_effect=OSError("synthetic fsync failure")), \
                patch.object(runner, "provider_sources") as sources, patch.object(provider, "run") as run_child:
            result = runner.provider_followup(self.output, self.checkpoint, self.env, None, str(self.volume),
                                              self.root, Mock())
        self.assertEqual(result["status"], "failed")
        self.assertIn("synthetic fsync failure", result["error"])
        self.assertIn("receipt_error", result)
        self.assertNotIn("recovery_receipt_sha256", result)
        sources.assert_not_called()
        run_child.assert_not_called()

    def test_preparation_child_and_outcome_failures_return_with_the_recovery_receipt(self):
        real_sources, real_pe = runner.provider_sources, provider.require_native_pe
        for failure in ("import", "format", "build", "pe", "changed-binary", "child", "outcome", None):
            with self.subTest(failure=failure):
                area = self.output / (failure or "passed")
                area.mkdir()
                recovery = area / "recovery-before-provider.json"
                outcome = area / "windows-provider.json"
                if failure == "outcome":
                    outcome.write_bytes(b"original exclusive output")
                events = []

                def sources():
                    self.assertEqual(fsync.call_count, 1)
                    self.assertEqual(json.loads(recovery.read_bytes()), self.checkpoint)
                    events.append("sources")
                    return real_sources()

                def command(preparation, _env, _result, name, arguments):
                    self.assertEqual(preparation, area / "provider-preparation")
                    events.append(name)
                    if name == failure:
                        raise ValueError("synthetic " + failure + " failure")
                    if name == "library-build":
                        Path(arguments[-1]).write_bytes(b"portable library test double")
                    if name == "build":
                        machine = 0xaa64 if failure == "pe" else 0x8664
                        Path(arguments[-1]).write_bytes(pe_header(machine))

                def verify_pe(binary, target):
                    events.append("pe")
                    real_pe(binary, target)
                    if failure == "changed-binary":
                        with binary.open("ab") as stream:
                            stream.write(b"synthetic staged file change")

                def child(*_args):
                    events.append("child")
                    if failure == "child":
                        raise OSError("synthetic child failure")
                    return {"status": "passed"}

                modules = {"windows_provider": None} if failure == "import" else {}
                with patch.dict(sys.modules, modules), patch.object(runner.os, "fsync", wraps=os.fsync) as fsync, \
                        patch.object(runner, "provider_sources", sources), patch.object(runner, "logged_command", command), \
                        patch.object(provider, "require_native_pe", verify_pe), patch.object(provider, "run", child):
                    result = runner.provider_followup(area, self.checkpoint, self.env, None, str(self.volume),
                                                      self.root, Mock())
                self.assertEqual(result["status"], "failed" if failure else "passed")
                self.assertEqual(result["recovery_receipt_sha256"], runner.sha256(recovery))
                expected = ["sources", "format", "controls", "library-build", "build", "pe", "child"]
                last = {"import": "sources", "changed-binary": "pe", "outcome": "child"}.get(failure, failure or "child")
                self.assertEqual(events, expected[:expected.index(last) + 1])
                if failure == "outcome":
                    self.assertIn("receipt_error", result)
                    self.assertEqual(outcome.read_bytes(), b"original exclusive output")
                else:
                    self.assertEqual(json.loads(outcome.read_bytes()), result)

    def test_only_complete_realistic_observations_pass_and_identity_change_is_allowed(self):
        for changed in (False, True):
            self.assertEqual(provider.validate_observation(child_result(changed=changed)), observation(changed))
        for key in provider.CHECKS:
            bad = child_result()
            value = json.loads(bad["stdout"])
            value[key] = False
            bad["stdout"] = json.dumps(value)
            with self.assertRaisesRegex(ValueError, "missing ordinary"):
                provider.validate_observation(bad)
        bad = child_result()
        value = json.loads(bad["stdout"])
        value["identity_changed_on_reopen"] = True
        bad["stdout"] = json.dumps(value)
        with self.assertRaisesRegex(ValueError, "inconsistent identity"):
            provider.validate_observation(bad)
        with self.assertRaises(provider.Unavailable):
            provider.validate_observation(child_result(2))

    def test_direct_child_is_killed_and_waited_before_returning_on_timeout(self):
        result = provider.run_child([sys.executable, "-c", "import time; time.sleep(30)"],
                                    os.environ.copy(), self.root, timeout=0.05)
        self.assertTrue(result["timed_out"])
        self.assertTrue(result["wait_completed"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_unconfirmed_child_is_not_treated_as_quiescent(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired("owned fake child", 15)
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("owned fake child", 10)
        with patch.object(provider.subprocess, "Popen", return_value=process):
            with self.assertRaises(provider.ChildNotQuiescent):
                provider.run_child(["owned-test-double"], {}, self.root)
        self.assertGreaterEqual(process.kill.call_count, 1)
        process.wait.assert_called_once_with(timeout=10)

    def exercise(self, code=0, mount_error=None, child_names=("renamed.txt",), renamed_contents=None):
        calls = []

        class FakeMount:
            def __init__(inner, _api, directory, _volume):
                self.assertEqual(directory, self.scratch)
                inner.receipt = {"test_double": True}

            def create(inner):
                calls.append("mount")
                if mount_error:
                    raise mount_error

            def verify(inner):
                calls.append("verify")

            def probe_root(inner, name):
                return self.volume / name

            def close(inner):
                calls.append("unmount")
                return []

        def child(arguments, _env, _cwd):
            calls.append("child-wait-complete")
            root = Path(arguments[1])
            self.assertEqual((root / "original.txt").read_bytes(), provider.CONTENTS)
            original = root / "original.txt"
            if "renamed.txt" in child_names:
                original.rename(root / "renamed.txt")
                if renamed_contents is not None:
                    (root / "renamed.txt").write_bytes(renamed_contents)
                if "original.txt" in child_names:
                    original.write_bytes(provider.CONTENTS)
            elif not child_names:
                original.unlink()
            return child_result(code)

        def validate():
            calls.append("validate-owned-volume")
            return {"total_bytes": 15679488, "available_bytes": 1000, "free_bytes": 1000}

        with patch.object(provider, "Mount", FakeMount), patch.object(provider, "run_child", child), \
                patch.object(provider, "require_no_mount_paths"):
            result = provider.run(Path("test-double"), self.env, None, str(self.volume), self.output, validate, self.recovery)
        if renamed_contents is None:
            self.assertEqual(result["volume_files_before"], result["volume_files_after"])
            self.assertEqual({path.name for path in self.volume.iterdir()}, {"state.db"})
            self.assertEqual(result["cleanup_errors"], [])
        else:
            self.assertTrue(any("unexpected provider entry" in error for error in result["cleanup_errors"]))
            [retained] = self.volume.glob("ifw-provider-*/renamed.txt")
            self.assertEqual(retained.read_bytes(), renamed_contents)
        return result, calls

    def test_success_and_failed_child_both_remove_owned_names_and_unmount(self):
        for code in (0, 1, 2):
            with self.subTest(code=code):
                result, calls = self.exercise(code)
                self.assertEqual(result["status"], {0: "passed", 1: "failed", 2: "unavailable"}[code])
                if code == 0:
                    self.assertEqual(result["renamed_file_readback"], {"names": ["renamed.txt"],
                        "bytes": len(provider.CONTENTS), "sha256": hashlib.sha256(provider.CONTENTS).hexdigest()})
                self.assertTrue(result["probe_removed"])
                self.assertLess(calls.index("child-wait-complete"), calls.index("unmount"))

    def test_missing_mount_capability_does_not_create_fat_entries_or_start_child(self):
        result, calls = self.exercise(mount_error=provider.Unavailable("existing rights absent"))
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("child-wait-complete", calls)
        self.assertIn("unmount", calls)

    def test_successful_child_requires_only_the_renamed_file_on_the_volume_guid(self):
        for names in ((), ("original.txt",), ("original.txt", "renamed.txt")):
            with self.subTest(names=names):
                result, _ = self.exercise(child_names=names)
                self.assertEqual(result["status"], "failed")
                self.assertIn("exactly the renamed", result["error"])
                self.assertTrue(result["probe_removed"])

    def test_changed_qualified_volume_identity_is_a_failure_before_mounting(self):
        with patch.object(provider, "Mount") as mount:
            result = provider.run(Path("unused"), self.env, None, str(self.volume), self.output,
                                  Mock(side_effect=ValueError("volume extent changed")), self.recovery)
        self.assertEqual(result["status"], "failed")
        self.assertIn("extent changed", result["error"])
        mount.assert_not_called()

    def test_supervisor_rejects_and_retains_renamed_file_with_wrong_length(self):
        result, _ = self.exercise(renamed_contents=b"short")
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("renamed_file_readback", result)

    def test_supervisor_rejects_and_retains_different_bytes_of_the_correct_length(self):
        result, _ = self.exercise(renamed_contents=b"x" * len(provider.CONTENTS))
        self.assertEqual(result["status"], "failed")
        self.assertIn("contents differ", result["error"])
        self.assertNotIn("renamed_file_readback", result)

    def test_mount_parent_cannot_be_the_workspace_evidence_or_a_common_ancestor(self):
        self.assertEqual(provider.mount_parent(self.env, self.output), self.scratch)
        for temp in (self.root, self.workspace, self.output):
            with self.subTest(temp=temp), self.assertRaisesRegex(ValueError, "outside the workspace"):
                provider.mount_parent({**self.env, "RUNNER_TEMP": str(temp)}, self.output)

    def test_cli_requires_explicit_vhd_without_creating_output(self):
        output = self.root / "not-created"
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("run.py")),
            "x86_64-pc-windows-msvc", "--output", str(output), "--windows-provider"],
            capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"requires the existing --windows-vhd", result.stderr)
        self.assertFalse(output.exists())


class MountCleanupTests(unittest.TestCase):
    def test_only_the_created_mapping_is_deleted_and_handles_close_on_mismatch(self):
        for foreign in (False, True):
            with self.subTest(foreign=foreign), tempfile.TemporaryDirectory() as directory:
                area = Path(directory)
                workspace = area / "workspace"
                evidence = workspace / "evidence"
                evidence.mkdir(parents=True)
                root = area / "runner-temp"
                root.mkdir()
                api = Mock()
                mapped = {"value": None}
                handles = {}
                closed = []

                def open_file(path, *_args):
                    handle = len(handles) + 1
                    handles[handle] = Path(path)
                    return handle

                def identity(handle):
                    path = handles[handle]
                    return {"extended_supported": True, "extended_id": "0" * 31 + ("1" if path == root else "2"),
                            "extended_volume_serial": 10, "attributes": 0x10 | (0x400 if path != root and mapped["value"] else 0)}

                def mount(_path, volume):
                    mapped["value"] = volume
                    return 1

                def unmount(_path):
                    mapped["value"] = None
                    return 1

                def get_mapping(_path, buffer, _size):
                    buffer.value = mapped["value"]
                    return 1

                def filesystem(*args):
                    args[-2].value = "NTFS"
                    return 1

                api.CreateFileW.side_effect = open_file
                api.GetDriveTypeW.return_value = 3
                api.identity.side_effect = identity
                api.CloseHandle.side_effect = lambda handle: closed.append(handle) or 1
                api.require.side_effect = lambda ok, message: None if ok else (_ for _ in ()).throw(OSError(message))
                api.kernel.SetVolumeMountPointW.side_effect = mount
                api.kernel.DeleteVolumeMountPointW.side_effect = unmount
                api.kernel.GetVolumeNameForVolumeMountPointW.side_effect = get_mapping
                api.kernel.GetVolumeInformationByHandleW.side_effect = filesystem
                env = {"GITHUB_WORKSPACE": str(workspace), "RUNNER_TEMP": str(root)}
                fixture = provider.Mount(api, provider.mount_parent(env, evidence), "owned-volume")
                fixture.create()
                if foreign:
                    mapped["value"] = "other-volume"
                errors = fixture.close()
                self.assertEqual(bool(errors), foreign)
                self.assertEqual(api.kernel.DeleteVolumeMountPointW.call_count, 0 if foreign else 1)
                self.assertEqual(fixture.path.exists(), foreign)
                self.assertEqual(set(closed), set(handles))
                self.assertFalse(fixture.path.is_relative_to(workspace))
                if foreign:
                    # Ordinary portable stand-in for a retained mapping. Neither evidence walk can reach it.
                    (fixture.path / "retained-synthetic-entry").write_bytes(b"private fixture")
                    self.assertEqual(runner.evidence_inventory(evidence), {})
                    self.assertEqual(list(evidence.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
