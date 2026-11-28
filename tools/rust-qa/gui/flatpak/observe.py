"""Observe the installed application's Flatpak, D-Bus, process and X11 identities."""

import configparser
from contextlib import ExitStack
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time

from flatpak_fixture import LAUNCH_BUS, start_launch_bus
from gi.repository import Gio, GLib
from session import checked_start, check_alive, private_session, wait_for
sys.path.insert(0, '/driver/worker')
from second_launch import identity, visible_pid
from run import APP, sha
import tray_menu


def flatpak_ps():
    output = subprocess.check_output(['flatpak', 'ps', '--columns=instance,pid,child-pid,application,arch,branch,commit,runtime-commit'],
                                     text=True, timeout=4)
    rows = []
    for line in output.splitlines():
        instance, wrapper, sandbox, app, arch, branch, commit, runtime = line.split('\t')
        rows.append(dict(instance=instance, wrapper=int(wrapper), sandbox=int(sandbox), app=app, arch=arch,
                         branch=branch, commit=commit, runtime=runtime))
    return rows


def dbus_call(bus, method, name):
    return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', method,
                         GLib.Variant('(s)', (name,)), None, Gio.DBusCallFlags.NO_AUTO_START, 2000, None).unpack()[0]


def owner(bus):
    name = dbus_call(bus, 'GetNameOwner', APP)
    return {'name': name, 'proxyPid': dbus_call(bus, 'GetConnectionUnixProcessID', name)}


def launch_line(log):
    lines = re.findall(r'^FLATPAK_LAUNCH instance=(\d+) pid=(\d+) socket=(/run/flatpak/bus|/run/user/0/bus) commit=([0-9a-f]{64})$',
                       log.read_text(), flags=re.MULTILINE)
    if len(lines) != 1:
        raise RuntimeError('Missing unique in-sandbox Flatpak launch identity')
    instance, pid, socket, commit = lines[0]
    return {'instance': instance, 'namespacePid': int(pid), 'proxySocket': socket, 'commit': commit}


def process_witness(primary, log, bus, inputs, installed, out):
    row, = flatpak_ps()
    original = owner(bus)
    proxy = identity(original['proxyPid'])
    marker = launch_line(log)
    arch = inputs['architecture']
    if (row['wrapper'] != primary.pid or row['app'] != APP or row['arch'] != arch
            or row['branch'] != 'test' or row['instance'] != marker['instance']
            or not all(len(short) >= 12 and full.startswith(short) for short, full in
                       ((row['commit'], installed['commit']), (row['runtime'], inputs['platform']['commit'])))
            or marker['commit'] != installed['commit'] or proxy['executable'] != '/usr/bin/xdg-dbus-proxy'
            or sha(Path('/proc') / str(proxy['pid']) / 'exe') != inputs['commands'][proxy['executable']]):
        raise RuntimeError('The Flatpak instance or session-bus proxy differs from the launch')
    sandbox = identity(row['sandbox'])
    if sandbox['parent'] != primary.pid:
        raise RuntimeError('The native sandbox supervisor is outside the primary launch')
    children = Path(f'/proc/{row["sandbox"]}/task/{row["sandbox"]}/children').read_text().split()
    candidates = [identity(int(pid)) for pid in children]
    gui, = [p for p in candidates if p['executable'] == '/app/bin/native-gui-assessment']
    proc = Path('/proc') / str(gui['pid'])
    field, = [line for line in (proc / 'status').read_text().splitlines() if line.startswith('NSpid:')]
    ns_pids = [int(v) for v in field.split()[1:]]
    ns = os.readlink(proc / 'ns/pid')
    image = sha(proc / 'exe')
    if (ns_pids != [gui['pid'], marker['namespacePid']] or ns == os.readlink('/proc/self/ns/pid')
            or ns != os.readlink(f'/proc/{sandbox["pid"]}/ns/pid') or gui['pid'] == proxy['pid']
            or image != inputs['guiSha256']):
        raise RuntimeError('The actual native GUI differs from the sandboxed executable or PID namespace')
    base = proc / 'root'
    libraries = {row.split(None, 5)[-1] for row in (proc / 'maps').read_text().splitlines()
                 if row.endswith('/libvulkan_lvp.so')}
    if len(libraries) != 1:
        raise RuntimeError('The live process must map exactly one llvmpipe Vulkan driver')
    library = libraries.pop()
    native_gl = inputs['gl']
    icd = native_gl['icdSandboxPath']
    driver_digest = sha(base / library.lstrip('/'))
    icd_digest = sha(base / icd.lstrip('/'))
    if (library != native_gl['driverSandboxPath'] or driver_digest != native_gl['driverSha256']
            or icd_digest != native_gl['icdSha256']):
        raise RuntimeError('The loaded Mesa library or installed Vulkan ICD differs from the native GL extension')
    contents = (base / '.flatpak-info').read_bytes()
    (out / 'primary.flatpak-info').write_bytes(contents)
    info = configparser.ConfigParser(interpolation=None)
    info.optionxform = str
    info.read_string(contents.decode())
    inst = info['Instance']
    context = info['Context']
    link = os.readlink(base / 'tmp/session-bus')
    target = (base / marker['proxySocket'].lstrip('/')).stat()
    desktop = Path('/tmp/session-bus').stat()
    extension = native_gl['ref'].split('/')[1] + '=' + native_gl['commit']
    if (info['Application']['name'] != APP or info['Application']['runtime'] != inputs['platform']['ref']
            or inst['instance-id'] != row['instance'] or inst['arch'] != arch
            or inst['app-commit'] != installed['commit'] or inst['runtime-commit'] != inputs['platform']['commit']
            or inst['runtime-extensions'] != extension or inst['branch'] != 'test'
            or not inst.getboolean('session-bus-proxy') or not inst.getboolean('system-bus-proxy')
            or dict(context) != {'shared': 'ipc;', 'sockets': 'x11;'}
            or dict(info['Session Bus Policy']) != {'org.kde.StatusNotifierWatcher': 'talk'}
            or (info.has_section('System Bus Policy') and len(info['System Bus Policy']) > 0)
            or link != marker['proxySocket'] or not stat.S_ISSOCK(target.st_mode)
            or (target.st_dev, target.st_ino) == (desktop.st_dev, desktop.st_ino)):
        raise RuntimeError('The running Flatpak does not have the expected deployment, proxy or sandbox policy')
    return dict(flatpak=row, dbusOwner=original, proxy=proxy, wrapper=identity(primary.pid), sandbox=sandbox,
                gui=gui, guiSha256=image, namespacePids=ns_pids, pidNamespace=ns, inSandboxLaunch=marker,
                loadedDriver={'sandboxPath': library, 'sha256': driver_digest, 'icdPath': icd, 'icdSha256': icd_digest},
                busSocketInodes={'desktop': desktop.st_ino, 'proxy': target.st_ino},
                flatpakInfoSha256=sha(out / 'primary.flatpak-info'))


