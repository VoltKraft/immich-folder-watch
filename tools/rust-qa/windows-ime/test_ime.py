"""Check that installed-language hints or directly entered Unicode cannot pass the IME trial."""

import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from run import FIELD_SOURCES, KEYBOARD_CATEGORY, ROOT, accepted, checked_build, digest, eligibility, launch_ps, run


class ImeTests(unittest.TestCase):
    def test_compose_inherits_only_a_short_lived_duplicate_and_stops_on_timeout(self):
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        control = self.enterContext(os.fdopen(writer, "wb"))
        # Use the real duplicate descriptor lifetime with a modeled Windows handle table.
        self.enterContext(patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda fd: fd + 1000)}))
        inheritance = self.enterContext(patch.object(os, "set_handle_inheritable", create=True))
        self.enterContext(patch.object(subprocess, "CREATE_NO_WINDOW", 0, create=True))
        self.enterContext(patch.object(subprocess, "STARTUPINFO", SimpleNamespace, create=True))
        process = MagicMock()
        process.wait.side_effect = subprocess.TimeoutExpired("compose", 115)
        process.poll.return_value = None

        def start(command, **options):
            handle, = options["startupinfo"].lpAttributeList["handle_list"]
            self.assertEqual(command[-2:], ["-SamplePipe", str(handle)])
            self.assertTrue(options["close_fds"])
            self.assertNotEqual(handle - 1000, writer)
            os.fstat(handle - 1000)
            inheritance.assert_called_once_with(handle, True)
            return process

        with tempfile.TemporaryDirectory() as area, patch.object(subprocess, "Popen", side_effect=start):
            with self.assertRaises(subprocess.TimeoutExpired):
                launch_ps("test-only", "compose", Path(area), {}, sample_pipe=control)
        with self.assertRaises(OSError):
            os.fstat(inheritance.call_args.args[0] - 1000)
        os.fstat(writer)
        process.kill.assert_called_once_with()

    def test_observed_composition_remains_failed_when_removing_its_profile_raises(self):
        with tempfile.TemporaryDirectory() as area:
            output = Path(area)
            profile = output / "ime-profile-fixture"
            profile.mkdir()
            args = SimpleNamespace(output=output, binary=output / "probe.exe", build_receipt=None, inventory_only=False)
            context = {"threadDesktop": "Default"}
            directory = Mock(name="private temporary directory")
            directory.name = str(profile)
            error = PermissionError(13, "in use", str(profile))
            error.winerror = 32
            directory.cleanup.side_effect = error
            self.enterContext(patch("windows_observer.tempfile.TemporaryDirectory", return_value=directory))
            self.enterContext(patch("windows_observer.time.monotonic", side_effect=[0, 21]))
            self.enterContext(patch("run.Desktop")).return_value.context.return_value = context
            self.enterContext(patch("run.ordinary_console", return_value=True))
            host = self.enterContext(patch("run.select_powershell", return_value=("pwsh", [])))
            self.enterContext(patch("run.launch_ps", return_value=0))
            self.enterContext(patch("run.read", return_value={"status": "observed", "layouts": [
                {"language": 0x411, "immIme": True}]}))
            self.enterContext(patch("run.native_target", return_value=("aarch64-pc-windows-msvc", 0xaa64)))
            self.enterContext(patch("run.checked_build", return_value={}))
            observed = self.enterContext(patch("run.subject"))
            result = {"status": "failed"}
            with self.assertRaises(PermissionError):
                result["status"] = run(args, result)
            observed.assert_called_once()
            self.assertEqual(host.call_args.args[0], output)
            self.assertEqual(host.call_args.kwargs["env"]["USERPROFILE"], str(profile))
            self.assertTrue(result["compositionObserved"])
            self.assertFalse(result["profileRemoved"])
            self.assertEqual(result["profileCleanupError"]["winerror"], 32)
            self.assertEqual(result["status"], "failed")

    def test_inventory_requires_loaded_layout_and_usable_engine(self):
        row = {"language": 0x411, "immIme": False}
        profile = {"type": 1, "language": 0x411, "enabled": True, "category": KEYBOARD_CATEGORY}
        observation = {"layouts": [row], "profiles": [profile], "enumeratedTsf": True}
        self.assertIsNone(eligibility(observation))
        self.assertIsNone(eligibility({"layouts": [{"language": 0x411, "immIme": True}]}))
        for changes in ({"layouts": [{"language": 0x409, "immIme": False}]},
                        {"enumeratedTsf": False}, {"profiles": [{**profile, "enabled": False}]},
                        {"profiles": [{**profile, "type": 2}]}, {"profiles": [{**profile, "category": "other"}]},
                        {"profiles": [{**profile, "language": 0x409}]},
                        {"profiles": [], "japaneseBasicCapability": ["Installed"]}):
            with self.subTest(changes=changes):
                self.assertIsNotNone(eligibility({**observation, **changes}))

    def test_requires_ordered_native_events_exact_field_and_restoration(self):
        field = {"state": "observed", "lastObservation": "focused-filename-read", "attempts": 2}
        positive = {"status": "passed", "subjectId": 23, "windowHandle": 55, "fieldAfterLayout": field,
                    "selectedLayout": 0xe0010411, "preeditBeforeEnter": True,
                    "commitAfterEnter": True, "normalFilenameConfirmed": True, "committedCodePoint": "U+3042",
                    "originalLayout": 0x04090409, "restoredLayout": 0x04090409}
        self.assertTrue(accepted(positive, 23, 55))
        self.assertFalse(accepted(positive, 42, 55))
        self.assertFalse(accepted(positive, 23, 56))
        for k in positive:
            self.assertFalse(accepted({n: v for n, v in positive.items() if n != k}, 23, 55), k)
        for change in ({"state": "unavailable"}, {"lastObservation": "filename-unfocused"}, {"attempts": 0}):
            self.assertFalse(accepted({**positive, "fieldAfterLayout": {**field, **change}}, 23, 55))
        self.assertFalse(accepted({**positive, "restoredLayout": 0x411}, 23, 55))
        self.assertFalse(accepted({**positive, "committedCodePoint": "U+0061"}, 23, 55))
        diagnostic = {"beforeA": {"state": "observed", "open": True, "conversionFlags": 1}}
        self.assertFalse(accepted({**positive, "preeditBeforeEnter": False, "attempts": [diagnostic]}, 23, 55))

    def test_gui_receipt_binds_executable_native_machine_and_field_source(self):
        with tempfile.TemporaryDirectory() as d:
            binary, record = Path(d) / "app.exe", Path(d) / "receipt.json"
            pe = bytearray(150)
            pe[:2], pe[60:64], pe[100:106] = b"MZ", struct.pack("<I", 100), b"PE\0\0\x64\xaa"
            binary.write_bytes(pe)
            info = {"source": "revision", "binarySha256": digest(binary), "target": "aarch64-pc-windows-msvc",
                    "compilerSources": {p.relative_to(ROOT).as_posix(): digest(p) for p in FIELD_SOURCES}}
            record.write_text(json.dumps(info))
            self.assertEqual(checked_build(binary, record, info["target"], 0xaa64, "revision")["source"], "revision")
            for machine, source in ((0x8664, "revision"), (0xaa64, "changed")):
                with self.assertRaises(ValueError):
                    checked_build(binary, record, info["target"], machine, source)
            for source in FIELD_SOURCES:
                for missing in (False, True):
                    bad = copy.deepcopy(info)
                    key = source.relative_to(ROOT).as_posix()
                    if missing:
                        del bad["compilerSources"][key]
                    else:
                        bad["compilerSources"][key] = "changed"
                    record.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):
                        checked_build(binary, record, info["target"], 0xaa64, None)


if __name__ == "__main__":
    unittest.main()
