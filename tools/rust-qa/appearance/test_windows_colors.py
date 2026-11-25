"""Test the native fixture's rollback and independent bitmap checks using synthetic observations."""
from dataclasses import replace
from concurrent.futures import Future
from contextlib import contextmanager
import ctypes as c
import hashlib
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
observer = runpy.run_path(str(HERE / "windows.py"))
from windows_colors import AVAILABLE, ON, HighContrast, State, SystemColors, contrast_cycle, label_bitmap, label_colors


BASE = State(AVAILABLE | 4, "original scheme", {"window": [248, 248, 248], "text": [0, 0, 0]})
HIGH = replace(BASE, flags=BASE.flags | ON, colors={"window": [20, 30, 40], "text": [255, 225, 0]})


class FakeSystem:
    def __init__(self, state=BASE):
        self.state, self.calls = state, []

    def read(self):
        return self.state

    def set_mode(self, original, enabled):
        self.calls.append(enabled)
        self.state = HIGH if enabled else BASE


def instant(read, condition, label):
    state = read()
    if not condition(state):
        raise TimeoutError(label)
    return state


def run_cycle(system, capture=lambda phase, state: {"rasterSha256": str(state.flags)}, record=None,
              window_guard=lambda: None):
    record = {} if record is None else record
    contrast_cycle(system, lambda: None, window_guard, capture, record, wait=instant)
    return record


def bitmap(foreground, paper):
    width, height = 7, 5
    stride = (3 * width + 3) & ~3
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            color = foreground if x == 1 else ([110, 102, 123] if x == 2 else paper)
            pixels.extend(reversed(color))
        pixels.extend(bytes(stride - 3 * width))
    return (b"BM" + struct.pack("<IHHI", 54+len(pixels), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0) + pixels)


