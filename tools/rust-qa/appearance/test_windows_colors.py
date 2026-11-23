"""Test the native fixture's rollback and independent bitmap checks using synthetic observations."""
from dataclasses import replace
from concurrent.futures import Future
import hashlib
from pathlib import Path
import runpy
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
observer = runpy.run_path(str(HERE / "windows.py"))
from windows_colors import AVAILABLE, ON, State, contrast_cycle, label_bitmap, label_colors


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
    def test_observes_both_modes_and_restores_each_initial_state(self):
        for initial in (BASE, HIGH):
            with self.subTest(initial=initial.enabled):
                api = FakeSystem(initial)
                r = run_cycle(api)
                self.assertEqual(api.calls, [not initial.enabled, initial.enabled])
                self.assertTrue(r["restoreVerified"])
                self.assertEqual(r["original"], r["restored"])
                self.assertEqual(r["originalFrame"], r["restoredFrame"])

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
                self.assertEqual(api.calls, [True, False] if applied else [True, False, False])

    def test_setting_a_different_flag_before_a_confirmed_transition_aborts(self):
        class ForeignFlag(FakeSystem):
            def set_mode(self, original, enabled):
                super().set_mode(original, enabled)
                self.state = replace(self.state, flags=self.state.flags | 16)
        api, record = ForeignFlag(), {}
        with self.assertRaisesRegex(RuntimeError, "Another accessibility setting"):
            run_cycle(api, record=record)
        self.assertEqual(api.calls, [True])
        self.assertFalse(record["restoreVerified"])

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

    def test_supervisor_rechecks_hwnd_owner_visibility_and_active_desktop_before_the_set(self):
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
        api.name.return_value = desk
        api.visible.return_value, api.iconic.return_value = True, False
        api.ancestor.return_value = hwnd
        guard = lambda: observer["require_live_window"](api, session, desk, pid, hwnd)
        guard()
        for method, replacement in (("context", dict(context, inputDesktop="Default")),
                                    ("context", dict(context, inputObjectReceivesInput=False)),
                                    ("pid_session", session + 1), ("name", "Default"),
                                    ("visible", False), ("iconic", True), ("ancestor", hwnd + 1)):
            system = FakeSystem()
            def closes_after_baseline(phase, state):
                getattr(api, method).return_value = replacement
                return {"rasterSha256": "baseline"}
            with self.subTest(method=method), patch.object(api, method, wraps=getattr(api, method)):
                with self.assertRaisesRegex(ValueError, "original visible Rust root"):
                    run_cycle(system, closes_after_baseline, window_guard=guard)
                self.assertEqual(system.calls, [])
        with patch.object(api, "owner", return_value=0), self.assertRaises(ValueError):
            guard()

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
