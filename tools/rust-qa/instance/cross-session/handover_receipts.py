"""Validate the handover using the original desktop, worker, and admission records."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'windows-msi-interop'))
from common import require
from reverse.evidence import QUIT_SOURCE, engine_lines, verify_menu_anchor

START = 'Folder watcher started with 1 source(s).'
STOP = 'Folder watch worker received shutdown signal.'
FLUSH = 'Flushing pending uploads before shutdown.'


def shutdown(start, end, menu, before, console, logs):
    root = {'hwnd': start['hwnd'], 'pid': start['pid'], 'tid': start['tid']}
    verify_menu_anchor(menu, root)
    popup = menu['menuHwnd']
    require(menu['status'] == 'invoked' and menu['sourceSha256'] == QUIT_SOURCE and isinstance(popup, int)
            and popup > 0 and menu['rawInteraction'] == f'tray-menu-quit; popup={popup}; verifiedHighlightedCommandId=3; nativeMouseClick'
            and [menu[k] for k in ('pid', 'created', 'receiver', 'tid')] == [start[k] for k in ('pid', 'created100ns', 'receiver', 'tid')]
            and start['receiver'] > 0 and start['receiver'] != start['hwnd'], 'Missing original WPF menu selection')
    require(end['method'] == 'shipping tray Quit' and end['exitCode'] == 0 and end['pid'] == start['pid']
            and end['created100ns'] == start['created100ns'] < end['exit100ns'] and start['issuedNs'] < end['exitedNs'],
            'Original process did not exit zero after its Quit')
    require(console.startswith(before), 'WPF console changed before Quit')
    suffix = console[len(before):].decode('utf-8', errors='replace')
    messages = [m for name in sorted(logs) for m in engine_lines(logs[name].decode('utf-8-sig'))]
    require(all(messages.count(m) == 1 for m in (START, STOP, FLUSH)) and messages.index(START) < messages.index(STOP) < messages.index(FLUSH)
            and all('FolderWatchWorker[0] ' + message in suffix for message in (STOP, FLUSH)),
            'Original engine and post-Quit console do not establish shutdown and start of the flush')
    return {'method': end['method'], 'shutdownSignal': True, 'flushStarted': True, 'flushCompletion': 'unobserved'}


def ordered(case, raw_refusal, raw_admitted, raw_writer):
    previous, end, active = case['installedWpf'], case['ended'], case['admitted']
    endpoint, writer = active['endpoint'], active['writer']
    require(end['pid'] == previous['pid'] and end['created100ns'] == previous['created100ns']
            and end['exit100ns'] <= endpoint['created100ns'] <= writer['created100ns']
            and endpoint['pid'] != writer['pid'] and active['guard'] == case['guard']
            and active['guardExit'] == active['endpointExit'] == 0
            and case['upload']['responseNs'] < end['exitedNs'] < active['endpointNs'] <= active['guardNs'] <= active['releasedNs'],
            'Rust endpoint and guard did not follow the original worker exit')
    require(raw_refusal.splitlines() == [f"SESSION_MUTEX session={endpoint['sessionId']} created=true",
                                         f"PIPE_REFUSED code=Some({case['pipeRefusalWin32']})",
                                         f"EXISTING_PIPE_SERVER pid={previous['pid']}"]
            and raw_admitted.splitlines() == [f"SESSION_MUTEX session={endpoint['sessionId']} created=true", 'RUST_PRIMARY', 'RUST_RELEASED']
            and raw_writer.splitlines() == ['WRITER_HELD', 'WRITER_RELEASED'], 'Native process transcripts differ')
    require(case['originalConfig'] == active['config'] and case['originalConfig']['sha256'] == case['configSha256']
            and min(case['originalConfig'][k] for k in ('volume', 'fileId', 'bytes')) > 0,
            'Config file identity or bytes changed across handover')
