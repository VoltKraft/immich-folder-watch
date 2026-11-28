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


if __name__ == "__main__":
    unittest.main()
