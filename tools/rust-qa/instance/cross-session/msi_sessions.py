"""Measure installed WPF uploads during Rust admission in another standard-user Windows session."""
from contextlib import ExitStack
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

from existing import interactive
from fixture import Accounts, HERE, MARKER, guard_id, instance, release, verified_process, wait, write
from standard import FixedWriter, qualifies

QA = HERE.parents[1]
sys.path.extend([str(QA / 'windows-msi-interop/upload'), str(QA / 'windows-performance')])
from shared import configuration, peer, require
from owners import client_connection, decode_connection

ADMIN = Path(r'C:\Program Files\IFW-QA-CrossSession')
APP = Path(r'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe')
APP_SHA = 'b8354424bd6c6eba133bb7939ce0de42afbe234bcbb77853b30c25dd645f8675'
WRITER_SHA = '134813fb4f69aeadd9fe6f21de922e24a0632a8a007f4aae6a4b220fa216d07b'
ORDERS = ('rust-first', 'wpf-first')


class Server(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class SuspendedEndpoint(instance.Child):
    """Keep the short-lived refusal path suspended until its native identity is verified."""
    def __init__(self, exe, area):
        self.proc = subprocess.Popen([exe], cwd=area, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding='utf-8', bufsize=1, creationflags=4)
        self.events = queue.Queue()
        self.reader = threading.Thread(target=self.read_output, daemon=True)
        self.reader.start()

    resume = FixedWriter.resume


def ordinary(accounts, pid, sid, image, session, created=None):
    token = verified_process(accounts, pid, sid, image, session, created)
    require(qualifies(token), 'Expected ordinary process authority')
    return token


def launch_wpf(work, session, sid, accounts, orders=ORDERS):
    for order in orders:
        area = work / order
        wait(area, 'launch-wpf.json', timeout=140)
        with subprocess.Popen([APP], cwd=APP.parent) as proc:
            try:
                who = ordinary(accounts, proc.pid, sid, APP, session)
                write(area / 'wpf-process.json', who)
                observed = wait(area, 'socket.json', timeout=90)
                raw = client_connection(proc, observed)
                write(area / 'wpf-socket.json', {'raw': raw, 'owner': decode_connection(bytes.fromhex(raw))})
                wait(area, 'stop-wpf.json')
            finally:
                if proc.poll() is None:
                    # End only this identified test process after its committed row has been read back.
                    proc.terminate()
                    proc.wait(timeout=15)
        write(area / 'wpf-ended.json', {'pid': proc.pid, 'exitCode': proc.returncode, 'cleanup': 'test-process termination'})


def endpoint(stack, work, area, own, accounts, sid):
    exe = work / 'bin/msi-session-endpoint.exe'
    native = stack.enter_context(SuspendedEndpoint(exe, area))
    who = ordinary(accounts, native.proc.pid, sid, exe, own['sessionId'])
    native.resume()
    native.expect('SESSION_MUTEX session=' + str(own['sessionId']) + ' created=true')
    return native, who


def begin_guard(stack, work, profile, own, sid, accounts):
    exe = work / 'bin/instance.exe'
    require(instance.sha(exe) == WRITER_SHA, 'Unexpected retained writer image')
    child = stack.enter_context(instance.Child([exe, 'writer', profile, sid, '0'], profile,
                                                {**os.environ, 'IFW_QA_EXISTING_SESSION': '1'}))
    child.expect('WRITER_HELD')
    return child, ordinary(accounts, child.proc.pid, sid, exe, own['sessionId'])


def await_row(profile, media):
    expected = [(str(media), peer.FILENAME, peer.ASSET_ID, len(peer.IMAGE), 0, 0)]
    until = time.monotonic() + 15
    while time.monotonic() < until:
        rows = peer.rows(profile / 'sync-state.db')
        if rows == expected:
            return rows
        time.sleep(.1)
    raise RuntimeError('The installed worker did not commit its own PNG row')


def measure(work, order, own, other, accounts, sid):
    area = work / order
    area.mkdir()
    profile = Path(os.environ['LOCALAPPDATA']) / 'Immich Folder Watch'
    # Both orders start from an absent profile in the explicitly marked synthetic account.
    profile.mkdir(exist_ok=False)
    (profile / '.ifw-instance-fixture').write_bytes(MARKER)
    (profile / 'writer.lock').touch(exist_ok=False)
    media = area / 'media'
    media.mkdir()
    (media / peer.FILENAME).write_bytes(peer.IMAGE)
    result = {'order': order, 'guard': guard_id(profile)}
    write(area / 'started.json', result)
    with ExitStack() as stack:
        server = stack.enter_context(Server(('127.0.0.1', 0), peer.UploadPeer))
        server.phase, server.output, server.posts, server.uploads = order, area, [], []
        server.assets = {peer.FILENAME: (peer.IMAGE, peer.ASSET_ID)}
        server.post_lock, server.received, server.release = threading.Lock(), threading.Event(), threading.Event()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join, 5)
        stack.callback(server.shutdown)
        stack.callback(server.release.set)
        (profile / 'config.yaml').write_text(configuration(media, f'http://127.0.0.1:{server.server_port}'), encoding='utf-8')
        if order == 'rust-first':
            native, result['rustProcess'] = endpoint(stack, work, area, own, accounts, sid)
            native.expect('RUST_PRIMARY')
            writer, result['guardWriter'] = begin_guard(stack, work, profile, own, sid, accounts)
            result['rustPrimaryNs'] = time.monotonic_ns()
        write(area / 'launch-wpf.json', {'timeNs': time.monotonic_ns()})
        wpf = wait(area, 'wpf-process.json')
        result['installedWpf'] = ordinary(accounts, wpf['pid'], sid, APP, other['sessionId'], wpf['created100ns'])
        require(result['installedWpf'] == wpf and server.received.wait(60), 'Missing upload from installed WPF')
        require(len(server.uploads) == 1, 'Expected one native image POST')
        observed = server.uploads[0]
        write(area / 'socket.json', observed)
        result['heldSocket'] = wait(area, 'wpf-socket.json', timeout=12)
        if order == 'wpf-first':
            native, result['rustProcess'] = endpoint(stack, work, area, own, accounts, sid)
            refusal = native.events.get(timeout=10)
            allowed = {'PIPE_REFUSED code=Some(5)': 5, 'PIPE_REFUSED code=Some(231)': 231}
            require(refusal in allowed, f'Expected refusal of the occupied first pipe instance, received {refusal!r}')
            result['pipeRefusalWin32'] = allowed[refusal]
            native.expect('EXISTING_PIPE_SERVER pid=' + str(wpf['pid']))
            native.success()
            result['rustRefusedNs'] = time.monotonic_ns()
            result['existingPipePid'] = wpf['pid']
        else:
            require(native.proc.poll() is None and writer.proc.poll() is None, 'A Rust owner exited during the WPF upload')
            result['bothRustOwnersAliveNs'] = time.monotonic_ns()
        server.release.set()
        result['rows'] = await_row(profile, media)
        if order == 'rust-first':
            require(native.proc.poll() is None and guard_id(profile) == result['guard'], 'Changed native owner or guard')
            release(writer)
            native.send('RELEASE')
            native.expect('RUST_RELEASED')
            native.success()
        peer.verify_asset_posts(server.posts, [(order, peer.FILENAME)])
        if order == 'rust-first':
            require(result['rustPrimaryNs'] < observed['requestNs'] <= result['bothRustOwnersAliveNs'] < observed['responseNs'],
                    'Rust admission and its file guard must overlap the installed upload')
        else:
            require(observed['requestNs'] <= result['rustRefusedNs'] < observed['responseNs'],
                    'Rust refusal must occur during the installed upload')
        result.update(posts=server.posts, upload=observed, configSha256=instance.sha(profile / 'config.yaml'))
        write(area / 'stop-wpf.json', True)
        result['ended'] = wait(area, 'wpf-ended.json')
    # Preserve the full first profile instead of reusing its database for the second order.
    profile.rename(area / 'finished-profile')
    write(area / 'result.json', result)
    return result


