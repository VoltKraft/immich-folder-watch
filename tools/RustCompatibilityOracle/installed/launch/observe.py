"""Observe the two unmodified application processes and their X11 clients from the private desktop."""

import configparser
from contextlib import ExitStack
import ctypes as c
import os
from pathlib import Path
import select
import subprocess
import sys
import time

from gi.repository import Gio, GLib
from run import APP, COMMIT, require, sha
from session import checked_start, check_alive, wait_for
from x11 import WindowAttributes, bind
sys.path.insert(0, '/driver/worker')
from second_launch import identity, visible_pid

HOST = '/app/lib/immich-folder-watch/immich-folder-watch'


class ClientSpec(c.Structure):
    _fields_ = [('client', c.c_ulong), ('mask', c.c_uint)]


class ClientValue(c.Structure):
    _fields_ = [('spec', ClientSpec), ('length', c.c_long), ('value', c.c_void_p)]


def window(display, xid):
    xres = c.CDLL('libXRes.so.1')
    query = bind(xres, 'XResQueryClientIds', c.c_int, c.c_void_p, c.c_long, c.POINTER(ClientSpec),
                 c.POINTER(c.c_long), c.POINTER(c.POINTER(ClientValue)))
    get_pid = bind(xres, 'XResGetClientPid', c.c_int, c.POINTER(ClientValue))
    free = bind(xres, 'XResClientIdsDestroy', None, c.c_long, c.POINTER(ClientValue))
    number, values = c.c_long(), c.POINTER(ClientValue)()
    query(display.display, 1, c.byref(ClientSpec(xid, 2)), c.byref(number), c.byref(values))
    try:
        require(number.value == 1, 'X-Resource did not identify a unique local client')
        pid = get_pid(values)
        require(pid > 0, 'The X server did not provide its local client PID')
    finally:
        if values:
            free(number, values)
    properties = subprocess.check_output(['xprop', '-id', str(xid), 'WM_CLASS', 'WM_NAME', '_NET_WM_PID'], text=True, timeout=2)
    return dict(xid=xid, xserverClientPid=pid, namespacePid=visible_pid(xid), properties=properties)


