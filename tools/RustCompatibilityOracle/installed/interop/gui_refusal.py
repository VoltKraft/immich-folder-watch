"""Exercise the actual Rust GUI's ordinary startup while the signed shipping application owns its endpoint."""

from pathlib import Path
import errno
import fcntl
import os
import re
import signal
import socket
import stat
import struct
import subprocess
import threading
import time

from gi.repository import Gio, GLib
from observe import app_identity, identity, launching_app, window, witness
from run import APP, require, sha
from session import checked_start, check_alive, wait_for

NAME = APP + '.RustAssessment'
WORKER_EXE = '/app/bin/ifw-performance-worker'
MENU_PATH = '/StatusNotifierItem/Menu'
MENU_INTERFACE = 'com.canonical.dbusmenu'


def watch_directory_read(fd):
    # Linux x86_64 and aarch64 use these UAPI values. Python 3.12 omits both names.
    set_owner = getattr(fcntl, 'F_SETOWN_EX', 15)
    thread_owner = getattr(fcntl, 'F_OWNER_TID', 0)
    fcntl.fcntl(fd, set_owner, struct.pack('=ii', thread_owner, threading.get_native_id()))
    fcntl.fcntl(fd, fcntl.F_SETSIG, signal.SIGRTMIN)
    fcntl.fcntl(fd, fcntl.F_NOTIFY, fcntl.DN_ACCESS)


def workers():
    found = []
    for proc in Path('/proc').iterdir():
        if proc.name.isdecimal():
            try:
                if os.readlink(proc / 'exe') == WORKER_EXE:
                    found.append(identity(int(proc.name)))
            except (FileNotFoundError, ProcessLookupError):
                continue
    return sorted(found, key=lambda entry: entry['pid'])


