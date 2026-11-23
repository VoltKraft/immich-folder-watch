"""Model the observed foreign-thread denial while exercising real HWND qualification and rejection paths."""
import ctypes as c
import os
import unittest
from unittest.mock import Mock, patch

import native_tray
import window_readback as readback


class PrivateWindows:
    def __init__(self):
        self.name = "IfwQa_Tray_" + "7" * 32
        self.desktop, self.anchor, self.gui, self.receiver = 91, 75, 86, 87
        self.pid, self.tid, self.receiver_tid, self.observer_tid = 305, 306, 307, 310
        self.title, self.creation = "Desktop input probe", 134398656810877460
        self.denied, self.foreign_handle = {"win32Error": 5}, 0
        self.proc = Mock(pid=self.pid, _handle=105)
        self.proc.poll.return_value = None
        self.api, self.desk, self.windows = Mock(), Mock(), Mock()
        self.api.process_identity.return_value = self.creation
        self.desk.thread.return_value = self.observer_tid
        self.desk.receiving_input.return_value = False
        self.desk.thread_desktop.side_effect = lambda tid: self.desktop if tid == self.observer_tid else self.foreign_handle
        self.desk.name.side_effect = lambda handle: self.name if handle == self.desktop else self.denied
        self.windows.pid, self.windows.desktop = self.pid, self.desktop
        self.windows.enum_callback = lambda f: f
        self.handles = [self.anchor, self.gui, self.receiver]
        self.owners = {self.anchor: (os.getpid(), self.observer_tid), self.gui: (self.pid, self.tid),
                       self.receiver: (self.pid, self.receiver_tid)}
        self.names = {self.anchor: self.name, self.gui: self.title, self.receiver: readback.RECEIVER_CLASS}
        self.classes = {self.anchor: "Static", self.gui: readback.ROOT_CLASS, self.receiver: readback.RECEIVER_CLASS}
        self.shown = {self.gui}
        self.after_enum = lambda: None
        self.record = {}
        self.windows.enumerate.side_effect = self.enumerate
        self.windows.owner.side_effect = self.owner
        self.windows.caption.side_effect = lambda hwnd, buf, n: self.read_text(self.names[hwnd], buf, n)
        self.desk.window_class.side_effect = lambda hwnd, buf, n: self.read_text(self.classes[hwnd], buf, n)
        self.windows.is_visible.side_effect = self.shown.__contains__
        self.desk.visible.side_effect = self.shown.__contains__
        self.desk.iconic.return_value = False
        self.desk.window.side_effect = lambda hwnd: dict(hwnd=hex(hwnd), pid=self.owners[hwnd][0],
            tid=self.owners[hwnd][1], rect=[1, 1, 150, 99], **{"class": self.classes[hwnd]})

    def bind(self):
        return readback.PrivateMembership(self.desk, self.windows, self.name, self.desktop, self.anchor,
                                          self.proc, self.tid, self.creation, self.api, self.title, self.record)

    def owner(self, hwnd, pid):
        pid._obj.value, tid = self.owners[hwnd]
        return tid

    def enumerate(self, desktop, visit, _):
        if not desktop or desktop != self.desktop:
            raise AssertionError("The enumeration did not use the original private desktop handle")
        for hwnd in self.handles:
            if not visit(hwnd, 0):
                raise AssertionError("The HWND enumeration stopped early")
        self.after_enum()
        return True

    @staticmethod
    def read_text(value, buf, size):
        buf.value = value[:size-1]
        return len(buf.value.encode("utf-16-le")) // 2


class PrivateMembershipTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(c, "set_last_error", create=True))
        self.enterContext(patch.object(c, "get_last_error", return_value=0, create=True))

    def test_exact_held_desktop_enumeration_preserves_both_forms_of_foreign_denial_and_the_name_if_available(self):
        for handle, name_available in ((0, False), (102, False), (91, True)):
            with self.subTest(handle=handle):
                world = PrivateWindows()
                world.foreign_handle = handle
                subject = world.bind()
                target = subject.verify(world.gui, "ready", visible=True)
                self.assertEqual(target["desktop"], world.name if name_available else {"win32Error": 5})
                self.assertEqual(target["threadDesktopHandleReturned"], bool(handle))
                self.assertTrue(world.record["ready"]["qualified"])
                self.assertEqual(world.record["ready"]["enumerated"], {"witness": 1, "target": 1})
                self.assertEqual(world.record["ready"]["after"]["witness"]["pid"], os.getpid())
                self.assertEqual(world.record["ready"]["beforeProcess"], world.record["ready"]["afterProcess"])
                self.assertEqual(world.windows.enumerate.call_args.args[0], world.desktop)
                # The private surface still needs the same live, visible, non-minimized HWND.
                world.desk.attribute.return_value = 0
                output = {}
                readback.visible_surface(world.desk, world.name, world.pid, world.gui, output, "surface", private=subject)
                self.assertEqual(output["surface"]["tid"], world.tid)
                world.desk.iconic.return_value = True
                with self.assertRaisesRegex(ValueError, "non-minimized"):
                    readback.visible_surface(world.desk, world.name, world.pid, world.gui, {}, "surface", private=subject)

    def test_rejects_missing_and_duplicate_target_or_witness_and_native_enumeration_failure(self):
        for which in ("anchor", "gui"):
            for duplicate in (False, True):
                with self.subTest(which=which, duplicate=duplicate):
                    world = PrivateWindows()
                    hwnd = getattr(world, which)
                    (world.handles.append if duplicate else world.handles.remove)(hwnd)
                    with self.assertRaisesRegex(ValueError, "enumerate the unique"):
                        world.bind().verify(world.gui, "ready", visible=True)
                    self.assertFalse(world.record["ready"]["qualified"])
        world = PrivateWindows()
        world.windows.enumerate.side_effect = None
        world.windows.enumerate.return_value = False
        with self.assertRaisesRegex(OSError, "EnumDesktopWindows"):
            world.bind().verify(world.gui, "ready")

    def test_rejects_the_wrong_desktop_and_other_os_errors_before_or_after_enumeration(self):
        for change in ("Default", {"win32Error": 6}, {"win32Error": 0}, None):
            for late in (False, True):
                with self.subTest(observed=change, late=late):
                    world = PrivateWindows()
                    if late:
                        world.after_enum = lambda: setattr(world, "denied", change)
                    else:
                        world.denied = change
                    with self.assertRaisesRegex(ValueError, "thread desktop"):
                        world.bind().verify(world.gui, "ready")
                    self.assertEqual(world.record["ready"]["after"]["target"]["desktop"], change)
        world = PrivateWindows()
        with self.assertRaisesRegex(ValueError, "original primary"):
            readback.visible_surface(world.desk, "Default", world.pid, world.gui, {}, "surface")
        with self.assertRaisesRegex(ValueError, "different subjects"):
            readback.visible_surface(world.desk, "Default", world.pid, world.gui, {}, "surface", private=world.bind())

    def test_snapshot_denial_is_preserved_but_other_errors_and_contradictory_names_fail(self):
        name = PrivateWindows().name
        accepted = {"desktop": name, "witnessSeen": True, "initialThreadDesktop": {"win32Error": 5},
                    "windows": [{"desktop": {"win32Error": 5}, "windowClass": readback.ROOT_CLASS}]}
        self.assertIsNone(readback.check_private_snapshot(accepted, name))
        for changes in (dict(witnessSeen=False), dict(desktop="Default"), dict(initialThreadDesktop="Default"),
                        dict(initialThreadDesktop={"win32Error": 6}),
                        dict(windows=[{"desktop": "Default", "windowClass": "Winit Thread Event Target"}]),
                        dict(windows=[{"desktop": {"win32Error": 6}, "windowClass": readback.RECEIVER_CLASS}])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                readback.check_private_snapshot(accepted | changes, name)

    def test_checks_bound_process_liveness_and_creation_at_both_ends(self):
        for sequence in ([91, 91], [None, 91], [None, None]):
            with self.subTest(sequence=sequence):
                world = PrivateWindows()
                world.proc.poll.side_effect = sequence
                if sequence == [None, None]:
                    world.api.process_identity.side_effect = [world.creation, world.creation + 1]
                with self.assertRaises(ValueError):
                    world.bind().verify(world.gui, "ready")
                self.assertFalse(world.record["ready"]["qualified"])

    def test_rejects_wrong_target_and_witness_identity_even_when_both_handles_were_enumerated(self):
        for obj, field in (("gui", "pid"), ("gui", "tid"), ("gui", "title"), ("gui", "class"), ("gui", "visible"),
                           ("anchor", "pid"), ("anchor", "tid"), ("anchor", "title"), ("anchor", "class"),
                           ("anchor", "visible")):
            with self.subTest(object=obj, field=field):
                world = PrivateWindows()
                hwnd = getattr(world, obj)
                def replace():
                    if field == "pid":
                        world.owners[hwnd] = (world.pid + 82, world.owners[hwnd][1])
                    elif field == "tid":
                        world.owners[hwnd] = (world.owners[hwnd][0], 2020)
                    elif field == "title":
                        world.names[hwnd] += " – 別"
                    elif field == "class":
                        world.classes[hwnd] += " helper"
                    else:
                        world.shown.symmetric_difference_update({hwnd})
                world.after_enum = replace
                with self.assertRaisesRegex(ValueError, "identity"):
                    world.bind().verify(world.gui, "ready", visible=True)
                self.assertEqual(world.record["ready"]["enumerated"], {"witness": 1, "target": 1})

    def test_refuses_default_null_desktop_unowned_or_input_desktop_and_null_witness(self):
        for change in ("Default", "nullDesktop", "otherHandle", "noWitness", "input"):
            with self.subTest(change=change):
                world = PrivateWindows()
                if change == "Default":
                    world.name = change
                elif change == "nullDesktop":
                    world.windows.desktop = world.desktop = 0
                elif change == "otherHandle":
                    world.windows.desktop += 1
                elif change == "noWitness":
                    world.anchor = 0
                else:
                    world.desk.receiving_input.return_value = True
                with self.assertRaises(ValueError):
                    world.bind().verify(world.gui, "ready")
                world.windows.enumerate.assert_not_called()
        world = PrivateWindows()
        world.desk.receiving_input.side_effect = [False, True]
        with self.assertRaisesRegex(ValueError, "selected desktop changed"):
            world.bind().verify(world.gui, "ready")

    def test_private_registration_requires_its_hidden_receiver_on_the_same_held_desktop(self):
        for defect in (None, "absent", "visible", "wrongTitle", "otherThread", "wrongDesktop"):
            with self.subTest(defect=defect):
                world = PrivateWindows()
                pid, hwnd = world.pid, world.receiver
                token = "7" * 32
                log = ("gui_tray.initial.add=false\n"
                       f"TRAY_REGISTER phase=initial pid={pid} hwnd={hwnd} id=23 token={token} added=0 version4=0\n")
                probe = native_tray.NativeTray(world.api, world.desk, world.name, token)
                if defect == "absent":
                    world.handles.remove(hwnd)
                elif defect == "visible":
                    world.shown.add(hwnd)
                elif defect == "wrongTitle":
                    world.names[hwnd] += " other"
                elif defect == "otherThread":
                    world.after_enum = lambda: world.owners.update({hwnd: (pid, world.receiver_tid + 1)})
                elif defect == "wrongDesktop":
                    world.denied = "Default"
                with patch.object(native_tray, "shell_rect", return_value={"hresult": -1, "rect": None}) as rect:
                    receipt = {}
                    def register():
                        return probe.registration(world.proc, lambda: log, lambda fn, _: fn(), receipt,
                                                  no_host=True, private=world.bind())
                    if defect:
                        with self.assertRaises(ValueError):
                            register()
                        rect.assert_not_called()
                    else:
                        self.assertEqual(register(), (str(pid), str(hwnd), "23"))
                        self.assertEqual(receipt["registration"]["desktop"], {"win32Error": 5})
                        target = world.record["trayReceiver"]["after"]["target"]
                        self.assertEqual((target["tid"], target["visible"]), (world.receiver_tid, False))
                        world.desk.attribute.return_value = 0
                        private = world.bind()
                        probe.visible_window(world.proc, world.gui, receipt, "fallbackWindow", private=private)
                        self.assertTrue(world.record["fallbackWindow.receiver"]["qualified"])
                        world.handles.remove(hwnd)
                        with self.assertRaisesRegex(ValueError, "unique witness"):
                            probe.visible_window(world.proc, world.gui, receipt, "activatedWindow", private=private)


if __name__ == "__main__":
    unittest.main()
