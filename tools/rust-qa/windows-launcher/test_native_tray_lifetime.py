"""Check ordered notification-icon ownership against a separately held synthetic Shell process."""
from contextlib import ExitStack
import ctypes as c
import unittest
from unittest.mock import Mock, patch

import native_tray as tray
from test_native_tray import KEY, TOKEN, closed, registration

PRIMARY = "LAUNCHER_PRIMARY pid=18\n"
BIND = "TRAY_BIND phase=recreate pid=18 hwnd=43 id=23 shell_pid=81 shell_hwnd=51 verified=1\n"
RETIRED = ("gui_tray.shutdown=false\nTRAY_RETIRED pid=18 hwnd=43 id=23 shell_pid=81 shell_hwnd=51\n"
           "TRAY_CLEANUP pid=18 hwnd=43 id=23 registered=1 removed=0\nDRAINED passes=2\n")
WITHDRAW = "gui_tray.existing.version4=false\ngui_tray.existing.withdraw=true\n"


def attempt(phase, added, version):
    truth = lambda value: str(value).lower()
    return (f"gui_tray.{phase}.add={truth(added)}\n"
            + (f"gui_tray.{phase}.version4={truth(version)}\n" + BIND.replace("phase=recreate", "phase=" + phase)
               if added else "")
            + f"TRAY_REGISTER phase={phase} pid=18 hwnd=43 id=23 token={TOKEN} added={int(added)} version4={int(version)}\n"
            + ("gui_tray.incompatible_version=true\n" if added and not version else ""))


class NativeLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.bar, self.shell, self.shell_pid, self.shell_wait = 51, 50, 81, 258
        self.hresult, self.receiver_reused = -1, False
        self.stack = self.enterContext(ExitStack())
        self.api, self.desk, self.proc = Mock(), Mock(), Mock(pid=18)
        self.proc.poll.return_value = 0
        self.api.wait_job_empty.return_value = True
        self.desk.thread.return_value, self.desk.thread_desktop.return_value, self.desk.station.return_value = 1, 71, 72
        self.desk.name.side_effect = lambda handle: {71: "Default", 72: "WinSta0"}[handle]
        self.desk.shell.side_effect = lambda: self.shell
        self.desk.window.return_value = dict(tid=2, pid=18, **{"class": "IFW RW02 synthetic tray receiver"})

        def owner(hwnd, pid):
            if hwnd == 43:
                pid._obj.value = 90 if self.receiver_reused else 0
                return 9 if self.receiver_reused else 0
            pid._obj.value = self.shell_pid
            return 7 if self.shell_pid else 0
        self.desk.owner.side_effect = owner
        self.api.open.return_value = 717
        self.api.close.return_value = True
        self.wait = Mock(side_effect=lambda handle, timeout: self.shell_wait if (handle, timeout) == (717, 0) else -1)
        self.find = Mock(side_effect=lambda name, title: self.bar if (name, title) == ("Shell_TrayWnd", None) else None)
        self.stack.enter_context(patch.object(c, "WinDLL", create=True))
        self.stack.enter_context(patch.object(tray, "bind", side_effect=lambda _, name, *_args: {
            "WaitForSingleObject": self.wait, "FindWindowW": self.find}[name]))
        self.stack.enter_context(patch.object(tray, "shell_rect", side_effect=self.rect))
        self.probe = tray.NativeTray(self.api, self.desk, "Default", TOKEN)
        self.report = {}

    def rect(self, hwnd):
        self.assertEqual(hwnd, 43)
        return dict(hresult=self.hresult, rect=None)

    def bracket(self):
        self.probe.watch_original(self.stack, self.report)
        self.api.open.assert_called_once_with(0x100000, False, 81)
        evidence = self.probe.registration(self.proc, lambda: registration(True), lambda get, _: get(),
                                            self.report, no_host=False)
        self.assertEqual(evidence, KEY)

    def gone(self):
        self.shell_wait, self.bar, self.shell = 0, 0, 0

    def drain(self, tail):
        log = PRIMARY + registration(True) + tail
        self.probe.check_drain(self.proc, 1, log, self.report)
        return self.report["nativeShutdown"]

    def test_genuine_withdrawal_is_ordered_before_a_refused_or_acknowledged_replacement(self):
        for rest, final, method in [(attempt("recreate", False, False), closed(False), "withdrawnBeforeQuit"),
                                    (attempt("recreate", True, True), closed(True), "deletedAtQuit"),
                                    (attempt("recreate", True, False), closed(False), "withdrawnBeforeQuit")]:
            with self.subTest(method=method, rest=rest):
                report = self.drain(WITHDRAW + rest + final)
                self.assertEqual(report["cleanupMethod"], method)
                self.assertEqual(report["withdrawals"][0], "existing.withdraw")
                self.assertFalse(report["stableRegistration"])
        for invalid in [WITHDRAW + closed(False),
                        "gui_tray.existing.withdraw=true\n" + attempt("retry", False, False) + closed(False),
                        WITHDRAW + attempt("recreate", True, True) + closed(False),
                        WITHDRAW + attempt("retry", False, False) + closed(True),
                        attempt("retry", False, False) + closed(False),
                        attempt("retry", False, False) + closed(True),
                        attempt("recreate", True, False) + closed(False),
                        WITHDRAW + attempt("retry", True, True).replace("id=23", "id=27") + closed(True),
                        closed(True) + WITHDRAW]:
            with self.subTest(invalid=invalid), self.assertRaises(tray.CleanupUnconfirmed):
                self.drain(invalid)

    def test_original_process_signaled_and_both_shell_windows_and_exact_icon_gone_confirms_retirement_only(self):
        self.bracket()
        self.gone()
        report = self.drain(RETIRED)
        self.assertEqual(report["cleanup"][0][-2:], ("1", "0"))
        self.assertEqual(report["hostExitReadback"]["wait"], 0)
        self.assertEqual(report["cleanupMethod"], "originalShellExited")
        self.assertFalse(report["stableRegistration"])
        with self.assertRaises(tray.Unavailable):
            self.probe.qualify_quiet_shell("", self.report, no_host=False)
        self.stack.close()
        self.api.close.assert_called_once_with(717)

    def test_refused_v4_withdrawal_keeps_the_icon_outstanding_until_confirmed_cleanup(self):
        refused = attempt("initial", True, False).replace("incompatible_version=true", "incompatible_version=false")
        retry = "gui_tray.existing.version4=true\n" + BIND.replace("phase=recreate", "phase=retry")
        for recovery in ("", retry):
            with self.subTest(recovery=recovery):
                self.probe.check_drain(self.proc, 1, PRIMARY + refused + recovery + closed(True), self.report)
                report = self.report["nativeShutdown"]
                self.assertEqual(report["cleanupMethod"], "deletedAtQuit")
                self.assertEqual(report["withdrawals"], [])
                self.assertFalse(report["stableRegistration"])
        for invalid in (closed(False), attempt("retry", False, False) + closed(True), RETIRED):
            with self.subTest(invalid=invalid), self.assertRaises(tray.CleanupUnconfirmed):
                self.probe.check_drain(self.proc, 1, PRIMARY + refused + invalid, self.report)

    def test_live_unpinned_or_superseded_handle_cannot_certify_a_failed_delete(self):
        self.gone()
        with self.assertRaises(tray.CleanupUnconfirmed):
            self.drain(RETIRED)
        self.assertNotIn("cleanupMethod", self.report["nativeShutdown"])
        self.bar, self.shell, self.shell_wait = 51, 50, 258
        self.bracket()
        # An extant taskbar with an unreadable owner is still an extant window.
        for state in [(0, 0, 258, 81, -1), (0, 0, 0xffffffff, 81, -1), (51, 0, 0, 0, -1),
                      (0, 50, 0, 81, -1), (0, 0, 0, 81, 0), (0, 0, 0, 81, 1)]:
            self.bar, self.shell, self.shell_wait, self.shell_pid, self.hresult = state
            with self.subTest(state=state), self.assertRaises(tray.CleanupUnconfirmed):
                self.drain(RETIRED)
        self.hresult = -1
        self.gone()
        for invalid in [RETIRED.replace("shell_pid=81", "shell_pid=82"),
                        RETIRED.replace("hwnd=43", "hwnd=44"), RETIRED.replace("removed=0", "removed=1"),
                        "gui_tray.existing.version4=true\n" + BIND + RETIRED,
                        "gui_tray.existing.version4=true\n" + BIND.replace("shell_pid=81 shell_hwnd=51 verified=1",
                                                                           "shell_pid=0 shell_hwnd=0 verified=0") + RETIRED,
                        WITHDRAW + attempt("retry", True, True) + RETIRED,
                        "gui_tray.change=true\n" + RETIRED, RETIRED + "gui_tray.cleanup_retry=true\n"]:
            with self.subTest(invalid=invalid), self.assertRaises(tray.CleanupUnconfirmed):
                self.drain(invalid)
        self.receiver_reused = True
        with self.assertRaises(tray.CleanupUnconfirmed):
            self.drain(RETIRED)

    def test_returning_after_ack_without_the_original_process_does_not_establish_a_witness(self):
        self.probe.watch_original(self.stack, self.report)
        self.gone()  # The matching initial stdout cannot retrospectively bracket the registration.
        with self.assertRaises(tray.Unavailable):
            self.probe.registration(self.proc, lambda: registration(True), lambda fn, _: fn(), self.report, no_host=False)
        self.assertFalse(self.report["shellWitness"]["initialBindingConfirmed"])
        with self.assertRaises(tray.CleanupUnconfirmed):
            self.drain(RETIRED)


if __name__ == "__main__":
    unittest.main()
