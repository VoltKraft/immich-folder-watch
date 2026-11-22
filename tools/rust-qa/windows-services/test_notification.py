"""Receipt regressions for the late read-only Shell presentation observer."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import notification as n

TOKEN = "cf" * 16
WIN = r"C:\Windows"
HOST = dict(hwnd=212, creation=19, pid=34, session=2, sameUser=True, image=WIN + r"\explorer.exe", windowClass="Shell_TrayWnd")
LABEL = dict(pid=34, bounds=[10, 10, 100, 24], point=[55, 17], offscreen=False, nativeHit=True, providerHit=True)
MATCH = dict(desktop="Default", tick=192, host=HOST, container="12,87",
             title=dict(LABEL, text="IFW notice " + TOKEN, runtimeId="12,88"),
             body=dict(LABEL, text="Synthetic IFW notification " + TOKEN, runtimeId="12,89"))
BASE = {"notice.pid": 14, "notice.icon_id": 23, "notice.owner_hwnd": 110, "notice.thread_desktop": "Default",
        "notice.session": 2, "notice.initial.add": True, "notice.initial.version4": True, "notice.notification_state": 6,
        "notice.notification_request": True, "notice.requested": True, "notice.balloon_show": 1, "notice.balloon_hide": 0,
        "notice.balloon_click": 0, "notice.balloon_timeout": 0, "notice.taskbar_created": 0,
        "notice.remove": True, "notice.receiver_closed": True}


def subject():
    return dict(subject=dict(pid=14, exit=0, jobEmpty=True), receiver=dict(hwnd=110))


class NotificationTests(unittest.TestCase):
    def test_raw_shell_callback_during_quiet_time_does_not_substitute_for_visible_title_and_body(self):
        absent = dict(stage="unavailable", reason="missing title/body")
        stated = dict(stage="visible", match=MATCH)
        for metrics, event, expected in ((BASE, absent, "unavailable"), (BASE, stated, "passed"),
                                        (BASE | {"notice.balloon_show": 0}, stated, "unavailable"),
                                        (BASE | {"notice.taskbar_created": 1}, stated, "unavailable"), (BASE, None, "unavailable")):
            report = subject()
            self.assertEqual(n.outcome(metrics, event, TOKEN, 2, WIN, report), expected)
            self.assertEqual(report["observations"]["queryName"], "QUIET_TIME")
            self.assertEqual(report["observations"]["independentlyVisible"], event is stated)
        declined = BASE | {"notice.initial.add": False, "notice.requested": False, "notice.balloon_show": 0}
        for k in ("notice.initial.version4", "notice.remove", "notice.notification_request"):
            declined.pop(k)
        self.assertEqual(n.outcome(declined, absent, TOKEN, 2, WIN, subject()), "unavailable")
        with self.assertRaises(ValueError):
            n.outcome(declined, stated, TOKEN, 2, WIN, subject())

    def test_receiver_identity_and_cleanup_failure_keep_confirmed_presentation_observable(self):
        event = dict(stage="visible", match=MATCH)
        for changes in ({"notice.remove": False}, {"notice.receiver_closed": False}):
            report = subject()
            with self.assertRaises(n.CleanupUnconfirmed):
                n.outcome(BASE | changes, event, TOKEN, 2, WIN, report)
            self.assertTrue(report["observations"]["independentlyVisible"])
            self.assertEqual(report["observations"]["show"], 1)
        with self.assertRaisesRegex(ValueError, "mismatched native"):
            n.outcome(BASE | {"notice.owner_hwnd": 111}, event, TOKEN, 2, WIN, subject())

    def test_exact_pair_requires_same_session_os_host_and_two_separate_on_screen_hits(self):
        n.check_match(MATCH, TOKEN, 2, WIN)
        for key, subkey, value in (("host", "image", r"C:\untrusted\explorer.exe"), ("host", "session", 3),
                                   ("host", "sameUser", False), ("body", "text", "Another notification"),
                                   ("title", "offscreen", True), ("title", "point", [100, 11]), ("body", "nativeHit", False),
                                   ("title", "bounds", [0, 0, float("nan"), 30]), ("body", "providerHit", False),
                                   ("title", "pid", 35), ("title", "runtimeId", "12,89")):
            sample = deepcopy(MATCH)
            sample[key][subkey] = value
            with self.subTest(key=key, subkey=subkey), self.assertRaises(ValueError):
                n.check_match(sample, TOKEN, 2, WIN)

    def test_only_armed_current_request_can_account_for_the_visible_sample(self):
        seen = dict(stage="visible", match=MATCH)
        armed = dict(stage="armed", tick=160, preexistingMatch=False)
        self.assertEqual(n.observed_presentation([armed, seen], TOKEN, 2, WIN, 182, 210), seen)
        for sequence, release, finish in (([seen], 182, 210), ([armed, seen, seen], 182, 210),
                                          ([armed | {"preexistingMatch": True}, seen], 182, 210),
                                          ([armed, seen], 193, 210), ([armed, seen], 182, 190)):
            with self.assertRaises(ValueError):
                n.observed_presentation(sequence, TOKEN, 2, WIN, release, finish)

    def test_early_build_can_be_reused_after_an_unrelated_early_observer_failure_only_with_its_exact_inputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "early"
            original.mkdir()
            (root / "rust").mkdir()
            binary = root / "services.exe"
            binary.write_bytes(b"fixture")
            source = root / "service.rs"
            source.write_bytes(b"compiled input")
            target = "x86_64-pc-windows-msvc"
            graph = {"fixture": 3}
            digest = hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            (root / "inputs.json").write_text(json.dumps(dict(lockSha256="lock", targetGraphs={target: digest})))
            (root / "rust/toolchain-inputs.json").write_text(json.dumps(dict(version="1.100.0", commit="abc")))
            (original / "compiler.txt").write_text(f"host: {target}\nrelease: 1.100.0\ncommit-hash: abc\n")
            (original / "graph.json").write_text(json.dumps(graph))
            (original / "build.txt").write_text("built")
            (original / "balloon-id.txt").write_text("test tray::shell::notification_tests::balloon_callbacks_belong_to_the_registered_v4_icon ... ok\n")
            inputs = dict(hosted=True, target=target, head="revision", runner="host", workflowRun="7", workflowAttempt="2",
                          probeCompleted=False, probeSha256=n.sha(binary), locked="lock", canonicalGraphSha256=digest,
                          measureUptimeMs=420, sourceFiles={"service.rs": n.sha(source)},
                          evidenceFiles={p.name: n.sha(p) for p in original.iterdir()},
                          steps=dict(compiler=0, inventory=0, format=0, clippy=0, build=0, **{"balloon-id": 0}))
            (original / "result.json").write_text(json.dumps(inputs))
            env = dict(GITHUB_SHA="revision", GITHUB_RUN_ID="7", GITHUB_RUN_ATTEMPT="2", RUNNER_NAME="host")
            with (patch.object(n, "ROOT", root), patch.object(n, "HERE", root), patch.object(n, "DEPS", []),
                  patch.object(n, "source_files", return_value=[source]), patch.dict(n.os.environ, env),
                  patch.object(n.subprocess, "check_output", return_value="revision\n")):
                report = {}
                n.bind_build(target, binary, original, report)
                self.assertFalse(report["earlyProbeCompleted"])
                for path in (binary, source, original / "compiler.txt", original / "graph.json"):
                    data = path.read_bytes()
                    path.write_bytes(data + b"changed")
                    with self.assertRaises(ValueError):
                        n.bind_build(target, binary, original, {})
                    path.write_bytes(data)
                inputs["workflowAttempt"] = "1"
                (original / "result.json").write_text(json.dumps(inputs))
                with self.assertRaises(ValueError):
                    n.bind_build(target, binary, original, {})


if __name__ == "__main__":
    unittest.main()