def run(report, inputs, out):
    with ExitStack() as stack:
        display, server = private_session(stack)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        report['xserver'] = server
        report['launchBus'] = start_launch_bus(stack, bus)
        if inputs['trayMenu']:
            trace = tray_menu.monitor(stack, out)
        watcher_log = out / 'watcher.log'
        watcher = checked_start(stack, [sys.executable, '-B', '/app/watcher.py'], watcher_log)
        wait_for(lambda: check_alive(watcher, watcher_log) or 'WATCHER_READY' in watcher_log.read_text(), 5, 'Missing watcher')
        command = ['env', 'DBUS_SYSTEM_BUS_ADDRESS=' + LAUNCH_BUS, 'flatpak', '--verbose', 'run', '--user', '--branch=test', APP]
        log = out / 'primary.log'
        primary = checked_start(stack, command, log)
        xid = wait_for(lambda: check_alive(primary, log) or display.visible(), 20, 'The primary did not map its X11 window')
        before = report['primary'] = process_witness(primary, log, bus, inputs, report['installation'], out)
        marker = before['inSandboxLaunch']
        report['originalXid'] = xid
        if (visible_pid(xid) != marker['namespacePid'] or not re.search('^READY Visible Available$', log.read_text(), re.M)
                or f'REGISTERED {APP} {before["dbusOwner"]["name"]}' not in watcher_log.read_text()):
            raise RuntimeError('The original window, owner or tray registration differs')
        pids = [before[k]['pid'] for k in ('wrapper', 'sandbox', 'gui', 'proxy')]
        fds = {}
        poll = select.poll()
        for pid in pids:
            fd = os.pidfd_open(pid)
            stack.callback(os.close, fd)
            poll.register(fd, select.POLLIN)
            fds[fd] = pid
        target = before['dbusOwner']['name']
        def quit_primary(via_menu=False):
            if 'cleanup' in report:
                return
            cleanup = report['cleanup'] = {'passed': False, 'quitDestination': APP if via_menu else target,
                                           'method': 'Event' if via_menu else 'ActivateAction'}
            try:
                if (primary.poll() is not None or poll.poll(0)
                        or owner(bus) != before['dbusOwner']):
                    raise RuntimeError('The original process or its bus proxy is unavailable during cleanup')
                if via_menu:
                    tray_menu.click(bus, report['trayMenu']['menuPath'], 3)
                else:
                    bus.call_sync(target, '/org/example/IfwGuiProbe', 'org.freedesktop.Application', 'ActivateAction',
                                  GLib.Variant('(sava{sv})', ('quit', [], {})), None,
                                  Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
                report['primaryExit'] = primary.wait(timeout=12)
                exited = set()
                def drained():
                    exited.update(fds[fd] for fd, _ in poll.poll(0))
                    return exited == set(pids) and not dbus_call(bus, 'NameHasOwner', APP) and not flatpak_ps()
                wait_for(drained, 8, 'A GUI process, bus name or Flatpak instance survived Quit')
                cleanup.update(exitedPids=sorted(exited), flatpakInstances=flatpak_ps(),
                               drained=bool(re.search(r'^DRAINED passes=[1-9]\d*$', log.read_text(), re.M)))
                cleanup['passed'] = report['primaryExit'] == 0 and cleanup['drained'] and display.visible() is None
            except Exception as error:
                cleanup['error'] = str(error)
        stack.callback(quit_primary)
        instances = {marker['instance']}
        report['secondary'] = []
        for index, arguments in enumerate(([], ['--background']), start=1):
            display.request_close(xid)
            wait_for(lambda: check_alive(primary, log) or (
                display.visible() is None and log.read_text().splitlines().count('WINDOW_HIDDEN') == index),
                8, 'The primary did not hide its original XID')
            leaf = out / ('second-background.log' if arguments else 'second-ordinary.log')
            trial = {'arguments': arguments, 'hiddenXid': xid, 'samples': 0}
            report['secondary'].append(trial)
            child = checked_start(stack, [*command, *arguments], leaf)
            deadline = time.monotonic() + 15
            while True:
                trial['samples'] += 1
                polled = child.poll()
                if poll.poll(0) or owner(bus) != before['dbusOwner']:
                    raise RuntimeError('The primary process tree or its unique D-Bus owner changed')
                current = display.visible()
                if current is not None and current != xid:
                    raise RuntimeError('A second X11 window appeared')
                if polled is not None and (polled != 0 or current == xid):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Second launch did not exit and reopen its primary')
                time.sleep(.025)
            after = launch_line(leaf)
            replies = [line for line in leaf.read_text().splitlines() if line.startswith(('SECONDARY_ACTIVATED', 'READY ', 'DRAINED '))]
            trial.update(exit=polled, outerLauncherPid=child.pid, inSandboxLaunch=after, reopenedXid=display.visible(),
                         windowNamespacePid=visible_pid(xid), primaryOwner=owner(bus), replies=replies)
            if (polled != 0 or trial['windowNamespacePid'] != marker['namespacePid'] or after['instance'] in instances
                    or after['commit'] != marker['commit']
                    or replies != ['SECONDARY_ACTIVATED owner=' + before['dbusOwner']['name']]):
                raise RuntimeError('The secondary or reopened XID does not match the original installed application')
            instances.add(after['instance'])

            def only_primary():
                rows = trial['instancesAfterLaunch'] = flatpak_ps()
                if before['flatpak'] not in rows or any(row['instance'] not in instances for row in rows):
                    raise RuntimeError('The primary Flatpak instance changed during cleanup')
                if len(rows) > 1:
                    time.sleep(.1)
                return len(rows) == 1

            wait_for(only_primary, 8, 'The secondary Flatpak instance survived its launcher')
        if inputs['trayMenu']:
            menu = report['trayMenu'] = {'hiddenXid': xid}
            display.request_close(xid)
            wait_for(lambda: check_alive(primary, log) or (
                display.visible() is None and log.read_text().splitlines().count('WINDOW_HIDDEN') == 3),
                8, 'The original XID did not hide before the watcher handover')

            def require_hidden():
                if poll.poll(0) or owner(bus) != before['dbusOwner'] or display.visible() is not None:
                    raise RuntimeError('The original hidden GUI or its bus proxy changed before menu Open')

            tray_menu.replace_watcher(stack, bus, dbus_call, watcher, watcher_log, log, target, out, menu, require_hidden)
            tray_menu.read_layout(bus, dbus_call, menu)
            require_hidden()
            tray_menu.click(bus, menu['menuPath'], 1)
            menu['reopenedXid'] = wait_for(lambda: check_alive(primary, log) or display.visible(), 8,
                                           'The menu Open event did not reopen the hidden GUI')
            menu.update(windowNamespacePid=visible_pid(xid), primaryOwner=owner(bus), instances=flatpak_ps())
            if (poll.poll(0) or menu['reopenedXid'] != xid or menu['windowNamespacePid'] != marker['namespacePid']
                    or menu['primaryOwner'] != before['dbusOwner'] or menu['instances'] != [before['flatpak']]):
                raise RuntimeError('Menu Open did not retain the original window, proxy and Flatpak instance')
            quit_primary(via_menu=True)
            if report['cleanup']['passed']:
                tray_menu.verify_trace(trace, menu, target)
        stack.close()
        if not report['cleanup']['passed']:
            raise RuntimeError('The installed GUI did not drain cleanly')
