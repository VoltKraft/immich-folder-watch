"""Keep missing input evidence distinct from a completed visual or edit observation."""

import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from observe import TRIALS, digest, run, verify_result
from text_observations import CASES, MissingObservation, wait_value


class ObservationSummary(unittest.TestCase):
    def test_missing_caret_reports_the_received_events_and_keeps_the_negative_field(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "native.log"
            log.write_text("FONT_FIELD\t-1\t-1\t51.50\t-1\tL-بتث-R.jpg\t 4C:16.00:15.72\n"
                           "FONT_INPUT 6 move 70 52 true true false false\nFONT_INPUT 7 gone -1 -1 false true false false\n"
                           "FONT_INPUT incomplete", encoding="utf-8")
            proc = Mock()
            proc.poll.return_value = None
            with self.assertRaises(MissingObservation) as raised:
                wait_value(lambda _: None, proc, log, "initial bidi caret click", start=1, seconds=0)
        info = raised.exception.detail
        self.assertIsNone(info["childExitAtFailure"])
        self.assertEqual(info["phase"], "initial bidi caret click")
        self.assertEqual(info["fieldCount"], info["fieldsBeforeAction"])
        self.assertEqual(info["lastField"]["primary"], -1)
        move, gone = info["lastEguiInputs"]
        self.assertEqual(move["clientPixel"], [70, 52])
        self.assertEqual([move["pass"], gone["pass"]], [6, 7])
        self.assertFalse(move["fieldFocused"])
        self.assertTrue(move["inField"])
        self.assertIsNone(gone["clientPixel"])

    def test_completed_later_cases_cannot_erase_a_missing_click_or_numbers_raster(self):
        rows = [dict(profile=p, name=n, renderedCoverageMatches=True, editMatches=True, caretAfterRightFromStart=1,
                     visualOrderMatches=True, keyboardMatches=True, fieldPixelOrderMatchesOracle=True) for p, n in TRIALS]
        failure = dict(profile="fallback", name="mixed", phase="initial bidi caret click")
        with self.assertRaisesRegex(SystemExit, "initial bidi caret click"):
            verify_result({"runs": rows[:2] + rows[3:], "failures": [failure]}, True)
        with self.assertRaisesRegex(SystemExit, "four"):
            verify_result({"runs": rows[:2], "failures": []}, True)
        verify_result({"runs": rows, "failures": []}, True)
        del rows[-1]["fieldPixelOrderMatchesOracle"]
        with self.assertRaisesRegex(SystemExit, "bidirectional"):
            verify_result({"runs": rows, "failures": []}, True)

    def test_missing_click_is_retained_after_draining_and_observing_the_independent_digits_case(self):
        attempted = []

        def case(profile, name, _controls, _process, log, directory):
            attempted.append((profile, name))
            log.write_text("ADAPTER test adapter\nDRAINED\n", encoding="utf-8")
            (directory / "observed.ppm").write_bytes(b"test readback")
            if name == "mixed":
                raise MissingObservation("initial bidi caret click", None, "", 1)
            return {"profile": profile, "name": name, "renderedCoverageMatches": True, "observedVisual": CASES[name][0]}

        def reference(cmd, **kw):
            if "--version" in cmd:
                return "portable test reference"
            order = next(order for text, order in CASES.values() if text + "\n" == kw["input"])
            return "map\n" + " ".join(map(str, order))

        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            binary = work / "subject"
            binary.write_bytes(b"test process")
            (work / "subject.json").write_text(json.dumps({"target": "test", "binarySha256": digest(binary)}), encoding="utf-8")
            process = Mock()
            process.poll.return_value, process.wait.return_value = None, 0
            with patch("observe.os", SimpleNamespace(name="posix", environ=os.environ)), \
                    patch.dict(sys.modules, {"native": SimpleNamespace(action=Mock())}), \
                    patch("observe.subprocess.Popen", return_value=process), patch("observe.X11Input"), \
                    patch("observe.subprocess.check_output", side_effect=reference), \
                    patch("observe.check_case", side_effect=case), patch("builtins.print"):
                run(binary, work)
            report = json.loads((work / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(attempted, list(TRIALS))
            self.assertTrue(report["failures"][0]["drained"])
            self.assertEqual(report["failures"][0]["nativeLogSha256"], digest(work / "fallback-mixed/native.log"))
            self.assertEqual(report["runs"][-1]["name"], "numbers")
            with self.assertRaisesRegex(SystemExit, "initial bidi caret click"):
                verify_result(report, True)


if __name__ == "__main__":
    unittest.main()
