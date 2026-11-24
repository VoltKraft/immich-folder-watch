"""Observe the signed Flatpak uploading one synthetic image while Rust attempts an ordinary launch."""

import base64
from contextlib import closing
from email.parser import BytesParser
from email.policy import default
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import struct
import subprocess
import threading
import time


FILENAME = 'signed-worker.png'
IMAGE = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNQKp8JAAHxATMPPYvFAAAAAElFTkSuQmCC')
ASSET_ID = '85a783ae-f459-41e9-ad2a-9f1fdc123742'
TEST_KEY = 'synthetic-installed-upload'


def multipart_image(content_type, body, filename=FILENAME, image=IMAGE):
    message = BytesParser(policy=default).parsebytes(
        b'Content-Type: ' + content_type.encode('ascii') + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
    files = [part for part in message.iter_parts()
             if part.get_param('name', header='Content-Disposition') == 'assetData']
    return len(files) == 1 and files[0].get_filename() == filename and files[0].get_payload(decode=True) == image


class UploadPeer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, content):
        payload = json.dumps(content).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path in ('/api/server/ping', '/api/server-info/ping'):
            self.reply(200, {'res': 'pong'})
        elif self.path == '/api/albums':
            self.reply(200, [])
        else:
            self.reply(404, {})

    def do_POST(self):
        if self.path != '/api/assets' or self.headers.get('x-api-key') != TEST_KEY:
            self.reply(404, {})
            return
        length = int(self.headers.get('Content-Length', '-1'))
        if not 0 <= length <= 65536:
            self.reply(411, {})
            return
        body = self.rfile.read(length)
        content_type = self.headers.get('Content-Type', '')
        matched = [name for name, (image, _) in self.server.assets.items() if multipart_image(content_type, body, name, image)]
        if len(matched) != 1:
            self.reply(400, {})
            return
        name, = matched
        observed = dict(filename=name, client=self.connection.getpeername(), server=self.connection.getsockname(), requestNs=time.monotonic_ns(),
                        contentType=content_type, bodySha256=hashlib.sha256(body).hexdigest())
        self.server.uploads.append(observed)
        (self.server.output / f'shipping-upload-{self.client_address[1]}.multipart').write_bytes(body)
        self.server.received.set()
        if not self.server.release.wait(30):
            self.reply(503, {})
            return
        observed['responseNs'] = time.monotonic_ns()
        self.reply(201, {'id': self.server.assets[name][1], 'status': 'created'})


def endpoint_tuple(field):
    address, port = field.split(':')
    packed = b''.join(struct.pack('=I', int(address[i:i+8], 16)) for i in range(0, len(address), 8))
    ip = ipaddress.ip_address(packed)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return str(ip), int(port, 16)


def client_socket(pid, observed):
    """Find the exact accepted loopback connection among the signed apphost's live descriptors."""
    proc = Path('/proc') / str(pid)
    bound = set()
    for descriptor in (proc / 'fd').iterdir():
        try:
            bound.add(os.readlink(descriptor))
        except FileNotFoundError:
            continue
    inodes = []
    for name in ('tcp', 'tcp6'):
        for line in (proc / 'net' / name).read_text().splitlines()[1:]:
            fields = line.split()
            local, remote = map(endpoint_tuple, fields[1:3])
            if (local, remote) == (observed['client'], observed['server']) and fields[3] == '01' and f'socket:[{fields[9]}]' in bound:
                inodes.append(int(fields[9]))
    if len(inodes) != 1:
        raise RuntimeError('The signed apphost does not own exactly one matching established client socket')
    return inodes[0]


def rows(path):
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as database:
        return database.execute('SELECT source_path,relative_path,asset_id,file_size,direction,status FROM sync_entries').fetchall()


