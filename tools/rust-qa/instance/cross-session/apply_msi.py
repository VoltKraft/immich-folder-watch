"""Exercise Save and Apply on the installed WPF window across a real config-handle release."""
from contextlib import ExitStack
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import time

from config_guard_msi import config_state, identify_window, sharing_violation
from msi_sessions import (ADMIN, APP, APP_SHA, MARKER, Accounts, Server, await_row, client_connection, configuration,
                          decode_connection, instance, interactive, ordinary, peer, qualifies, require, wait, write)

HERE = Path(__file__).resolve().parent
ENDPOINT_SHA = 'e0f4aa779264f5bb33cf1ab0d8f94c34072765ff8c16af252b5b3233813b330e'


class ApplyPeer(peer.UploadPeer):
    """Answer the shipping access checks while retaining the original multipart observer."""
    def reply(self, status, content):
        stamp = time.monotonic_ns()
        self.server.requests.append({'phase': self.server.phase, 'method': self.command,
                                     'path': self.path, 'status': status, 'requestNs': stamp})
        if self.server.phase == 'released' and self.command == 'GET' and self.path.startswith('/socket.io/?EIO=4&transport=polling'):
            self.server.worker_started.set()
        super().reply(status, content)

    def permission(self):
        self.reply(400, {'message': 'Invalid synthetic permission-check identifier'})

    def do_GET(self):
        if self.path == '/api/assets/not-a-valid-id/original':
            self.permission()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path in ('/api/albums', '/api/search/metadata', '/api/albums/not-a-valid-id/assets'):
            self.permission()
        else:
            super().do_POST()

    def do_DELETE(self):
        if self.path in ('/api/assets', '/api/albums/not-a-valid-id', '/api/albums/not-a-valid-id/assets'):
            self.permission()
        else:
            self.reply(404, {})

    def do_PATCH(self):
        self.permission() if self.path == '/api/albums/not-a-valid-id' else self.reply(404, {})

    def do_PUT(self):
        self.permission() if self.path == '/api/albums/not-a-valid-id/assets' else self.reply(404, {})


def serve(stack, area, cert_dir=None):
    server = stack.enter_context(Server(('127.0.0.1', 0), ApplyPeer))
    if cert_dir is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_dir / 'host.pem', cert_dir / 'host-key.pem')
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.phase, server.output = 'held', area
    server.posts, server.uploads, server.requests = [], [], []
    server.worker_started = threading.Event()
    server.assets = {peer.FILENAME: (peer.IMAGE, peer.ASSET_ID), 'held-canary.png': (peer.IMAGE, peer.ASSET_ID)}
    server.post_lock, server.received, server.release = threading.Lock(), threading.Event(), threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join, 5)
    stack.callback(server.shutdown)
    stack.callback(server.release.set)
    return server


def apply_window(work, pid, who, hwnd, phase):
    exe = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    with (work / 'apply' / (phase + '-driver.log')).open('xb') as log:
        subprocess.run([exe, '-NoProfile', '-NonInteractive', '-File', HERE / 'apply_window.ps1', phase,
                        str(pid), str(who['created100ns']), str(hwnd), work],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=75)


def wpf(work, own, sid, accounts):
    area = work / 'apply'
    wait(area, 'launch.json', timeout=180)
    with subprocess.Popen([APP], cwd=APP.parent) as process:
        try:
            who = ordinary(accounts, process.pid, sid, APP, own['sessionId'])
            deadline = time.monotonic() + 35
            while not (windows := identify_window(process.pid)) and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.1)
            require(len(windows) == 1 and process.poll() is None, 'Expected one visible installed WPF window')
            hwnd, = windows
            write(area / 'started.json', {'hwnd': hwnd, 'identity': who})
            for phase in ('held', 'released'):
                wait(area, phase + '-invoke.json', timeout=180)
                require(identify_window(process.pid) == [hwnd], 'WPF window changed before Apply')
                apply_window(work, process.pid, who, hwnd, phase)
                write(area / (phase + '-finished.json'), True)
            raw = client_connection(process, wait(area, 'socket.json', timeout=120))
            write(area / 'owner.json', {'raw': raw, 'owner': decode_connection(bytes.fromhex(raw))})
            wait(area, 'stop.json')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
    write(area / 'exit.json', {'pid': process.pid, 'exit': process.returncode})


