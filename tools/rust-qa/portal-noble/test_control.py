"""Regression checks for strict lock results and authenticated Ubuntu package selection."""
import errno
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inputs import POOL, SOURCE, VERSION
from observe import require_result
from verify import signed_packages


class Controls(unittest.TestCase):
    def test_refusal_and_real_conflict_are_distinct(self):
        require_result("REFUSED errno=38", errno.ENOSYS, "rust")
        require_result("REFUSED kind=WouldBlock", errno.EAGAIN, "rust")
        require_result("REFUSED errno=11 runtime=10", errno.EAGAIN, "dotnet")
        for line, reason, kind in (("REFUSED errno=38", errno.EAGAIN, "dotnet"),
                ("REFUSED errno=11", errno.ENOSYS, "exclusive"), ("REFUSED errno=38", None, "rust"),
                ("REFUSED kind=WouldBlock", errno.ENOSYS, "rust"), ("REFUSED kind=WouldBlock", errno.EAGAIN, "shared"),
                ("ACQUIRED identity=1", errno.ENOSYS, "rust")):
            with self.assertRaises(ValueError):
                require_result(line, reason, kind)

    def test_unsigned_bytes_or_unsigned_package_selection_cannot_supply_a_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lists = root / "var/lib/apt/lists"
            lists.mkdir(parents=True)
            prefix = "mirror_dists_noble-updates_"
            (lists / (prefix + "InRelease")).write_text("Origin: Ubuntu\n")
            control = POOL + SOURCE + "_" + VERSION + "_amd64.deb"
            item = "pool/main/t/test/test_1_amd64.deb"
            digest = "0" * 64
            content = "".join(f"Package: example\nFilename: {p}\nSHA256: {digest}\n\n" for p in (control, item)).encode()
            index = lists / (prefix + "main_binary-amd64_Packages")
            index.write_bytes(content)
            rows = {"main/binary-amd64/Packages": (hashlib.sha256(content).hexdigest(), len(content))}
            plan = [{"Filename": item, "SHA256": digest}]
            with patch("verify.signed_release", return_value=("", rows)):
                self.assertEqual(signed_packages(root, "amd64", plan, root)["packages"][control], digest)
                with self.assertRaisesRegex(ValueError, "do not cover"):
                    signed_packages(root, "amd64", [{"Filename": item, "SHA256": "1" * 64}], root)
                index.write_bytes(content.replace(digest.encode(), b"2" * 64))
                with self.assertRaisesRegex(ValueError, "does not match"):
                    signed_packages(root, "amd64", plan, root)


if __name__ == "__main__":
    unittest.main()
