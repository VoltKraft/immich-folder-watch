"""Check whether an exclusive handle on the original configuration blocks an installed WPF startup."""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from msi_sessions import (ADMIN, APP, APP_SHA, MARKER, Accounts, Server, await_row, client_connection, configuration,
                          decode_connection, instance, interactive, launch_wpf, measure, ordinary, peer, qualifies,
                          require, wait, write)


def config_state(path):
    info = path.stat()
    return {'volume': info.st_dev, 'fileId': info.st_ino, 'bytes': info.st_size, 'sha256': instance.sha(path)}


def identify_window(pid):
    import ctypes as c
    from ctypes import wintypes as w
    u = c.WinDLL('user32', use_last_error=True)
    u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    u.IsWindowVisible.argtypes = [w.HWND]
    u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    matches = []
    proc = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

    @proc
    def enum(hwnd, _):
        owner = w.DWORD()
        u.GetWindowThreadProcessId(hwnd, c.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            label = c.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, label, 256)
            if label.value == 'Immich Folder Watch':
                matches.append(int(hwnd))
        return True

    u.EnumWindows.argtypes = [proc, w.LPARAM]
    require(u.EnumWindows(enum, 0), 'EnumWindows failed')
    return matches


def guest_wpf(work, own, sid, accounts):
    launch_wpf(work, own['sessionId'], sid, accounts, ('wpf-first',))
    for name in ('protected', 'released'):
        area = work / name
        wait(area, 'launch.json', timeout=100)
        with subprocess.Popen([APP], cwd=APP.parent) as proc:
            try:
                identity = ordinary(accounts, proc.pid, sid, APP, own['sessionId'])
                deadline = time.monotonic() + 30
                while proc.poll() is None and time.monotonic() < deadline:
                    windows = identify_window(proc.pid)
                    if windows:
                        break
                    time.sleep(.15)
                require(proc.poll() is None and windows, 'Missing visible installed WPF window')
                write(area / 'started.json', {'identity': identity, 'hwnd': windows[0]})
                if name == 'released':
                    sample = wait(area, 'socket.json')
                    raw = client_connection(proc, sample)
                    write(area / 'owner.json', {'raw': raw, 'owner': decode_connection(bytes.fromhex(raw))})
                wait(area, 'stop.json')
                require(windows[0] in identify_window(proc.pid), 'Original WPF window disappeared')
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=15)
        write(area / 'exit.json', {'pid': proc.pid, 'exit': proc.returncode})


def start(area, accounts, sid, other):
    write(area / 'launch.json', True)
    record = wait(area, 'started.json')
    token = record['identity']
    require(token == ordinary(accounts, token['pid'], sid, APP, other['sessionId'], token['created100ns']), 'Changed WPF process')
    return record