def main():
    role = sys.argv[1]
    work = Path(sys.argv[2]).resolve(strict=True)
    shared = Path(os.environ['LOCALAPPDATA']) / 'IFW-MsiSessions'
    require(work.parent == shared and work.name.startswith('trial-') and role in ('controller', 'peer'), 'Expected owned VM trial root')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(qualifies(own) and (ADMIN / 'marker.txt').read_bytes() == f'IFW disposable installed MSI session test\n{sid}\n'.encode('ascii')
            and instance.sha(APP) == APP_SHA, 'Marked standard account and original MSI executable required')
    require(desktop['connectionState'] == 0 and desktop['clientProtocol'] == (0 if role == 'controller' else 2), 'Both ordinary sessions must be active')
    write(work / (role+'-session.json'), {'identity': own, 'desktop': desktop})
    try:
        if role == 'peer':
            launch_wpf(work, own['sessionId'], sid, accounts)
        else:
            other = wait(work, 'peer-session.json')['identity']
            require(other['sidSha256'] == own['sidSha256'] and other['sessionId'] != own['sessionId'], 'Expected same SID in two sessions')
            cases = [measure(work, order, own, other, accounts, sid) for order in ORDERS]
            write(work / 'result.json', {'completed': True, 'oldNewExclusionPassed': False,
                  'reason': 'Original WPF uploaded after Rust acquired both admission endpoints and the new file guard', 'cases': cases})
    except BaseException as exc:
        write(work / (role+'-error.json'), {'error': repr(exc)})
        for name in ORDERS:
            if (work / name).is_dir(): (work / name / 'abort').touch()
        raise


if __name__ == '__main__':
    main()
