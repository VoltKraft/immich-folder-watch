"""Check native tray receipt identity, activation beats and normal quit on degraded hosts."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import native_tray as tray
import retained_window
from test_retained_window import FIRST_RENDER, OwnedRoot, TITLE

TOKEN = "1234567890abcdef" * 2
KEY = "18", "43", "23"
RGB, COMPLEMENT = tray.marker_colors(TOKEN)
RECT = [-4, 10, 28, 42]
SURFACE = dict(pid=18, hwnd=43, id=23, creation=101, rect=RECT, point=[12, 26], bar=51, hit=52,
               shellPid=81, shellCreation=102, desktop="Default", rgb=RGB)
ELEMENT = dict(runtimeId="42,99", matchCount=1, matchedLabel="IFW tray " + TOKEN, pid=81, hitDepth=2,
               nameMatches=True, helpMatches=False, enabled=True, offscreen=False, bounds=[-4, 10, 28, 42])


def registration(added):
    return (f"gui_tray.initial.add={str(added).lower()}\n"
            + ("gui_tray.initial.version4=true\n"
               "TRAY_BIND phase=initial pid=18 hwnd=43 id=23 shell_pid=81 shell_hwnd=51 verified=1\n" if added else "")
            + f"TRAY_REGISTER phase=initial pid=18 hwnd=43 id=23 token={TOKEN} added={int(added)} version4={int(added)}\n")


def closed(added):
    return (("gui_tray.shutdown=true\n" if added else "") +
            f"TRAY_CLEANUP pid=18 hwnd=43 id=23 registered={int(added)} removed={int(added)}\nDRAINED passes=2\n")


def callback(queued="22", dispatched=23, code=0x401):
    return (f"TRAY_CALLBACK pid=18 hwnd=43 id=23 code={code} ordinal=1 queued_ms={queued} dispatch_ms={dispatched}\n"
            "TRAY_OPEN pid=18 ordinal=1\n")


class TrayProofTests(unittest.TestCase):
    def test_native_source_ignores_incomplete_records_and_rejects_a_mismatched_incarnation(self):
        probe = tray.NativeTray(Mock(), Mock(), "Default", TOKEN)
        probe.witness = Mock(confirmed=True)
        proc = Mock(pid=18)
        probe.desk.name.return_value = "Default"
        probe.desk.window.return_value = dict(tid=2, pid=18, **{"class": "IFW RW02 synthetic tray receiver"})
        text = registration(True)
        with patch.object(tray, "shell_rect", return_value=dict(hresult=0, rect=RECT)):
            self.assertEqual(probe.registration(proc, lambda: text, lambda callback, _: callback(), {}, no_host=False), KEY)
            for invalid in (text.replace("pid=18", "pid=20"), text.replace("id=23", "id=25"),
                            text.replace(TOKEN, "0" * 32), text.replace("version4=true", "version4=false"), text + text):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    probe.registration(proc, lambda: invalid, lambda callback, _: callback(), {}, no_host=False)
            with self.assertRaises(tray.Unavailable):
                probe.registration(proc, lambda: text, lambda callback, _: callback(), {}, no_host=True)
            self.assertEqual(tray.records(text.rstrip(), "TRAY_REGISTER"), [])
        for observed, expect in ((dict(hresult=-1, rect=None), False), (dict(hresult=0, rect=RECT), True)):
            with patch.object(tray, "shell_rect", return_value=observed):
                verify = lambda: probe.registration(proc, lambda: registration(False), lambda fn, _: fn(), {}, no_host=True)
                if expect:
                    with self.assertRaises(tray.Unavailable):
                        verify()
                else:
                    self.assertEqual(verify(), KEY)

    def test_same_physical_target_and_a_unique_exact_enabled_provider_are_required_before_invocation(self):
        self.assertEqual((RGB, COMPLEMENT), ("2ad846", "d527b9"))
        first = tray.confirm_surface({"surface": SURFACE}, KEY, 101, RECT, RGB)
        second = dict(SURFACE, rgb=COMPLEMENT)
        self.assertEqual(tray.confirm_surface({"surface": second}, KEY, 101, RECT, COMPLEMENT, first), second)
        for changes in (dict(hit=88), dict(bar=88), dict(shellCreation=999), dict(rect=[-5, 10, 28, 42]),
                        dict(point=[0, 0]), dict(rgb=RGB), dict(desktop="Other"), dict(creation=100), dict(id=33)):
            with self.subTest(changes=changes), self.assertRaises((ValueError, tray.Unavailable)):
                tray.confirm_surface({"surface": second | changes}, KEY, 101, RECT, COMPLEMENT, first)
        self.assertEqual(tray.confirm_provider({"provider": ELEMENT}, second, TOKEN), ELEMENT)
        for changes in (dict(matchCount=2), dict(matchedLabel="IFW tray other"), dict(runtimeId=""), dict(pid=1),
                        dict(nameMatches=False), dict(enabled=False), dict(offscreen=True), dict(hitDepth=12),
                        dict(bounds=[-5, 10, 28, 42]), dict(bounds=[13, 10, 28, 42]), dict(bounds=[0, 0, float("nan"), 30])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tray.confirm_provider({"provider": ELEMENT | changes}, second, TOKEN)

    def test_shell_callback_matches_one_open_and_windows_uptime_epoch_across_queue_tick_wrap(self):
        for code in (0x400, 0x401, 0x203):
            for queued in ("none", "22"):
                result = tray.delivery(callback(queued, code=code), KEY, 21, 29)
                self.assertEqual((result["code"], result["pid"], result["hwnd"]), (code, 18, 43))
        wrap = 1 << 32
        self.assertEqual(tray.delivery(callback("2", wrap + 4), KEY, wrap - 1, wrap + 6)["dispatchMs"], wrap + 4)
        for invalid in (callback("15"), callback("100"), callback(dispatched=30), callback(code=0x202),
                        callback().replace("hwnd=43", "hwnd=44"), callback().replace("TRAY_OPEN pid=18", "TRAY_OPEN pid=19"),
                        callback() + callback(), callback().replace("ordinal=1", "ordinal=2")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                tray.delivery(invalid, KEY, 21, 29)
        for ambiguous in (callback("21"), callback("none", 21)):
            with self.assertRaises(tray.Unavailable):
                tray.delivery(ambiguous, KEY, 21, 29)
        self.assertIsNone(tray.delivery("LAUNCHER_OPEN client=7\nREADY Visible Available\n", KEY, 21, 29))

    def test_real_primary_shutdown_requires_empty_job_native_removal_and_independent_absence(self):
        api, desk, proc = Mock(), Mock(), Mock(pid=18)
        api.wait_job_empty.return_value = True
        proc.poll.return_value = 0
        desk.owner.return_value = 0
        probe = tray.NativeTray(api, desk, "Default", TOKEN)
        head = "LAUNCHER_PRIMARY pid=18\n"
        with patch.object(tray, "shell_rect", return_value=dict(hresult=-1, rect=None)):
            for added in (False, True):
                state = {}
                log = head + registration(added) + closed(added)
                probe.check_drain(proc, 1, log, state)
                if added:
                    self.assertEqual(state["nativeShutdown"]["cleanupMethod"], "deletedAtQuit")
                    with self.assertRaises(tray.Unavailable):
                        probe.qualify_quiet_shell(log, state, no_host=False)
                else:
                    probe.qualify_quiet_shell(log, state, no_host=True)
                self.assertEqual(state["nativeShutdown"]["uiPasses"], 2)
            without_frame = log.replace("DRAINED passes=2", "DRAINED passes=0")
            probe.check_drain(proc, 1, without_frame, state)
            self.assertEqual(state["nativeShutdown"]["uiPasses"], 0)
            for invalid in (log.replace("removed=1", "removed=0"), log.replace("pid=18 hwnd=43 id=23 registered", "pid=33 hwnd=43 id=23 registered"),
                            log.replace("DRAINED passes=2", "INVENTORY"), log.replace("gui_tray.shutdown=true", "gui_tray.shutdown=false")):
                with self.assertRaises(tray.CleanupUnconfirmed):
                    probe.check_drain(proc, 1, invalid, {})
            api.wait_job_empty.return_value = False
            with self.assertRaises(tray.CleanupUnconfirmed):
                probe.check_drain(proc, 1, log, {})
        api.wait_job_empty.return_value = True
        with patch.object(tray, "shell_rect", return_value=dict(hresult=0, rect=RECT)):
            with self.assertRaises(tray.CleanupUnconfirmed):
                probe.check_drain(proc, 1, log, {})

    def test_default_requires_a_real_monitor_and_positive_visible_area(self):
        desk, proc = Mock(), Mock(pid=18)
        desk.name.return_value = "Default"
        desk.attribute.return_value = 0
        desk.iconic.return_value = False
        desk.window.side_effect = lambda _: dict(pid=18, tid=2, rect=[3000, 10, 3070, 70])
        native = tray.NativeTray(Mock(), desk, "Default", TOKEN)
        for work in (None, [0, 0, 1920, 1080], [0, 0, 3000, 100]):
            with patch.object(tray, "monitor_work_area", return_value=work), self.assertRaisesRegex(ValueError, "intersect"):
                native.visible_window(proc, 99, {}, "window")
        with patch.object(tray, "monitor_work_area", return_value=[3000, 0, 3200, 60]):
            evidence = {}
            native.visible_window(proc, 99, evidence, "window")
            self.assertEqual(evidence["window"]["visibleWorkArea"], [3000, 10, 3070, 60])


class ResidentTests(unittest.TestCase):
    def exercise(self, refusal, *, subject="canonical", reopen=False):
        api, desk, windows = Mock(), Mock(), OwnedRoot(18)
        proc, helper = Mock(pid=18, _handle=42), Mock()
        proc.poll.return_value = None
        api.process_identity.return_value = 101
        api.wait_job_empty.return_value = True
        desk.owner.return_value = 0
        desk.name.return_value = "Default"
        desk.foreground.side_effect = lambda: windows.hwnd
        desk.window.side_effect = lambda hwnd: dict(pid=18, tid=2, rect=RECT, **{"class": "IFW RW02 synthetic tray receiver"})
        desk.iconic.return_value = False
        desk.attribute.return_value = 0
        state, commands, requests = {}, [], []
        with TemporaryDirectory() as directory:
            out = Path(directory)
            logfile = out / "resident-primary.log"
            def append(msg):
                with logfile.open("a", encoding="utf-8") as stream:
                    stream.write(msg)
            def report_icon(phase, color):
                append(f"TRAY_ICON phase={phase} pid=18 hwnd=43 id=23 rgb={color} rect=-4,10,28,42 ok=1\n")
            windows.on_close = lambda: append("WINDOW_HIDDEN\n")
            def send(data):
                commands.append(data)
                if data == b"B":
                    startup = "Visible" if reopen else "BackgroundStartup"
                    append("LAUNCHER_PRIMARY pid=18\n" + registration(refusal != "shell") + f"READY {startup} Available\n")
                    if reopen:
                        append(FIRST_RENDER)
                        windows.show(3, create=True)
                    report_icon("initial", RGB)
                elif data in (b"M", b"P"):
                    if data == b"M":
                        if refusal != "missing-modify":
                            append("gui_tray.change=true\n")
                        if refusal == "duplicate-modify":
                            append("gui_tray.change=true\n")
                        if refusal == "superseded":
                            append("TRAY_HOST pid=18 previous=81 current=82 previous_hwnd=51 current_hwnd=53\n")
                    report_icon("changed" if data == b"M" else "sample", COMPLEMENT)
                elif data == b"Q":
                    if subject == "retained" and windows.visible():
                        append("WINDOW_RELEASED passes=2\n")
                    ending = closed(refusal != "shell")
                    append(ending.replace("passes=2", "passes=0") if refusal == "no-frame" else ending)
                    proc.poll.return_value = 0
                else:
                    self.fail("Unexpected synthetic launcher control")
            proc.stdin.write.side_effect = send
            def receive(stage):
                if stage == "first":
                    return {"surface": SURFACE | {"shellPid": 87} if refusal == "foreign-provider" else SURFACE}
                if stage == "ready" and refusal == "provider":
                    raise tray.Unavailable("No exact accessible icon")
                if stage in ("ready", "attempt"):
                    return dict(surface=dict(SURFACE, rgb=COMPLEMENT), provider=ELEMENT, tick=19)
                if stage == "invoked":
                    append(callback("20", 20) if refusal == "early" else callback())
                    if not reopen:
                        append(FIRST_RENDER if subject == "retained" else "ADAPTER Dx12 Cpu\n")
                    if refusal == "second-generation":
                        append("GRAPHICS_READY generation=2\n")
                    if refusal == "different-window":
                        windows.hwnd = 100
                    windows.show(16 if refusal == "premature-show" else 24, create=not reopen)
                    return {"startTick": 21, "returnedTick": 25}
                self.fail("Unexpected provider stage")
            helper.stdin.write.side_effect = requests.append

            @contextmanager
            def child(*_, **_kw):
                yield proc, 1, 2

            @contextmanager
            def provider(*_):
                yield helper, receive

            witness = Mock(markers=0, confirmed=refusal != "unbound", original=(81, 51))
            witness.live.side_effect = lambda stage: stage != refusal
            with (patch.object(tray, "ShellWitness", return_value=witness),
                  patch.object(retained_window, "WindowLifetime", return_value=Mock(events=windows.life)),
                  patch.object(retained_window, "visible_surface", side_effect=lambda *a: tray.visible_surface(
                      *a, monitor_area=lambda _: [-20, 0, 100, 100])),
                  patch.object(retained_window, "focus_sample", return_value=dict(foreground=True, active=True, focused=True)),
                  patch.object(tray, "bind", return_value=lambda: 28), patch.object(tray, "ordinary_console", return_value=True),
                  patch.object(tray.launcher, "child", child), patch.object(tray.launcher, "snapshot", return_value={}),
                  patch.object(tray.launcher, "system_console_path"), patch.object(tray.recorder, "load_windows_fixture") as fixture,
                  patch.object(tray.recorder, "idle_complete", return_value=True), patch.object(tray.recorder, "owned_worker", return_value=28),
                  patch.object(tray.launcher, "primary_job_members",
                               side_effect=[[28, 201], [28, 302] if refusal == "different-worker" else [28, 201]]),
                  patch.object(tray, "provider", provider),
                  patch.object(tray, "monitor_work_area", return_value=[-20, 0, 100, 100]),
                  patch.object(tray, "shell_rect", return_value=dict(hresult=-1, rect=None))):
                fixture.return_value.Windows.return_value = windows
                fixture.return_value.TITLE = TITLE
                operation = lambda: tray.resident(api, desk, out / "gui.exe", out, {"IFW_QA_INVENTORY_TOKEN": TOKEN},
                                                  out, state, subject=subject, reopen=reopen)
                if refusal == "early":
                    with self.assertRaisesRegex(ValueError, "outside the provider observation"):
                        operation()
                elif refusal in ("missing-modify", "duplicate-modify", "no-frame", "second-generation",
                                 "different-window", "premature-show", "different-worker"):
                    expected = {"no-frame": "no UI pass", "second-generation": "first ordinary DX12",
                                "different-window": "replaced its HWND", "premature-show": "outside its native activation",
                                "different-worker": "inventory worker changed"}.get(refusal, "one acknowledged")
                    with self.assertRaisesRegex(ValueError, expected):
                        operation()
                elif refusal:
                    with self.assertRaises(tray.Unavailable):
                        operation()
                else:
                    operation()
        self.assertEqual(state["nativeShutdown"]["exit"], 0)
        self.assertTrue(state["nativeShutdown"]["jobEmpty"])
        return commands, requests, state

    def test_resident_uses_only_the_native_color_challenge_and_provider_then_joins_both_original_processes(self):
        commands, requests, state = self.exercise(None)
        self.assertEqual(commands, [b"B", b"M", b"P", b"Q"])
        self.assertEqual(requests, [b"second\n", b"invoke\n"])
        self.assertEqual(state["workerBefore"], state["workerAfter"])
        self.assertEqual(state["openedWindow"]["pid"], state["primaryPid"])

    def test_real_callback_covers_first_activation_and_reopening_the_previously_closed_retained_hwnd(self):
        for reopen in (False, True):
            with self.subTest(reopen=reopen):
                commands, requests, state = self.exercise(None, subject="retained", reopen=reopen)
                self.assertEqual(commands, [b"B", b"M", b"P", b"Q"])
                self.assertEqual(requests, [b"second\n", b"invoke\n"])
                self.assertEqual(state["primaryArguments"], [] if reopen else ["--autostart"])
                window = state["retainedWindow"]
                self.assertEqual("hidden" in window, reopen)
                self.assertEqual(window["callbackShow"]["showEvent"]["hwnd"], window["first"]["hwnd"])
                self.assertTrue(state["keyboardFocus"]["observed"])
                self.assertEqual(window["first"]["renderer"], window["beforeQuit"]["renderer"])
        for wrong in ("second-generation", "different-window", "premature-show", "different-worker"):
            with self.subTest(wrong=wrong):
                self.exercise(wrong, subject="retained", reopen=True)

    def test_registration_refusal_or_unidentified_icon_still_quits_naturally_without_activation(self):
        for reason, commands, requests in (("shell", [b"B", b"Q"], []),
                                           ("provider", [b"B", b"M", b"P", b"Q"], [b"second\n"])):
            with self.subTest(reason=reason):
                actual, sent, state = self.exercise(reason)
                self.assertEqual((actual, sent), (commands, requests))
                self.assertNotIn("delivery", state)

    def test_callback_during_attempt_receipt_output_precedes_the_real_provider_invocation(self):
        commands, _, state = self.exercise("early")
        self.assertEqual(commands[-1], b"Q")
        self.assertNotIn("delivery", state)
        self.assertLess(state["provider"]["attemptTick"], state["provider"]["startTick"])

    def test_lost_or_foreign_shell_cannot_authorize_invoke_and_delete_does_not_imply_stability(self):
        for refusal in ("unbound", "foreign-provider", "beforeMarker", "afterMarker", "beforeInvoke",
                        "missing-modify", "duplicate-modify", "superseded"):
            with self.subTest(refusal=refusal):
                _, requests, state = self.exercise(refusal)
                self.assertNotIn(b"invoke\n", requests)
                self.assertEqual(state["nativeShutdown"]["cleanupMethod"], "deletedAtQuit")
                self.assertFalse(state["nativeShutdown"]["stableRegistration"])
        for refusal in ("providerAttempt", "afterInvoke", "afterQuit"):
            with self.subTest(refusal=refusal):
                _, requests, state = self.exercise(refusal)
                self.assertIn(b"invoke\n", requests)
                self.assertFalse(state["nativeShutdown"]["activationHostChecks"][refusal])
                self.assertTrue(state["nativeShutdown"]["observedHostInstability"])
                self.assertFalse(state["nativeShutdown"]["stableRegistration"])
                self.assertEqual(state["nativeShutdown"]["cleanupMethod"], "deletedAtQuit")
        self.exercise("no-frame")


class TrialSelectionTests(unittest.TestCase):
    def test_independent_retained_normal_and_autostart_profiles_obey_prior_cleanup(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            @contextmanager
            def subject(*_, **_options):
                yield Mock(), Mock(), root / "selected-gui", {}, "revision"
            @contextmanager
            def profile(state, *_):
                state["profile"] = str(len(profiles))
                profiles.append(state)
                try:
                    yield root / "selected-gui", root, {}
                finally:
                    state["cleanupConfirmed"] = state["profile"] != unconfirmed
            def resident(_api, _desk, gui, _trial, _env, out, state, *, subject, reopen):
                calls.append((gui.name, subject, reopen, out.name))
                if state["profile"] == "1":
                    raise tray.Unavailable("Provider declined this profile")
            for variant, unconfirmed, expected_calls in (("retained", None, 2), ("retained", "1", 1),
                                                        ("canonical", None, 1)):
                with self.subTest(subject=variant, unconfirmed=unconfirmed):
                    out = root / f"{variant}-{unconfirmed}"
                    out.mkdir()
                    profiles, calls, result = [], [], {}
                    with (patch.object(tray.launcher, "native_subject", subject), patch.object(tray.launcher, "staged_profile", profile),
                          patch.object(tray, "resident", resident), patch.object(tray.launcher, "private_desktop"),
                          patch.object(tray.c, "WinDLL", create=True), patch.object(tray, "bind")):
                        if unconfirmed:
                            with self.assertRaises(tray.Unavailable):
                                tray.assess("target", out, result, subject=variant)
                            self.assertEqual(result["inputDesktopReopen"]["status"], "not-run")
                        else:
                            self.assertEqual(tray.assess("target", out, result, subject=variant), "unavailable")
                    self.assertEqual(len(calls), expected_calls)
                    self.assertEqual(calls[0], ("selected-gui", variant, False, out.name))
                    if expected_calls == 2:
                        self.assertEqual(calls[1], ("selected-gui", variant, True, "inputDesktopReopen"))
                        self.assertEqual(result["inputDesktopReopen"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
