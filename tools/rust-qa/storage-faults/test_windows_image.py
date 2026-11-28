"""Portable preparation checks, not native Windows VHD execution evidence."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.dont_write_bytecode = True
import windows_image as image
import windows_vhd

ROOT = Path(__file__).resolve().parents[3]


class ReleaseProtocolTests(unittest.TestCase):
    def test_windows_text_translation_changes_the_old_token(self) -> None:
        with io.BytesIO() as raw:
            with io.TextIOWrapper(raw, encoding="utf-8", newline="\r\n") as pipe:
                pipe.write("release-space\n")
                pipe.flush()
                self.assertEqual(raw.getvalue(), b"release-space\r\n")
                self.assertNotEqual(raw.getvalue(), b"release-space\n")

    def test_release_is_exact_lf_under_both_host_line_endings(self) -> None:
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=newline), io.BytesIO() as raw:
                with io.TextIOWrapper(raw, encoding="utf-8", newline=newline) as pipe:
                    receipt = windows_vhd.send_release_space(pipe)
                    self.assertEqual(raw.getvalue(), b"release-space\n")
                    self.assertEqual(receipt, {"bytes": len(raw.getvalue()), "utf8_hex": raw.getvalue().hex()})

    def test_closed_release_pipe_is_not_reported_as_acknowledged(self) -> None:
        pipe = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\r\n")
        pipe.close()
        with self.assertRaises(ValueError):
            windows_vhd.send_release_space(pipe)


class WindowsImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="image-check-", dir=ROOT / "artifacts/rust/storage-faults")
        self.path = Path(self.directory.name) / "owned.vhd"
        self.identity = uuid.UUID("14542bbf-bd8b-4534-a09b-d9e471497d1a")
        self.receipt = image.create(self.path, self.identity)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_complete_deterministic_image_and_capacity(self) -> None:
        self.assertEqual(image.verify(self.path, self.identity), self.receipt)
        self.assertEqual(self.receipt["image_sha256"], "75618ec886d23d9d438c1f98f861cc714839f1b8fd9d2d8decff36274fdae42b")
        self.assertEqual(self.receipt["virtual_bytes"], 16777216)
        self.assertEqual(self.receipt["data_clusters"], 7656)
        self.assertEqual(self.receipt["data_bytes"], 15679488)

    def test_existing_file_is_never_replaced(self) -> None:
        with self.assertRaises(ValueError):
            image.create(self.path, uuid.uuid4())
        self.assertEqual(image.verify(self.path, self.identity), self.receipt)

    def test_changed_payload_rejected_before_attachment(self) -> None:
        with self.path.open("r+b") as stream:
            stream.seek(image.PARTITION_OFFSET + 100000)
            stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "filesystem differs"):
            image.verify(self.path, self.identity)

    def test_extra_partition_rejected_before_attachment(self) -> None:
        with self.path.open("r+b") as stream:
            stream.seek(462)
            stream.write(b"\x80")
        with self.assertRaisesRegex(ValueError, "partition layout"):
            image.verify(self.path, self.identity)

    def test_differencing_footer_rejected_even_with_valid_checksum(self) -> None:
        data = bytearray(self.path.read_bytes())
        struct.pack_into(">I", data, image.DISK_BYTES + 60, 4)
        data[-448:-444] = bytes(4)
        struct.pack_into(">I", data, image.DISK_BYTES + 64, (~sum(data[-512:])) & 0xffffffff)
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "fixed, parentless"):
            image.verify(self.path, self.identity)

    def test_foreign_identity_and_extra_bytes_rejected(self) -> None:
        with self.assertRaises(ValueError):
            image.verify(self.path, uuid.uuid4())
        with self.path.open("ab") as stream:
            stream.write(b"x")
        with self.assertRaises(ValueError):
            image.verify(self.path, self.identity)

    @unittest.skipIf(os.name == "nt", "portable symlink trial requires no Windows symlink privilege")
    def test_redirected_file_rejected(self) -> None:
        link = self.path.with_name("redirect.vhd")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            image.verify(link, self.identity)

    def test_native_runner_gate_does_not_accept_missing_authority(self) -> None:
        with self.assertRaises(windows_vhd.Unavailable):
            windows_vhd.hosted_gate(ROOT, {})

    def test_local_vhd_mode_refuses_an_actions_environment_before_opening_a_volume(self) -> None:
        with patch.object(windows_vhd.subprocess, "run") as query:
            with self.assertRaises(windows_vhd.Unavailable):
                windows_vhd.require_disposable_host(ROOT, {"GITHUB_ACTIONS": "true"}, True)
            query.assert_not_called()

    def test_win32_parameter_layouts_are_native_64_bit_compatible(self) -> None:
        self.assertEqual(windows_vhd.ct.sizeof(windows_vhd.StorageType), 20)
        self.assertEqual(windows_vhd.StorageType.vendor.offset, 4)

    def test_capability_and_post_attach_errors_close_only_owned_handles(self) -> None:
        class FakeApi:
            def __init__(self, attach_error: int, detach_error: int):
                self.attach_error, self.detach_error = attach_error, detach_error
                self.closed, self.detached = [], []

            def GetDriveTypeW(self, _path):
                return 3

            def system_modules(self):
                return {"test_double": "no native code executed"}

            def volumes(self):
                return set()

            def open_file(self, path, *_args):
                self.path = path
                return 101

            def identity(self, handle):
                if handle != 101:
                    raise AssertionError("foreign handle")
                return {"links": 1, "legacy_id": 7, "attributes": 0x20}

            def GetFinalPathNameByHandleW(self, handle, buffer, *_args):
                if handle != 101:
                    raise AssertionError("foreign backing handle")
                buffer.value = self.path
                return len(buffer.value)

            def OpenVirtualDisk(self, storage, path, access, flags, parameters, handle):
                if (storage._obj.device, path, access, flags, parameters) != (2, self.path, 0x000e0000, 0, None):
                    raise AssertionError("unexpected VHD open request")
                handle._obj.value = 202
                return 0

            def AttachVirtualDisk(self, handle, descriptor, flags, provider_flags, parameters, overlapped):
                if (handle, descriptor, flags, provider_flags, parameters, overlapped) != (202, None, 2, 0, None, None):
                    raise AssertionError("foreign disk or unexpected attachment parameters")
                return self.attach_error

            def physical_path(self, _handle):
                raise OSError("injected post-attachment discovery failure")

            def DetachVirtualDisk(self, handle, *_args):
                self.detached.append(handle)
                return self.detach_error

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return 1

        for index, (attach_error, detach_error) in enumerate(((1314, 0), (0, 0), (0, 5))):
            with self.subTest(attach_error=attach_error, detach_error=detach_error):
                fake = FakeApi(attach_error, detach_error)
                case = Path(self.directory.name) / f"cleanup-{index}"
                with patch.object(windows_vhd, "Api", return_value=fake), patch.object(windows_vhd, "hosted_gate"):
                    with self.assertRaises((OSError, windows_vhd.Unavailable)):
                        windows_vhd.run(Path("unused"), Path("unused"), case, "sensitive", {}, ROOT)
                self.assertEqual(fake.closed, [202, 101])
                self.assertEqual(fake.detached, [] if attach_error else [202])
                receipt = json.loads((case.with_name(case.name + "-volume") / "windows-vhd.json").read_text())
                self.assertEqual(receipt["status"], "unavailable" if attach_error else "failed")
                self.assertEqual(bool(receipt["cleanup_errors"]), bool(detach_error))


if __name__ == "__main__":
    unittest.main()
