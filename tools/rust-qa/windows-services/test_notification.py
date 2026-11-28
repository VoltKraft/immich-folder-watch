"""Receipt regressions for the late read-only Shell presentation observer."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import notification_probe as n
import notification_host as h
from service_sources import verify_checkout

TOKEN = "cf" * 16
WIN = r"C:\Windows"
HOST = dict(hwnd=212, creation=19, pid=34, session=2, sameUser=True, image=WIN + r"\explorer.exe", windowClass="Shell_TrayWnd")
def label(text, runtime, bounds, point):
    return dict(text=text + TOKEN, runtimeId=runtime, directParent="12,87", pid=34, bounds=bounds, point=point,
                offscreen=False, nativeHit=dict(hwnd=214, root=212, monitor=134, pid=34, tid=752),
                providerHit=dict(pid=34, runtimePath=[runtime], kind="label"))


MATCH = dict(desktop="Default", tick=192, host=HOST, container="12,87", rootId="12,80",
             title=label("IFW notice ", "12,88", [10, 10, 100, 24], [55, 17]),
             body=label("Synthetic IFW notification ", "12,89", [10, 24, 120, 40], [65, 32]))
SHELL = dict(taskbar_hwnd=212, taskbar_pid=34, taskbar_tid=752, taskbar_creation=19, taskbar_session=2,
             taskbar_desktop="Default", shell_hwnd=124, shell_pid=34, shell_tid=168)
BASE = {"notice.pid": 14, "notice.tid": 152, "notice.icon_id": 23, "notice.owner_hwnd": 110,
        "notice.initial.add": True, "notice.initial.version4": True, "notice.notification_state": 6,
        "notice.notification_request": True, "notice.requested": True, "notice.balloon_show": 1, "notice.balloon_hide": 0,
        "notice.balloon_click": 0, "notice.balloon_timeout": 0, "notice.taskbar_created": 0,
        "notice.remove": True, "notice.receiver_closed": True}
for phase in ("notice", "notice_after"):
    BASE.update({phase + "." + k: v for k, v in dict(SHELL, shell_window=True, taskbar_present=True, taskbar_visible=True,
                                                     station_visible=True, thread_desktop="Default", session=2).items()})


def subject():
    return dict(subject=dict(pid=14, exit=0, jobEmpty=True), receiver=dict(hwnd=110, readback=dict(tid=152)),
                registrationHost={name: dict(SHELL, verified=True) for name in
                                  ("beforeLaunch", "beforeRequest", "afterRequest", "afterQuit")})


def trace(match_sample=None):
    """A 1 kHz synthetic clock with a Shell request from 186 to 202 and ten seconds of post-request sweeps."""
    baseline = dict(stage="armed", tick=160, qpc=160, nativeBeforeQpc=159, nativeAfterQpc=161,
                    frequency=1000, initialRoots=3, preexistingMatch=False)
    rows = []
    for start, stop, released, sent in [(170, 175, False, False), (188, 198, True, False)] + [
            (start, start + 5, True, True) for start in range(210, 10211, 100)]:
        number = len(rows) + 1
        row = dict(stage="sample", number=number, startQpc=start, endQpc=stop, released=released, sent=sent,
                   roots=3, providerErrors=0)
        if number == match_sample:
            row["match"] = MATCH | {"qpc": start + 4}
        rows.append(row)
    terminal = dict(stage="visible" if match_sample else "unavailable", complete=True, samples=len(rows),
                    sentObservedQpc=208, peakKnownRoots=3, providerErrors=0)
    record = dict(armBeforeRequest=n.arm_event([baseline, rows[0]]), qpcFrequency=1000,
                  releaseQpc=182, acknowledgedQpc=210, finishQpc=10230)
    native = BASE | {"notice.qpc_frequency": 1000, "notice.request_begin_qpc": 186, "notice.request_end_qpc": 202}
    return [baseline, *rows, terminal], record, native


def observed(events, record, native):
    return n.observed_presentation(events, TOKEN, 2, WIN, record, native)


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

    def test_transient_match_during_synchronous_call_is_retained_through_the_full_post_request_interval(self):
        for number, phase in ((2, "during-shell-call"), (3, "after-shell-call")):
            events, record, native = trace(number)
            event = observed(events, record, native)
            self.assertEqual(event["match"], events[number]["match"])
            self.assertEqual(record["samplingWindow"]["acceptedSample"], number)
            self.assertEqual(record["samplingWindow"]["matchPhase"], phase)
            self.assertEqual(record["samplingWindow"]["nativeOverlapSamples"], 1)
            self.assertTrue(record["samplingWindow"]["fullPostRequest"])
            self.assertEqual(n.outcome(native, event, TOKEN, 2, WIN, subject()), "passed")

    def test_a_post_request_match_survives_a_short_call_between_sweeps_and_a_sweep_can_span_the_return(self):
        events, record, native = trace(3)
        for begin, end in ((201, 204), (198, 202), (182, 188), (193, 193)):
            native.update({"notice.request_begin_qpc": begin, "notice.request_end_qpc": end})
            with self.subTest(begin=begin, end=end):
                event = observed(events, record, native)
                self.assertEqual(n.outcome(native, event, TOKEN, 2, WIN, subject()), "passed")
                self.assertEqual(record["samplingWindow"]["nativeOverlapSamples"], 0)
                self.assertEqual(record["samplingWindow"]["matchPhase"], "after-shell-call")
        events, record, native = trace(2)
        events[2]["endQpc"] = 206
        events[2]["match"]["qpc"] = 204
        self.assertEqual(observed(events, record, native)["stage"], "visible")
        self.assertEqual(record["samplingWindow"]["matchPhase"], "spans-shell-return")

    def test_sparse_delayed_or_blocked_post_request_scans_preserve_a_real_match_but_fail_the_trial(self):
        for case in ("two-distant-sweeps", "late-return-marker", "blocked-last-sweep"):
            events, record, native = trace(2)
            if case == "two-distant-sweeps":
                events = events[:4] + events[-2:]
                events[-2]["number"] = events[-1]["samples"] = 4
            elif case == "late-return-marker":
                for row in events[3:-1]:
                    row["startQpc"] += 1200
                    row["endQpc"] += 1200
                events[-1]["sentObservedQpc"] += 1200
                record["finishQpc"] += 1200
            else:
                events[-2]["endQpc"] += 1200
                record["finishQpc"] += 1200
            event = observed(events, record, native)
            window = record["samplingWindow"]
            with self.subTest(case=case):
                self.assertFalse(window["fullPostRequest"])
                self.assertGreater(window["maxPostIntervalQpc"], window["maxPostIntervalLimitQpc"])
                self.assertEqual(window["postStartQpc"], native["notice.request_end_qpc"])
                self.assertEqual(event["stage"], "incomplete")
                self.assertEqual(event["match"], events[2]["match"])
                report = subject()
                with self.assertRaisesRegex(ValueError, "exceeded one second"):
                    n.outcome(native, event, TOKEN, 2, WIN, report)
                self.assertTrue(report["observations"]["independentlyVisible"])

    def test_pending_or_pre_request_ui_read_cannot_prove_the_notification_was_shown(self):
        events, record, native = trace(2)
        for start, released in ((180, False), (184, True), (186, True)):
            events[2].update(startQpc=start, released=released)
            with self.subTest(start=start):
                self.assertEqual(observed(events, record, native)["stage"], "unavailable")
                self.assertNotIn("acceptedSample", record["samplingWindow"])
        events[3]["match"] = MATCH | {"qpc": 214}
        self.assertEqual(observed(events, record, native)["match"], events[3]["match"])
        events[2]["startQpc"] = 184
        events[2]["match"]["qpc"] = 185
        with self.assertRaisesRegex(ValueError, "before its Shell request"):
            observed(events, record, native)

    def test_only_an_active_negative_sweep_can_release_the_sender(self):
        events, record, _ = trace()
        self.assertIsNotNone(n.arm_event(events[:2]))
        for items in ([], events[:1], [events[0] | {"preexistingMatch": True}, events[1]],
                      [events[0] | {"nativeBeforeQpc": 162}, events[1]],
                      [events[0], events[1] | {"match": MATCH}], [events[0], events[1] | {"providerErrors": 1}],
                      [events[0], events[1] | {"released": True}], [events[0], events[1] | {"startQpc": 159}],
                      [events[0], dict(stage="unavailable")]):
            self.assertIsNone(n.arm_event(items))
        self.assertEqual(record["armBeforeRequest"]["lastSampleEndQpc"], 175)
        with patch.object(n, "events", side_effect=[events[:1], events[:2]]), patch.object(n.time, "sleep"):
            self.assertTrue(n.wait_for_observer(None, Mock(poll=Mock(return_value=None))))
        with patch.object(n, "events", return_value=events[:2]):
            self.assertFalse(n.wait_for_observer(None, Mock(poll=Mock(return_value=2))))

    def test_missing_or_disordered_receipts_and_incomplete_post_request_sampling_are_rejected(self):
        for description, edit in (
                ("missed arm", lambda e, r, m: r.update(armBeforeRequest=None)),
                ("preexisting title", lambda e, r, m: e[0].update(preexistingMatch=True)),
                ("frequency", lambda e, r, m: m.update({"notice.qpc_frequency": 1001})),
                ("release after call", lambda e, r, m: r.update(releaseQpc=187)),
                ("native return after observer acknowledgement", lambda e, r, m: m.update({"notice.request_end_qpc": 209})),
                ("no native timing", lambda e, r, m: m.pop("notice.request_end_qpc")),
                ("missing sweep", lambda e, r, m: e.pop(2)),
                ("reversed sweep", lambda e, r, m: e[2].update(endQpc=180)),
                ("lost sent marker", lambda e, r, m: e[4].update(sent=False)),
                ("sampled after finish", lambda e, r, m: r.update(finishQpc=10212)),
                ("no ten-second window", lambda e, r, m: e.pop(-2)),
                ("false complete", lambda e, r, m: e[-1].update(complete=False)),
                ("missing root evidence", lambda e, r, m: e[-1].update(peakKnownRoots=4)),
                ("sampled physical hit after query", lambda e, r, m: e[2]["match"].update(qpc=199)),
                ("untimed terminal match", lambda e, r, m: e[-1].update(match=MATCH)),
                ("duplicate outcome", lambda e, r, m: e.append(e[-1]))):
            events, record, native = trace(2)
            edit(events, record, native)
            with self.subTest(description=description), self.assertRaises(ValueError):
                observed(events, record, native)
        events, record, native = trace()
        native.update({"notice.request_begin_qpc": 201, "notice.request_end_qpc": 204})
        self.assertIn("between two", observed(events, record, native)["reason"])
        self.assertEqual(record["samplingWindow"]["nativeOverlapSamples"], 0)

    def test_declined_icon_still_requires_a_complete_observer_receipt_and_cannot_have_call_timestamps(self):
        events, record, native = trace()
        native.update({"notice.initial.add": False, "notice.requested": False, "notice.balloon_show": 0})
        for key in ("notice.initial.version4", "notice.notification_request", "notice.remove",
                    "notice.request_begin_qpc", "notice.request_end_qpc"):
            native.pop(key)
        absent = observed(events, record, native)
        self.assertEqual(n.outcome(native, absent, TOKEN, 2, WIN, subject()), "unavailable")
        self.assertTrue(record["samplingWindow"]["fullPostRequest"])
        self.assertEqual(record["samplingWindow"]["nativeOverlapSamples"], 0)
        for key in ("notice.request_begin_qpc", "notice.request_end_qpc", "notice.notification_request.raw_last_error"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "unregistered"):
                observed(events, record, native | {key: 192})
        with self.assertRaisesRegex(ValueError, "complete sampling interval"):
            observed(events[:-1] + [dict(stage="unavailable", complete=False)], record, native)
        with self.assertRaises(ValueError):
            observed(events[:3] + events[-1:], record, native)
        events, record, _ = trace(2)
        with self.assertRaises(ValueError):
            observed(events, record, native)

    def test_shared_parent_requires_separately_hittable_pixels_and_immediate_parent_in_both_labels(self):
        sample = deepcopy(MATCH)
        for key in ("title", "body"):
            sample[key]["providerHit"] = dict(pid=34, runtimePath=[sample["container"]], kind="sharedParent")
        n.check_match(sample, TOKEN, 2, WIN)
        for name, changes in (
                ("body", dict(bounds=sample["title"]["bounds"], point=sample["title"]["point"])),
                ("body", dict(bounds=sample["title"]["bounds"], point=[56, 17])),
                ("body", dict(bounds=[10, 16, 120, 40])),
                ("title", dict(directParent="12,7")),
                ("body", dict(providerHit=dict(pid=34, runtimePath=["12,700"], kind="sharedParent")))):
            invalid = deepcopy(sample)
            invalid[name].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                n.check_match(invalid, TOKEN, 2, WIN)
        with self.assertRaises(ValueError):
            n.check_match(dict(sample, rootId=sample["container"]), TOKEN, 2, WIN)

    def test_hit_path_and_native_window_owner_are_checked(self):
        positive = deepcopy(MATCH)
        positive["title"]["providerHit"] = dict(kind="descendant", pid=34, runtimePath=["12,18", positive["title"]["runtimeId"]])
        n.check_match(positive, TOKEN, 2, WIN)
        for field, key, val in (("providerHit", "runtimePath", ["12,18", "12,89"]),
                                ("providerHit", "runtimePath", ["12,87", "12,88"]),
                                ("providerHit", "runtimePath", ["12,89", "12,88"]),
                                ("providerHit", "pid", 89), ("nativeHit", "root", 442),
                                ("nativeHit", "pid", 443), ("nativeHit", "hwnd", 0), ("nativeHit", "monitor", 0)):
            invalid = deepcopy(positive)
            invalid["title"][field][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                n.check_match(invalid, TOKEN, 2, WIN)

    def test_late_receipt_requires_original_taskbar_session_and_live_explorer_across_all_reads(self):
        visible = dict(stage="visible", match=MATCH)
        for phase in ("notice", "notice_after"):
            for key, value in (("taskbar_present", False), ("taskbar_creation", 20), ("taskbar_pid", 191),
                               ("taskbar_tid", 78), ("taskbar_hwnd", 999), ("shell_tid", 0), ("shell_window", False),
                               ("taskbar_session", 3), ("taskbar_desktop", "Other")):
                report = subject()
                with self.subTest(phase=phase, key=key):
                    self.assertEqual(n.outcome(BASE | {phase + "." + key: value}, visible, TOKEN, 2, WIN, report), "unavailable")
                    self.assertTrue(report["observations"]["independentlyVisible"])
        for phase in ("beforeLaunch", "beforeRequest", "afterRequest", "afterQuit"):
            report = subject()
            report["registrationHost"][phase]["taskbar_creation"] += 1
            self.assertEqual(n.outcome(BASE, visible, TOKEN, 2, WIN, report), "unavailable")
            report = subject()
            report["registrationHost"][phase]["verified"] = False
            self.assertEqual(n.outcome(BASE, visible, TOKEN, 2, WIN, report), "unavailable")
        report = subject()
        for image, expected in ((WIN + r"\explorer.exe", "unavailable"),
                                (WIN + r"\SystemApps\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\StartMenuExperienceHost.exe", "passed")):
            sample = deepcopy(MATCH)
            sample["host"].update(creation=250, image=image)
            self.assertEqual(n.outcome(BASE, dict(stage="visible", match=sample), TOKEN, 2, WIN, report), expected)

    def test_early_replacement_and_absence_do_not_disqualify_a_stable_independent_late_request(self):
        for early, relation in (({}, "early-observation-unavailable"), ({"taskbar_present": False}, "early-taskbar-absent"),
                                (dict(SHELL, taskbar_present=True, taskbar_creation=None), "early-identity-unverified"),
                                (dict(SHELL, taskbar_present=True, taskbar_creation=87), "different-explorer-process"),
                                (dict(SHELL, taskbar_present=True, taskbar_hwnd=318), "same-explorer-new-taskbar"),
                                (dict(SHELL, taskbar_present=True), "same-explorer-and-taskbar")):
            report = subject()
            report["earlyNotification"] = {"host": early}
            self.assertEqual(n.outcome(BASE, dict(stage="visible", match=MATCH), TOKEN, 2, WIN, report), "passed")
            self.assertEqual(report["observations"]["earlyHostComparison"], relation)

    def test_host_witness_checks_actual_handle_after_reading_its_image_and_rechecks_both_window_owners(self):
        api, desk = Mock(), Mock()
        api.open.return_value = 3
        desk.shell.return_value = 124
        def owner(hwnd, pid):
            pid._obj.value = 34
            return 752 if hwnd == 212 else 168
        desk.owner.side_effect = owner
        desk.context.return_value = {"session": 2}
        desk.pid_session.return_value = 2
        desk.name.return_value = "Default"
        desk.visible.return_value = True
        def image(handle, _, path, size):
            self.assertEqual(handle, 3)
            path.value = WIN + r"\explorer.exe"
            return True
        desk.image.side_effect = image
        api.process_identity.return_value = 19
        bar, wait = Mock(return_value=212), Mock(return_value=258)
        with (patch.object(h.c, "WinDLL", create=True), patch.object(h, "bind", side_effect=[bar, wait]),
              patch.object(h, "ordinary_console", return_value=True), ExitStack() as pins):
            witness = h.ShellWitness(api, desk, 2, WIN, pins)
            sample = witness.sample()
            self.assertTrue(sample["verified"])
            self.assertEqual({k: sample[k] for k in SHELL}, SHELL)
            wait.side_effect = [258, 0]  # The original process exited during the read.
            self.assertFalse(witness.sample()["verified"])
            wait.side_effect = None
            bar.side_effect = [212, 435]
            self.assertFalse(witness.sample()["verified"])
            bar.side_effect = None
            reads = 0
            def replaced(hwnd, pid):
                nonlocal reads
                reads += 1
                tid = owner(hwnd, pid)
                if reads >= 3:
                    pid._obj.value = 88
                return tid
            desk.owner.side_effect = replaced
            self.assertFalse(witness.sample()["verified"])
            api.close.assert_not_called()
        api.open.assert_called_once_with(0x101000, False, 34)
        api.close.assert_called_once_with(3)

    def test_unknown_job_membership_preserves_the_original_failure_and_owned_profile(self):
        import native
        for operation in ("query-after-exit", "terminate", "final-query", "process-close", "job-close"):
            api, proc, record = Mock(), Mock(), {}
            api.new_job.return_value = 71
            api.machine.return_value = (34, 34)
            api.process_identity.return_value = 191
            api.close.return_value = True
            api.file_info.return_value = (16, "fixture-id")
            proc.pid, proc._handle = 54, 543
            proc.wait.return_value = 0
            err = OSError("controlled " + operation)
            api.wait_job_empty.side_effect = {"query-after-exit": [err], "terminate": [False], "final-query": [True, err]}.get(
                operation, [True, True])
            if operation == "terminate":
                api.terminate_job.side_effect = err
            if operation == "process-close":
                proc.close.side_effect = err
            if operation == "job-close":
                def close(handle):
                    if handle == 71:
                        raise err
                    return True
                api.close.side_effect = close
            with TemporaryDirectory() as tmp:
                area = Path(tmp) / ("ifw-shell-" + TOKEN)
                api.create_child_directory.side_effect = lambda *args: (area.mkdir() or 5)
                with (patch.object(n, "start", return_value=proc),
                      patch.object(native, "pin_path", return_value=nullcontext((4, "parent"))),
                      patch.object(native, "remove_owned_contents") as cleanup,
                      self.subTest(operation=operation), self.assertRaises(n.CleanupUnconfirmed) as seen):
                    with n.fixture_profile(api, Path(tmp), TOKEN, record) as profile:
                        (profile / "witness").write_text("retained")
                        with n.child(api, Path("windows.exe"), [], profile, {}, profile / "log", record):
                            pass
                self.assertIs(seen.exception.__cause__, err)
                self.assertEqual(record["exit"], 0)
                self.assertFalse(record["profileRemoved"])
                self.assertTrue((area / "witness").is_file())
                cleanup.assert_not_called()
                proc.close.assert_called_once()

    def test_notification_profile_reaches_native_creation_under_its_pinned_parent(self):
        import native
        api = object.__new__(n.Win32)
        # Stop at the OS boundary after exercising the real name and parent checks.
        api.nt_create = Mock(side_effect=OSError("controlled native creation failure"))
        with TemporaryDirectory() as temp, patch.object(native, "pin_path", return_value=nullcontext((42, "parent"))):
            with self.assertRaisesRegex(OSError, "controlled native creation failure"):
                with n.fixture_profile(api, Path(temp), TOKEN, {}):
                    self.fail("The operating system rejected creation")
            api.nt_create.assert_called_once()
            attributes = api.nt_create.call_args.args[2]._obj
            self.assertEqual(attributes.root, 42)
            counted = attributes.name.contents
            self.assertEqual(n.c.wstring_at(counted.buffer), "ifw-shell-" + TOKEN)
            for invalid_token in (TOKEN[:-1], TOKEN.upper(), TOKEN + "/extra"):
                with self.subTest(token=invalid_token), self.assertRaises(ValueError):
                    with n.fixture_profile(api, Path(temp), invalid_token, {}):
                        self.fail("Expected a single lowercase-token fixture name")
            api.nt_create.assert_called_once()

    def test_checkout_proof_refuses_untracked_inputs_and_shared_dirty_inputs_even_when_early_and_late_agree(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked, untracked = root / "unit.py", root / "extra.py"
            tracked.write_bytes(b"fixture\n")
            (root / ".gitattributes").write_text("* text eol=crlf\n")
            def git(*args):
                return subprocess.check_output(["git", "-c", "user.name=Test", "-c", "user.email=test@invalid",
                                                "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.DEVNULL)
            git("init", "-q")
            git("add", ".gitattributes", tracked.name)
            git("commit", "-qm", "fixture")
            head = git("rev-parse", "HEAD").decode().strip()
            tracked.write_bytes(b"fixture\r\n")
            self.assertEqual(verify_checkout(root, [tracked], head), {tracked.name: n.sha(tracked)})
            untracked.write_text("fixture")
            with self.assertRaises(ValueError):
                verify_checkout(root, [tracked, untracked], head)
            tracked.write_text("modified")
            git("update-index", "--assume-unchanged", tracked.name)
            with self.assertRaises(ValueError):
                verify_checkout(root, [tracked], head)

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
            (original / "notification-points.txt").write_text("Notification pixel selection passed.\nNotification timing controls passed.\n")
            (original / "native.txt").write_text("tray.taskbar_present=true\ntray.taskbar_creation=19\ntray.taskbar_pid=34\n")
            inputs = dict(checkoutVerified=True, hosted=True, target=target, head="revision", runner="host", workflowRun="7", workflowAttempt="2",
                          probeCompleted=False, probeSha256=n.sha(binary), locked="lock", canonicalGraphSha256=digest,
                          measureUptimeMs=420, sourceFiles={"service.rs": n.sha(source)},
                          evidenceFiles={p.name: n.sha(p) for p in original.iterdir()},
                          steps=dict(compiler=0, inventory=0, format=0, clippy=0, build=0,
                                     **{"balloon-id": 0, "notification-points": 0}))
            (original / "result.json").write_text(json.dumps(inputs))
            env = dict(GITHUB_SHA="revision", GITHUB_RUN_ID="7", GITHUB_RUN_ATTEMPT="2", RUNNER_NAME="host")
            with (patch.object(n, "ROOT", root), patch.object(n, "HERE", root),
                  patch.dict(n.os.environ, env),
                  patch.object(n.subprocess, "check_output", return_value="revision\n")):
                report = {"observerInputs": {"service.rs": n.sha(source)}}
                n.bind_build(target, binary, original, report)
                self.assertFalse(report["earlyProbeCompleted"])
                self.assertEqual(report["earlyNotification"]["host"]["taskbar_creation"], 19)
                self.assertEqual(report["earlyNotification"]["nativeSha256"], n.sha(original / "native.txt"))
                for path in (binary, source, original / "compiler.txt", original / "graph.json", original / "native.txt"):
                    data = path.read_bytes()
                    path.write_bytes(data + b"changed")
                    with self.assertRaises(ValueError):
                        n.bind_build(target, binary, original, {"observerInputs": {"service.rs": n.sha(source)}})
                    path.write_bytes(data)
                points = original / "notification-points.txt"
                restored = points.read_bytes()
                points.write_text("Notification pixel selection passed.\n")
                inputs["evidenceFiles"][points.name] = n.sha(points)
                (original / "result.json").write_text(json.dumps(inputs))
                with self.assertRaisesRegex(ValueError, "sampling controls"):
                    n.bind_build(target, binary, original, {"observerInputs": {source.name: n.sha(source)}})
                points.write_bytes(restored)
                inputs["evidenceFiles"][points.name] = n.sha(points)
                inputs["workflowAttempt"] = "1"
                (original / "result.json").write_text(json.dumps(inputs))
                with self.assertRaises(ValueError):
                    n.bind_build(target, binary, original, {"observerInputs": {"service.rs": n.sha(source)}})


if __name__ == "__main__":
    unittest.main()
