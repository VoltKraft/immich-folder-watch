"""Check the compiler receipt's PE header and complete image digest."""
from pathlib import Path
import struct
import tempfile
import unittest

from backup_build import TARGETS, image_receipt, verify_image, sha


class ImageReceiptTests(unittest.TestCase):
    def test_architecture_and_image_digest_must_both_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.exe"
            for target, (_, machine) in TARGETS.items():
                with self.subTest(target=target):
                    header = bytearray(128)
                    header[:2] = b"MZ"
                    struct.pack_into("<I", header, 60, 88)
                    header[88:92] = b"PE\0\0"
                    struct.pack_into("<H", header, 92, machine)
                    path.write_bytes(header)
                    image = image_receipt(path)
                    verify_image(image, target, sha(path))
                    other = next(t for t in TARGETS if t != target)
                    with self.assertRaises(ValueError):
                        verify_image(image, other, sha(path))
                    path.write_bytes(header + b"different executable body")
                    with self.assertRaises(ValueError):
                        verify_image(image, target, sha(path))

    def test_incomplete_headers_cannot_qualify_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.exe"
            path.write_bytes(b"MZ")
            with self.assertRaises(ValueError):
                image_receipt(path)
            path.write_bytes(b"MZ" + bytes(58) + struct.pack("<I", 64) + b"PE\0\0")
            with self.assertRaises(ValueError):
                verify_image(image_receipt(path), next(iter(TARGETS)), sha(path))