def observe(stack, bus, display, pins, report, out, backup=None):
    from assess import pidfd
    from gui_refusal import NAME, owner, quit_shipping, workers
    from observe import identity, window, witness
    from run import APP, require, sha
    from session import checked_start, check_alive, wait_for

    profile = Path('/tmp/home/.var/app') / APP
    require(out == Path('/qa') and Path.home() == Path('/tmp/home') and
            not Path('/proc/net/route').read_text().splitlines()[1:] and
            not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True).strip(),
            'The configured upload requires the empty private offline desktop')
    details = report['configuredShippingUpload'] = {'uploads': []}
    server = ThreadingHTTPServer(('127.0.0.1', 0), UploadPeer)
    stack.callback(server.server_close)
    server.output, server.uploads = out, details['uploads']
    server.assets = {FILENAME: (IMAGE, ASSET_ID)}
    server.received, server.release = threading.Event(), threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join, 3)
    stack.callback(server.shutdown)
    stack.callback(server.release.set)
    port = server.server_port
    config = profile / 'config/immich-folder-watch/config.yaml'
    database = config.with_name('sync-state.db')
    media = profile / 'data/interop-upload'
    require(not config.exists() and not database.exists(), 'Expected the unconfigured private shipping profile')
    media.mkdir()
    image = media / FILENAME
    image.write_bytes(IMAGE)
    config.write_text(f'''immich:
  serverApiUrl: "http://127.0.0.1:{port}/api"
  apiKey: "{TEST_KEY}"
  allowInsecureHttp: true
watch:
  sources:
    - path: "{media}"
      syncMode: "uploadAll"
      deleteAfterUpload: false
      extensions: [".png"]
  batchIntervalSeconds: 1
logging:
  target: "file"
  logDirectory: "{profile / 'data/interop-logs'}"
''')
    shutil.copyfile(config, out / 'shipping-upload.yaml')
    log = out / 'shipping-upload.log'
    shipping = checked_start(stack, ['flatpak', 'run', '--user', '--branch=master', APP], log)
    xid = wait_for(lambda: check_alive(shipping, log) or display.visible(), 20, 'No configured shipping window')
    original = details['shipping'] = witness(shipping, window(display, xid), pins, report, out, 'configured-shipping')
    pid = original['gui']['pid']
    lifetime = pidfd(stack, pid)
    def held():
        check_alive(shipping, log)
        return server.received.is_set()
    try:
        wait_for(held, 28, 'The signed worker did not upload the expected image')
        observed, = server.uploads
        require(observed['client'][0] == '127.0.0.1' and observed['server'] == server.server_address,
                'Expected both endpoints of the private loopback peer')
        original_socket = client_socket(pid, observed)
        endpoint = Path(f'/proc/{pid}/root') / original['paths']['XDG_RUNTIME_DIR'].lstrip('/') / 'immich-folder-watch.sock'
        runtime = os.open(endpoint.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        stack.callback(os.close, runtime)
        before = endpoint.lstat()
        require(stat.S_ISSOCK(before.st_mode) and not owner(bus, NAME) and not workers() and not rows(database),
                'Unexpected writer, endpoint or prior upload history')
        details['launchNs'] = time.monotonic_ns()
        arguments = report['inventory']['transientRustArguments']
        require(report['positiveWorkerEnabled'] and arguments == [
            '--filesystem=/qa/files:ro', '--filesystem=/qa/worker-profile/config:ro', '--env=IFW_QA_BENCHMARK=1'],
            'Reuse the read-only inputs of the earlier successful installed worker')
        details['rustArguments'] = arguments
        result = subprocess.run(['flatpak', 'run', '--user', '--branch=test', *arguments, APP],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
        details['refusalNs'] = time.monotonic_ns()
        (out / 'shipping-upload-refusal.log').write_bytes(result.stdout)
        details.update(refusal=result.returncode, clientSocket=original_socket, serverPort=port,
                       remainingWorkers=workers(), endpoint=[before.st_dev, before.st_ino])
        require(result.returncode == 1 and b'Shipping activation endpoint is occupied' in result.stdout
                and not any(marker in result.stdout for marker in (b'READY ', b'INVENTORY_STARTED', b'ADAPTER '))
                and not owner(bus, NAME) and not details['remainingWorkers'] and not lifetime.poll(0)
                and identity(pid) == original['gui'] and os.path.samestat(before, endpoint.lstat())
                and original_socket == client_socket(pid, observed) and not rows(database),
                'Rust startup or the held shipping transfer changed unexpectedly')
        if backup:
            from installed_backup import start_snapshot, capture, restart
            reader = start_snapshot(database, out, port, backup, sha(config))
            stack.callback(reader.close)
        server.release.set()
        expected = [(str(media), FILENAME, ASSET_ID, len(IMAGE), 0, 0)]
        wait_for(lambda: check_alive(shipping, log) or rows(database) == expected, 20, 'No durable shipping upload row')
        if backup:
            details['rustBackup'] = capture(database, out, port, backup, sha(config), reader)
            require(not lifetime.poll(0) and identity(pid) == original['gui'], 'Signed apphost exited during live backup')
        quit_shipping(bus)
        details['exit'] = shipping.wait(timeout=15)
        wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=4).strip(),
                 5, 'A Flatpak process remained after configured shipping Quit')
        try:
            os.stat(endpoint.name, dir_fd=runtime, follow_symlinks=False)
        except FileNotFoundError:
            details['socketReleased'] = True
        else:
            raise RuntimeError('The configured shipping GUI retained its activation socket after Quit')
        require(not owner(bus, NAME) and not owner(bus, APP + '.Tray'), 'A desktop owner survived configured shipping Quit')
        details['instancesAndNamesReleased'] = True
        require(details['exit'] == 0 and lifetime.poll(1000) and len(server.uploads) == 1 and
                observed['requestNs'] < details['launchNs'] <= details['refusalNs'] < observed['responseNs'] and
                rows(database) == expected and image.read_bytes() == IMAGE and sha(config) == sha(out / 'shipping-upload.yaml'),
                'The configured worker did not commit its single upload and quit cleanly')
        # Retain a consistent SQLite snapshot even when the original used WAL.
        copy = out / 'configured-shipping.db'
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(copy)) as dest:
            source.backup(dest)
            require(dest.execute('PRAGMA journal_mode=DELETE').fetchone() == ('delete',), 'Cannot finalize standalone SQLite copy')
        require(rows(copy) == expected, 'The exported shipping history did not reopen')
        details.update(rows=expected, databaseSha256=sha(copy), mediaSha256=sha(image), passed=True)
        if backup:
            restart(stack, bus, display, pins, report, out, details, server, config, database, media)
    finally:
        server.release.set()
        for path in sorted((profile / 'data/interop-logs').glob('*.log')):
            shutil.copyfile(path, out / ('configured-' + path.name))