class Inventory:
    def __init__(self, info, out, report):
        from assess import WORKER_CONFIG
        from session import fresh_profile
        require(out == Path('/qa') and not Path('/proc/net/route').read_text().splitlines()[1:],
                'Inventory requires the routed-off private desktop')
        self.config = Path(WORKER_CONFIG)
        self.media = out / 'files'
        self.media.mkdir(mode=0o700)
        self.leaf = self.media / 'album'
        self.leaf.mkdir(mode=0o700)
        fresh_profile(self.config.parent, self.media)
        self.log = out / 'released.log'
        self.inputs = info
        self.arguments = [f'--filesystem={path}:ro' for path in (self.media, self.config)] + ['--env=IFW_QA_BENCHMARK=1']
        self.report = report['inventory'] = dict(inputs=info, transientRustArguments=self.arguments,
            configSha256=sha(self.config / 'immich-folder-watch/config.yaml'), observations=[])

    def attach(self, stack, primary):
        from assess import pidfd
        self.primary = primary
        self.worker, = wait_for(workers, 8, 'The installed GUI did not start its worker')
        pid = self.worker['pid']
        proc = Path('/proc') / str(pid)
        require(self.worker['parent'] == primary and sha(proc / 'exe') == self.inputs['binary'],
                'Expected the actual reviewed direct inventory child of the installed GUI')
        self.lifetime = pidfd(stack, pid)
        root = proc / 'root'
        env = dict(item.split(b'=', 1) for item in (proc / 'environ').read_bytes().split(b'\0') if b'=' in item)
        required = {'IFW_QA_ISOLATED': '1', 'IFW_QA_BENCHMARK': '1', 'XDG_CONFIG_HOME': str(self.config),
                    'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/tmp/session-bus', 'FLATPAK_ID': APP}
        require(all(env.get(k.encode()) == v.encode() for k, v in required.items()), 'Worker environment differs')
        mounts = dict((f[4], f[5]) for f in (s.split() for s in (proc / 'mountinfo').read_text().splitlines()) if f[4].startswith('/qa/'))
        require(set(mounts) == {str(self.config), str(self.media)} and all('ro' in v.split(',') for v in mounts.values()) and
                not (root / 'qa/inputs.json').exists() and
                all(os.path.samestat(p.stat(), (root / p.relative_to('/')).stat()) for p in (self.media, self.config)),
                'Expected only the two read-only synthetic input mounts')
        link = os.readlink(root / 'tmp/session-bus')
        require(link in ('/run/user/0/bus', '/run/flatpak/bus') and stat.S_ISSOCK((root / link.lstrip('/')).stat().st_mode)
                and (root / 'app/ifw-performance-worker').is_file() and sha(root / 'app/ifw-performance-worker') == self.inputs['launcher']
                and os.readlink(proc / 'ns/net') == os.readlink('/proc/self/ns/net'), 'Worker bus, network or launcher differs')
        with socket.socket() as local:
            code = local.connect_ex(('127.0.0.1', 9))
        require(code == errno.ECONNREFUSED, 'Expected ECONNREFUSED at the private loopback endpoint')
        self.report.update(worker=self.worker, primary=identity(primary), mounts=mounts, environment=required, busTarget=link,
                           privateNetwork=os.readlink(proc / 'ns/net'), offlineLoopbackErrno=code)
        wait_for(lambda: len(self.sweeps()) >= 2, 12, 'Missing the two initial inventory sweeps')
        require(self.sweeps()[:2] == [(0, 0, 0), (0, 0, 1)], 'The synthetic album did not start empty')
        self.check('initial')

    def sweeps(self):
        return [tuple(map(int, m)) for m in re.findall(r'^INVENTORY_COMPLETE files=(\d+) changed=(\d+) pass=(\d+)$',
                                                        self.log.read_text(), re.MULTILINE)]

    def check(self, phase):
        require(not self.lifetime.poll(0) and workers() == [self.worker] and identity(self.primary) == self.report['primary'],
                'The reviewed worker or its primary changed at ' + phase)
        self.report['observations'].append(dict(phase=phase, primary=self.primary, workers=[self.worker['pid']]))

    def discover(self, phase, count):
        previous = self.sweeps()[-1][2]
        # A one-shot, inode-bound Linux directory notification also works through the worker's read-only bind.
        fd = os.open(self.leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        selected = os.fstat(fd)
        signals = {signal.SIGRTMIN}
        saved = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        try:
            watch_directory_read(fd)
            start = time.monotonic()
            with (self.leaf / (phase + '.jpg')).open('xb') as file:
                file.write(phase.encode())
            read = signal.sigtimedwait(signals, 12)
            accessed = time.monotonic() - start
            require(read and read.si_code > 0, 'No independent Linux directory-access notification for ' + phase)
            sweep = wait_for(lambda: next((r for r in self.sweeps() if r[2] > previous and r[:2] == (count, 1)), None),
                             7, 'The installed worker did not discover ' + phase)
        finally:
            os.close(fd)
            signal.sigtimedwait(signals, 0)
            signal.pthread_sigmask(signal.SIG_SETMASK, saved)
        require(os.path.samestat(selected, self.leaf.stat()), 'The observed album identity changed')
        self.check(phase)
        self.report[phase] = dict(file=phase + '.jpg', sweep=sweep, seconds=round(time.monotonic()-start, 4),
                                  device=selected.st_dev, inode=selected.st_ino, directoryReadSeconds=accessed,
                                  signal=read.si_signo, code=read.si_code, band=read.si_band)

    def drained(self):
        self.report['workerExited'] = bool(self.lifetime.poll(1000))
        self.report['sweeps'] = self.sweeps()
        require(self.report['workerExited'] and not workers() and self.log.read_text().splitlines().count('INVENTORY_STARTED') == 1
                and sha(self.config / 'immich-folder-watch/config.yaml') == self.report['configSha256'],
                'Expected one drained worker and its unchanged synthetic configuration')


def owner(bus, name):
    return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
                         GLib.Variant('(s)', (name,)), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()[0]


def observe_later_launches(stack, bus, display, pins, report, out, command, primary, first_window, lifetime, inventory=None):
    """Launch each installed ref while the unconfigured Rust GUI is hidden on the private X server."""
    from assess import pidfd
    xid = first_window['xid']
    native = first_window['xserverClientPid']
    proc_root = Path(f'/proc/{native}/root')
    runtime = proc_root / 'run/user/0'
    endpoint = runtime / 'immich-folder-watch.sock'
    def socket_id(name):
        try:
            node = name.lstat()
        except FileNotFoundError:
            return None
        require(stat.S_ISSOCK(node.st_mode), 'Unexpected entry at the private runtime endpoint')
        return [node.st_dev, node.st_ino]

    before = socket_id(endpoint)
    def read_owner():
        return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                             'GetNameOwner', GLib.Variant('(s)', (NAME,)), None,
                             Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()[0]
    initial_owner = read_owner()
    original_gui = identity(native)
    later = report['laterLaunches'] = dict(candidateSocket=before, candidateOwner=initial_owner)
    display.request_close(xid)
    wait_for(lambda: check_alive(primary, out / 'released.log') or display.visible() is None, 8, 'Rust window did not hide')
    require(not owner(bus, APP + '.Tray'), 'Shipping GUI still holds its tray name')
    if inventory:
        inventory.attach(stack, native)
        inventory.discover('before-shipping', 1)
    oldlog = out / 'later-shipping.log'
    old = checked_start(stack, [*command, '--branch=master', APP], oldlog)
    pid = wait_for(lambda: check_alive(old, oldlog) or launching_app(old), 8, 'Could not identify the later shipping apphost')
    old_lifetime = pidfd(stack, pid)
    if inventory:
        root_fd = os.open(f'/proc/{pid}/root', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            for path in (inventory.media, inventory.config):
                try:
                    os.stat(path.relative_to('/'), dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise RuntimeError('The shipping application received candidate-only workload grants')
        finally:
            os.close(root_fd)
        inventory.report['shippingInputGrantsAbsent'] = True
    later['shipping'] = app_identity(old, pid, pins, report, out, 'later-shipping')
    old_directory = later['shipping']['directoryIdentity']['XDG_RUNTIME_DIR']
    observed_directory = runtime.stat()
    require(old_directory == [observed_directory.st_dev, observed_directory.st_ino] and
            later['shipping']['directoryIdentity'] == report['original']['directoryIdentity'],
            'The later shipping executable used a different private runtime or profile')
    old_runtime = Path(f'/proc/{pid}/root') / later['shipping']['paths']['XDG_RUNTIME_DIR'].lstrip('/')
    later['socketSeenByShipping'] = socket_id(old_runtime / endpoint.name)
    if inventory:
        inventory.check('shipping-identified')
    def old_outcome():
        require(not lifetime.poll(0), 'Rust exited during the later shipping launch')
        visible = display.visible()
        if visible is not None:
            return ('window', visible)
        if owner(bus, APP + '.Tray'):
            return ('tray', None)
        if old.poll() is not None:
            return ('exited', None)
    route, shown = wait_for(old_outcome, 15, 'The later shipping launch did not resolve')
    later.update(legacyOutcome=route, observedWindow=window(display, shown) if shown is not None else None)
    if route != 'exited':
        # A separate primary is a real failure. Quit it through its own menu before collecting cleanup.
        wait_for(lambda: owner(bus, APP + '.Tray'), 6, 'Second shipping primary has no tray')
        later['shippingQuit'] = quit_shipping(bus, old, old_lifetime, later['shipping'], out)
    later.update(shippingExit=old.wait(timeout=10), shippingExited=bool(old_lifetime.poll(1000)),
                 socketAfterShipping=socket_id(endpoint), stillHidden=display.visible() is None)
    require(later['shippingExit'] == 0 and later['shippingExited'] and later['stillHidden']
            and not owner(bus, APP + '.Tray'), 'The isolated shipping launch did not finish cleanly')
    if inventory:
        inventory.discover('after-shipping', 2)
    result = subprocess.run([*command, '--branch=test', *(inventory.arguments if inventory else []), APP],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
    (out / 'later-rust.log').write_bytes(result.stdout)
    wait_for(lambda: check_alive(primary, out / 'released.log') or display.visible() == xid, 10, 'Rust secondary failed to reopen the first window')
    later.update(rustSecondaryExit=result.returncode, reopenedWindow=window(display, xid), socketAfterRust=socket_id(endpoint),
                 ownerAfterRust=read_owner(), primaryAfterRust=identity(native))
    require(result.returncode == 0 and (f'SECONDARY_ACTIVATED owner={initial_owner}'.encode() in result.stdout)
            and later['reopenedWindow'] == first_window and later['primaryAfterRust'] == original_gui
            and later['ownerAfterRust'] == initial_owner and not lifetime.poll(0), 'Rust secondary failed to preserve the original primary')
    if inventory:
        require(not any(mark in result.stdout for mark in (b'READY ', b'INVENTORY_STARTED', b'INVENTORY_COMPLETE')),
                'The second worker-enabled Rust launch started a new supervisor or inventory')
        inventory.check('after-rust-secondary')
    later['exclusive'] = (route == 'exited' and before is not None
                          and before == later['socketSeenByShipping'] == later['socketAfterShipping'] == later['socketAfterRust'])


def quit_delivery(reply, serial, receiver, sender):
    require(serial > 0 and reply.get_reply_serial() == serial and reply.get_destination() == sender,
            'The bus reply does not identify the issued shipping Quit click')
    if reply.get_message_type() == Gio.DBusMessageType.METHOD_RETURN:
        require(reply.get_sender() == receiver and not reply.get_signature(), 'Unexpected shipping menu acknowledgement')
        return 'menu-reply'
    # The private dbus-daemon emits this reply for a routed, pending method when its recipient disconnects.
    # Timeouts, a target gone before routing, proxy denials and application-generated errors remain failures.
    body = reply.get_body()
    require(reply.get_message_type() == Gio.DBusMessageType.ERROR and reply.get_sender() == 'org.freedesktop.DBus'
            and reply.get_error_name() == 'org.freedesktop.DBus.Error.NoReply' and body is not None
            and body.get_type_string() == '(s)' and body.unpack() == ('Message recipient disconnected from message bus without replying',),
            'The shipping Quit click lacks a menu reply or a routed recipient-disconnected reply')
    return 'recipient-disconnected'


def shipping_proxy(bus, receiver, proc):
    addresses = [value.removeprefix(b'DBUS_SESSION_BUS_ADDRESS=unix:path=').decode()
                 for value in (proc / 'environ').read_bytes().split(b'\0')
                 if value.startswith(b'DBUS_SESSION_BUS_ADDRESS=unix:path=')]
    require(len(addresses) == 1, 'The original signed GUI must use a single private session bus socket')
    address, = addresses
    root = proc / 'root'
    if address == '/tmp/session-bus':
        address = os.readlink(root / 'tmp/session-bus')
    require(address in ('/run/flatpak/bus', '/run/user/0/bus'), 'Unexpected signed Flatpak bus proxy socket')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(3)
        peer.connect(str(root / address.lstrip('/')))
        proxy_pid, _, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    reported_pid, = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                                  'GetConnectionUnixProcessID', GLib.Variant('(s)', (receiver,)), None,
                                  Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()
    proxy = identity(proxy_pid)
    require(reported_pid == proxy_pid and proxy['executable'] == '/usr/bin/xdg-dbus-proxy',
            'The menu connection does not belong to the original signed GUI session bus proxy')
    return dict(proxy=proxy, proxySocket=address, busReportedPid=reported_pid)


def shipping_menu(bus, process, lifetime, app, out):
    tray = APP + '.Tray'
    receiver, = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                              'GetNameOwner', GLib.Variant('(s)', (tray,)), None,
                              Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()
    require(Gio.dbus_is_unique_name(receiver) and identity(process.pid) == app['wrapper']
            and identity(app['gui']['pid']) == app['gui'] and not lifetime.poll(0),
            'The original signed application is required before the Quit click')
    proxy = shipping_proxy(bus, receiver, Path('/proc') / str(app['gui']['pid']))
    wait_for(lambda: f'REGISTERED {tray} {receiver}' in (out / 'watcher.log').read_text().splitlines(),
             5, 'The private watcher did not observe the original menu connection')
    label, = bus.call_sync(receiver, MENU_PATH, MENU_INTERFACE, 'GetProperty', GLib.Variant('(is)', (3, 'label')),
                           GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()
    require(label in ('Quit', 'Beenden'), 'The original shipping menu does not identify item 3 as Quit')
    return dict(receiver=receiver, **proxy, gui=app['gui']['pid'],
                instance=app['instance'], menuId=3, label=label)


def quit_shipping(bus, process, lifetime, app, out, worker_log=None):
    menu = shipping_menu(bus, process, lifetime, app, out)
    receiver = menu['receiver']
    offset = worker_log.stat().st_size if worker_log else None
    message = Gio.DBusMessage.new_method_call(receiver, MENU_PATH, MENU_INTERFACE, 'Event')
    message.set_flags(Gio.DBusMessageFlags.NO_AUTO_START)
    message.set_body(GLib.Variant('(isvu)', (3, 'clicked', GLib.Variant('i', 0), 0)))
    reply, serial = bus.send_message_with_reply_sync(message, Gio.DBusSendMessageFlags.NONE, 3000, None)
    delivery = quit_delivery(reply, serial, receiver, bus.get_unique_name())
    require(process.wait(timeout=15) == 0 and lifetime.poll(1000),
            'The original signed process did not exit normally after the Quit click')
    wait_for(lambda: not owner(bus, receiver) and not owner(bus, APP + '.Tray'), 5,
             'The original shipping menu or its private bus connection survived Quit')
    if worker_log:
        with worker_log.open('rb') as stream:
            stream.seek(offset)
            require(b'Folder watch worker received shutdown signal.' in stream.read(),
                    'The configured signed worker did not acknowledge shutdown after the Quit click')
    response = dict(sender=reply.get_sender(), destination=reply.get_destination(), replySerial=reply.get_reply_serial())
    if delivery == 'recipient-disconnected':
        response.update(error=reply.get_error_name(), reason=reply.get_body().unpack()[0])
    return dict(**menu, serial=serial, delivery=delivery, response=response, exit=0, workerShutdownObserved=worker_log is not None)


def run(stack, bus, display, pins, report, out, gui_hash, worker=None):
    from assess import pidfd
    watcher = out / 'watcher.log'
    watcher_process = checked_start(stack, ['/usr/bin/python3', '-B', '/watcher.py'], watcher)
    wait_for(lambda: check_alive(watcher_process, watcher) or 'WATCHER_READY' in watcher.read_text(), 5, 'No private status watcher')
    command = ['flatpak', 'run', '--user']
    original_log = out / 'shipping.log'
    original = checked_start(stack, [*command, '--branch=master', APP], original_log)
    xid = wait_for(lambda: check_alive(original, original_log) or display.visible(), 20, 'Missing original application window')
    first = report['original'] = witness(original, window(display, xid), pins, report, out, 'shipping')
    old_pid = first['gui']['pid']
    old_lifetime = pidfd(stack, old_pid)
    wait_for(lambda: check_alive(original, original_log) or 'REGISTERED ' in watcher.read_text(), 10, 'No original status menu')
    base = Path(f'/proc/{old_pid}/root')
    runtime = base / first['paths']['XDG_RUNTIME_DIR'].lstrip('/')
    endpoint = runtime / 'immich-folder-watch.sock'
    def endpoint_identity():
        item = endpoint.lstat()
        require(stat.S_ISSOCK(item.st_mode), 'The original application must own a normal socket')
        return [item.st_dev, item.st_ino]
    config = Path(first['paths']['XDG_CONFIG_HOME']) / 'immich-folder-watch'
    data = Path(first['paths']['XDG_DATA_HOME']) / 'immich-folder-watch'
    def profile_files():
        return {str(p): sha(p) for tree in (config, data) if tree.exists() for p in tree.rglob('*') if p.is_file()}
    before = report['originalEndpointBefore'] = endpoint_identity()
    marker = config / 'autostart-initialized'
    wait_for(lambda: check_alive(original, original_log) or marker.is_file(), 8, 'The shipping startup marker is missing')
    profile = report['profileBefore'] = profile_files()
    require(set(profile) == {str(marker)} and not owner(bus, NAME), 'Expected only the shipping startup marker and no candidate')
    arguments = [*command, '--branch=test', APP]
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
    (out / 'refused.log').write_bytes(result.stdout)
    report['candidateBusOwnerAfterOrdinary'] = owner(bus, NAME)
    require(not report['candidateBusOwnerAfterOrdinary'], 'The refused ordinary start retained the candidate bus name')
    requested = subprocess.run([*command, '--branch=test', '--env=IFW_QA_BENCHMARK=1', APP],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
    (out / 'worker-requested.log').write_bytes(requested.stdout)
    report['workerRequestedRefusal'] = dict(exit=requested.returncode, outputSha256=sha(out / 'worker-requested.log'))
    require(requested.returncode != 0 and requested.stdout == result.stdout,
            'Requesting the optional worker must produce the same pre-start refusal')
    report['refused'] = dict(exit=result.returncode, profileAfter=profile_files(), originalEndpointAfter=endpoint_identity(),
                             candidateBusOwner=owner(bus, NAME), originalIdentity=identity(old_pid),
                             originalWindow=window(display, display.visible()), oldAlive=not bool(old_lifetime.poll(0)))
    refusal = report['refused']
    require(result.returncode != 0 and b'Shipping activation endpoint is occupied' in result.stdout
            and not any(mark in result.stdout for mark in (b'READY ', b'ADAPTER ', b'INVENTORY_STARTED'))
            and refusal['oldAlive'] and not refusal['candidateBusOwner'] and refusal['originalIdentity'] == first['gui']
            and refusal['originalWindow'] == first['window'] and refusal['originalEndpointAfter'] == before
            and refusal['profileAfter'] == profile, 'The candidate did not refuse before startup with the original state intact')
    report['originalQuit'] = quit_shipping(bus, original, old_lifetime, first, out)
    report['originalExit'] = report['originalQuit']['exit']
    log = out / 'released.log'
    inventory = Inventory(worker, out, report) if worker else None
    candidate = checked_start(stack, [*command, '--branch=test', *(inventory.arguments if inventory else []), APP], log)
    new_xid = wait_for(lambda: check_alive(candidate, log) or (display.visible() if owner(bus, NAME) else None), 22, 'Rust did not show its window after the original quit')
    new_window = window(display, new_xid)
    native = new_window['xserverClientPid']
    lifetime = pidfd(stack, native)
    report['runningAfterRelease'] = dict(gui=identity(native), window=new_window, executable=sha(Path(f'/proc/{native}/exe')))
    require(report['runningAfterRelease']['executable'] == gui_hash and 'READY ' in log.read_text(), 'The released GUI differs from the candidate')
    runtime_handle = os.open(f'/proc/{native}/root/run/user/0', os.O_DIRECTORY | os.O_RDONLY | os.O_CLOEXEC)
    stack.callback(os.close, runtime_handle)
    observe_later_launches(stack, bus, display, pins, report, out, command, candidate, new_window, lifetime, inventory)
    bus.call_sync(NAME, '/org/example/IfwGuiProbe', 'org.freedesktop.Application', 'ActivateAction',
                  GLib.Variant('(sava{sv})', ('quit', [], {})), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
    report['candidateExit'] = candidate.wait(timeout=14)
    require(report['candidateExit'] == 0 and lifetime.poll(1000) and 'DRAINED ' in log.read_text(), 'Candidate did not drain and quit')
    if inventory:
        inventory.drained()
    counts = re.findall(r'^LEGACY_SOCKET_ACCEPTED ([0-9]+)$', log.read_text(), re.MULTILINE)
    report['acceptedConnectionsDuringRun'] = int(counts[0]) if len(counts) == 1 else None
    try:
        os.stat('immich-folder-watch.sock', dir_fd=runtime_handle, follow_symlinks=False)
    except FileNotFoundError:
        report['endpointAbsentAfterRustQuit'] = True
    else:
        raise RuntimeError('A legacy endpoint remained in the pinned runtime directory after Rust quit')
    require(not owner(bus, NAME), 'The Rust GUI retained its bus name after exit')
    restored_log = out / 'restored-shipping.log'
    restored = checked_start(stack, [*command, '--branch=master', APP], restored_log)
    shown = wait_for(lambda: check_alive(restored, restored_log) or display.visible(), 20, 'The original GUI did not return after Rust quit')
    restored_app = report['shippingAfterRustQuit'] = witness(restored, window(display, shown), pins, report, out, 'restored-shipping')
    restored_lifetime = pidfd(stack, restored_app['gui']['pid'])
    require(restored_app['directoryIdentity'] == first['directoryIdentity'], 'Restored application used a different profile or runtime directory')
    wait_for(lambda: check_alive(restored, restored_log) or owner(bus, APP + '.Tray'), 8, 'The restored original did not own its tray')
    report['restoredShippingQuit'] = quit_shipping(bus, restored, restored_lifetime, restored_app, out)
    report['restoredShippingExit'] = report['restoredShippingQuit']['exit']
    wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=4).strip(),
             6, 'A private application remained after both exited')
    report.update(profileAfterQuit=profile_files(), positiveWorkerEnabled=bool(inventory), refusalObserved=True)
    require(report['profileAfterQuit'] == profile, 'The private application data differs after the clean GUI run')
    require(report['laterLaunches']['exclusive'], 'The installed Rust primary did not exclude the later shipping primary')
    require(report['acceptedConnectionsDuringRun'] is not None and report['acceptedConnectionsDuringRun'] > 0,
            'The Rust listener did not observe a connection during the later shipping launch')