class WindowsContrastTests(unittest.TestCase):
    def test_passive_label_crop_requires_its_entire_unobstructed_rectangle(self):
        host = (Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                if os.name == "nt" else shutil.which("pwsh"))
        if not host:
            self.skipTest("PowerShell is required for the label observer")
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, POWERSHELL_TELEMETRY_OPTOUT="1")
            if os.name != "nt":
                for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
                    env[key] = str(Path(temp) / key)
            subprocess.run([host, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", HERE / "test_passive_label.ps1"], cwd=temp, env=env, check=True, timeout=30)

    def test_publisher_restores_its_thread_before_closing_the_owned_handle(self):
        publish = observer["on_subject_desktop"]
        name = "IfwQa_" + "1" * 32
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                active = [21]
                events = []
                api = Mock()
                api.open_named.return_value = 42
                api.thread.return_value = 7
                api.thread_desktop.side_effect = lambda _: active[0]
                api.name.side_effect = {21: "Default", 42: name}.__getitem__
                def attach(handle):
                    events.append(("attach", handle))
                    active[0] = handle
                    return True
                def close(handle):
                    events.append(("close", handle))
                    return active[0] == 21
                def cycle(handle):
                    self.assertEqual(handle, 42)
                    self.assertEqual(active[0], 42)
                    if interrupted:
                        raise ValueError("Original window was lost")
                    return "observed"
                api.close.side_effect = close
                receipt = {}
                with patch.object(c, "WinDLL", create=True), patch.dict(publish.__globals__,
                        bind=lambda *_: attach, ordinary_console=lambda *_: True):
                    if interrupted:
                        with self.assertRaisesRegex(ValueError, "Original window was lost"):
                            publish(api, name, cycle, receipt)
                    else:
                        self.assertEqual(publish(api, name, cycle, receipt), "observed")
                self.assertEqual(events, [("attach", 42), ("attach", 21), ("close", 42)])
                self.assertEqual(receipt, dict(originalThreadDesktop="Default", originalThreadDesktopRestored=True,
                                               ownedHandleClosed=True))

    def test_repeated_reads_copy_the_name_from_user32_owned_storage(self):
        scheme = c.create_unicode_buffer(32)
        def parameters(action, size, pointer, flags):
            self.assertEqual((action, size, flags), (0x42, c.sizeof(HighContrast), 0))
            value = c.cast(pointer, c.POINTER(HighContrast)).contents
            value.flags, value.scheme = AVAILABLE, c.addressof(scheme)
            return 1
        exports = {"SystemParametersInfoW": parameters, "GetSysColor": lambda _: 0x20c3d5}
        with patch.object(c, "WinDLL", create=True):
            system = SystemColors(lambda library, name, *args: exports[name], self.assertTrue)
        observations = []
        for name in ("", "Contrast A", "Contrast B"):
            scheme.value = name
            observations.append(system.read())
        self.assertEqual([s.scheme for s in observations], ["", "Contrast A", "Contrast B"])
        self.assertEqual(observations[-1].colors["text"], [213, 195, 32])

    def test_supervisor_owns_the_profile_across_an_abrupt_capture_exit(self):
        target = "x86_64-pc-windows-msvc"
        name = "IfwQa_" + "a" * 32
        released = []
        @contextmanager
        def selected(desk, placement):
            try:
                yield name
            finally:
                released.append(name)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "windows-contrast"
            def early_exit(actual, desktop, receipt):
                self.assertEqual((actual, desktop), (target, name))
                profile = observer["capture_profile"](output)
                (profile / "observer-cache").write_text("synthetic")
                receipt.update(workerExit=91, jobClosed=True)
                return 91
            supervise = observer["supervise"]
            api = Mock()
            api.context.return_value = {"session": 2}
            with (patch.dict(supervise.__globals__, Desktop=lambda: api, Win32=Mock, job_guard=lambda: None,
                             ordinary_console=lambda ctx, desk: True, inputs=lambda _: {}, capture_job=early_exit),
                  patch.dict(observer["TEXT"]["DESKTOP"], named_input_desktop=selected),
                  patch.dict("os.environ", GITHUB_SHA="a"*40, GITHUB_RUN_ID="7", GITHUB_RUN_ATTEMPT="1"),
                  patch("builtins.print")):
                self.assertEqual(supervise(target, root, output), 1)
            record = observer["TEXT"]["read"](output / "result.json")
            self.assertTrue(record["profileRemoved"])
            self.assertTrue(record["captureJob"]["jobClosed"])
            self.assertIn("ended with 91 before ready", record["error"])
            self.assertNotIn("original", record)
            self.assertEqual(list(output.glob("profile-*")), [])
            self.assertEqual(released, [name])

    def test_observes_both_modes_and_restores_each_initial_state(self):
        for initial in (BASE, HIGH):
            with self.subTest(initial=initial.enabled):
                api = FakeSystem(initial)
                r = run_cycle(api)
                self.assertEqual(api.calls, [not initial.enabled, initial.enabled])
                self.assertIs(r["settingChangeAttempted"], True)
                self.assertTrue(r["restoreVerified"])
                self.assertEqual(r["afterSet"], r["changed"])
                self.assertEqual(r["beforeRestore"], r["changed"])
                self.assertEqual(r["original"], r["restored"])
                self.assertEqual(r["originalFrame"], r["restoredFrame"])

    def test_unnamed_scheme_retains_the_verified_baseline_without_a_set_or_restore(self):
        for scheme, kind in ((None, "NULL"), ("", "empty")):
            with self.subTest(scheme=scheme):
                system = FakeSystem(replace(BASE, scheme=scheme))
                system.read = Mock(wraps=system.read)
                capture = Mock(return_value={"rasterSha256": "baseline"})
                report = {}
                reason = contrast_cycle(system, lambda: None, lambda: None, capture, report, wait=instant)
                self.assertIn(kind + " original scheme", reason)
                self.assertEqual(system.calls, [])
                self.assertEqual(system.read.call_count, 2)
                capture.assert_called_once_with("original", system.state)
                self.assertEqual(report["baselineReadback"], report["original"])
                self.assertEqual(report["original"]["scheme"], scheme)
                self.assertIs(report["settingChangeAttempted"], False)
                self.assertNotIn("restoreVerified", report)
                child = dict(status="baseline-only", drained=True, subjectExit=0)
                report.update(captureJob=dict(jobClosed=True), profileRemoved=True)
                finish = observer["finish_contrast"]
                for bad_report, bad_child, exit_code in ((dict(profileRemoved=False), {}, 0),
                        (dict(captureJob=dict(jobClosed=False)), {}, 0), ({}, dict(drained=False), 0),
                        ({}, dict(subjectExit=1), 0), ({}, dict(status="failed"), 0), ({}, {}, 1)):
                    with self.assertRaises(RuntimeError):
                        finish(dict(report, **bad_report), dict(child, **bad_child), exit_code, reason)
                finish(report, child, 0, reason)
                self.assertEqual((report["status"], report["reason"]), ("unavailable", reason))

    def test_unnamed_scheme_changes_during_baseline_are_reported_as_failure(self):
        system, report = FakeSystem(replace(BASE, scheme="")), {}
        def changed(*_):
            system.state = BASE
            return {"rasterSha256": "initial"}
        with self.assertRaisesRegex(RuntimeError, "changed during the baseline"):
            run_cycle(system, changed, report)
        self.assertEqual(report["original"]["scheme"], "")
        self.assertEqual(report["baselineReadback"], vars(BASE))
        self.assertEqual(system.calls, [])

    def test_unnamed_worker_only_finishes_after_the_bound_baseline_stop(self):
        run, announce = observer["exercise"], observer["announce"]
        system = FakeSystem(replace(BASE, scheme=""))
        for confirmed in (True, False):
            with self.subTest(confirmed=confirmed), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                control = output / "control"
                control.mkdir()
                report = dict(build=dict(source="a"*40), target="aarch64-pc-windows-msvc")
                announce(control, "session", "nonce", session=2, source=report["build"]["source"],
                         target=report["target"], run="7", attempt="1")
                announce(control, "request-original", "nonce", state=vars(system.state))
                stop = {"baselineOnly": True} if confirmed else {}
                announce(control, "stop", "nonce", **stop)
                with (patch.dict(run.__globals__, require_live_window=Mock(), SystemColors=lambda *_: system,
                                 powershell=Mock(return_value=0), verify_frames=Mock(return_value={"pixels": 7})),
                      patch.dict("os.environ", GITHUB_RUN_ID="7", GITHUB_RUN_ATTEMPT="1")):
                    args = (Mock(), dict(session=2, threadDesktop="IfwQa_" + "a"*32), 72, 85, {}, "ps", output, report)
                    if confirmed:
                        run(*args)
                        self.assertIs(report["baselineOnly"], True)
                    else:
                        with self.assertRaisesRegex(RuntimeError, "did not confirm"):
                            run(*args)
                        self.assertNotIn("baselineOnly", report)
                self.assertEqual(sorted(p.name for p in control.glob("observed-*.json")), ["observed-original.json"])
                self.assertEqual(system.calls, [])

    def test_missing_baseline_or_unavailable_mode_never_changes_appearance(self):
        for system, capture in [(FakeSystem(replace(BASE, flags=0)), lambda *_: 1),
                                (FakeSystem(), lambda *_: self.fail("inaccessible label"))]:
            with self.subTest():
                with self.assertRaises((RuntimeError, AssertionError)):
                    run_cycle(system, capture)
                self.assertEqual(system.calls, [])

    def test_failed_capture_keeps_its_error_and_restores_the_original(self):
        api, r = FakeSystem(), {}
        def capture(phase, state):
            if phase == "changed":
                raise OSError("owned GUI exited")
            return state.flags
        with self.assertRaisesRegex(OSError, "owned GUI exited"):
            run_cycle(api, capture, r)
        self.assertEqual(api.state, BASE)
        self.assertEqual(api.calls, [True, False])
        self.assertTrue(r["restoreVerified"])
        self.assertNotIn("restoredFrame", r)

    def test_loss_of_input_desktop_does_not_prevent_restoring_own_session(self):
        api, r = FakeSystem(), {}
        def still_visible():
            if api.state == HIGH:
                raise OSError("desktop changed")
        with self.assertRaisesRegex(OSError, "desktop changed"):
            run_cycle(api, record=r, window_guard=still_visible)
        self.assertEqual(api.state, BASE)
        self.assertTrue(r["restoreVerified"])

    def test_partial_setting_failure_is_restored_even_if_native_function_raises(self):
        class Partial(FakeSystem):
            def set_mode(self, original, enabled):
                super().set_mode(original, enabled)
                if enabled:
                    raise OSError("system returned an error after changing the mode")
        api = Partial()
        with self.assertRaisesRegex(OSError, "after changing"):
            run_cycle(api)
        self.assertEqual(api.calls, [True, False])
        self.assertEqual(api.state, BASE)

    def test_unrelated_change_is_preserved_and_unconfirmed_restore_fails(self):
        for unrelated in (replace(HIGH, flags=HIGH.flags | 8), replace(HIGH, scheme="external"),
                          replace(HIGH, colors=BASE.colors)):
            api, r = FakeSystem(), {}
            def capture(phase, state):
                if phase == "changed":
                    api.state = unrelated
                return state.flags
            with self.subTest(unrelated=unrelated), self.assertRaisesRegex(RuntimeError, "Another accessibility setting"):
                run_cycle(api, capture, r)
            self.assertEqual(api.calls, [True])
            self.assertEqual(api.state, unrelated)
            self.assertFalse(r["restoreVerified"])
            self.assertEqual(r["afterSet"], vars(HIGH))
            self.assertEqual(r["beforeRestore"], vars(unrelated))

    def test_unchanged_window_pixels_and_wrong_restored_palette_fail(self):
        api = FakeSystem()
        with self.assertRaisesRegex(ValueError, "original pixels"):
            run_cycle(api, lambda *_: {"rasterSha256": "same pixels"})
        class BadRestore(FakeSystem):
            def set_mode(self, original, enabled):
                super().set_mode(original, enabled)
                if not enabled:
                    self.state = replace(BASE, colors=HIGH.colors)
        r = {}
        with self.assertRaisesRegex(TimeoutError, "original flags, scheme and colors"):
            run_cycle(BadRestore(), record=r)
        self.assertFalse(r["restoreVerified"])

    def test_exact_two_frames_bind_the_original_uia_rectangle_and_system_colors(self):
        data = bitmap(HIGH.colors["text"], HIGH.colors["window"])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            samples = []
            for i in (1, 2):
                name = f"changed.json.{i}.bmp"
                (folder / name).write_bytes(data)
                samples.append({"file": name, "sha256": hashlib.sha256(data).hexdigest()})
            r = dict(status="observed", phase="changed", pid=72, hwnd=85, label="Dateiname", rect=[10, 20, 7, 5], samples=samples)
            verify = observer["verify_frames"]
            result = verify(folder, "changed", r, 72, 85, HIGH)
            self.assertEqual(result["paper"], HIGH.colors["window"])
            self.assertEqual(result["systemTextPixels"], 5)
            for wrong in (dict(hwnd=99), dict(pid=88), dict(rect=[10, 20, 8, 5]), dict(samples=samples[:1]),
                          dict(samples=[dict(samples[0], file="../another.bmp"), samples[1]])):
                with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                    verify(folder, "changed", dict(r, **wrong), 72, 85, HIGH)
            alternative = bytearray(data)
            alternative[54 + 3*2] += 1
            (folder / samples[1]["file"]).write_bytes(alternative)
            with self.assertRaisesRegex(ValueError, "differs from its receipt"):
                verify(folder, "changed", r, 72, 85, HIGH)
            samples[1]["sha256"] = hashlib.sha256(alternative).hexdigest()
            with self.assertRaisesRegex(ValueError, "different pixels"):
                verify(folder, "changed", r, 72, 85, HIGH)

    def test_rejects_a_flat_label_or_foreground_colors_from_a_different_palette(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "frame.bmp"
            for foreground, paper in (([0, 0, 0], HIGH.colors["window"]), (HIGH.colors["text"], [21, 31, 41])):
                path.write_bytes(bitmap(foreground, paper))
                with self.assertRaisesRegex(ValueError, "live Windows"):
                    label_colors(label_bitmap(path)[2], HIGH)
            flat = bitmap([0, 0, 0], [0, 0, 0])
            path.write_bytes(flat)
            with self.assertRaisesRegex(ValueError, "distinct"):
                label_colors(label_bitmap(path)[2], BASE)
            for invalid in (flat[:-1], flat[:28] + b"\x20\0" + flat[30:]):
                path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    label_bitmap(path)

    def test_static_bitmap_matching_both_palettes_does_not_prove_a_visual_change(self):
        data = bitmap(HIGH.colors["text"], HIGH.colors["window"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unchanged.bmp"
            def unchanged(phase, state):
                sample = bytearray(data)
                if phase == "changed":
                    struct.pack_into("<i", sample, 38, 600)
                    sample[54 + 21] = 123  # Padding in the first row.
                path.write_bytes(sample)
                _, _, colors, raster = label_bitmap(path)
                return {"rasterSha256": raster, "fileSha256": hashlib.sha256(sample).hexdigest(), **label_colors(colors, state)}
            r = {}
            with self.assertRaisesRegex(ValueError, "original pixels"):
                run_cycle(FakeSystem(), unchanged, r)
            self.assertNotEqual(r["originalFrame"]["fileSha256"], r["changedFrame"]["fileSha256"])
            self.assertNotIn("systemTextPixels", r["originalFrame"])
            self.assertIn("systemTextPixels", r["changedFrame"])
            self.assertTrue(r["restoreVerified"])

    def test_partial_set_does_not_replace_an_unrelated_scheme_or_flag(self):
        for changed in (replace(HIGH, scheme="another scheme"), replace(HIGH, flags=HIGH.flags | 32)):
            class Interrupted(FakeSystem):
                def set_mode(self, original, enabled):
                    super().set_mode(original, enabled)
                    self.state = changed
                    raise OSError("interrupted set")
            api, record = Interrupted(), {}
            with self.subTest(changed=changed), self.assertRaisesRegex(RuntimeError, "Another accessibility setting"):
                run_cycle(api, record=record)
            self.assertEqual(api.state, changed)
            self.assertEqual(api.calls, [True])
            self.assertFalse(record["restoreVerified"])
            self.assertEqual(record["afterSet"], vars(changed))
            self.assertEqual(record["beforeRestore"], vars(changed))

    def test_palette_changes_after_a_switched_sample_but_before_stabilization(self):
        foreign = replace(HIGH, colors=BASE.colors)
        api, record = FakeSystem(), {}
        def interrupted(read, condition, label):
            self.assertEqual(read(), HIGH)
            api.state = foreign
            raise OSError("next contrast query failed")
        with self.assertRaisesRegex(RuntimeError, "Another accessibility setting"):
            contrast_cycle(api, lambda: None, lambda: None, lambda *_: {}, record, wait=interrupted)
        self.assertEqual(api.calls, [True])
        self.assertEqual(record["afterSet"], vars(HIGH))
        self.assertEqual(record["beforeRestore"], vars(foreign))
        self.assertNotIn("changed", record)
        self.assertFalse(record["restoreVerified"])

    def test_cleanup_survives_two_transient_read_errors_after_worker_exit(self):
        class LostWorker(FakeSystem):
            pending = 0
            def read(self):
                if self.pending:
                    self.pending -= 1
                    raise OSError("transient read error")
                return super().read()
        api, record = LostWorker(), {}
        def capture(phase, state):
            if phase == "changed":
                api.pending = 2
                raise RuntimeError("worker exited")
            return {"rasterSha256": "original"}
        with patch("windows_colors.time.sleep"), self.assertRaisesRegex(RuntimeError, "worker exited"):
            run_cycle(api, capture, record)
        self.assertEqual(api.calls, [True, False])
        self.assertEqual(api.state, BASE)
        self.assertTrue(record["restoreVerified"])
        self.assertNotIn("restoredFrame", record)

    def test_restore_reads_back_after_a_failed_native_set(self):
        for applied in (True, False):
            class RestoreError(FakeSystem):
                def set_mode(self, original, enabled):
                    if not enabled and self.calls == [True]:
                        self.calls.append(False)
                        if applied:
                            self.state = BASE
                        raise OSError("restore call interrupted")
                    super().set_mode(original, enabled)
            api = RestoreError()
            with self.subTest(applied=applied):
                record = run_cycle(api)
                self.assertTrue(record["restoreVerified"])
                self.assertEqual(record["restoreReportedError"], "restore call interrupted")
                self.assertEqual(record["afterRestoreError"], vars(BASE if applied else HIGH))
                self.assertEqual(api.calls, [True, False] if applied else [True, False, False])

    def test_failed_restore_retains_the_foreign_readback_and_does_not_retry(self):
        foreign = replace(HIGH, scheme="external")
        class RestoreError(FakeSystem):
            def set_mode(self, original, enabled):
                super().set_mode(original, enabled)
                if not enabled:
                    self.state = foreign
                    raise OSError("interrupted restore")
        api, record = RestoreError(), {}
        with self.assertRaisesRegex(TimeoutError, "original flags, scheme and colors"):
            run_cycle(api, record=record)
        self.assertEqual(api.calls, [True, False])
        self.assertEqual(record["beforeRestore"], vars(HIGH))
        self.assertEqual(record["afterRestoreError"], vars(foreign))
        self.assertFalse(record["restoreVerified"])

    def test_unexpected_scheme_or_flag_after_a_reported_set_is_retained_before_rejecting_restore(self):
        for changed in (replace(HIGH, scheme="another scheme"), replace(HIGH, flags=HIGH.flags | 16)):
            class ForeignState(FakeSystem):
                def set_mode(self, original, enabled):
                    super().set_mode(original, enabled)
                    self.state = changed
            api, record = ForeignState(), {}
            with self.subTest(changed=changed), self.assertRaisesRegex(RuntimeError, "Another accessibility setting"):
                run_cycle(api, record=record)
            self.assertEqual(api.calls, [True])
            self.assertFalse(record["restoreVerified"])
            self.assertEqual(record["afterSet"], vars(changed))
            self.assertEqual(record["beforeRestore"], vars(changed))
            self.assertNotIn("changed", record)

    def test_phases_are_atomic_bound_to_the_trial_and_reject_a_stopped_worker(self):
        announce, message = observer["announce"], observer["message"]
        with tempfile.TemporaryDirectory() as temp:
            control = Path(temp)
            announce(control, "ready", "nonce", pid=321)
            self.assertFalse((control / "ready.tmp").exists())
            self.assertEqual(message(control, "ready", "nonce"), {"pid": 321})
            with self.assertRaisesRegex(ValueError, "belongs to another"):
                message(control, "ready", "different")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                announce(control, "ready", "nonce", pid=555)
            with self.assertRaisesRegex(TimeoutError, "request-original"):
                message(control, "request-original", "nonce", timeout=0)
            worker = Future()
            worker.set_result(8)
            with self.assertRaisesRegex(RuntimeError, "ended with 8 before observed-changed"):
                message(control, "observed-changed", "nonce", worker)
            announce(control, "stop", "nonce")
            with self.assertRaisesRegex(RuntimeError, "ended the observation"):
                message(control, "request-restored", "nonce")

    def test_bounded_desktop_child_runs_only_the_read_only_capture_entry_point(self):
        target = "aarch64-pc-windows-msvc"
        launch = observer["capture_job"]
        run_worker = Mock(return_value=0)
        receipt = {}
        with patch.dict(launch.__globals__, run_worker=run_worker):
            self.assertEqual(launch(target, "Default", receipt), 0)
        run_worker.assert_called_once_with(HERE / "windows.py", [target, "--capture-worker"],
                                           "Default", observer["ROOT"], receipt, timeout_seconds=300)

    def owned_window(self):
        self.enterContext(patch.object(c, "set_last_error", create=True))
        self.enterContext(patch.object(c, "get_last_error", return_value=0, create=True))
        api = Mock()
        desk = "IfwQa_" + "a" * 32
        session, pid, hwnd = 2, 123, 789
        context = {"windowStation": "WinSta0", "stationVisible": True, "session": session,
                   "activeConsoleSession": session, "inputDesktop": desk, "inputObjectReceivesInput": True,
                   "threadDesktop": "Default", "threadReceivesInput": False,
                   "wts": {"session": session, "connectionState": 0, "lockFlags": 1}}
        api.context.return_value = context
        def owner(_, slot):
            slot._obj.value = pid
            return 72
        api.owner.side_effect = owner
        api.pid_session.return_value = session
        api.thread_desktop.return_value = 456
        api.name.return_value = desk
        api.visible.return_value, api.iconic.return_value = True, False
        api.ancestor.return_value = hwnd
        def guard(**kwargs):
            return observer["require_live_window"](api, session, desk, pid, hwnd, **kwargs)
        return api, context, guard

    def test_publisher_enumerates_the_exact_root_on_its_held_private_input_desktop(self):
        api, context, guard = self.owned_window()
        context.update(threadDesktop=context["inputDesktop"], threadReceivesInput=True)
        api.receiving_input.return_value = True
        api.count_top_level_window.return_value = 1
        self.assertEqual(guard(publisher_desktop=731), 72)
        api.count_top_level_window.assert_called_once_with(731, 789)
        api.receiving_input.assert_called_once_with(731)
        self.assertEqual(api.owner.call_count, 2)
        api.thread_desktop.assert_not_called()

    def test_publisher_refuses_wrong_desktop_or_incomplete_membership_before_palette_write(self):
        for failure in ("publisher thread", "thread input query", "desktop handle name", "desktop handle receives input",
                        "no match", "duplicate", "enumeration error", "PID changed", "TID changed"):
            with self.subTest(failure=failure):
                api, context, guard = self.owned_window()
                context.update(threadDesktop=context["inputDesktop"], threadReceivesInput=True)
                api.receiving_input.return_value = True
                api.count_top_level_window.return_value = 1
                if failure == "publisher thread":
                    context["threadDesktop"] = "Default"
                elif failure == "thread input query":
                    context["threadReceivesInput"] = {"win32Error": 5}
                elif failure == "desktop handle name":
                    api.name.return_value = "Default"
                elif failure == "desktop handle receives input":
                    api.receiving_input.return_value = {"win32Error": 5}
                elif failure == "enumeration error":
                    api.count_top_level_window.side_effect = OSError(5, "EnumDesktopWindows")
                elif failure in ("no match", "duplicate"):
                    api.count_top_level_window.return_value = 0 if failure == "no match" else 2
                else:
                    owners = iter([(123, 72), (9000, 72) if failure == "PID changed" else (123, 91)])
                    def owner(_, slot):
                        slot._obj.value, tid = next(owners)
                        return tid
                    api.owner.side_effect = owner
                system = FakeSystem()
                with self.assertRaises((ValueError, OSError)) as raised:
                    run_cycle(system, window_guard=lambda: guard(publisher_desktop=731))
                if failure in ("thread input query", "desktop handle receives input"):
                    self.assertIn("'win32Error': 5", str(raised.exception))
                self.assertEqual(system.calls, [])
                api.thread_desktop.assert_not_called()

    def test_supervisor_rechecks_hwnd_owner_visibility_and_active_desktop_before_the_set(self):
        api, context, guard = self.owned_window()
        guard()
        api.pid_session.assert_called_once_with(123)
        api.thread_desktop.assert_called_once_with(72)
        api.name.assert_called_once_with(456)
        api.visible.assert_called_once_with(789)
        api.ancestor.assert_called_once_with(789, observer["GA_ROOT"])
        for method, replacement, operation, value in (
                ("context", dict(context, session=3), "observer session", "observed 3"),
                ("context", dict(context, wts={"win32Error": 5}), "unlocked_console", "'win32Error': 5"),
                ("context", dict(context, wts=dict(context["wts"], lockFlags=0)), "unlocked_console", "'lockFlags': 0"),
                ("context", dict(context, inputDesktop="Default"), "input desktop name", "'Default'"),
                ("context", dict(context, inputObjectReceivesInput=False), "UOI_IO", "observed False"),
                ("pid_session", 3, "ProcessIdToSessionId", "observed 3"),
                ("name", {"win32Error": 5}, "GetUserObjectInformationW(UOI_NAME)", "'win32Error': 5"),
                ("name", "UnrelatedDesktop", "GetUserObjectInformationW(UOI_NAME)", "<different desktop>"),
                ("visible", False, "IsWindowVisible", "observed False"),
                ("iconic", True, "IsIconic", "observed True"),
                ("ancestor", 790, "GetAncestor(GA_ROOT)", "observed 790")):
            system = FakeSystem()
            def closes_after_baseline(phase, state):
                getattr(api, method).return_value = replacement
                return {"rasterSha256": "baseline"}
            with self.subTest(method=method), patch.object(api, method, wraps=getattr(api, method)):
                with self.assertRaisesRegex(ValueError, "original visible Rust root HWND 789 of PID 123") as raised:
                    run_cycle(system, closes_after_baseline, window_guard=guard)
                self.assertIn(operation, str(raised.exception))
                self.assertIn(value, str(raised.exception))
                self.assertNotIn("UnrelatedDesktop", str(raised.exception))
                self.assertEqual(system.calls, [])

    def test_native_failure_reports_the_current_error_and_stops_at_the_failed_operation(self):
        for method, operation, following, error in (("owner", "GetWindowThreadProcessId", "thread_desktop", 1400),
                                                   ("thread_desktop", "GetThreadDesktop", "name", 5),
                                                   ("ancestor", "GetAncestor(GA_ROOT)", None, 0)):
            api, _, guard = self.owned_window()
            error_slot = [999]
            def fail(*_):
                self.assertEqual(error_slot[0], 0)
                error_slot[0] = error
                return 0
            with self.subTest(operation=operation), patch.object(api, method, side_effect=fail), \
                    patch.object(c, "set_last_error", side_effect=lambda e: error_slot.__setitem__(0, e)), \
                    patch.object(c, "get_last_error", side_effect=lambda: error_slot[0]):
                with self.assertRaises(ValueError) as raised:
                    guard()
                self.assertIn(operation, str(raised.exception))
                self.assertIn(f"'win32LastError': {error}", str(raised.exception))
                if following:
                    getattr(api, following).assert_not_called()

    def test_reused_hwnd_stops_before_reading_the_other_process_or_its_desktop(self):
        api, _, guard = self.owned_window()
        def new_owner(_, slot):
            slot._obj.value = 9000
            return 81
        api.owner.side_effect = new_owner
        with self.assertRaisesRegex(ValueError, "owner PID .*observed 9000"):
            guard()
        api.pid_session.assert_called_once_with(123)
        api.thread_desktop.assert_not_called()
        api.name.assert_not_called()
        api.visible.assert_not_called()
        api.iconic.assert_not_called()
        api.ancestor.assert_not_called()

    def test_temporary_setting_requires_a_real_disposable_rewrite_job(self):
        guard = observer["job_guard"]
        env = {"GITHUB_REPOSITORY":"VoltKraft/immich-folder-watch", "GITHUB_REF":"refs/heads/rewrite/rust",
               "GITHUB_SHA":"a"*40, "GITHUB_RUN_ID":"73", "GITHUB_RUN_ATTEMPT":"1"}
        with patch.dict(guard.__globals__, hosted=lambda: True), patch.dict("os.environ", env, clear=True):
            guard()
            for key, wrong in (("GITHUB_REF","refs/heads/main"),("GITHUB_SHA","short"),
                               ("GITHUB_REPOSITORY","another/repo"),("GITHUB_RUN_ID",""),("GITHUB_RUN_ATTEMPT","")):
                with self.subTest(key=key), patch.dict("os.environ", {key:wrong}), self.assertRaises(ValueError):
                    guard()
        with patch.dict(guard.__globals__, hosted=lambda: False), patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ValueError): guard()


if __name__ == "__main__":
    unittest.main()
