"""Observe an installed worker's ordinary RDP Quit before Rust admission in the console."""
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from config_guard_msi import config_state, identify_window
from fixture import guard_id, read, release
from msi_sessions import (ADMIN, APP, APP_SHA, HERE, QA, WRITER_SHA, Accounts, SuspendedEndpoint, await_row,
                          begin_guard, client_connection, decode_connection, endpoint, instance,
                          interactive, measure, ordinary, peer, qualifies, require, wait, write)
from handover_receipts import shutdown
from native import wpf_tray_receiver

ORDER = 'wpf-handover'
ENDPOINT_SHA = 'e0f4aa779264f5bb33cf1ab0d8f94c34072765ff8c16af252b5b3233813b330e'


def tracked(base, dest):
    """Retain the original ASCII controls separately from the controller's parsed receipts."""
    class Observed(base):
        def read_output(self):
            try:
                with dest.open('x', encoding='utf-8', newline='') as stream:
                    for line in self.proc.stdout:
                        stream.write(line)
                        stream.flush()
                        self.events.put(line.rstrip('\r\n'))
            finally:
                self.events.put(None)
    return Observed


def exit_time(process, created):
    """Use the retained original process handle even after the menu closed it."""
    times = c.WinDLL('kernel32', use_last_error=True).GetProcessTimes
    times.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
    fields = [w.FILETIME() for _ in range(4)]
    if not times(int(process._handle), *(c.byref(f) for f in fields)):
        raise c.WinError(c.get_last_error())
    stamp, ended = [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in fields[:2]]
    require(stamp == created and ended >= stamp, 'Original WPF process exit time unavailable')
    return ended


def rdp(work, own, sid, accounts):
    area = work / ORDER
    wait(area, 'launch-wpf.json', timeout=150)
    pwsh = shutil.which('pwsh')
    require(pwsh, 'Put the native x64 PowerShell 7 QA distribution on the session PATH')
    log = area / 'wpf.log'
    with log.open('xb', buffering=0) as stream, subprocess.Popen(
            [APP], cwd=APP.parent, stdout=stream, stderr=subprocess.STDOUT) as process:
        try:
            who = ordinary(accounts, process.pid, sid, APP, own['sessionId'])
            write(area / 'wpf-process.json', who)
            raw = client_connection(process, wait(area, 'socket.json', timeout=90))
            write(area / 'wpf-socket.json', {'raw': raw, 'owner': decode_connection(bytes.fromhex(raw))})
            wait(area, 'stop-wpf.json')
            roots = identify_window(process.pid)
            receiver = wpf_tray_receiver(process.pid)
            require(len(roots) == 1 and receiver and process.poll() is None, 'Expected the installed visible editor and tray receiver')
            root, = roots
            hwnd, tid = receiver
            proposal = {'pid': process.pid, 'created100ns': who['created100ns'], 'hwnd': root,
                        'receiver': hwnd, 'tid': tid, 'issuedNs': time.monotonic_ns()}
            write(area / 'before-quit.json', proposal)
            (area / 'before-quit.log').write_bytes(log.read_bytes())
            with (area / 'quit-helper.log').open('xb') as helper:
                subprocess.run([pwsh, '-NoProfile', '-NoLogo', '-NonInteractive', '-STA', '-File',
                                HERE / 'handover_quit.ps1', '-ProcessId', str(process.pid), '-Created', str(who['created100ns']),
                                '-Root', str(root), '-Receiver', str(hwnd), '-ThreadId', str(tid),
                                '-Evidence', area / 'quit-menu.json'], stdout=helper, stderr=subprocess.STDOUT,
                               check=True, timeout=45)
            require(process.wait(timeout=30) == 0, 'The original WPF process did not quit normally')
            ended = {'pid': process.pid, 'created100ns': who['created100ns'],
                     'exit100ns': exit_time(process, who['created100ns']), 'exitCode': process.returncode,
                     'exitedNs': time.monotonic_ns(), 'method': 'shipping tray Quit'}
            verify_shutdown(area, proposal, ended)
            write(area / 'wpf-ended.json', ended)
        finally:
            if process.poll() is None:
                # A failed test still owns this specific child. Cleanup is never a successful handover.
                process.terminate()
                code = process.wait(timeout=15)
                write(area / 'wpf-cleanup.json', {'pid': process.pid, 'exitCode': code,
                                                  'method': 'owned process termination after failed handover'})


