"""Verify the RAM limit and the kernel lock held by the actual background QEMU."""
import fcntl
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guest_slot


def qmp(path, command):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(5)
        client.connect(str(path))
        with client.makefile("rwb") as stream:
            if "QMP" not in json.loads(stream.readline()):
                raise ValueError("Missing QMP greeting")
            for operation in ("qmp_capabilities", command):
                stream.write(json.dumps({"execute": operation}).encode() + b"\n")
                stream.flush()
                while True:
                    reply = json.loads(stream.readline())
                    if "return" in reply:
                        break
                    if "event" not in reply:
                        raise ValueError(reply)
            return reply["return"]


class GuestSlotTests(unittest.TestCase):
    def test_valid_sizes(self):
        for size in ("3072M", "3G", "1G", "8M", "256"):
            with self.subTest(size=size):
                guest_slot.validate(["qemu-system-x86_64", "-m", size])

    def test_ordinary_display_and_storage_options_are_available(self):
        guest_slot.validate(["qemu-system-x86_64", "-m", "3G", "-M", "pc,accel=tcg",
                             "-device", "virtio-gpu-pci", "-device", "virtio-scsi-pci,id=scsi",
                             "-object", "iothread,id=io1", "-global", "VGA.xres=1280"])

    def test_invalid_or_separately_configured_memory_fails_before_launch(self):
        commands = ([], ["-m", "4096"], ["-m", "3073M"], ["-m", "4G"], ["-m", "0"],
                    ["-m", "1G", "-m", "8M"], ["-m", "512M,slots=1,maxmem=4G"], ["-m"],
                    ["-m", "8M", "--m", "4G"], ["-m", "8M", "-machine", "q35,memory-backend=b"],
                    ["-m", "8M", "-object", "memory-backend-ram,id=b,size=4G"],
                    ["-m", "8M", "-device", "pc-dimm,memdev=b"], ["-m", "8M", "-readconfig", "q.cfg"],
                    ["-m", "8M", "-numa", "node,mem=4G"], ["-m", "8M", "-M", '{"memory":{"size":4294967296}}'],
                    ["-m", "8M", "-add-fd", "fd=5,set=0"])
        with tempfile.TemporaryDirectory() as name, patch.object(guest_slot.subprocess, "run") as launch:
            folder = Path(name)
            slot = folder / "slot"
            for args in commands:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    guest_slot._run(["qemu-system-x86_64", *args], cwd=folder, slot=slot, check=True)
            launch.assert_not_called()
            self.assertFalse(slot.exists())

    def test_failed_launch_releases_the_slot(self):
        with tempfile.TemporaryDirectory() as name:
            slot = Path(name) / "slot"
            with patch.object(guest_slot.subprocess, "run", side_effect=OSError("QEMU unavailable")):
                with self.assertRaisesRegex(OSError, "QEMU unavailable"):
                    guest_slot._run(["qemu-system-x86_64", "-m", "8M"], cwd=name, check=True, slot=slot)
            with slot.open("rb") as independent:
                fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @unittest.skipUnless(shutil.which("qemu-system-x86_64"), "QEMU is required for the lock lifetime test")
    def test_daemon_owns_the_lock_until_exit_and_allows_the_next_start(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            slot, monitor = folder / "slot", folder / "monitor.sock"
            args = ["qemu-system-x86_64", "-machine", "none", "-m", "8M", "-S", "-daemonize",
                    "-nodefaults", "-no-user-config", "-display", "none", "-nic", "none",
                    "-pidfile", "qemu.pid", "-qmp", "unix:monitor.sock,server=on,wait=off"]
            for _ in range(2):
                self.assertEqual(guest_slot._run(args, cwd=folder, slot=slot, check=True).returncode, 0)
                pidfd = os.pidfd_open(int((folder / "qemu.pid").read_text()))
                poller = select.poll()
                poller.register(pidfd, select.POLLIN)
                try:
                    self.assertFalse(qmp(monitor, "query-status")["running"])
                    # A separate QMP connection confirms that closing a monitor does not free the slot.
                    fdsets = qmp(monitor, "query-fdsets")
                    self.assertTrue(any(fd.get("opaque") == "ifw-guest-slot"
                                        for fdset in fdsets for fd in fdset["fds"]))
                    with slot.open("rb") as independent, self.assertRaises(BlockingIOError):
                        fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaisesRegex(RuntimeError, "holds the VM slot"):
                        guest_slot._run(args, cwd=folder, slot=slot, check=True)
                    qmp(monitor, "quit")
                    self.assertTrue(poller.poll(5000), "QEMU did not exit normally")
                finally:
                    if not poller.poll(0):
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        self.assertTrue(poller.poll(5000), "The isolated QEMU remained alive")
                    os.close(pidfd)
            with slot.open("rb") as independent:
                fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == "__main__":
    unittest.main()
