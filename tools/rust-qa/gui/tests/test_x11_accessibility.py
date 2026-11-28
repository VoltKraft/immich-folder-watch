"""Regression checks for native X11 accessibility snapshots and transient AT-SPI errors."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

GUI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GUI), str(GUI.parent / "performance")]

import desktop_input as ui

MESSAGE = "Unknown interface 'org.a11y.atspi.Accessible'"


def node(role, name, pid, children=()):
    obj = Mock()
    obj.get_role.return_value = role
    obj.get_role_name.return_value = role.value_nick
    obj.get_name.return_value = name
    obj.get_process_id.return_value = pid
    obj.get_child_count.return_value = len(children)
    obj.get_child_at_index.side_effect = children.__getitem__
    obj.get_state_set.return_value.contains.return_value = False
    obj.get_text_iface.return_value = None
    return obj


class X11TreeTests(unittest.TestCase):
    def test_editor_message_locale_is_private_and_preserves_the_input_method(self):
        desktop = {"LANG": "C.UTF-8", "LC_ALL": "en_US.UTF-8", "XMODIFIERS": "@im=ibus"}
        with patch.dict(os.environ, desktop, clear=True):
            child = ui.german_editor_env()
            self.assertEqual(dict(os.environ), desktop)
        self.assertEqual(child, {"LANG": "C.UTF-8", "LC_MESSAGES": "de_DE.UTF-8", "XMODIFIERS": "@im=ibus"})

    def test_disappearing_child_restarts_from_desktop_and_retains_the_actual_target_field(self):
        stale = Mock()
        stale.get_role.side_effect = ui.GLib.Error(MESSAGE, "atspi_error", 1)
        field = node(ui.Atspi.Role.ENTRY, "Dateiname", 120)
        field.get_state_set.return_value.contains.return_value = True
        field.get_text_iface.return_value = field
        target = node(ui.Atspi.Role.APPLICATION, "native-gui-assessment", 120, [field])
        foreign = node(ui.Atspi.Role.APPLICATION, "unrelated", 148, [node(ui.Atspi.Role.ENTRY, "Dateiname", 148)])
        first = node(ui.Atspi.Role.DESKTOP_FRAME, "main", 101, [stale, target])
        fresh = node(ui.Atspi.Role.DESKTOP_FRAME, "main", 101, [foreign, target])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            with (patch.object(ui.Atspi, "get_desktop", side_effect=[first, fresh]) as get_desktop,
                  patch.object(ui.Atspi.Text, "get_text", return_value="Grüße – Sommer.jpg") as get_text,
                  patch.object(ui, "Path", return_value=path), patch.object(ui.time, "sleep") as sleep):
                snapshot = ui.filename_snapshot(lambda: ui.read_x11_tree(120))
            self.assertEqual(get_desktop.call_count, 2)
            sleep.assert_called_once_with(.05)
            foreign.get_child_at_index.assert_not_called()
            get_text.assert_called_once_with(field, 0, -1)
            self.assertEqual(snapshot[-1], {"name": "Dateiname", "role": "entry", "focused": True,
                                            "text": "Grüße – Sommer.jpg"})
            self.assertEqual(json.loads(path.read_bytes()), snapshot)

    def test_only_the_observed_domain_code_and_interface_are_retryable(self):
        for message, domain, code in ((MESSAGE, "g-dbus-error-quark", 1), (MESSAGE, "atspi_error", 2),
                                      ("Unknown interface 'org.a11y.atspi.Text'", "atspi_error", 1),
                                      ("Connection closed", "atspi_error", 1)):
            error = ui.GLib.Error(message, domain, code)
            with (self.subTest(message=message, domain=domain, code=code),
                  patch.object(ui, "read_tree", side_effect=error) as read, patch.object(ui.time, "sleep") as sleep,
                  self.assertRaises(ui.GLib.Error) as raised):
                ui.read_x11_tree(120)
            self.assertIs(raised.exception, error)
            read.assert_called_once_with(120, False)
            sleep.assert_not_called()

    def test_persistent_stale_node_and_absent_or_mislabelled_filename_do_not_pass(self):
        error = ui.GLib.Error(MESSAGE, "atspi_error", 1)
        with (patch.object(ui, "read_tree", side_effect=error) as read, patch.object(ui.time, "sleep") as sleep,
              self.assertRaises(ui.GLib.Error) as raised):
            ui.read_x11_tree(120)
        self.assertIs(raised.exception, error)
        self.assertEqual(read.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        for tree in ([], [{"name": "Dateiname", "role": "label"}], [{"name": "other", "role": "entry"}]):
            self.assertIsNone(ui.filename_snapshot(lambda: tree))
