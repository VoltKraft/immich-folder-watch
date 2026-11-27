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
               root=51, rootClass="Shell_TrayWnd", overflow=0, pane=None, monitor=2, cursor=[4, 3],
               shellPid=81, shellCreation=102, desktop="Default", rgb=RGB)
ELEMENT = dict(runtimeId="42,99", matchCount=1, matchedLabel="IFW tray " + TOKEN, pid=81, hitDepth=2,
               root=51, hitRuntimeId="42,199",
               nameMatches=True, helpMatches=False, enabled=True, offscreen=False, bounds=[-4, 10, 28, 42])
MSAA = dict(method="MSAA.accDoDefaultAction", matchCount=1, matchedLabel="IFW tray " + TOKEN,
            root=51, pid=81, nativeHit=52, role=0x2b, state=0, childId=4, pointChildId=4,
            hitTestChildId=4, childCount=5, nameMatches=True, bounds=RECT)


def registration(added):
    return (f"gui_tray.initial.add={str(added).lower()}\n"
            + ("gui_tray.initial.version4=true\n"
               "TRAY_BIND phase=initial pid=18 hwnd=43 id=23 shell_pid=81 shell_hwnd=51 verified=1\n" if added else "")
            + f"TRAY_REGISTER phase=initial pid=18 hwnd=43 id=23 token={TOKEN} added={int(added)} version4={int(added)}\n")


def closed(added):
    return (("gui_tray.shutdown=true\n" if added else "") +
            f"TRAY_CLEANUP pid=18 hwnd=43 id=23 registered={int(added)} removed={int(added)}\nDRAINED passes=2\n")


def callback(queued="22", dispatched=23, code=0x401, counter=None):
    qpc = "" if counter is None else f" dispatch_qpc={counter}"
    return (f"TRAY_CALLBACK pid=18 hwnd=43 id=23 code={code} ordinal=1 queued_ms={queued} dispatch_ms={dispatched}{qpc}\n"
            "TRAY_OPEN pid=18 ordinal=1\n")