def guard_trial(work, own, other, sid, accounts):
    area = work / 'protected'
    released = work / 'released'
    area.mkdir()
    released.mkdir()
    media = area / 'media'
    media.mkdir()
    (media / peer.FILENAME).write_bytes(peer.IMAGE)
    profile = Path(os.environ['LOCALAPPDATA']) / 'Immich Folder Watch'
    profile.mkdir(exist_ok=False)
    (profile / '.ifw-instance-fixture').write_bytes(MARKER)
    cfg = profile / 'config.yaml'
    exe = work / 'bin/msi-session-endpoint.exe'
    record = {'passed': False}
    with ExitStack() as stack:
        server = stack.enter_context(Server(('127.0.0.1', 0), peer.UploadPeer))
        server.phase, server.output, server.posts, server.uploads = 'protected', area, [], []
        server.assets = {peer.FILENAME: (peer.IMAGE, peer.ASSET_ID)}
        server.post_lock, server.received, server.release = threading.Lock(), threading.Event(), threading.Event()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join, 5)
        stack.callback(server.shutdown)
        stack.callback(server.release.set)
        cfg.write_text(configuration(media, f'http://127.0.0.1:{server.server_port}'), encoding='utf-8')
        record['before'] = before = config_state(cfg)
        with instance.Child([exe, '--hold-synthetic-config'], area, os.environ) as rust:
            record['guardProcess'] = ordinary(accounts, rust.proc.pid, sid, exe, own['sessionId'])
            rust.expect(f"CONFIG_HELD volume={before['volume']} id={before['fileId']}")
            record['heldNs'] = time.monotonic_ns()
            for mode in ('rb', 'r+b'):
                try:
                    with cfg.open(mode): pass
                except OSError as exc:
                    require(exc.winerror == 32, 'Expected a Windows sharing violation')
                    record[mode + 'Win32'] = exc.winerror
                else:
                    raise RuntimeError('A configuration handle opened while the Rust share was held')
            record['protectedWpf'] = start(area, accounts, sid, other)
            record['windowObservedNs'] = time.monotonic_ns()
            require(not server.received.wait(12) and not server.posts and not (profile / 'sync-state.db').exists(),
                    'Unexpected installed worker activity while Rust held the config')
            record['protectedEndNs'] = time.monotonic_ns()
            record['protectedAssetPosts'] = list(server.posts)
            record['protectedDatabasePresent'] = (profile / 'sync-state.db').exists()
            write(area / 'stop.json', True)
            record['protectedExit'] = wait(area, 'exit.json')
            rust.send('RELEASE')
            rust.expect('CONFIG_RELEASED')
            rust.success()
        record['releasedNs'] = time.monotonic_ns()
        record['afterRelease'] = config_state(cfg)
        require(record['afterRelease'] == before, 'Configuration changed during admission')
        server.phase, server.output = 'released', released
        record['controlWpf'] = start(released, accounts, sid, other)
        require(server.received.wait(60) and len(server.uploads) == 1, 'Missing unguarded upload from installed WPF')
        record['upload'] = server.uploads[0]
        write(released / 'socket.json', record['upload'])
        record['controlSocket'] = wait(released, 'owner.json', timeout=12)
        server.release.set()
        record['rows'] = await_row(profile, media)
        peer.verify_asset_posts(server.posts, [('released', peer.FILENAME)])
        record['posts'] = server.posts
        write(released / 'stop.json', True)
        record['controlExit'] = wait(released, 'exit.json')
    record['afterControl'] = config_state(cfg)
    require(record['afterControl'] == before, 'Control changed the original configuration')
    profile.rename(released / 'finished-profile')
    record['passed'] = True
    write(work / 'config-guard.json', record)


def main():
    role, arg = sys.argv[1:]
    work = Path(arg).resolve(strict=True)
    require(work.parent == Path(os.environ['LOCALAPPDATA']) / 'IFW-MsiSessions' and work.name.startswith('trial-'), 'Expected dedicated VM directory')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(role in ('controller', 'peer') and qualifies(own) and desktop['connectionState'] == 0 and
            desktop['clientProtocol'] == (0 if role == 'controller' else 2) and instance.sha(APP) == APP_SHA
            and (ADMIN / 'marker.txt').read_bytes() == f'IFW disposable installed MSI session test\n{sid}\n'.encode('ascii'), 'Expected disposable standard account')
    write(work / (role+'-session.json'), {'identity': own, 'desktop': desktop})
    try:
        if role == 'peer':
            guest_wpf(work, own, sid, accounts)
        else:
            other = wait(work, 'peer-session.json')['identity']
            require(other['sidSha256'] == own['sidSha256'] and other['sessionId'] != own['sessionId'], 'Expected the same account in two active sessions')
            measure(work, 'wpf-first', own, other, accounts, sid)
            guard_trial(work, own, other, sid, accounts)
    except BaseException as exc:
        write(work / (role+'-error.json'), {'error': repr(exc)})
        for name in ('wpf-first', 'protected', 'released'):
            if (work / name).is_dir(): (work / name / 'abort').touch()
        raise


if __name__ == '__main__':
    main()
