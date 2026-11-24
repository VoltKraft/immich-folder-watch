"""Exercise the actual Rust GUI's ordinary startup while the signed shipping application owns its endpoint."""

from pathlib import Path
import stat
import subprocess

from gi.repository import Gio, GLib
from observe import identity, window, witness
from run import APP, require, sha
from session import checked_start, check_alive, wait_for

NAME = APP + '.RustAssessment'


def owner(bus, name):
    return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
                         GLib.Variant('(s)', (name,)), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()[0]


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
    bus.call_sync(APP + '.Tray', '/StatusNotifierItem/Menu', 'com.canonical.dbusmenu', 'Event',
                  GLib.Variant('(isvu)', (3, 'clicked', GLib.Variant('i', 0), 0)), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
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
    bus.call_sync(NAME, '/org/example/IfwGuiProbe', 'org.freedesktop.Application', 'ActivateAction',
                  GLib.Variant('(sava{sv})', ('quit', [], {})), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
    report['candidateExit'] = candidate.wait(timeout=14)
    require(report['candidateExit'] == 0 and lifetime.poll(1000) and 'DRAINED ' in log.read_text(), 'Candidate did not drain and quit')
    wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=4).strip(),
             6, 'A private application remained after both exited')
    report.update(profileAfterQuit=profile_files(), positiveWorkerEnabled=False, refusalObserved=True)
    require(report['profileAfterQuit'] == profile, 'The private application data differs after the clean GUI run')
