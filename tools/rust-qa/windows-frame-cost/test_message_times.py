"""Controls for same-thread nested Win32 processing and the unknown part of the direct Show call."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import unittest

import message_times


class WindowMessages(unittest.TestCase):
    nodes = {4: dict(id=4, stage='show-call', arg=9),
             5: dict(id=5, stage='direct', parent=4, arg=5, tid=7, hwnd=9, start=100, end=200),
             6: dict(id=6, stage='show-call', arg=9),
             7: dict(id=7, stage='direct', parent=6, arg=4, tid=7, hwnd=9, start=240, end=270)}
    slow = [dict(action='reopen', issuedQpc=155, responseQpc=250)]
    rows = ['1 0 show 5 99 201', '2 1 wndproc 24 110 195', '3 2 default 24 135 190',
            '4 3 wndproc 71 150 180', '5 4 default 71 160 166', '6 1 wndproc 1024 197 198',
            '7 0 show 7 239 272']

    def replay(self, rows=None, header=None):
        rows = self.rows if rows is None else rows
        log = '\n'.join([header or f'WND_BEGIN 1 20 7 1000 {len(rows)} 0', *['WND '+r for r in rows], 'WND_END'])
        return message_times.analyze(log, self.nodes, 20, 7, 9, 1000, self.slow)

    def test_nested_default_processing_counts_each_tick_once_and_preserves_the_gap(self):
        result = self.replay()
        first, empty = result['shows']
        self.assertEqual((first['showTicks'], first['wndprocUnionTicks'], first['defaultProcTicks'],
                          first['wndprocOtherTicks'], first['outsideWndprocTicks']), (100, 86, 31, 55, 14))
        self.assertEqual(first['byMessage'], {'0x0018': {'wndprocOtherTicks': 30, 'defaultProcTicks': 25},
                                              '0x0047': {'wndprocOtherTicks': 24, 'defaultProcTicks': 6},
                                              'WM_USER_or_higher': {'wndprocOtherTicks': 1}})
        self.assertEqual((empty['messages'], empty['wndprocUnionTicks'], empty['outsideWndprocTicks']), (0, 0, 30))
        a, b = result['slowReopens'][0]['shows']
        self.assertEqual((a['nativeSpan'], a['showTicks'], a['wndprocUnionTicks'], a['defaultProcTicks']), (5, 45, 41, 16))
        self.assertEqual((b['nativeSpan'], b['showTicks'], b['outsideWndprocTicks']), (7, 10, 10))

    def test_lost_foreign_and_misnested_message_evidence_fails_closed(self):
        for header in ('WND_BEGIN 1 21 7 1000 7 0','WND_BEGIN 1 20 8 1000 7 0','WND_BEGIN 1 20 7 10 7 0',
                       'WND_BEGIN 1 20 7 1000 7 1','WND_BEGIN 1 20 7 1000 6 0'):
            with self.subTest(header=header), self.assertRaises(ValueError):
                self.replay(header=header)
        for index, bad in [(0, '1 0 show 4 99 201'), (0, '1 0 show 5 105 201'), (1, '2 1 wndproc 24 99 195'),
                           (2, '3 2 default 25 135 190'), (2, '3 1 default 24 135 190'), (3, '4 3 wndproc 71 134 180'),
                           (5, '6 1 wndproc 1025 197 198'), (5, '6 1 wndproc 10 175 198'),
                           (6, '7 0 show 5 99 201')]:
            rows = self.rows.copy(); rows[index] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.replay(rows)
        with self.assertRaisesRegex(ValueError, 'Missing per-call'):
            self.replay(self.rows[:-1])
        with self.assertRaises(ValueError):
            self.replay([])

    def test_real_recorder_filters_threads_and_windows_and_emits_an_empty_show(self):
        here = Path(__file__).resolve().parent
        rustc = here.parents[2] / 'artifacts/rust/toolchain/bin/rustc'
        if not rustc.is_file():
            rustc = shutil.which('rustc')
        if not rustc:
            self.skipTest('Rust compiler is needed for the message recorder control')
        with TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'control.exe'
            subprocess.run([str(rustc), '--edition=2024', str(here / 'message_controls.rs'), '-o', str(exe)], check=True)
            data = subprocess.check_output([str(exe)], text=True)
        calls, header, *_ = data.splitlines()
        intervals = list(map(int, calls.split()[1:]))
        nodes = {k: dict(row) for k, row in self.nodes.items()}
        nodes[5].update(start=intervals[0], end=intervals[1])
        nodes[7].update(start=intervals[2], end=intervals[3])
        result = message_times.analyze(data, nodes, int(header.split()[2]), 7, 9, 1000, [])
        full, empty = result['shows']
        self.assertEqual((full['messages'], empty['messages']), (2, 0))
        self.assertEqual(set(full['byMessage']), {'0x0018', 'WM_USER_or_higher'})
        self.assertGreater(full['defaultProcTicks'], 0)
        self.assertGreater(full['outsideWndprocTicks'], 0)
