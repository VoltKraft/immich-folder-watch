"""Controls for native speaker log delivery, exact roles, password masking and private audio."""

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

from verify import HERE, ROOT, native, sha
sys.path[:0] = [str(HERE.parent / folder) for folder in ("gui", "performance")]
from screen_reader import ScreenReader, announces, live_debug


class SpeechTests(unittest.TestCase):
    def test_both_orca_button_roles_keep_the_exact_label(self):
        self.assertTrue(announces("English push button.", "English"))
        self.assertTrue(announces("English button", "English"))
        for wrong in ("English label", "Not English push button.", "English buttons", "Deutsch button"):
            self.assertFalse(announces(wrong, "English"))

    def test_partial_utf8_and_raw_key_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = ScreenReader.__new__(ScreenReader)
            reader.orca = Mock()
            reader.orca.poll.return_value = None
            reader.log = reader.debug = Path(tmp) / "debug"
            reader.position, reader.utterances = 0, []
            data = "12:15 - SPEECH DISPATCHER: Speaking '•' as char\n".encode()
            split = data.index("•".encode())+1
            reader.debug.write_bytes(data[:split])
            self.assertEqual(reader.spoken(), [])
            with reader.debug.open("ab") as stream:
                stream.write(data[split:] + b"SPEECH DISPATCHER: Speaking 'x' as key\n")
            self.assertEqual(reader.spoken(), ["•", "x"])
            self.assertEqual(reader.spoken(), ["•", "x"])

    def test_debug_receives_line_before_producer_exit(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            dest = Path(tmp) / "debug"
            with open(live_debug(stack,dest), "w", encoding="utf-8") as writer:
                self.assertTrue(writer.isatty())
                writer.write("one utterance\n")
                until = time.monotonic()+2
                while (not dest.is_file() or not dest.stat().st_size) and time.monotonic() < until:
                    time.sleep(.01)
                self.assertEqual(dest.read_text(), "one utterance\n")

    def test_archive_controls_require_real_mask_and_synthesis_after_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            target = "aarch64-unknown-linux-gnu"
            build = {"target":target,"binary_sha256":"test"}
            driver = {p.relative_to(ROOT).as_posix():sha(p) for name in ("native.py","screen_reader.py","desktop_input.py","wayland.py")
                      if (p := HERE.parent/"gui"/name).is_file()}
            for f,v in (("build",build),("driver",driver),("namespace",{})):
                (run/(f+".json")).write_text(json.dumps(v))
            (run/"xserver.log").touch()
            (run/"input-app.log").touch()
            for problem in ("none","clear-key","silent-after-focus","no-synth"):
                with self.subTest(problem=problem):
                    masks = ["•","•","•"] + (["x"] if problem == "clear-key" else [])
                    spoken = ["Dateiname entry.","Kennwort password text.",*masks,"English push button.","Filename entry."]
                    raw = b"x"*400 + (b"\x00" if problem == "silent-after-focus" else b"x")*9000
                    fake = dict(orcaVersion="46.1",orcaModifierDisplay=None,spoken=spoken,protectedFieldSpeech=masks,
                                audioStartOfTraversal=400,audioBytesObserved=len(raw),audioPrefixSha256=hashlib.sha256(raw).hexdigest())
                    (run/"orca-audio.raw").write_bytes(raw)
                    (run/"speechd.log").write_text("Module espeak-ng started successfully\n" + (
                        "" if problem=="no-synth" else "Initialized for server audio for espeak-ng\n"))
                    (run/"orca-debug.log").write_text("".join(f"SPEECH DISPATCHER: Speaking '{s}' as string\n" for s in spoken))
                    data=dict(backend="x11",arch="aarch64",binary_sha256="test",mesa_present_mode_override=None,
                              build=build,driver=driver,runs=[{}]*4,input=dict(backend="x11",screen_reader=fake,password_accessible_text="•••"))
                    (run/"results.json").write_text(json.dumps(data))
                    if problem=="none":
                        self.assertEqual(native(run,target,"test")[1]["measuredAudioBytes"],9000)
                    else:
                        with self.assertRaises(ValueError): native(run,target,"test")


if __name__ == "__main__":
    unittest.main()
