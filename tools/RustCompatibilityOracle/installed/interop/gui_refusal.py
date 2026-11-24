"""Exercise the actual Rust GUI's ordinary startup while the signed shipping application owns its endpoint."""

from pathlib import Path
import os
import re
import stat
import subprocess

from gi.repository import Gio, GLib
from observe import app_identity, identity, launching_app, window, witness
from run import APP, require, sha
from session import checked_start, check_alive, wait_for

NAME = APP + '.RustAssessment'


def owner(bus, name):
    return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
                         GLib.Variant('(s)', (name,)), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()[0]


def observe_later_launches(stack, bus, display, pins, report, out, command, primary, first_window, lifetime):
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
    oldlog = out / 'later-shipping.log'
    old = checked_start(stack, [*command, '--branch=master', APP], oldlog)
    pid = wait_for(lambda: check_alive(old, oldlog) or launching_app(old), 8, 'Could not identify the later shipping apphost')
    old_lifetime = pidfd(stack, pid)
    later['shipping'] = app_identity(old, pid, pins, report, out, 'later-shipping')
    old_directory = later['shipping']['directoryIdentity']['XDG_RUNTIME_DIR']
    observed_directory = runtime.stat()
    require(old_directory == [observed_directory.st_dev, observed_directory.st_ino] and
            later['shipping']['directoryIdentity'] == report['original']['directoryIdentity'],
            'The later shipping executable used a different private runtime or profile')
    old_runtime = Path(f'/proc/{pid}/root') / later['shipping']['paths']['XDG_RUNTIME_DIR'].lstrip('/')
    later['socketSeenByShipping'] = socket_id(old_runtime / endpoint.name)
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
        quit_shipping(bus)
    later.update(shippingExit=old.wait(timeout=10), shippingExited=bool(old_lifetime.poll(1000)),
                 socketAfterShipping=socket_id(endpoint), stillHidden=display.visible() is None)
    require(later['shippingExit'] == 0 and later['shippingExited'] and later['stillHidden']
            and not owner(bus, APP + '.Tray'), 'The isolated shipping launch did not finish cleanly')
    result = subprocess.run([*command, '--branch=test', APP], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
    (out / 'later-rust.log').write_bytes(result.stdout)
    wait_for(lambda: check_alive(primary, out / 'released.log') or display.visible() == xid, 10, 'Rust secondary failed to reopen the first window')
    later.update(rustSecondaryExit=result.returncode, reopenedWindow=window(display, xid), socketAfterRust=socket_id(endpoint),
                 ownerAfterRust=read_owner(), primaryAfterRust=identity(native))
    require(result.returncode == 0 and (f'SECONDARY_ACTIVATED owner={initial_owner}'.encode() in result.stdout)
            and later['reopenedWindow'] == first_window and later['primaryAfterRust'] == original_gui
            and later['ownerAfterRust'] == initial_owner and not lifetime.poll(0), 'Rust secondary failed to preserve the original primary')
    later['exclusive'] = (route == 'exited' and before is not None
                          and before == later['socketSeenByShipping'] == later['socketAfterShipping'] == later['socketAfterRust'])


def quit_shipping(bus):
    bus.call_sync(APP + '.Tray', '/StatusNotifierItem/Menu', 'com.canonical.dbusmenu', 'Event',
                  GLib.Variant('(isvu)', (3, 'clicked', GLib.Variant('i', 0), 0)), None,
                  Gio.DBusCallFlags.NO_AUTO_START, 3000, None)


def run(stack, bus, display, pins, report, out, gui_hash):
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
    quit_shipping(bus)
    report['originalExit'] = original.wait(timeout=12)
    require(report['originalExit'] == 0 and old_lifetime.poll(1000), 'The original GUI did not quit normally')
    log = out / 'released.log'
    candidate = checked_start(stack, arguments, log)
    new_xid = wait_for(lambda: check_alive(candidate, log) or (display.visible() if owner(bus, NAME) else None), 22, 'Rust did not show its window after the original quit')
    new_window = window(display, new_xid)
    native = new_window['xserverClientPid']
    lifetime = pidfd(stack, native)
    report['runningAfterRelease'] = dict(gui=identity(native), window=new_window, executable=sha(Path(f'/proc/{native}/exe')))
    require(report['runningAfterRelease']['executable'] == gui_hash and 'READY ' in log.read_text(), 'The released GUI differs from the candidate')
    runtime_handle = os.open(f'/proc/{native}/root/run/user/0', os.O_DIRECTORY | os.O_RDONLY | os.O_CLOEXEC)
    stack.callback(os.close, runtime_handle)
    observe_later_launches(stack, bus, display, pins, report, out, command, candidate, new_window, lifetime)
    bus.call_sync(NAME, '/org/example/IfwGuiProbe', 'org.freedesktop.Application', 'ActivateAction',
                  GLib.Variant('(sava{sv})', ('quit', [], {})), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
    report['candidateExit'] = candidate.wait(timeout=14)
    require(report['candidateExit'] == 0 and lifetime.poll(1000) and 'DRAINED ' in log.read_text(), 'Candidate did not drain and quit')
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
    quit_shipping(bus)
    report['restoredShippingExit'] = restored.wait(timeout=12)
    require(report['restoredShippingExit'] == 0 and restored_lifetime.poll(1000), 'The restored original did not quit normally')
    wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=4).strip(),
             6, 'A private application remained after both exited')
    report.update(profileAfterQuit=profile_files(), positiveWorkerEnabled=False, refusalObserved=True)
    require(report['profileAfterQuit'] == profile, 'The private application data differs after the clean GUI run')
    require(report['laterLaunches']['exclusive'], 'The installed Rust primary did not exclude the later shipping primary')
    require(report['acceptedConnectionsDuringRun'] is not None and report['acceptedConnectionsDuringRun'] > 0,
            'The Rust listener did not observe a connection during the later shipping launch')
