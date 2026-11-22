"""Exercise desktop readback, primary failure preservation and independent launcher trials."""
from contextlib import contextmanager
import ctypes as c
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, call, patch

import observe
import window_readback


class DesktopReadbackTests(unittest.TestCase):
    def test_only_the_visible_owned_window_with_the_canonical_gui_title_qualifies(self):
        fixture = observe.recorder.load_windows_fixture()
        source = (observe.QA / "gui/src/main.rs").read_text(encoding="utf-8")
        self.assertIn(f'.with_title("{fixture.TITLE}")', source)
        windows = fixture.Windows.__new__(fixture.Windows)
        windows.pid, windows.desktop = 12, 10
        windows.enum_callback = lambda callback: callback
        windows.pump = Mock()
        # The observer's witness, a foreign window, a similarly titled helper, and the true root.
        owners = {50: 10, 51: 55, 52: 12, 53: 12}
        visible = {50, 51, 52}
        titles = {52: "Desktop input probe (Grüße)", 53: fixture.TITLE}

        def caption(hwnd, output, _size):
            output.value = titles[hwnd]
            return len(output.value)

        def owner(hwnd, output):
            output._obj.value = owners[hwnd]
            return hwnd + 100

        windows.enumerate = lambda _desktop, visit, _data: all(visit(hwnd, 0) for hwnd in owners)
        windows.owner, windows.caption, windows.is_visible = owner, caption, visible.__contains__
        with patch.object(c, "set_last_error", create=True):
            self.assertIsNone(windows.visible(waiting_for_first=True))
            visible.add(53)
            self.assertEqual(windows.visible(), 53)

    def test_reads_only_owned_windows_and_reports_the_primary_threads_actual_desktop(self):
        desk, windows = Mock(), Mock()
        windows.pid = 12
        windows.enum_callback = lambda callback: callback
        objects = {10: [50, 51, 52], 20: [53, 54]}
        owners = {50: (25, 1), 51: (12, 2), 52: (26, 3), 53: (12, 4), 54: (27, 5)}
        names = {10: "IfwQa", 20: "Default"}
        titles = {51: "Grüße – 猫📷", 53: "Desktop input probe"}

        def enumerate_desktop(handle, callback, _data):
            return all(callback(hwnd, 0) for hwnd in objects[handle])

        def owner(hwnd, pid):
            pid._obj.value, tid = owners[hwnd]
            return tid

        def title(hwnd, buf, _length):
            buf.value = titles[hwnd]
            return len(titles[hwnd].encode("utf-16-le")) // 2

        def window_class(hwnd, buf, _length):
            self.assertIn(hwnd, titles)
            buf.value = "A real Unicode class"
            return len(buf.value)

        windows.enumerate.side_effect = enumerate_desktop
        windows.owner.side_effect = owner
        windows.caption.side_effect = title
        windows.is_visible.side_effect = lambda hwnd: hwnd == 53
        desk.name.side_effect = names.__getitem__
        desk.thread_desktop.side_effect = lambda tid: 10 if tid == 2 else 20
        desk.window_class.side_effect = window_class
        with patch.object(c, "set_last_error", create=True):
            result = window_readback.snapshot(desk, windows, 10, 50, 4, 1234)
        self.assertTrue(result["witnessSeen"])
        self.assertEqual((result["primaryPid"], result["primaryCreation100ns"], result["initialThreadDesktop"]),
                         (12, 1234, "Default"))
        self.assertEqual(result["ownedCount"], 1)
        first, = result["windows"]
        self.assertEqual((first["hwnd"], first["pid"], first["desktop"], first["title"], first["visible"]),
                         (51, 12, "IfwQa", titles[51], False))
        self.assertEqual(first["windowClass"], "A real Unicode class")
        actual = result["initialThreadWindows"]
        self.assertIsNone(actual["witnessSeen"])
        self.assertEqual([(row["title"], row["visible"]) for row in actual["windows"]], [(titles[53], True)])
        self.assertEqual(window_readback.printable("A\ud83d").encode("utf-8"), br"A\x3d\xd8")

    def test_hidden_paint_diagnostic_and_real_show_are_limited_to_the_witness(self):
        desk, user, record = Mock(), Mock(), {}
        desk.name.return_value = "IfwQa"
        desk.receiving_input.return_value = False
        visible = False

        def show(hwnd, how):
            nonlocal visible
            self.assertEqual(hwnd, 50)
            old, visible = visible, bool(how)
            return old

        def peek(output, hwnd, first, last, remove):
            self.assertEqual((hwnd, first, last, remove), (50, 15, 15, 1))
            output._obj.hWnd, output._obj.message = hwnd, 15
            return visible

        user.ShowWindow.side_effect, user.PeekMessageW.side_effect = show, peek
        desk.visible.side_effect = lambda hwnd: visible
        window_readback.paint_control(user, desk, 50, 10, "IfwQa", record)
        self.assertEqual(record, dict(initiallyVisible=False, hiddenPaintMessage=False, showVisible=True,
                                      shownPaintMessage=True, visibleAfterHide=False))
        self.assertEqual(user.RedrawWindow.call_args_list, [call(50, None, None, 2)] * 2)
        self.assertEqual(user.ShowWindow.call_args_list, [call(50, 4), call(50, 0)])
        user.DispatchMessageW.assert_called_once()


