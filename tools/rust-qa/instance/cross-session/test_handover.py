"""Reject premature takeover, substituted menu owners and shutdown evidence from before Quit."""
from copy import deepcopy
import unittest

from handover_receipts import FLUSH, QUIT_SOURCE, START, STOP, ordered, shutdown


class HandoverTest(unittest.TestCase):
    def setUp(self):
        self.start = dict(pid=11, created100ns=100, hwnd=70, receiver=135, tid=150, issuedNs=200)
        self.end = dict(pid=11, created100ns=100, exit100ns=300, exitCode=0, exitedNs=220, method='shipping tray Quit')
        point = dict(x=301, y=172)
        hit = dict(hwnd=70, root=70, pid=11, tid=150, rootPid=11, rootTid=150)
        self.menu = dict(pid=11, created=100, root=70, receiver=135, tid=150, status='invoked', stage='original-close',
                         menuHwnd=170, sourceSha256=QUIT_SOURCE,
                         rawInteraction='tray-menu-quit; popup=170; verifiedHighlightedCommandId=3; nativeMouseClick',
                         anchor=dict(dpiContext='per-monitor-v2', clientRect=dict(left=1, top=22, right=401, bottom=222),
                                     point=point, before=hit, after=hit, cursor=point, physicalCursor=point, probes=[hit]))
        self.logs = {'20261128.log': ''.join('2026-11-28 01:23:00.000 +00:00 [Information] '
                     'ImmichFolderWatch.Core.Services.FolderWatchWorker: ' + msg + '\n' for msg in (START, STOP, FLUSH)).encode()}
        self.console = ''.join('info: ImmichFolderWatch.Core.Services.FolderWatchWorker[0] ' + msg + '\n'
                               for msg in (STOP, FLUSH)).encode()
        config = dict(sha256='ab' * 32, volume=1, fileId=4, bytes=196)
        self.case = dict(installedWpf={'pid': 11, 'created100ns': 100}, ended=self.end, guard={'volume': '1', 'fileId': '9'},
                         pipeRefusalWin32=231, upload={'responseNs': 199}, originalConfig=config, configSha256=config['sha256'],
                         admitted=dict(endpoint=dict(pid=31, created100ns=310, sessionId=3),
                                       writer=dict(pid=43, created100ns=320), endpointNs=225, guardNs=230, releasedNs=243,
                                       guardExit=0, endpointExit=0, config=config.copy(), guard={'volume': '1', 'fileId': '9'}))
        self.streams = ('SESSION_MUTEX session=3 created=true\nPIPE_REFUSED code=Some(231)\nEXISTING_PIPE_SERVER pid=11\n',
                        'SESSION_MUTEX session=3 created=true\nRUST_PRIMARY\nRUST_RELEASED\n', 'WRITER_HELD\nWRITER_RELEASED\n')

    def test_retains_source_bound_menu_and_post_quit_engine_output(self):
        self.assertTrue(shutdown(self.start, self.end, self.menu, b'', self.console, self.logs)['shutdownSignal'])
        self.assertIsNone(ordered(self.case, *self.streams))

    def test_rejects_cleanup_exit_and_wrong_menu_or_earlier_log(self):
        for end, menu, before in (({**self.end, 'method': 'test-process termination'}, self.menu, b''),
                                  (self.end, {**self.menu, 'receiver': 132}, b''),
                                  (self.end, {**self.menu, 'sourceSha256': '00' * 32}, b''),
                                  (self.end, self.menu, self.console)):
            with self.subTest(end=end['method'], before=before, receiver=menu['receiver']):
                with self.assertRaises(ValueError):
                    shutdown(self.start, end, menu, before, self.console, self.logs)

    def test_refuses_admission_before_exit_and_changed_database_guard_or_config(self):
        for path, value in (('endpoint.created100ns', 295), ('guardNs', 218), ('guard.fileId', '44'),
                            ('config.fileId', 41), ('guardExit', 1)):
            modified = deepcopy(self.case)
            node = modified['admitted']
            keys = path.split('.')
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                ordered(modified, *self.streams)

    def test_rejects_incomplete_or_misattributed_rust_evidence(self):
        for index, value in enumerate(('PIPE_REFUSED code=Some(231)\n', 'RUST_PRIMARY\n', 'WRITER_HELD\n')):
            logs = list(self.streams)
            logs[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                ordered(self.case, *logs)


if __name__ == '__main__':
    unittest.main()