class TrayProofTests(unittest.TestCase):
    def test_consumed_open_must_identify_the_held_gui_thread_root_and_callback_ordinal(self):
        root = dict(pid=18, tid=8, hwnd=99)
        delivered = dict(pid=18, ordinal=1, dispatchMs=23)
        line = "TRAY_OPEN_ROOT pid=18 tid=8 hwnd=99 ordinal=1 visible=false tick=23\n"
        self.assertEqual(tray.tray_open_root(line, delivered, root, 28),
                         dict(**root, ordinal=1, visible=False, tick=23))
        for source, wrong in (("pid=18", "pid=19"), ("tid=8", "tid=9"), ("hwnd=99", "hwnd=43"),
                              ("ordinal=1", "ordinal=2"), ("tick=23", "tick=22"), ("tick=23", "tick=29")):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                tray.tray_open_root(line.replace(source, wrong), delivered, root, 28)
        with self.assertRaises(ValueError):
            tray.tray_open_root(line + line, delivered, root, 28)
        self.assertIsNone(tray.tray_open_root(line.rstrip(), delivered, root, 28))

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
            with self.assertRaises(ValueError):
                probe.registration(proc, lambda: text, lambda callback, _: callback(), {}, no_host=True)
            self.assertEqual(tray.records(text.rstrip(), "TRAY_REGISTER"), [])
        probe.name = "IfwQa_Tray_" + TOKEN
        probe.desk.name.return_value = {"win32Error": 5}
        private = Mock()
        private.name = probe.name
        private.proc = proc
        for observed, expect in ((dict(hresult=-1, rect=None), False), (dict(hresult=0, rect=RECT), True)):
            with patch.object(tray, "shell_rect", return_value=observed):
                verify = lambda: probe.registration(proc, lambda: registration(False), lambda fn, _: fn(), {},
                                                    no_host=True, private=private)
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

    def test_fast_sent_callback_uses_performance_counter_order_on_a_shared_uptime_tick(self):
        def read(counter, queued="none"):
            return tray.delivery(callback(queued, 21, counter=counter), KEY, 21, 21,
                                 start_qpc=501, observed_qpc=600)
        self.assertEqual(read(503)["dispatchQpc"], 503)
        for counter in (500, 501, 502):
            with self.subTest(counter=counter), self.assertRaises(tray.Unavailable):
                read(counter)
        for counter in (None, 0, 499, 602):
            with self.subTest(counter=counter), self.assertRaises(ValueError):
                read(counter)
        with self.assertRaisesRegex(tray.Unavailable, "queue time"):
            read(503, "21")

    def test_msaa_requires_the_shell_hit_and_one_named_enabled_button_with_concordant_child_ids(self):
        event = dict(provider=MSAA, surface=SURFACE)
        self.assertEqual(tray.confirm_surface(event, KEY, 101, RECT, RGB), SURFACE)
        self.assertEqual(tray.confirm_provider(event, SURFACE, TOKEN), MSAA)
        for changes in (dict(role=22), dict(state=0x8000), dict(state=0x10000), dict(state=1), dict(nativeHit=53),
                        dict(hitTestChildId=3), dict(childCount=129), dict(childCount=0), dict(nameMatches=False),
                        dict(matchCount=2), dict(matchedLabel="other"), dict(bounds=[-5,10,28,42])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tray.confirm_provider(dict(provider=MSAA | changes), SURFACE, TOKEN)

    def test_msaa_route_follows_original_uia_absence_and_can_never_open_a_flyout(self):
        first = dict(stage="first", surface=dict(SURFACE, rgb=RGB))
        second = dict(SURFACE, rgb=COMPLEMENT)
        lookup = dict(stage="msaa-lookup", surface=second, uiaVisibleNamedItems=0)
        ready = dict(stage="ready", surface=second, provider=MSAA)
        tray.verify_msaa_route([first, lookup, ready], ready, True)
        for events, enabled in (([lookup, first, ready], True), ([first, lookup, ready], False),
                ([first, lookup | {"uiaVisibleNamedItems":1}, ready], True), ([first, dict(stage="opening"), lookup, ready], True),
                ([first, lookup | {"surface":SURFACE}, ready], True), ([first, ready], True)):
            with self.subTest(events=events, enabled=enabled), self.assertRaises(ValueError):
                tray.verify_msaa_route(events, ready, enabled)

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
    def exercise(self, refusal, *, subject="canonical", reopen=False, flyout=False, compare=False, msaa=False,
                 tied_sample=None, root_show=True):
        api, desk, windows = Mock(), Mock(), OwnedRoot(18)
        proc, helper = Mock(pid=18, _handle=42), Mock()
        unpresented = bool(refusal and refusal.startswith("fallback-"))
        windows.desktop = 44
        proc.poll.return_value = None
        api.process_identity.return_value = 101
        api.wait_job_empty.return_value = True
        api.frequency = 10_000_000
        api.clock.return_value = 300
        desk.owner.return_value = 0
        desk.name.return_value = "Default"
        desk.foreground.side_effect = lambda: windows.hwnd
        desk.window.side_effect = lambda hwnd: dict(pid=18, tid=2, rect=RECT, **{"class": "IFW RW02 synthetic tray receiver"})
        desk.iconic.return_value = False
        desk.attribute.return_value = 0
        state, commands, requests = {}, [], []
        visible_rect = [310, 410, 342, 442] if flyout else RECT
        visible_surface = (dict(SURFACE, rect=visible_rect, point=[326, 426], hit=62, root=61, overflow=61,
                                rootClass="TopLevelWindowForOverflowXamlIsland",
                                pane=dict(hwnd=61, pid=81, tid=82, windowClass="TopLevelWindowForOverflowXamlIsland")) if flyout else SURFACE)
        visible_element = dict(MSAA if msaa else ELEMENT, root=visible_surface["root"], bounds=visible_rect)
        with TemporaryDirectory() as directory:
            out = Path(directory)
            logfile = out / "resident-primary.log"
            def append(msg):
                with logfile.open("a", encoding="utf-8") as stream:
                    stream.write(msg)
            def report_icon(phase, color):
                coords = RECT if phase == "initial" or refusal == "stale-flyout" else visible_rect
                if refusal == "moved-before-invoke" and commands.count(b"P") >= 3:
                    coords = RECT
                append(f"TRAY_ICON phase={phase} pid=18 hwnd=43 id=23 rgb={color} rect={','.join(map(str,coords))} ok=1\n")
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
                    report_icon("changed" if data == b"M" else "sample", COMPLEMENT if b"M" in commands else RGB)
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
                    if unpresented:
                        raise tray.Unavailable("No verified presentation")
                    if compare:
                        return None
                    return {"surface": visible_surface | {"shellPid": 87} if refusal == "foreign-provider" else visible_surface}
                if stage == "taskbar-before":
                    return dict(stage=stage, surface=dict(SURFACE, rgb="eeeeee"), barBounds=[-20,0,100,100], expectedRgb=RGB)
                if stage == "taskbar-after":
                    return dict(color=COMPLEMENT, comparison=dict(barBounds=[-20,0,100,100], iconBounds=RECT, stable=30,
                                rows=5, columns=6, firstColor=3, secondColor=2, inside=0, outside=2,
                                startTick=[1,5,29,32], endTick=[4,7,30,34]))
                if stage == "ready" and refusal == "provider":
                    raise tray.Unavailable("No exact accessible icon")
                if stage in ("ready", "attempt"):
                    return dict(surface=dict(visible_surface, rgb=COMPLEMENT), provider=visible_element, tick=19)
                if stage == "invoked":
                    append(callback("20", 20, counter=190) if refusal == "early" else callback(counter=240))
                    if not reopen:
                        append(FIRST_RENDER if subject == "retained" else "ADAPTER Dx12 Cpu\n")
                    if refusal == "second-generation":
                        append("GRAPHICS_READY generation=2\n")
                    if refusal == "different-window":
                        windows.hwnd = 100
                    if tied_sample:
                        append(tied_sample)
                    show_tick = 23 if tied_sample is not None else 24
                    windows.show(16 if refusal == "premature-show" else show_tick, create=not reopen)
                    windows.events[-1]["root"] = root_show
                    invoked = dict(visible_surface, rgb=COMPLEMENT)
                    if refusal == "recycled-at-invoke":
                        invoked["pane"] = invoked["pane"] | {"tid": 777}
                    return dict(startTick=21, returnedTick=25, startQpc=211, returnedQpc=251,
                                qpcFrequency=api.frequency, surface=invoked, provider=visible_element)
                self.fail("Unexpected provider stage")
            helper.stdin.write.side_effect = requests.append

            @contextmanager
            def child(_api, _desk, desktop, exe, args, trial, env, stream, primary, **kwargs):
                if primary:
                    yield proc, 1, 2
                    return
                self.assertEqual((desktop, exe, args, trial, kwargs["private"]), ("Default", out / "gui.exe", [], out, False))
                secondary = Mock(pid=19, _handle=41)
                secondary.poll.return_value = 0
                kwargs["before_resume"](secondary)
                stream.write(b"LAUNCHER_FOREGROUND_GRANT server=18 state=granted\nLAUNCHER_SECONDARY server=18\n")
                stream.flush()
                append("LAUNCHER_OPEN client=19\nWINDOW_FOREGROUND_REQUEST pid=18 hwnd=99 accepted=true\n")
                if refusal == "fallback-other-callback":
                    append(callback())
                if not reopen:
                    append(FIRST_RENDER)
                if refusal == "fallback-replaced-window":
                    windows.hwnd = 100
                if refusal in ("fallback-delayed-stale", "fallback-tied-witness"):
                    # Deliver the out-of-context hook only after the observer samples the resumed secondary.
                    if refusal == "fallback-delayed-stale":
                        windows.shown = True
                    def deliver_show():
                        windows.show(21 if refusal == "fallback-delayed-stale" else 23, create=not reopen)
                        return 0
                    secondary.poll.side_effect = deliver_show
                else:
                    windows.show(23 if refusal == "fallback-tied-visible" else 24, create=not reopen)
                yield secondary, 2, None

            @contextmanager
            def provider(*args):
                try:
                    yield helper, receive
                finally:
                    if unpresented:
                        args[-2].update(exit=2, jobEmpty=True, flyoutHistory=[
                            dict(stage="baseline"), dict(stage="hint", surface=None, markerObserved=False,
                                reason="Independent Shell_NotifyIconGetRect returned 00000001"),
                            dict(stage="cleanup", attempted=False, iconAttempted=refusal == "fallback-invoked")])

            def read_rect(_hwnd):
                if refusal == "fallback-reappeared" and "ordinaryLauncherFallback" in state and proc.poll() is None:
                    return dict(hresult=0, rect=RECT)
                return dict(hresult=1 if unpresented and proc.poll() is None else -1, rect=None)

            def query_job(job, level, dest, *args):
                self.assertEqual((job, level), (2, 1))
                dest._obj.total = 2 if refusal == "fallback-extra-child" else 1
                return True

            api.query_job.side_effect = query_job

            witness = Mock(markers=0, confirmed=refusal != "unbound", original=(81, 51))
            witness.live.side_effect = lambda stage: stage != refusal
            clock = lambda: 28
            if compare:
                clock = Mock(side_effect=[26, 28, 35])
            elif unpresented:
                clock = Mock(side_effect=[22, 23, 23, 28] if refusal == "fallback-tied-witness" else [22, 23, 28])
            with (patch.object(tray, "ShellWitness", return_value=witness),
                  patch.object(retained_window, "WindowLifetime", return_value=Mock(events=windows.life)),
                  patch.object(retained_window, "visible_surface", side_effect=lambda *a: tray.visible_surface(
                      *a, monitor_area=lambda _: [-20, 0, 100, 100])),
                  patch.object(retained_window, "desktop_windows", return_value=dict(desktop="Default", ownedCount=0, windows=[])),
                  patch.object(retained_window, "focus_sample", return_value=dict(foreground=True, active=True,
                                                                                focused=refusal != "fallback-no-focus")),
                  patch.object(tray, "bind", return_value=clock),
                  patch.object(tray, "ordinary_console", return_value=True),
                  patch.object(tray.launcher, "child", child), patch.object(tray.launcher, "snapshot", return_value={}),
                  patch.object(tray.launcher, "system_console_path"), patch.object(tray.recorder, "load_windows_fixture") as fixture,
                  patch.object(tray.recorder, "idle_complete", return_value=True), patch.object(tray.recorder, "owned_worker", return_value=28),
                  patch.object(tray.launcher, "primary_job_members",
                               side_effect=[[28, 201], [28, 302] if refusal in ("different-worker", "fallback-worker") else [28, 201]]),
                  patch.object(tray, "provider", provider),
                  patch.object(tray, "monitor_work_area", return_value=[-20, 0, 100, 100]),
                  patch.object(tray, "shell_rect", side_effect=read_rect)):
                fixture.return_value.Windows.return_value = windows
                fixture.return_value.TITLE = TITLE
                env = {"IFW_QA_INVENTORY_TOKEN": TOKEN, "IFW_QA_TASKBAR_COMPARISON": "1" if compare else "0"}
                operation = lambda: tray.resident(api, desk, out / "gui.exe", out, env,
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
                elif tied_sample is not None and ("visible=false tick=23" not in tied_sample or not root_show):
                    with self.assertRaises(tray.launcher.ShowOrderUnavailable):
                        operation()
                elif refusal == "fallback-tied-visible":
                    with self.assertRaises(tray.launcher.ShowOrderUnavailable):
                        operation()
                elif refusal in ("fallback-worker", "fallback-other-callback", "fallback-extra-child", "fallback-replaced-window",
                                 "fallback-no-focus", "fallback-delayed-stale"):
                    with self.assertRaises(ValueError):
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
        self.assertEqual(commands, [b"B", b"M", b"P", b"P", b"Q"])
        self.assertEqual(requests, [b"second\n", b"invoke\n"])
        self.assertEqual(state["workerBefore"], state["workerAfter"])
        self.assertEqual(state["openedWindow"]["pid"], state["primaryPid"])

    def test_relocated_first_icon_requires_fresh_gui_rect_for_each_color_and_immediately_before_invocation(self):
        commands, requests, state = self.exercise(None, flyout=True)
        self.assertEqual(commands, [b"B", b"P", b"M", b"P", b"P", b"Q"])
        self.assertEqual(requests, [b"second\n", b"invoke\n"])
        self.assertNotEqual(state["initialGuiRect"], state["firstVisibleGuiRect"])
        for target in (state["first"], state["second"]):
            self.assertEqual(target["rect"], state["firstVisibleGuiRect"])
        self.assertEqual(state["beforeInvokeGuiRect"], state["secondGuiRect"])
        for wrong in ("stale-flyout", "moved-before-invoke"):
            _, requests, state = self.exercise(wrong, flyout=True)
            self.assertNotIn(b"invoke\n", requests)
            self.assertNotIn("delivery", state)
        _, _, rejected = self.exercise("recycled-at-invoke", flyout=True)
        self.assertNotIn("delivery", rejected)

    def test_real_callback_covers_first_activation_and_reopening_the_previously_closed_retained_hwnd(self):
        for reopen in (False, True):
            with self.subTest(reopen=reopen):
                commands, requests, state = self.exercise(None, subject="retained", reopen=reopen)
                self.assertEqual(commands, [b"B", b"M", b"P", b"P", b"Q"])
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

    def test_same_tick_requires_a_hidden_sample_on_the_gui_thread_and_an_independent_root_show(self):
        line = "TRAY_OPEN_ROOT pid=18 tid=8 hwnd=99 ordinal=1 visible=false tick=23\n"
        for sample, root in ((line, True), ("", True), (line.replace("false", "true"), True),
                             (line.replace("tick=23", "tick=24"), True), (line, False)):
            with self.subTest(sample=sample, root=root):
                _, _, state = self.exercise(None, subject="retained", reopen=True, tied_sample=sample, root_show=root)
                row = state["retainedWindow"]["callbackShow"]
                self.assertFalse(row["distinctTicks"])
                self.assertEqual(row["showEvent"], dict(event="show", hwnd=99, root=root, winEventTimeMs=23))
                if sample == line and root:
                    self.assertEqual(row["basis"], "hiddenOnGuiThreadBeforeTrayOpen")
                else:
                    self.assertEqual(row["status"], "inconclusive")

    def test_registration_refusal_or_unidentified_icon_still_quits_naturally_without_activation(self):
        for reason, commands, requests in (("shell", [b"B", b"Q"], []),
                                           ("provider", [b"B", b"M", b"P", b"Q"], [b"second\n"])):
            with self.subTest(reason=reason):
                actual, sent, state = self.exercise(reason)
                self.assertEqual((actual, sent), (commands, requests))
                self.assertNotIn("delivery", state)

    def test_ordinary_secondary_presents_the_same_primary_when_explorer_returns_s_false(self):
        for reopen in (False, True):
            with self.subTest(reopen=reopen):
                commands, requests, state = self.exercise("fallback-unpresented", subject="retained", reopen=reopen)
                self.assertEqual((commands, requests), ([b"B", b"Q"], []))
                self.assertNotIn("delivery", state)
                self.assertEqual(state["shellActivation"], dict(status="unavailable", reason="No verified presentation"))
                self.assertEqual(state["initialGuiRect"], RECT)
                receipt = state["ordinaryLauncherFallback"]
                self.assertEqual(receipt["status"], "passed")
                self.assertEqual(receipt["initialGuiWindow"], 99 if reopen else None)
                self.assertEqual(receipt["rootShow"]["hwnd"], state["retainedWindow"]["first"]["hwnd"])
                self.assertEqual(receipt["secondaryArguments"], [])
                self.assertEqual(receipt["workerBefore"], receipt["workerAfter"])
                self.assertTrue(receipt["keyboardFocus"]["observed"])
                self.assertEqual(state["retainedWindow"]["secondaryShow"]["basis"], "distinctTicks")
                self.assertEqual(state["nativeShutdown"]["cleanupMethod"], "deletedAtQuit")

    def test_fallback_show_order_for_stale_and_tied_native_events(self):
        for reopen in (False, True):
            for reason in ("fallback-delayed-stale", "fallback-tied-visible", "fallback-tied-witness"):
                with self.subTest(reopen=reopen, reason=reason):
                    _, _, state = self.exercise(reason, subject="retained", reopen=reopen)
                    receipt, root = state["ordinaryLauncherFallback"], state["retainedWindow"]
                    row = root["secondaryShow"]
                    self.assertEqual((row["earliestMs"], row["releasedByMs"], row["observedMs"]), (22, 23, 28))
                    if reason == "fallback-delayed-stale":
                        self.assertLess(row["showMs"], receipt["beforeResumeMs"])
                        self.assertEqual((receipt["status"], row["status"]), ("failed", "outsideInterval"))
                    elif reason == "fallback-tied-visible":
                        self.assertEqual((receipt["status"], row["status"]), ("inconclusive", "inconclusive"))
                    else:
                        self.assertEqual(receipt["status"], "passed")
                        self.assertEqual(row["basis"], "observedHiddenAfterTrigger")
                        self.assertEqual(root["afterTrigger"]["state"], "retainedRootHidden" if reopen else "noGuiRoot")
                        if not reopen:
                            self.assertEqual(row["createMs"], 23)

    def test_visible_fallback_with_no_keyboard_focus_keeps_its_order_and_normal_quit_receipts(self):
        _, _, state = self.exercise("fallback-no-focus", subject="retained")
        receipt = state["ordinaryLauncherFallback"]
        self.assertEqual(state["retainedWindow"]["secondaryShow"]["status"], "ordered")
        self.assertEqual(receipt["status"], "failed")
        self.assertFalse(receipt["keyboardFocus"]["lastSample"]["focused"])
        self.assertFalse(receipt["keyboardFocus"]["observed"])
        self.assertEqual(state["nativeShutdown"]["cleanupMethod"], "deletedAtQuit")

    def test_fallback_rejects_an_unrelated_worker_callback_secondary_child_or_replaced_window(self):
        for reason in ("fallback-worker", "fallback-other-callback", "fallback-extra-child", "fallback-replaced-window"):
            with self.subTest(reason=reason):
                commands, _, state = self.exercise(reason, subject="retained", reopen=True)
                self.assertEqual(commands[-1], b"Q")
                self.assertEqual(state["ordinaryLauncherFallback"]["status"], "failed")
                self.assertEqual(state["shellActivation"]["status"], "unavailable")

    def test_no_fallback_launch_when_a_provider_action_may_already_have_started(self):
        _, _, state = self.exercise("fallback-invoked", subject="retained")
        self.assertNotIn("ordinaryLauncherFallback", state)

    def test_secondary_stays_suspended_if_explorer_exposes_the_icon_before_resume(self):
        commands, _, state = self.exercise("fallback-reappeared", subject="retained")
        self.assertEqual(commands, [b"B", b"Q"])
        receipt = state["ordinaryLauncherFallback"]
        self.assertEqual(receipt["shellBeforeResume"], dict(hresult=0, rect=RECT))
        self.assertNotIn("secondaryExit", receipt)
        self.assertNotIn("rootShow", receipt)

    def test_comparison_after_provider_refusal_records_modify_and_quit_without_invoking_any_item(self):
        commands, requests, state = self.exercise("missing-provider", subject="retained", reopen=True, compare=True)
        self.assertEqual(commands, [b"B", b"P", b"M", b"P", b"Q"])
        self.assertEqual(requests, [b"compare\n"])
        self.assertEqual(state["taskbarComparison"]["status"], "transition-observed")
        self.assertEqual(state["nativeShutdown"]["markerAcknowledgements"], 1)
        self.assertEqual(state["nativeShutdown"]["cleanupMethod"], "deletedAtQuit")
        self.assertFalse(state["nativeShutdown"]["stableRegistration"])
        self.assertNotIn("delivery", state)

    def test_msaa_action_keeps_the_same_callback_worker_focus_and_shutdown_requirements(self):
        commands, requests, state = self.exercise(None, subject="retained", msaa=True)
        self.assertEqual(state["providerIdentity"]["method"], "MSAA.accDoDefaultAction")
        self.assertEqual(requests, [b"second\n", b"invoke\n"])
        self.assertEqual((state["delivery"]["pid"], state["delivery"]["hwnd"]), (18,43))
        self.assertEqual(state["workerBefore"], state["workerAfter"])
        self.assertTrue(state["keyboardFocus"]["observed"])
        self.assertTrue(state["nativeShutdown"]["stableRegistration"])
        self.assertEqual(commands[-1], b"Q")

    def test_callback_during_attempt_receipt_output_precedes_the_real_provider_invocation(self):
        for msaa in (False, True):
            with self.subTest(msaa=msaa):
                commands, _, state = self.exercise("early", subject="retained", msaa=msaa)
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
            def resident(_api, _desk, gui, _trial, env, out, state, *, subject, reopen):
                calls.append((gui.name, subject, reopen, out, env["IFW_QA_TASKBAR_COMPARISON"], env["IFW_QA_MSAA_ICON"]))
                if state["profile"] == "1":
                    raise tray.Unavailable("Provider declined this profile")
            background, reopen = "inputDesktop", "inputDesktopReopen"
            trials = (("x86_64", "retained", False, [background, reopen]), ("x86_64", "retained", True, [reopen, background]),
                      ("x86_64", "canonical", False, [background]), ("aarch64", "retained", False, [background, reopen]))
            for arch, variant, reopen_first, residents in trials:
                target = arch + "-pc-windows-msvc"
                order = ["shellLess", *residents]
                for unconfirmed in [None, *map(str, range(len(order)))]:
                    with self.subTest(target=target, subject=variant, reopen_first=reopen_first, unconfirmed=unconfirmed):
                        out = root / f"{arch}-{variant}-{reopen_first}-{unconfirmed}"
                        out.mkdir()
                        profiles, calls, result = [], [], {}
                        with (patch.object(tray.launcher, "native_subject", subject), patch.object(tray.launcher, "staged_profile", profile),
                              patch.object(tray, "resident", resident), patch.object(tray.launcher, "private_desktop"),
                              patch.object(tray.c, "WinDLL", create=True), patch.object(tray, "bind")):
                            if unconfirmed is None:
                                status = tray.assess(target, out, result, subject=variant, reopen_first=reopen_first)
                                self.assertEqual(status, "unavailable")
                                self.assertEqual(result[residents[0]]["status"], "unavailable")
                                if len(residents) == 2:
                                    self.assertEqual(result[residents[1]]["status"], "passed")
                                started = order
                            else:
                                error = tray.Unavailable if unconfirmed == "1" else tray.CleanupUnconfirmed
                                with self.assertRaises(error):
                                    tray.assess(target, out, result, subject=variant, reopen_first=reopen_first)
                                stop = int(unconfirmed) + 1
                                started = order[:stop]
                                self.assertEqual(result[started[-1]]["status"], "failed")
                                for missing in order[stop:]:
                                    self.assertEqual(result[missing]["status"], "not-run")
                        self.assertEqual(result["caseOrder"], order)
                        self.assertEqual(result["startedCases"], started)
                        self.assertEqual(len(profiles), len(started))
                        msaa = arch == "x86_64" and variant == "retained"
                        self.assertEqual(calls, [("selected-gui", variant, case == reopen, out / case if case == reopen else out,
                                                  str(int(msaa and case == reopen)), str(int(msaa))) for case in started[1:]])

    def test_reopen_first_rejects_other_subjects_before_native_setup(self):
        with patch.object(tray.launcher, "native_subject") as setup:
            for target, subject in (("x86_64-pc-windows-msvc", "canonical"), ("aarch64-pc-windows-msvc", "retained")):
                with self.subTest(target=target, subject=subject), self.assertRaisesRegex(ValueError, "--reopen-first requires"):
                    tray.assess(target, Path("unused"), {}, subject=subject, reopen_first=True)
            setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
