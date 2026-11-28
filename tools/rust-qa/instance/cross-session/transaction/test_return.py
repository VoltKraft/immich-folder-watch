"""Keep the observed value and its owner bound to the restored WPF."""
import unittest
from replay_return import verify_ui
from rust_return import ALBUM


class ProfileReadbackTests(unittest.TestCase):
    def test_accepts_only_the_edited_value_on_the_original_window(self):
        wpf = {'token': {'pid': 45, 'created100ns': 80, 'sessionId': 2}, 'window': {'window': 63}}
        ui = {'pid': 45, 'fieldPid': 45, 'created': 80, 'session': 2, 'hwnd': 63,
              'image': r'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe',
              'windowName': 'Immich Folder Watch', 'sourceSha256': 'source', 'status': 'read',
              'sourceCount': 1, 'label': 'Immich-Albumname', 'album': ALBUM, 'runtimeId': [1, 83]}
        verify_ui(ui, wpf, 'source')
        for change in ({'fieldPid': 46}, {'created': 81}, {'hwnd': 62}, {'session': 1}, {'album': ''},
                       {'album': 'Pictures'}, {'sourceCount': 0}, {'sourceSha256': 'other'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_ui({**ui, **change}, wpf, 'source')


if __name__ == '__main__':
    unittest.main()