def verify_shutdown(area, proposal, ended):
    profile = Path(os.environ['LOCALAPPDATA']) / 'Immich Folder Watch'
    logs = {p.name: p.read_bytes() for p in (profile / 'engine-logs').glob('immich-folder-watch-*.log')}
    return shutdown(proposal, ended, read(area / 'quit-menu.json'), (area / 'before-quit.log').read_bytes(),
                    (area / 'wpf.log').read_bytes(), logs)


def finish_handover(work, profile, media, server, own, accounts, sid, result):
    area = work / ORDER
    require(result['ended']['pid'] == result['installedWpf']['pid']
            and result['ended']['created100ns'] == result['installedWpf']['created100ns'],
            'Unexpected WPF exit')
    result['shutdown'] = verify_shutdown(area, read(area / 'before-quit.json'), result['ended'])
    with ExitStack() as stack:
        native, who = endpoint(stack, work, area, own, accounts, sid,
                               observer=tracked(SuspendedEndpoint, area / 'rust-admitted.stdout'))
        native.expect('RUST_PRIMARY')
        endpoint_ns = time.monotonic_ns()
        writer, writer_identity = begin_guard(stack, work, profile, own, sid, accounts,
                                              observer=tracked(instance.Child, area / 'writer.stdout'))
        acquired_ns = time.monotonic_ns()
        require(result['ended']['exit100ns'] <= who['created100ns'] <= writer_identity['created100ns']
                and native.proc.poll() is None and writer.proc.poll() is None
                and guard_id(profile) == result['guard'], 'Rust ownership did not follow WPF exit')
        require(len(server.uploads) == 1 and await_row(profile, media) == result['rows']
                and config_state(profile / 'config.yaml') == result['originalConfig'], 'Profile or uploads changed at handover')
        release(writer)
        native.send('RELEASE')
        native.expect('RUST_RELEASED')
        native.success()
        result['admitted'] = {'endpoint': who, 'writer': writer_identity, 'endpointNs': endpoint_ns,
                              'guardNs': acquired_ns, 'releasedNs': time.monotonic_ns(),
                              'guard': guard_id(profile), 'endpointExit': native.proc.returncode,
                              'guardExit': writer.proc.returncode, 'config': config_state(profile / 'config.yaml')}
    peer.verify_asset_posts(server.posts, [(ORDER, peer.FILENAME)])
    result['posts'] = list(server.posts)


def record_sources(work):
    root = QA.parents[1]
    paths = {Path(__file__).resolve(), HERE / 'handover_quit.ps1',
             QA / 'windows-msi-interop/reverse/quit-source.ps1', root / 'packaging/windows/Test-InstalledUpgrade.ps1'}
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            p = Path(name).resolve()
            if p.is_relative_to(root / 'tools') and p.suffix == '.py':
                paths.add(p)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    write(work / 'handover-observer.json', {'revision': revision,
          'sources': {p.relative_to(root).as_posix(): instance.sha(p) for p in sorted(paths)}})


def main():
    role, name = sys.argv[1:]
    work = Path(name).resolve(strict=True)
    require(role in ('controller', 'peer') and os.name == 'nt' and os.environ.get('COMPUTERNAME') == 'IFW-QA25'
            and work.parent == Path(r'C:\Users\ifw-test\AppData\Local\IFW-MsiSessions')
            and work.name.startswith('trial-'), 'Expected the local disposable trial')
    require(instance.sha(work / 'bin/msi-session-endpoint.exe') == ENDPOINT_SHA
            and instance.sha(work / 'bin/instance.exe') == WRITER_SHA and instance.sha(APP) == APP_SHA,
            'Unexpected native endpoint, writer, or installed WPF image')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(qualifies(own) and desktop['connectionState'] == 0 and desktop['clientProtocol'] == (0 if role == 'controller' else 2)
            and (ADMIN / 'marker.txt').read_bytes() == f'IFW disposable installed MSI session test\n{sid}\n'.encode('ascii'),
            'Expected the marked standard-user console and RDP desktop')
    write(work / (role + '-session.json'), {'identity': own, 'desktop': desktop})
    try:
        if role == 'peer':
            rdp(work, own, sid, accounts)
        else:
            record_sources(work)
            other = wait(work, 'peer-session.json', timeout=150)['identity']
            require(other['sidSha256'] == own['sidSha256'] and other['sessionId'] != own['sessionId'],
                    'The participants must be separate sessions of the same test account')
            case = measure(work, ORDER, own, other, accounts, sid)
            write(work / 'result.json', {'completed': True, 'order': ORDER, 'wpfPid': case['installedWpf']['pid']})
    except BaseException as error:
        write(work / (role + '-error.json'), {'error': repr(error)})
        if (work / ORDER).is_dir():
            (work / ORDER / 'abort').touch()
        raise


if __name__ == '__main__':
    main()
