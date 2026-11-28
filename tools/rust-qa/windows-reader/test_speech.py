import tempfile
import unittest
from pathlib import Path

from speech import EXPECTED, LogTail, Speech


HEADER = "IO - speech.speech.speak (17:03:40.183) - MainThread (3480):"


class SpeechTests(unittest.TestCase):
    def test_only_ordered_reader_output_advances(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe = Speech(root)
            probe.line("Speaking ['Dateiname']")
            probe.line("IO - keyboardHandler.internal_keyDownEvent (17:03:40.183):")
            probe.line("Speaking ['Dateiname']")
            for text in ("Kennwort", "Dateiname", "Kennwort", "star", "*", "•", "English", "Filename"):
                probe.line(HEADER)
                probe.line(f"Speaking ['{text}']")
            self.assertEqual(tuple(probe.observed), EXPECTED)
            self.assertEqual({path.name for path in root.iterdir()}, set(EXPECTED))

    def test_password_character_fails_before_a_positive_mask_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            probe = Speech(Path(temp))
            for text in ("Dateiname", "Kennwort"):
                probe.line(HEADER)
                probe.line(f"Speaking ['{text}']")
            probe.line(HEADER)
            with self.assertRaisesRegex(ValueError, "clear synthetic password"):
                probe.line("Speaking [CharacterModeCommand(True), 'z']")

    def test_pass_next_key_requires_the_request_and_actual_reader_speech(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe = Speech(root)
            for text in ("Dateiname", "Kennwort", "*", "*", "*", "English", "Filename", "Pass next key through"):
                probe.line(HEADER)
                probe.line(f"Speaking ['{text}']")
            self.assertFalse(probe.pass_key_announced)
            (root / "request-pass-key").touch()
            probe.line("IO - keyboardHandler.internal_keyDownEvent (17:03:40.183):")
            probe.line("Speaking ['Pass next key through']")
            probe.line(HEADER)
            probe.line("Speaking ['Pass next key through again']")
            self.assertFalse(probe.pass_key_announced)
            probe.line(HEADER)
            probe.line("Speaking ['Pass next key through']")
            self.assertTrue(probe.pass_key_announced)
            self.assertTrue((root / "pass-key-announced").exists())
            self.assertEqual(tuple(probe.observed), EXPECTED)

    def test_tail_waits_for_the_complete_output_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "test.log"
            probe = Speech(root)
            tail = LogTail(path, probe)
            path.write_bytes((HEADER + "\r\nSpeaking ['Datei").encode())
            tail.read()
            self.assertFalse(probe.observed)
            with path.open("ab") as stream:
                stream.write(b"name']\r\n")
            tail.read()
            tail.read()
            self.assertEqual(probe.observed, ["Dateiname"])
