"""Portable controls; these do not claim a native FAT mount or adapter pass."""

from __future__ import annotations

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


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="provider-control-", dir=ROOT / "artifacts/rust/storage-faults")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.volume = self.root / "volume"
        self.volume.mkdir()
        (self.volume / "state.db").write_bytes(b"synthetic preserved SQLite marker")
        self.recovery = self.root / "recovery.json"
        provider.durable_json(self.recovery, {"format": "ifw-before-provider-recovery-v1", "status": "passed",
            "completed_cases": 8, "csharp_assertions": 208, "original_snapshot_checks": 8})

    def test_gate_refuses_incomplete_recovery_before_mount_setup(self):
        for key, value in (("status", "failed"), ("completed_cases", 7), ("csharp_assertions", 207),
                           ("original_snapshot_checks", 7)):
            with self.subTest(key=key):
                data = json.loads(self.recovery.read_text())
                data[key] = value
                bad = self.root / (key + ".json")
                provider.durable_json(bad, data)
                with patch.object(provider, "Mount") as mount:
                    result = provider.run(Path("unused"), {}, None, str(self.volume), self.root,
                                          lambda: {}, bad)
                self.assertEqual(result["status"], "failed")
                mount.assert_not_called()
        self.assertEqual({p.name for p in self.volume.iterdir()}, {"state.db"})

    def test_durable_receipt_is_exclusive_and_source_inventory_is_exact(self):
        before = self.recovery.read_bytes()
        with self.assertRaises(FileExistsError):
            provider.durable_json(self.recovery, {"status": "replacement"})
        self.assertEqual(self.recovery.read_bytes(), before)
        files = provider.source_files(ROOT)
        self.assertEqual(len(files), len(set(files)))
        self.assertIn(ROOT / "rust/crates/safe-fs/src/windows.rs", files)
        self.assertIn(ROOT / "rust/Cargo.toml", files)
        self.assertTrue(all(path.is_file() and path.is_relative_to(ROOT) for path in files))
        output = self.root / "bound-sources"
        output.mkdir()
        inputs = [*files, Path(__file__).with_name("fat_provider.rs")]
        hashes = runner.export_source_snapshot(ROOT, output, inputs)
        locations = json.loads((output / "first-party-source-paths.json").read_text())
        self.assertEqual(set(hashes), {path.relative_to(ROOT).as_posix() for path in inputs})
        for path in inputs:
            logical = path.relative_to(ROOT).as_posix()
            self.assertEqual((output / locations[logical]).read_bytes(), path.read_bytes())
            self.assertEqual(runner.sha256(output / locations[logical]), hashes[logical])

    def test_native_machine_check_rejects_the_other_architecture_and_non_pe(self):
        binary = self.root / "probe.exe"
        for machine, target, other in ((0x8664, "x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc"),
                                       (0xaa64, "aarch64-pc-windows-msvc", "x86_64-pc-windows-msvc")):
            data = bytearray(128)
            data[:2], data[60:64], data[80:84], data[84:86] = b"MZ", (80).to_bytes(4, "little"), b"PE\0\0", machine.to_bytes(2, "little")
            binary.write_bytes(data)
            provider.require_native_pe(binary, target)
            with self.assertRaisesRegex(ValueError, "machine"):
                provider.require_native_pe(binary, other)
        binary.write_bytes(b"not an executable")
        with self.assertRaisesRegex(ValueError, "not PE"):
            provider.require_native_pe(binary, "x86_64-pc-windows-msvc")

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

    def exercise(self, code=0, mount_error=None):
        calls = []

        class FakeMount:
            def __init__(inner, *_args):
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
            (root / "original.txt").rename(root / "renamed.txt")
            return child_result(code)

        def validate():
            calls.append("validate-owned-volume")
            return {"total_bytes": 15679488, "available_bytes": 1000, "free_bytes": 1000}

        with patch.object(provider, "Mount", FakeMount), patch.object(provider, "run_child", child), \
                patch.object(provider, "require_no_mount_paths"):
            result = provider.run(Path("test-double"), {}, None, str(self.volume), self.root, validate, self.recovery)
        self.assertEqual(result["volume_files_before"], result["volume_files_after"])
        self.assertEqual({path.name for path in self.volume.iterdir()}, {"state.db"})
        self.assertEqual(result["cleanup_errors"], [])
        return result, calls

    def test_success_and_failed_child_both_remove_owned_names_and_unmount(self):
        for code in (0, 1, 2):
            with self.subTest(code=code):
                result, calls = self.exercise(code)
                self.assertEqual(result["status"], {0: "passed", 1: "failed", 2: "unavailable"}[code])
                self.assertTrue(result["probe_removed"])
                self.assertLess(calls.index("child-wait-complete"), calls.index("unmount"))

    def test_missing_mount_capability_does_not_create_fat_entries_or_start_child(self):
        result, calls = self.exercise(mount_error=provider.Unavailable("existing rights absent"))
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("child-wait-complete", calls)
        self.assertIn("unmount", calls)

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
                root = Path(directory)
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
                api.identity.side_effect = identity
                api.CloseHandle.side_effect = lambda handle: closed.append(handle) or 1
                api.require.side_effect = lambda ok, message: None if ok else (_ for _ in ()).throw(OSError(message))
                api.kernel.SetVolumeMountPointW.side_effect = mount
                api.kernel.DeleteVolumeMountPointW.side_effect = unmount
                api.kernel.GetVolumeNameForVolumeMountPointW.side_effect = get_mapping
                api.kernel.GetVolumeInformationByHandleW.side_effect = filesystem
                fixture = provider.Mount(api, root, "owned-volume")
                fixture.create()
                if foreign:
                    mapped["value"] = "other-volume"
                errors = fixture.close()
                self.assertEqual(bool(errors), foreign)
                self.assertEqual(api.kernel.DeleteVolumeMountPointW.call_count, 0 if foreign else 1)
                self.assertEqual(fixture.path.exists(), foreign)
                self.assertEqual(set(closed), set(handles))


if __name__ == "__main__":
    unittest.main()