def app_identity(launcher, pid, inputs, report, out, tag):
    proc = Path('/proc') / str(pid)
    image = identity(pid)
    info_bytes = (proc / 'root/.flatpak-info').read_bytes()
    info = configparser.ConfigParser(interpolation=None)
    info.read_string(info_bytes.decode('utf-8'))
    (out / (tag + '.flatpak-info')).write_bytes(info_bytes)
    instance = info['Instance']
    platform = inputs['platform']
    installed = Path(os.environ['FLATPAK_USER_DIR']) / 'app' / APP / 'x86_64/master' / COMMIT / 'files'
    runtime = Path(os.environ['FLATPAK_SYSTEM_DIR']) / platform['ref'] / platform['commit'] / 'files'
    extension = inputs['glRef'].split('/')[1] + '=' + inputs['glCommit']
    namespace_pids = [int(x) for x in next(s for s in (proc / 'status').read_text().splitlines() if s.startswith('NSpid:')).split()[1:]]
    sandbox = identity(image['parent'])
    require(info['Application']['name'] == APP and info['Application']['runtime'] == platform['ref']
            and instance['app-commit'] == COMMIT and instance['app-path'] == str(installed)
            and instance['runtime-commit'] == platform['commit'] and instance['runtime-path'] == str(runtime)
            and instance['runtime-extensions'] == extension
            and instance['arch'] == 'x86_64' and instance['branch'] == 'master' and instance.getboolean('session-bus-proxy')
            and len(namespace_pids) == 2 and namespace_pids[0] == pid and image['executable'] == HOST and sha(proc / 'exe') == report['apphost']
            and sandbox['parent'] == launcher.pid and os.readlink(proc / 'ns/net') == report['namespaces']['net'],
            'The live X11 client, sandbox, Flatpak instance, network or executable differs')
    env = dict(pair.split('=', 1) for pair in (proc / 'environ').read_bytes().decode().split('\0') if '=' in pair)
    locations = {key: env[key] for key in ('HOME', 'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'FLATPAK_ID')}
    require(locations['FLATPAK_ID'] == APP and locations['HOME'] == '/tmp/home'
            and locations['XDG_CONFIG_HOME'] == '/tmp/home/.var/app/' + APP + '/config', 'Unexpected application profile')
    roots = {}
    for key in ('XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME'):
        s = (proc / 'root' / locations[key].lstrip('/')).stat()
        roots[key] = [s.st_dev, s.st_ino]
    return dict(gui=image, wrapper=identity(launcher.pid), sandbox=sandbox, instance=instance['instance-id'],
                namespaces={n: os.readlink(proc / 'ns' / n) for n in ('pid', 'mnt', 'net')}, paths=locations,
                directoryIdentity=roots, namespacePids=namespace_pids)


def witness(launcher, native, inputs, report, out, tag):
    app = app_identity(launcher, native['xserverClientPid'], inputs, report, out, tag)
    rows = subprocess.check_output(['flatpak', 'ps', '--columns=instance,pid,child-pid,application'], text=True, timeout=4)
    require(app['namespacePids'][-1] == native['namespacePid'] and [app['instance'], str(launcher.pid), str(app['sandbox']['pid']), APP]
            in [line.split('\t') for line in rows.splitlines()], 'Flatpak and X11 do not identify the same running client')
    return {**app, 'window': native}


def launching_app(launcher):
    def children(pid):
        path = Path(f'/proc/{pid}/task/{pid}/children')
        try:
            return [int(p) for p in path.read_text().split()]
        except (FileNotFoundError, ProcessLookupError):
            return []
    for supervisor in children(launcher.pid):
        for child in children(supervisor):
            try:
                if os.readlink(f'/proc/{child}/exe') == HOST:
                    return child
            except (FileNotFoundError, ProcessLookupError):
                continue
    return None


def quit_footer(display, xid):
    attrs = WindowAttributes()
    require(display.attributes(display.display, xid, c.byref(attrs)) and attrs.map_state == 2 and
            attrs.width >= 600 and attrs.height >= 400, 'Expected the visible second window for its Quit footer')
    # The shipping XAML places Quit at the lower right, with 20 horizontal and 12 vertical padding.
    x, y = attrs.x + attrs.width - 45, attrs.y + attrs.height - 28
    xtest = c.CDLL('libXtst.so.6')
    motion = bind(xtest, 'XTestFakeMotionEvent', c.c_int, c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong)
    button = bind(xtest, 'XTestFakeButtonEvent', c.c_int, c.c_void_p, c.c_uint, c.c_int, c.c_ulong)
    require(motion(display.display, -1, x, y, 0) and button(display.display, 1, 1, 0) and button(display.display, 1, 0, 0),
            'The private X server refused the footer click')
    display.sync(display.display, 0)
    return [x, y]


def run(display, bus, inputs, report, out):
    config = Path.home() / '.var/app' / APP / 'config/immich-folder-watch/config.yaml'
    require(not config.exists(), 'A clean, unconfigured shipping application is required')
    command = ['flatpak', 'run', '--user', APP]
    report['launchArgv'] = command
    first_log, second_log = out / 'first.log', out / 'second.log'
    with ExitStack() as trials:
        watcher_log = out / 'watcher.log'
        watcher = checked_start(trials, ['/usr/bin/python3', '-B', '/watcher.py'], watcher_log)
        wait_for(lambda: check_alive(watcher, watcher_log) or 'WATCHER_READY' in watcher_log.read_text(), 5, 'No private tray watcher')
        primary = checked_start(trials, command, first_log)
        xid = wait_for(lambda: check_alive(primary, first_log) or display.visible(), 20, 'No first shipping window')
        first = report['first'] = witness(primary, window(display, xid), inputs, report, out, 'first')
        watch = select.poll()
        fd = os.pidfd_open(first['gui']['pid'])
        trials.callback(os.close, fd)
        watch.register(fd, select.POLLIN)
        flags = Gio.DBusCallFlags.NO_AUTO_START
        name = APP + '.Tray'
        wait_for(lambda: check_alive(primary, first_log) or 'REGISTERED ' in watcher_log.read_text(), 10, 'No primary tray registration')
        owner = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'GetNameOwner',
                              GLib.Variant('(s)', (name,)), None, flags, 3000, None).unpack()[0]
        display.request_close(xid)
        wait_for(lambda: check_alive(primary, first_log) or display.visible() is None, 8, 'The first window did not hide')
        for _ in range(5):
            time.sleep(.05)
            require(display.visible() is None and not watch.poll(0), 'Hidden primary did not stay hidden before launch')
        report['firstHidden'] = True
        secondary = checked_start(trials, command, second_log)
        second_pid = wait_for(lambda: check_alive(secondary, second_log) or launching_app(secondary), 8, 'No second shipping executable')
        short = report['secondLaunch'] = app_identity(secondary, second_pid, inputs, report, out, 'second-launch')
        require(short['instance'] != first['instance'] and short['gui']['pid'] != first['gui']['pid'] and
                short['namespaces']['pid'] != first['namespaces']['pid'] and short['paths'] == first['paths'] and
                short['directoryIdentity'] == first['directoryIdentity'],
                'The independent launch did not run in a new Flatpak instance of the same profile')
        short_poll = select.poll()
        short_fd = os.pidfd_open(second_pid)
        trials.callback(os.close, short_fd)
        short_poll.register(short_fd, select.POLLIN)
        def outcome():
            check_alive(primary, first_log)
            require(not watch.poll(0), 'The first GUI exited before the second launch completed')
            visible = display.visible()
            if secondary.poll() is not None:
                require(secondary.returncode == 0, f'Second launch exit {secondary.returncode}')
                return ('existing-primary-reopened', visible) if visible == xid else None
            if visible is not None and visible != xid:
                return 'separate-primary-visible', visible
            return None
        route, shown = wait_for(outcome, 20, 'The second launch did not establish a visible outcome')
        report['outcome'] = route
        same = shown == xid
        after = report['second'] = witness(primary if same else secondary, window(display, shown), inputs, report, out, 'second')
        require((first['gui'] == after['gui']) == same and (first['instance'] == after['instance']) == same
                and first['directoryIdentity'] == after['directoryIdentity']
                and not watch.poll(0), 'The native outcome differs from the process and profile observations')
        first_now = identity(first['gui']['pid'])
        require(first_now == first['gui'], 'The primary identity changed during the second launch')
        report['firstWhileSecondVisible'] = first_now
        if not same:
            report['secondQuitFooterAt'] = quit_footer(display, shown)
        report['secondExit'] = secondary.wait(timeout=10)
        report['secondGuiExited'] = bool(short_poll.poll(1000))
        require(report['secondGuiExited'], 'Second native apphost survived its launcher')
        # The isolated desktop invokes the first application's ordinary status menu Quit entry.
        bus.call_sync(owner, '/StatusNotifierItem/Menu', 'com.canonical.dbusmenu', 'Event',
                      GLib.Variant('(isvu)', (3, 'clicked', GLib.Variant('i', 0), 0)), None, flags, 3000, None)
        report['firstMenuOwner'] = owner
        report['firstExit'] = primary.wait(timeout=15)
        report['originalGuiExited'] = bool(watch.poll(1000))
        require(report['originalGuiExited'] and report['firstExit'] == report['secondExit'] == 0, 'Ordinary app cleanup failed')
    remaining = wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=4).strip(),
                         5, 'A private Flatpak instance remained after the two GUI exits')
    report.update(allInstancesExited=remaining, configCreated=config.exists())
    require(not config.exists(), 'The empty profile unexpectedly acquired a worker configuration')
