"""Check Windows build receipt reuse across the hosted build and the local VM."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import native_build as native


class NativeBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.blobs = {n: n.encode() for n in native.FILES}
        self.receipt = {"native_target": "x86_64-pc-windows-msvc", "passed": True,
                        "dotnet_sdk": json.loads((native.ROOT / "global.json").read_bytes())["sdk"]["version"],
                        "legacy_reference": json.loads((native.HERE / "legacy-inputs.json").read_bytes())["reference"],
                        "source_sha256": native.sources(), "rust_binary_sha256": native.digest(self.blobs["instance.exe"]),
                        "oracle_sha256": native.digest(self.blobs["InstanceOracle.dll"])}
        for name, content in self.blobs.items():
            (self.root / name).write_bytes(content)

    def archive(self):
        path = self.root / "original.zip"
        with ZipFile(path, "w") as z:
            for p in (self.root / "hosted").iterdir():
                z.write(p, p.name)
        return path

    def test_exact_tested_build_survives_transport(self):
        native.retain(self.root / "hosted", self.root / "instance.exe", self.root / "InstanceOracle.dll", self.receipt)
        path = self.archive()
        with patch("native_build.shutil.which", return_value="dotnet"):
            exe, oracle, result = native.stage(path, native.digest(path.read_bytes()), self.root / "local",
                                                self.receipt["native_target"], os.environ)
        self.assertEqual(exe.read_bytes(), self.blobs["instance.exe"])
        self.assertEqual(oracle[1].read_bytes(), self.blobs["InstanceOracle.dll"])
        self.assertEqual(result["nativeArchiveSha256"], native.digest(path.read_bytes()))

    def test_changed_managed_launch_inputs_are_rejected_before_install(self):
        native.retain(self.root / "hosted", self.root / "instance.exe", self.root / "InstanceOracle.dll", self.receipt)
        (self.root / "hosted/InstanceOracle.runtimeconfig.json").write_text("different")
        path = self.archive()
        with self.assertRaisesRegex(ValueError, "build receipt"):
            native.stage(path, native.digest(path.read_bytes()), self.root / "local", self.receipt["native_target"], os.environ)
        self.assertFalse((self.root / "local").exists())

    def test_wrong_target_or_local_writer_source_is_rejected(self):
        good = {**self.receipt, "files": {k: native.digest(v) for k, v in self.blobs.items()}}
        for change in ({"native_target": "aarch64-pc-windows-msvc"}, {"source_sha256": {}}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "reference sources"):
                native.validate({**good, **change}, self.receipt["native_target"], self.blobs)
