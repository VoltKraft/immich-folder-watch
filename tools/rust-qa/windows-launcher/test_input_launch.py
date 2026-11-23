"""Controls for the gesture, foreground caller and retained-window outcome on any build host."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import input_launch
import input_gesture
from input_gesture import DOWN, UP, F24, InputUnavailable, KeyWindow, accept_key


def event(msg, **changes):
    row = dict(hwnd=51, vk=F24, message=msg, time=701, repeats=1, previous=int(msg == UP), released=int(msg == UP),
               extra=912, dispatchThread=103)
    return {**row, **changes}


def completed():
    return dict(stage="drained", secondaryLaunch=dict(api="CreateProcessW", source="foreground-key-handler", callerPid=17),
                secondaryPid=21, secondaryCreation100ns=823, initialWindow=52, reopenedWindow=52,
                foregroundHandoff=dict(grant="granted", requestAccepted=True), foregroundObservation=dict(observed=True),
                keyboardFocus=dict(observed=True, lastSample=dict(foreground=True, active=True, focused=True)),
                inputGesture=dict(hwnd=51, callerPid=17, callerThread=103, marker=912, keys=[event(DOWN), event(UP)],
                                  beforeQueue=dict(owner=True, privateInput=True, foreground=True, focus=True, visible=True,
                                                   centerOwned=True, foregroundAfter=True),
                                  beforeCreate=dict(hwnd=51, thread=103, tick=710),
                                  created=dict(pid=21, creation100ns=823, parentPid=17, parentCreation100ns=433,
                                               image="native-gui-assessment.exe", foreground=51, tick=712),
                                  queued=2, windowDestroyed=True))


class InputLaunchTests(unittest.TestCase):
    def test_keyboard_target_or_modifier_change_never_submits_input_or_starts_the_secondary(self):
        for target, modifier in (([False], 0), ([True, False], 0), ([True], -32768)):
            with self.subTest(target=target, modifier=modifier):
                window = KeyWindow.__new__(KeyWindow)
                window.owned_input, window.key_state, window.send = Mock(side_effect=target), Mock(return_value=modifier), Mock()
                window.marker = 19
                create = Mock()
                with patch.object(input_gesture.c, "sizeof", return_value=40), self.assertRaises(InputUnavailable):
                    window.launch(create)
                create.assert_not_called()
                window.send.assert_not_called()

    def test_one_tagged_queue_transition_required_for_election(self):
        valid = []
        self.assertFalse(accept_key(valid, 51, 912, event(DOWN)))
        self.assertTrue(accept_key(valid, 51, 912, event(UP)))
        for initial, row in (([], event(UP)), (valid, event(UP)), ([], event(DOWN, previous=1)),
                             ([], event(DOWN, repeats=3)), ([], event(DOWN, extra=0)),
                             ([], event(DOWN, hwnd=53)), ([event(DOWN)], event(UP, vk=0)),
                             ([event(DOWN)], event(UP, released=0))):
            with self.subTest(row=row), self.assertRaises(ValueError):
                accept_key(list(initial), 51, 912, row)

    def test_held_caller_checks_immediately_bracket_process_creation(self):
        key = KeyWindow.__new__(KeyWindow)
        key.hwnd, key.pid, key.desk = 51, 17, Mock()
        key.desk.thread.return_value = 103
        key.owned_input = Mock(return_value=True)
        key.clock = Mock(side_effect=(710, 712))
        key.record = dict(keys=[event(DOWN), event(UP)])
        api, proc, exe = Mock(), Mock(), Mock()
        proc.pid, proc._handle, exe.name = 21, 33, "native-gui-assessment.exe"
        api.processes.return_value = {21: (17, exe.name)}
        api.process_identity.side_effect = (823, 433)
        key.before_create()
        key.observe_child(api, proc, exe)
        expected = completed()["inputGesture"]
        self.assertEqual(key.record["beforeCreate"], expected["beforeCreate"])
        self.assertEqual(key.record["created"], expected["created"])
        for foreground, parent in ((True, 99), (False, 17)):
            with self.subTest(foreground=foreground, parent=parent):
                key.owned_input.return_value = foreground
                api.processes.return_value[21] = (parent, exe.name)
                with self.assertRaises(ValueError):
                    key.observe_child(api, proc, exe)
        with self.assertRaises(ValueError):
            key.before_create()

    def test_receipt_rejects_observer_launch_or_foreign_focus_or_worker(self):
        current = completed()
        input_launch.check_handoff(current, 17)
        for nested, field, value in (
                ("secondaryLaunch", "source", "observer"), ("inputGesture", "windowDestroyed", False),
                ("keyboardFocus.lastSample", "focused", False), ("inputGesture.created", "foreground", 52),
                ("inputGesture.beforeCreate", "tick", 800), ("inputGesture.beforeCreate", "thread", 111),
                ("inputGesture.created", "creation100ns", 824), ("inputGesture.created", "parentPid", 18),
                ("inputGesture", "queued", 1), ("inputGesture", "marker", 913),
                ("inputGesture.beforeQueue", "centerOwned", False),
                ("inputGesture", "keys", [event(DOWN), event(UP, dispatchThread=99)]),
                ("foregroundHandoff", "grant", "denied"), ("foregroundHandoff", "requestAccepted", False),
                ("foregroundObservation", "observed", False), ("", "reopenedWindow", 53)):
            copy = deepcopy(current)
            row = copy
            for part in filter(None, nested.split(".")):
                row = row[part]
            row[field] = value
            with self.subTest(nested=nested, field=field), self.assertRaises(ValueError):
                input_launch.check_handoff(copy, 17)

    def test_only_the_original_retained_build_qualifies(self):
        ordinary = dict(subject="retained", revision="r", target="x", run="2", attempt="1", gui="g",
                        buildReceipt="b", graph="d", lock="l")
        input_launch.check_build("x", ordinary, ordinary)
        for field in ordinary:
            with self.subTest(field=field), self.assertRaises(ValueError):
                input_launch.check_build("x", {**ordinary, field: "different"}, ordinary)


if __name__ == "__main__":
    unittest.main()