def controller(work, own, other, sid, accounts, certificate_dir):
    area = work / 'apply'
    area.mkdir()
    media = area / 'media'
    media.mkdir()
    profile = Path(os.environ['LOCALAPPDATA']) / 'Immich Folder Watch'
    profile.mkdir(exist_ok=False)
    (profile / '.ifw-instance-fixture').write_bytes(MARKER)
    cfg, db = profile / 'config.yaml', profile / 'sync-state.db'
    exe = work / 'bin/msi-session-endpoint.exe'
    require(instance.sha(exe) == ENDPOINT_SHA, 'Incorrect archived Rust endpoint')
    result = {'passed': False}
    with ExitStack() as stack:
        original = serve(stack, area)
        https = serve(stack, area, certificate_dir)
        draft_url = f'https://127.0.0.1:{https.server_port}/api'
        pristine = configuration(media, f'http://127.0.0.1:{original.server_port}').encode('utf-8')
        cfg.write_bytes(pristine)
        (area / 'original.yaml').write_bytes(pristine)
        before = result['before'] = config_state(cfg)
        try:
            with instance.Child([exe, '--hold-synthetic-config'], area, os.environ) as rust:
                result['holder'] = ordinary(accounts, rust.proc.pid, sid, exe, own['sessionId'])
                rust.expect(f"CONFIG_HELD volume={before['volume']} id={before['fileId']}")
                result['held'] = time.monotonic_ns()
                result['initialDenial'] = sharing_violation(cfg, 0xc0000000)
                write(area / 'launch.json', {'media': str(media), 'url': draft_url, 'key': peer.TEST_KEY})
                started = result['started'] = wait(area, 'started.json')
                who = started['identity']
                require(who == ordinary(accounts, who['pid'], sid, APP, other['sessionId'], who['created100ns']), 'WPF identity changed')
                write(area / 'held-invoke.json', True)
                wait(area, 'held-finished.json', timeout=85)
                result['heldWindow'] = wait(area, 'held-window.json')
                require(result['heldWindow']['outcome'] == 'save-failed', 'Expected the shipping write failure')
                result['heldObservationStart'] = time.monotonic_ns()
                canary = media / 'held-canary.png'
                canary.write_bytes(peer.IMAGE)
                require(not https.received.wait(12) and not db.exists(), 'A worker started before config release')
                result['heldObservationEnd'] = time.monotonic_ns()
                result['heldDatabase'] = db.exists()
                result['heldPosts'] = list(https.posts)
                require(any(post['kind'] == 'permission-probe' for post in https.posts), 'Apply did not reach the peer')
                peer.verify_asset_posts(https.posts, [])
                require(not original.requests and not original.posts, 'The unreadable initial profile reached its peer')
                result['finalDenial'] = sharing_violation(cfg, 0xc0000000)
                require(rust.proc.poll() is None, 'Guard exited before the negative observation')
                canary.unlink()
                rust.send('RELEASE')
                rust.expect('CONFIG_RELEASED')
                rust.success()
            result['afterRelease'] = config_state(cfg)
            require(result['afterRelease'] == before and cfg.read_bytes() == pristine, 'Held Apply changed the configuration')
            https.phase = 'released'
            write(area / 'released-invoke.json', True)
            wait(area, 'released-finished.json', timeout=85)
            result['releasedWindow'] = wait(area, 'released-window.json')
            require(result['releasedWindow']['outcome'] == 'saved-applied', 'Released Apply did not succeed')
            saved = cfg.read_bytes()
            (area / 'saved.yaml').write_bytes(saved)
            result['afterApply'] = config_state(cfg)
            require(saved != pristine and draft_url.encode() in saved and str(media).encode() in saved,
                    'The installed WPF Apply did not persist the expected draft')
            require(https.worker_started.wait(45) and db.is_file(), 'A released worker did not start its database and realtime client')
            result['workerReady'] = {'timeNs': time.monotonic_ns(), 'database': config_state(db),
                                     'requests': [r for r in https.requests if r['phase'] == 'released' and r['path'].startswith('/socket.io/')]}
            (media / peer.FILENAME).write_bytes(peer.IMAGE)
            result['mediaCreatedNs'] = time.monotonic_ns()
            require(https.received.wait(90) and len(https.uploads) == 1, 'Missing upload after successful Apply')
            result['upload'] = https.uploads[0]
            write(area / 'socket.json', result['upload'])
            result['owner'] = wait(area, 'owner.json', timeout=15)
            https.release.set()
            result['rows'] = await_row(profile, media)
            peer.verify_asset_posts(https.posts, [('released', peer.FILENAME)])
            write(area / 'stop.json', True)
            result['exit'] = wait(area, 'exit.json')
            result['passed'] = True
        finally:
            result.update(posts=https.posts, requests=https.requests, initialConfigRequests=original.requests)
            write(area / 'apply.json', result)
    profile.rename(area / 'finished-profile')


def main():
    role, folder, cert_folder = sys.argv[1:]
    work = Path(folder).resolve(strict=True)
    require(work.parent == Path(os.environ['LOCALAPPDATA']) / 'IFW-MsiSessions' and work.name.startswith('trial-'),
            'Expected isolated local MSI fixture')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(role in ('controller', 'peer') and qualifies(own) and desktop['connectionState'] == 0 and
            desktop['clientProtocol'] == (0 if role == 'controller' else 2)
            and instance.sha(APP) == APP_SHA and (ADMIN / 'marker.txt').read_bytes() ==
            f'IFW disposable installed MSI session test\n{sid}\n'.encode('ascii'), 'Expected ordinary identities on the marked guest')
    write(work / (role + '-session.json'), {'identity': own, 'desktop': desktop})
    try:
        if role == 'peer':
            wpf(work, own, sid, accounts)
        else:
            other = wait(work, 'peer-session.json', timeout=240)['identity']
            require(other['sidSha256'] == own['sidSha256'] and other['sessionId'] != own['sessionId'], 'Expected distinct logons of the same test user')
            controller(work, own, other, sid, accounts, Path(cert_folder))
    except BaseException as exc:
        write(work / (role + '-error.json'), {'error': repr(exc)})
        if (work / 'apply').exists():
            (work / 'apply/abort').touch()
        raise


if __name__ == '__main__':
    main()
