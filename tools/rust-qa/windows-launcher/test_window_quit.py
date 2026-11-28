from copy import deepcopy
import unittest

from window_quit import verify_quit


class WindowQuitTests(unittest.TestCase):
    def setUp(self):
        token = "01ab" * 8
        self.result = {"primaryPid": 32, "inventoryPid": 38, "profile": token, "primaryExit": 0,
                       "workerAliveAfterQuit": False, "workerAtButton": [32, "ifw-performance-worker.exe"],
                       "window": {"pid": 32, "hwnd": 101, "desktopMatches": 1},
                       "button": {"pid": 32, "hwnd": 101, "name": "Beenden", "enabled": True,
                                  "offscreen": False, "width": 84, "height": 22, "method": "InvokePattern"}}
        self.log = "\n".join(["INVENTORY_WORKER pid=38", "gui_tray.initial.add=false",
                              f"TRAY_REGISTER phase=initial pid=32 hwnd=120 id=23 token={token} added=0 version4=0",
                              "READY Visible Unavailable", "INVENTORY_COMPLETE files=1 changed=1 pass=0",
                              "INVENTORY_COMPLETE files=1 changed=0 pass=1",
                              "TRAY_CLEANUP pid=32 hwnd=120 id=23 registered=0 removed=0",
                              "WORKER_EXIT pid=38 reason=quit success=true", "CONTROL_READER_STOPPED",
                              "DRAINED passes=8"])

    def test_one_visible_window_and_original_worker_complete(self):
        verify_quit(self.log, self.result)

    def test_quit_can_finish_the_worker_before_joining_the_tray_thread(self):
        lines = self.log.splitlines()
        cleanup, worker_exit = lines.index("TRAY_CLEANUP pid=32 hwnd=120 id=23 registered=0 removed=0"), lines.index("WORKER_EXIT pid=38 reason=quit success=true")
        lines[cleanup], lines[worker_exit] = lines[worker_exit], lines[cleanup]
        verify_quit("\n".join(lines), self.result)

    def test_rejects_a_worker_that_was_still_running_when_the_gui_drained(self):
        line = "WORKER_EXIT pid=38 reason=quit success=true"
        with self.assertRaises(ValueError):
            verify_quit(self.log.replace(line, "") + "\n" + line, self.result)

    def test_requires_native_refusal_worker_activity_and_full_shutdown(self):
        for line in self.log.splitlines():
            with self.subTest(line=line), self.assertRaises(ValueError):
                verify_quit(self.log.replace(line, ""), self.result)

    def test_rejects_another_shell_receiver_or_recovered_registration(self):
        for log in [self.log.replace("TRAY_CLEANUP pid=32 hwnd=120", "TRAY_CLEANUP pid=32 hwnd=130"),
                    self.log + "\ngui_tray.retry.add=true"]:
            with self.assertRaises(ValueError):
                verify_quit(log, self.result)

    def test_rejects_another_window_or_hidden_button(self):
        for key, value in [("pid", 48), ("hwnd", 120), ("offscreen", True), ("width", 0)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_quit(self.log, {**self.result, "button": {**self.result["button"], key: value}})

    def keyboard(self):
        result = deepcopy(self.result)
        button = result["button"]
        button.update(method="SendInput", buttonRuntimeId=[42, 4],
                      keys=[{"key": k, "events": 2} for k in ("Tab", "Tab", "Tab", "Space")],
                      focus=[{"name": name, "pid": 32, "foregroundHwnd": 101, "nativeFocusHwnd": 101,
                              "role": "ControlType.Edit" if i <= 2 else "ControlType.Button",
                              "runtimeId": [42, i], "hasKeyboardFocus": True, "isPassword": i == 2}
                             for i, name in enumerate(("Dateiname", "Kennwort", "English", "Beenden"), 1)])
        return result

    def test_native_keyboard_traversal_and_invoke_are_separate_observations(self):
        verify_quit(self.log, self.keyboard(), keyboard=True)
        with self.assertRaises(ValueError):
            verify_quit(self.log, self.keyboard())
        with self.assertRaises(ValueError):
            verify_quit(self.log, self.result, keyboard=True)

    def test_space_requires_the_original_focused_visible_quit_button(self):
        for key, value in [("hasKeyboardFocus", False), ("nativeFocusHwnd", 0), ("foregroundHwnd", 102),
                           ("role", "ControlType.Edit"), ("pid", 33), ("name", "English"),
                           ("runtimeId", [42, 1]), ("runtimeId", [42, 5])]:
            result = self.keyboard()
            result["button"]["focus"][-1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify_quit(self.log, result, keyboard=True)

    def test_partial_space_missing_tab_or_unprotected_password_fails(self):
        for action in ("partial", "missing", "wrong-key", "wrong-field"):
            result = self.keyboard()
            button = result["button"]
            if action == "partial":
                button["keys"][-1]["events"] = 1
            elif action == "missing":
                button["keys"].pop(0)
            elif action == "wrong-key":
                button["keys"][-1]["key"] = "Enter"
            else:
                button["focus"][1]["isPassword"] = False
            with self.subTest(action=action), self.assertRaises(ValueError):
                verify_quit(self.log, result, keyboard=True)


if __name__ == "__main__":
    unittest.main()
