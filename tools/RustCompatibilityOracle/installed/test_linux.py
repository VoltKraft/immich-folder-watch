"""Regression checks for the native shipping Flatpak observer."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import linux


class LinuxFlatpakTests(unittest.TestCase):
    def test_effective_permissions_allow_both_native_orders_and_exactly_the_shipping_rights(self):
        permissions = ("[Context]\nshared=ipc;network;\nsockets=x11;\ndevices=dri;\n"
                       "[Session Bus Policy]\norg.kde.StatusNotifierWatcher=talk\n")
        expected = linux.keyfile(permissions)
        self.assertEqual(linux.shipping_permissions(permissions), expected)
        self.assertEqual(linux.shipping_permissions(permissions.replace("ipc;network;", "network;ipc;")), expected)
        for changed in ("network;", "network;ipc;ipc;", "network;ipc;files;", "network;ipc;\nfilesystems=host;"):
            with self.subTest(shared=changed), self.assertRaisesRegex(ValueError, "sandbox permissions"):
                linux.shipping_permissions(permissions.replace("ipc;network;", changed))

    def test_payload_records_links_without_following_targets_or_linked_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outside = base / "outside"
            outside.mkdir()
            (outside / "private").write_text("unrelated")
            files = base / "files"
            files.mkdir()
            (files / "directory-link").symlink_to(outside, target_is_directory=True)
            (files / "dangling").symlink_to("/app/lib/immich-folder-watch/immich-folder-watch")
            binary = files / "binary"
            binary.write_bytes(b"fixture")
            binary.chmod(0o754)
            self.assertEqual(linux.payload(files), {
                "directory-link": {"link": str(outside)},
                "dangling": {"link": "/app/lib/immich-folder-watch/immich-folder-watch"},
                "binary": {"sha256": hashlib.sha256(b"fixture").hexdigest(), "executableBits": 0o110},
            })

    def test_architecture_digest_and_length_are_required_before_deployment(self):
        assets = {f"linux-{arch}": {"name": arch + ".flatpak", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for arch, data in (("x64", b"x64"), ("arm64", b"arm"))}
        with tempfile.TemporaryDirectory() as directory, patch.object(linux, "RELEASE", {"assets": assets}), \
                patch.object(linux, "native_target", return_value="linux-x64"):
            bundle = Path(directory) / "input.flatpak"
            bundle.write_bytes(b"x64")
            self.assertEqual(linux.verified_package(bundle), assets["linux-x64"])
            for changed in (b"arm", b"x64!"):
                with self.subTest(bytes=changed):
                    bundle.write_bytes(changed)
                    with self.assertRaisesRegex(ValueError, "original x64.flatpak"):
                        linux.run_native(bundle, Path(directory) / "native", {})
            self.assertFalse((Path(directory) / "native").exists())

    def test_direct_script_invocations_leave_foreign_profile_unopened(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            foreign = base / "foreign-profile"
            foreign.mkdir()
            for name in linux.NAMES:
                (foreign / name).write_bytes(b"unrelated synthetic data")
            (base / "sitecustomize.py").write_text("""
import os, sys
def guard(event, args):
    if event in ("open", "os.listdir", "os.scandir", "sqlite3.connect") and isinstance(args[0], (str, bytes)):
        if os.environ["FOREIGN_FIXTURE"] in os.fsdecode(args[0]):
            os._exit(91)
sys.addaudithook(guard)
""")
            guarded = dict(os.environ, PYTHONPATH=str(base), PYTHONNOUSERSITE="1", FOREIGN_FIXTURE=str(foreign))
            control = subprocess.run([sys.executable, "-B", "-c", "import sys; open(sys.argv[1])", foreign / "config.yaml"],
                                     env=guarded, timeout=30)
            self.assertEqual(control.returncode, 91, "The child must detect an attempted foreign profile access")
            profile_env = dict(guarded, HOME=str(foreign), XDG_CONFIG_HOME=str(foreign))
            cases = [
                ([base / "bundle.flatpak", foreign, base / "output"], profile_env, "Use run.py"),
                (["--inside"], profile_env, "private shipping Flatpak environment"),
                (["--inside"], {**guarded, **linux.ENV}, "private shipping Flatpak mounts"),
            ]
            for arguments, environment, error in cases:
                with self.subTest(error=error):
                    result = subprocess.run([sys.executable, "-B", linux.__file__, *arguments],
                                            env=environment, capture_output=True, text=True, timeout=30)
                    self.assertNotIn(result.returncode, (0, 91), "The fixture must exit before accessing the synthetic profile")
                    self.assertIn(error, result.stderr)
            self.assertFalse((base / "output").exists())

    def test_profile_rejects_linked_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.yaml").write_bytes(b"synthetic")
            (root / "sync-state.db").symlink_to(root / "config.yaml")
            with self.assertRaisesRegex(ValueError, "regular synthetic sync-state.db"):
                linux.profile_hashes(root)


if __name__ == "__main__":
    unittest.main()