class DesktopCleanupTests(unittest.TestCase):
    def test_same_thread_restores_original_and_records_both_primary_and_close_errors(self):
        desk, select, record = Mock(), Mock(), {}
        desk.thread.side_effect = threading.get_ident
        thread = threading.local()
        desk.thread_desktop.side_effect = lambda tid: getattr(thread, "desktop", 10)
        desk.name.side_effect = lambda handle: {10: "Default", 11: "Default", 20: "Private"}[handle]
        creator = []

        def create(*_args):
            creator.append(threading.get_ident())
            thread.desktop = 20
            return 20

        def attach(handle):
            self.assertEqual(creator, [threading.get_ident()])
            thread.desktop = 11 if handle == 10 else handle  # The borrowed handle's name identifies the desktop.
            return True

        def visit(handle):
            self.assertEqual((thread.desktop, handle), (20, 20))
            raise TimeoutError("First window was absent")

        desk.create.side_effect, select.side_effect = create, attach
        desk.close.return_value = False
        with patch.object(c, "get_last_error", return_value=170, create=True), self.assertRaises(observe.CleanupUnconfirmed) as caught:
            observe.private_desktop(desk, select, "Private", visit, record)
        self.assertEqual(record, dict(originalThreadDesktop="Default", threadRestored=True, handleClosed=False))
        desk.close.assert_called_once_with(20)
        self.assertEqual(select.call_args_list, [call(20), call(10)])
        messages = [row["message"] for row in observe.failures(caught.exception)]
        self.assertEqual(messages[0], "First window was absent")
        self.assertIn("Win32 170", messages[1])

    def test_cleanup_while_unwinding_keeps_original_error_and_blocks_next_trial(self):
        with TemporaryDirectory() as parent:
            parent = Path(parent)

            @contextmanager
            def owned(_api, directory, name):
                root = directory / name
                root.mkdir()
                try:
                    yield root
                finally:
                    root.rmdir()
                    raise OSError("owned directory close failed")

            cases = {}
            def visit(name, state):
                self.assertEqual(name, "shellLess")
                with observe.profile_resources(None, parent, "test", state):
                    raise TimeoutError("missing primary")

            with patch.object(observe.recorder, "owned_directory", owned), self.assertRaises(observe.CleanupUnconfirmed):
                observe.run_cases(visit, cases)
        self.assertFalse(cases["shellLess"]["cleanupConfirmed"])
        self.assertEqual([row["message"] for row in cases["shellLess"]["failures"]],
                         ["missing primary", "owned directory close failed"])
        self.assertEqual(cases["foreground"]["status"], "not-run")

    def test_confirmed_cleanup_permits_the_independent_trial_and_keeps_private_failure(self):
        with TemporaryDirectory() as parent:
            parent = Path(parent)
            profiles = []
            cases = {}

            @contextmanager
            def owned(_api, directory, name):
                root = directory / name
                root.mkdir()
                try:
                    yield root
                finally:
                    root.rmdir()

            def visit(name, record):
                with observe.profile_resources(None, parent, name, record) as (root, _):
                    profiles.append(root)
                    if name == "shellLess":
                        raise TimeoutError("missing private primary")
                    self.assertFalse(profiles[0].exists())

            with patch.object(observe.recorder, "owned_directory", owned):
                error = observe.run_cases(visit, cases)
        self.assertIsInstance(error, TimeoutError)
        self.assertEqual(len(set(profiles)), 2)
        self.assertEqual([value["status"] for value in cases.values()], ["failed", "passed"])
        self.assertTrue(all(value["cleanupConfirmed"] for value in cases.values()))

    def test_failure_drain_records_only_an_unambiguous_native_ui_pass_count(self):
        for status, log, passes in [(0, "DRAINED passes=3\n", 3), (1, "DRAINED passes=8\n", None),
                                    (0, "INVENTORY\n", None), (0, "DRAINED passes=1\nDRAINED passes=2\n", None)]:
            proc, report = Mock(), {}
            proc.poll.side_effect = [None, status]
            observe.drain_after_failure(proc, lambda: log, report, Mock())
            self.assertEqual(report["failureDrain"].get("uiPassesAtQuit"), passes)
            proc.stdin.write.assert_called_once_with(b"Q")


if __name__ == "__main__":
    unittest.main()
