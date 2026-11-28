"""Controls for an actual GNOME notification on the private screen and bus."""
import json
from pathlib import Path
import tempfile
import unittest

from notification_pixels import BODY, TITLE, check_text
from notification_readback import APP, calls, verify


class NotificationTest(unittest.TestCase):
    def setUp(self):
        self.samples = {'before-notification': 'Nov 20 22:59', 'notification': f'Clear {TITLE} {BODY}',
                        'withdrawn': 'Clear No Notifications'}
        route = ('method call time=1 sender=:1.10 -> destination=:1.4 serial=1 path=/org/gtk/Notifications; '
                 'interface=org.gtk.Notifications; member=')
        args = f'\n   string "{APP}"\n   string "native-test"\n'
        self.add = route + 'AddNotification' + args + (
            f'array [ dict entry( string "title" variant string "{TITLE}" ) '
            f'dict entry( string "body" variant string "{BODY}" ) ]\n')
        self.remove = route + 'RemoveNotification' + args

    def test_accepts_observed_message_and_open_list_after_withdrawal(self):
        check_text(self.samples)
        self.assertEqual(calls(self.add + self.remove, (':1.10',), ':1.4'), ':1.10')

    def test_accepts_a_separate_system_message_on_the_private_bus(self):
        trace = self.add + self.add.replace(APP, 'org.example.Other') + self.remove
        self.assertEqual(calls(trace, (':1.10',), ':1.4'), ':1.10')

    def test_rejects_blank_withdrawal_or_wrong_text(self):
        for stage, value in (('notification', 'Clear ' + TITLE), ('withdrawn', ''),
                             ('before-notification', TITLE), ('withdrawn', BODY),
                             ('withdrawn', 'Nov 20 22:59')):
            with self.subTest(stage=stage, value=value), self.assertRaises(ValueError):
                check_text(dict(self.samples, **{stage: value}))

    def test_rejects_wrong_provider_content_or_order(self):
        traces = (self.add + self.remove.replace(':1.10', ':1.9'), self.add + self.remove.replace(':1.4', ':1.3'),
                  self.remove + self.add, self.add + self.remove.replace('native-test', 'other'),
                  self.add.replace('string "title"', 'string "label"') + self.remove,
                  self.add.replace(BODY, TITLE) + self.remove, self.add + self.add + self.remove)
        for trace in traces:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                calls(trace, (':1.10',), ':1.4')

    def test_rejects_incomplete_host_and_empty_source_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'results.json').write_text('{}')
            inputs = dict(revision='f' * 40, run='111', attempt='1')
            args = folder, folder / 'sender', 'aarch64', inputs['revision'], '111', '1'
            (folder / 'inputs.json').write_text(json.dumps(inputs))
            with self.assertRaisesRegex(ValueError, 'host identity'):
                verify(*args)
            inputs['host'] = dict(architecture='aarch64', kernel='test', distribution='ubuntu',
                                  version='24.04', host_match_key='a' * 64)
            inputs.update(build={'sources': {}}, drivers={})
            (folder / 'inputs.json').write_text(json.dumps(inputs))
            with self.assertRaisesRegex(ValueError, 'observation sources'):
                verify(*args)


if __name__ == '__main__':
    unittest.main()
