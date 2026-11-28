"""Exercise a real FileChooser frontend, GTK backend and native parent windows on a private desktop."""

import argparse
import configparser
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
BASE = ROOT / 'artifacts/rust/portal-dialog'
APP = 'org.example.IfwPortalDialog'
FRONT = 'org.freedesktop.portal.Desktop'
GTK = 'org.freedesktop.impl.portal.desktop.gtk'


def sha(path):
    with path.open('rb') as fd:
        return hashlib.file_digest(fd, 'sha256').hexdigest()


def launch(backend, flatpak, shell, chooser_only, hosted_runtime, notification_only=False):
    sys.path.insert(0, str(ROOT / 'tools/rust-qa/performance'))
    from linux import namespace
    record = json.loads((BASE / 'build-inputs.json').read_text())
    if any((sha(ROOT / name) != digest for name, digest in record['sources'].items())):
        raise RuntimeError('Rebuild after changing a recorded source')
    work = Path(tempfile.mkdtemp(dir=BASE,
        prefix=('gnome-' if shell else '') + backend +
        ('-flatpak-' if flatpak else '-chooser-only-' if chooser_only else '-')))
    print('Private portal-dialog evidence', work, flush=True)
    binary = BASE / 'build/release/portal-dialog-assessment'
    if sha(binary) != record['binary']:
        raise RuntimeError('Source-bound executable differs')
    cmd = namespace(work, HERE, None)
    end = cmd.index('--chdir')
    (work / 'etc/passwd').write_text('root:x:0:0:Portal fixture:/tmp/home:/bin/false\n')
    (work / 'etc/group').write_text('root:x:0:\n')
    native_services = [Path('/usr/libexec') / n for n in ('xdg-desktop-portal', 'xdg-document-portal',
        'xdg-desktop-portal-gtk', 'xdg-permission-store')]
    if backend == 'wayland':
        native_services.append(Path('/usr/bin/gnome-shell' if shell else '/usr/bin/mutter'))
    if shell:
        native_services.extend(Path(p) for p in ('/usr/libexec/xdg-desktop-portal-gnome', '/usr/bin/pipewire',
                                                '/usr/bin/wireplumber', '/usr/bin/gst-launch-1.0'))
    if flatpak:
        native_services.extend(Path(p) for p in ('/usr/bin/flatpak', '/usr/bin/ostree'))
    shared = ROOT / 'tools/rust-qa/performance'
    drivers = [*sorted(HERE.glob('*.py')), *(shared / name for name in ('linux.py', 'session.py', 'x11.py'))]
    inputs = {
        'build': record,
        'outer_ns': {n: os.readlink(f'/proc/self/ns/{n}') for n in ('net', 'ipc', 'pid', 'mnt', 'user')},
        'runtime': {str(path): sha(path) for path in native_services},
        'drivers': {str(path.relative_to(ROOT)): sha(path) for path in drivers},
    }
    if notification_only:
        import platform
        from linux import system_identity
        distro = platform.freedesktop_os_release()
        inputs['host'] = dict(system_identity(), distribution=distro['ID'], version=distro['VERSION_ID'])
        inputs['revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        inputs['run'] = os.environ.get('GITHUB_RUN_ID')
        inputs['attempt'] = os.environ.get('GITHUB_RUN_ATTEMPT')
    flatpak_paths = []
    if flatpak:
        from flatpak_fixture import SYS_DIRS
        from runtime_pin import deployment
        runtime, details = deployment(hosted_runtime)
        inputs['platform'] = details
        destination = Path('/tmp/private-flatpak-system') / details['ref'] / details['commit']
        flatpak_paths = ['--tmpfs', '/sys', *(arg for path in SYS_DIRS for arg in ('--dir', path)),
            '--ro-bind', str(runtime), str(destination), '--setenv', 'FLATPAK_SYSTEM_DIR',
            '/tmp/private-flatpak-system', '--setenv', 'FLATPAK_USER_DIR', '/tmp/home/.local/share/flatpak']
    (work / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    cmd[end:] = ['--uid', '0', '--gid', '0', '--cap-add', 'CAP_SYS_ADMIN', '--cap-add', 'CAP_SETFCAP',
        '--cap-add', 'CAP_NET_ADMIN', '--dev-bind', '/dev/fuse', '/dev/fuse', *flatpak_paths, '--dir', '/probe',
        '--ro-bind', str(binary), '/probe/portal-dialog-assessment', '--dir', '/run/user/0', '--setenv',
        'XDG_RUNTIME_DIR', '/run/user/0', '--setenv', 'IFW_QA_ISOLATED', '1', '--setenv', 'GSETTINGS_BACKEND',
        'memory', '--setenv', 'XDG_CURRENT_DESKTOP', 'GNOME' if shell else 'IFWQA', '--setenv', 'GTK_USE_PORTAL',
        '0', '--setenv', 'NO_AT_BRIDGE', '1', '--setenv', 'GTK_A11Y', 'none', '--chdir', '/qa', '--',
        '/usr/bin/python3', '/app/native.py', backend, '--inside', *(['--flatpak'] if flatpak else []),
        *(['--gnome'] if shell else []), *(['--host-chooser-only'] if chooser_only else []),
        *(['--notification-only'] if notification_only else [])]
    return subprocess.run(cmd).returncode


def desktop_process(kind, backend, command):
    # Separate private roots for the chooser and the application. Only the GTK selector sees
    # the synthetic producer path. They share explicitly named session/display sockets.
    cmd = ['bwrap', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent', '--new-session',
        '--ro-bind', '/usr', '/usr', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/tmp/home',
        '--dir', '/run/user/0', '--dir', '/etc']
    for name in ('bin', 'lib', 'lib64'):
        path = Path('/') / name
        if path.is_symlink():
            cmd += ['--symlink', str(path.readlink()), str(path)]
        elif path.exists():
            cmd += ['--ro-bind', str(path), str(path)]
    files = ['/etc/passwd', '/etc/group', '/etc/fonts', '/etc/machine-id', '/etc/ld.so.cache', '/tmp/session-bus']
    files += ['/tmp/.X11-unix'] if backend == 'x11' else ['/run/user/0/ifw-dialog']
    if kind == 'gtk':
        files += ['/tmp/selection']
    else:
        files += ['/probe/portal-dialog-assessment', '/run/user/0/doc']
    for file in files:
        cmd += ['--ro-bind', file, file]
    cmd += ['--cap-drop', 'ALL', '--setenv', 'GIO_USE_VFS', 'local', '--setenv', 'GDK_BACKEND', backend]
    if kind == 'gtk':
        # Permit the distribution's own Glycin loader to create its private user and
        # loopback namespaces. This backend sees only selected read-only files.
        cmd += ['--cap-add', 'CAP_SETFCAP', '--cap-add', 'CAP_NET_ADMIN']
    if backend == 'wayland':
        cmd += ['--setenv', 'WAYLAND_DEBUG', 'client']
    return [*cmd, '--', *command]


def inside(backend, flatpak, shell, chooser_only, notification_only=False):
    sys.path.insert(0, '/driver')
    from session import checked_start, check_alive, wait_for, private_session
    from displays import X11, Wayland, input_action, stroke
    from gi.repository import Gio, GLib
    inputs = json.loads(Path('/qa/inputs.json').read_text())
    if not all((os.readlink(f'/proc/self/ns/{k}') != v for k,
        v in inputs['outer_ns'].items())) or os.environ.get('DBUS_SESSION_BUS_ADDRESS') != 'unix:path=/tmp/session-bus' or Path.home() != Path('/tmp/home'):
        raise RuntimeError('Private portal desktop required')
    if any((sha(Path(p)) != digest for p, digest in inputs['runtime'].items())):
        raise RuntimeError('Portal binaries changed')
    if Path('/proc/net/route').read_text().splitlines()[1:]:
        raise RuntimeError('The private desktop namespace must have no network routes')
    os.umask(63)
    Path.home().mkdir()
    Path('/run/user/0').chmod(448)
    config = Path.home() / '.config/xdg-desktop-portal'
    config.mkdir(parents=True)
    preferences = '[preferred]\ndefault=gtk\n'
    if shell:
        # Older GNOME installations provide notifications through the GTK portal.
        preferences += 'org.freedesktop.impl.portal.Notification=gnome;gtk;\norg.freedesktop.impl.portal.Background=gnome\n'
    (config / 'portals.conf').write_text(preferences)
    apps = Path.home() / '.local/share/applications'
    apps.mkdir(parents=True)
    (apps / (APP + '.desktop')).write_text('[Desktop Entry]\nType=Application\nName=Portal assessment\nExec=/probe/portal-dialog-assessment\n')
    selections = {'select': Path('/tmp/selection/album'),
                  'select-escaped': Path('/tmp/selection/Grüße #2 %2F')}
    markers = {'select': 'fixture', 'select-escaped': 'escaped-name-fixture'}
    for action, folder in selections.items():
        folder.mkdir(parents=True)
        (folder / markers[action]).write_text('Synthetic portal dialog directory\n')
    output = Path('/qa/results.json')
    result = {'backend': backend,
        'app_identity': ('installed temporary Flatpak' if flatpak else
                         'unregistered native FileChooser caller' if chooser_only else 'registered native host application'),
        'steps': {}}

    def record(key, data):
        result['steps'][key] = data
        output.write_text(json.dumps(result, indent=2) + '\n')
    with ExitStack() as stack:
        xd, server = private_session(stack)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        if shell:
            from shell_services import screen, exercise
            os.environ['XDG_SESSION_TYPE'] = 'wayland'
            pw_log = Path('/qa/pipewire.log')
            pw = checked_start(stack, ['pipewire'], pw_log)
            wait_for(lambda: check_alive(pw, pw_log) or Path('/run/user/0/pipewire-0').is_socket(), 5,
                'Private PipeWire not ready')
            if notification_only:
                from shell_services import private_video_policy
                record('video_policy', private_video_policy(stack))
            else:
                checked_start(stack, ['wireplumber'], Path('/qa/wireplumber.log'))
        display = X11(xd) if backend == 'x11' else Wayland(stack, bus, shell)

        def owner(name):
            try:
                return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                    'GetNameOwner', GLib.Variant('(s)', (name,)), None, Gio.DBusCallFlags.NONE, 650,
                    None).unpack()[0]
            except GLib.Error:
                return None

        def agent(label, cmd, name):
            path = Path('/qa') / (label + '.log')
            process = checked_start(stack, cmd, path)
            return wait_for(lambda: check_alive(process, path) or owner(name), 8, f'{label} did not own {name}')
        store = agent('store', ['/usr/libexec/xdg-permission-store', '-v'],
            'org.freedesktop.impl.portal.PermissionStore')
        docs = agent('documents', ['/usr/libexec/xdg-document-portal', '-v'], 'org.freedesktop.portal.Documents')
        if shell:
            notify = wait_for(lambda: owner('org.gtk.Notifications'), 8, 'Real notification display is unavailable')
            descriptor = configparser.ConfigParser()
            descriptor.read('/usr/share/xdg-desktop-portal/portals/gnome.portal')
            interfaces = descriptor.get('portal', 'Interfaces').split(';')
            gnome = None
            if not notification_only or 'org.freedesktop.impl.portal.Notification' in interfaces:
                gnome = agent('gnome-portal',
                    ['env', 'GDK_BACKEND=wayland', '/usr/libexec/xdg-desktop-portal-gnome', '-v'],
                    'org.freedesktop.impl.portal.desktop.gnome')
            record('gnome', {'backend': gnome, 'notification_provider': notify})
            result['notification_receiver'] = 'GNOME Shell org.gtk.Notifications'
            if notification_only:
                shell_pid, = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                    'org.freedesktop.DBus', 'GetConnectionUnixProcessID', GLib.Variant('(s)', (notify,)),
                    None, Gio.DBusCallFlags.NONE, 2000, None).unpack()
                shell_image = Path(f'/proc/{shell_pid}/exe').resolve(strict=True)
                if shell_pid != display.compositor_pid or shell_image != Path('/usr/bin/gnome-shell').resolve():
                    raise RuntimeError('The notification receiver is outside the private GNOME Shell process')
                record('shell_process', {'pid': shell_pid, 'compositor_pid': display.compositor_pid,
                                         'image': str(shell_image), 'sha256': sha(shell_image)})
        elif not chooser_only:
            notify = agent('receiver', [sys.executable, '/app/notifications.py'], 'org.freedesktop.Notifications')
            result['notification_receiver'] = 'synthetic freedesktop notification service'
        else:
            notify = None
        gtk = agent('gtk', desktop_process('gtk', backend, ['/usr/libexec/xdg-desktop-portal-gtk', '-v']), GTK)
        frontend = agent('frontend', ['/usr/libexec/xdg-desktop-portal', '-v'], FRONT)
        record('services',
            {'documents': docs, 'store': store, 'gtk': gtk, 'frontend': frontend, 'notification_receiver': notify,
            'xserver': server})
        if flatpak:
            import flatpak_fixture
            record('flatpak_launch_bus', flatpak_fixture.start_launch_bus(stack, bus))
            record('flatpak', flatpak_fixture.prepare(inputs['platform']['commit']))
            if notification_only:
                location = subprocess.check_output(['flatpak', '--user', 'info', '--show-location',
                    result['steps']['flatpak']['installed_ref']], text=True).strip()
                installed = Path(location) / 'files/bin/portal-dialog-assessment'
                if sha(installed) != inputs['build']['binary']:
                    raise RuntimeError('The installed notification sender differs from the native Rust build')
                record('sender_sha256', sha(installed))

        def app(action):
            path = Path('/qa') / (action + '.log')
            client_action = 'unregistered-host-' + action if chooser_only else action
            command = flatpak_fixture.command(action) if flatpak else desktop_process('app', backend,
                ['/probe/portal-dialog-assessment', client_action])
            return (checked_start(stack, command, path), path)

        def outcome(task, path):
            code = task.wait(timeout=12)
            lines = [l for l in path.read_text().splitlines() if re.match('^(PARENT|REQUEST|CHOOSER_|DOCUMENT_|APPLICATION_FLATPAK|BACKGROUND|NOTIFICATION|Error:)', l)]
            if code:
                raise RuntimeError(f'Native assessment {path.name}: {lines}')
            return lines
        if shell:
            capture = screen(stack, bus)
            exercise(stack, bus, display, record, app, outcome, capture, notification_only)
            return
        service = 'org.freedesktop.portal.Documents'
        documents_path = '/org/freedesktop/portal/documents'
        def document_info(doc_id):
            path, rights = bus.call_sync(service, documents_path, service, 'Info', GLib.Variant('(s)', (doc_id,)),
                                         None, Gio.DBusCallFlags.NONE, 2000, None).unpack()
            return os.fsdecode(bytes(path).removesuffix(b'\x00')), rights.get(APP, [])

        grants = {}
        for action in ('cancel', *selections):
            task, log = app(action)

            def parenting():
                check_alive(task, log)
                match = re.search('^PARENT (.+)$', log.read_text(), re.M)
                return display.observe(match[1]) if match else None
            link = wait_for(parenting, 6, f'{backend} backend did not parent its {action} dialog')
            record(action, {'parenting': link})
            input_action(display, action)
            if action in selections:
                try:
                    task.wait(timeout=0.7)
                except subprocess.TimeoutExpired:
                    stroke(display, 65293)
            lines = outcome(task, log)
            if chooser_only and 'CHOOSER_UNREGISTERED_HOST' not in lines:
                raise RuntimeError('The client did not use the unregistered FileChooser-only path')
            if action in selections:
                uri, = [line.removeprefix('CHOOSER_SELECTED ') for line in lines
                        if line.startswith('CHOOSER_SELECTED ')]
                if not flatpak and uri != selections[action].as_uri():
                    raise RuntimeError(f'GTK returned an unexpected selection: {lines}')
            if action in selections and flatpak:
                _, doc_id, reported_path = next(line for line in lines if line.startswith('DOCUMENT_GRANT ')).split(' ', 2)
                _, source, label = next(line for line in lines if line.startswith('DOCUMENT_LABEL ')).split(' ', 2)
                app_path = Path(os.environ['XDG_RUNTIME_DIR']) / 'doc' / doc_id / selections[action].name
                if (reported_path != str(app_path) or uri != app_path.as_uri()
                        or 'DOCUMENT_ENTRY ' + markers[action] not in lines):
                    raise RuntimeError('The chooser URI and the decoded application view disagree')
                host, rights = document_info(doc_id)
                if host != str(selections[action]) or 'read' not in rights:
                    raise RuntimeError('Documents portal backing or grant recipient disagreed')
                version, = bus.call_sync(service, documents_path, 'org.freedesktop.DBus.Properties', 'Get',
                    GLib.Variant('(ss)', (service, 'version')), None, Gio.DBusCallFlags.NONE, 2000, None).unpack()
                if source in ('xattr', 'Documents.GetHostPaths'):
                    if label != host:
                        raise RuntimeError('Displayed host label differs from the selected backing directory')
                elif source != 'grant' or label != reported_path or version >= 5:
                    raise RuntimeError('Unexpected display fallback for the available Documents portal')
                if action == 'select-escaped' and version >= 5 and 'DOCUMENT_PORTAL_LABEL ' + host not in lines:
                    raise RuntimeError('The installed client did not resolve its exact document ID through GetHostPaths')
                suffix = '-escaped' if action == 'select-escaped' else ''
                grant = {'id': doc_id, 'uri': uri, 'application_view': reported_path,
                         'backing': host, 'permissions': rights, 'display': label,
                         'display_source': source, 'documents_version': version}
                grants[suffix] = grant
                record('documents' + suffix, grant)
            result['steps'][action]['client'] = lines
            record(action, result['steps'][action])
        if chooser_only:
            return
        if flatpak:
            parent = grants['-escaped']
            relative = Path('2026/Urlaub %2F #1')
            backing = Path(parent['backing']) / relative
            backing.mkdir(parents=True)
            marker = 'nested-grant-fixture'
            contents = b'Synthetic nested folder\n'
            (backing / marker).write_bytes(contents)
            saved = Path(parent['application_view']) / relative
            reopen = flatpak_fixture.command('reopen-saved', str(saved))
            opened = subprocess.run([*reopen, '--observe-portal'], capture_output=True, text=True, check=True, timeout=10)
            lines = opened.stdout.splitlines()
            source, display_text = next(line for line in lines if line.startswith('DOCUMENT_LABEL ')).split(' ', 2)[1:]
            expected_label = saved if source == 'grant' else backing
            if (source not in ('xattr', 'Documents.GetHostPaths', 'grant') or display_text != str(expected_label)
                    or (source == 'grant' and parent['documents_version'] >= 5)
                    or not {f"DOCUMENT_GRANT {parent['id']} {saved}", f'DOCUMENT_ENTRY {marker}'}.issubset(lines)):
                raise RuntimeError(f'Fresh Flatpak could not reopen the nested watch folder: {lines}')
            if parent['documents_version'] >= 5 and f'DOCUMENT_PORTAL_LABEL {backing}' not in lines:
                raise RuntimeError('GetHostPaths did not map the descendant of the saved grant')
            record('saved-subfolder', {'access': str(saved), 'backing': str(backing), 'client': lines})
            disconnected = subprocess.run(flatpak_fixture.command('reopen-saved', str(saved), '--observe-portal', without_session_bus=True),
                                          capture_output=True, text=True, check=True, timeout=10)
            lines = disconnected.stdout.splitlines()
            offline_label = f'DOCUMENT_LABEL xattr {backing}' if source == 'xattr' else f'DOCUMENT_LABEL grant {saved}'
            if not {f"DOCUMENT_GRANT {parent['id']} {saved}", f'DOCUMENT_ENTRY {marker}', offline_label, 'DOCUMENT_PORTAL_UNAVAILABLE'}.issubset(lines):
                raise RuntimeError(f'Offline label or access differs for the granted subfolder: {lines}')
            record('saved-subfolder-without-bus', {'access': str(saved), 'client': lines})
        for suffix, grant in reversed(grants.items()):
            bus.call_sync(service, documents_path, service, 'RevokePermissions',
                GLib.Variant('(ssas)', (grant['id'], APP, grant['permissions'])), None, Gio.DBusCallFlags.NONE, 2000, None)
            host, remaining = document_info(grant['id'])
            if host != grant['backing'] or 'read' in remaining:
                raise RuntimeError('The Documents service did not revoke read access to the selected grant')
            control = grants[''] if suffix else None
            args = [control['uri']] if control else []
            denied = subprocess.run(flatpak_fixture.command('recheck-revoked', grant['uri'], *args),
                                    capture_output=True, text=True, check=True, timeout=8)
            observed = denied.stdout.splitlines()
            if not any(line.startswith('GRANT_REVOKED ') for line in observed):
                raise RuntimeError('Fresh Flatpak process did not confirm revoked root')
            if control and ('DOCUMENT_ENTRY ' + markers['select'] not in observed
                            or f"DOCUMENT_GRANT {control['id']} {control['application_view']}" not in observed):
                raise RuntimeError('The same Flatpak process could not read the surviving control grant')
            record('revoked' + suffix, {'uri': grant['uri'], 'remaining_permissions': remaining,
                                        'fresh_process': observed})
            if suffix == '-escaped':
                closed = subprocess.run(reopen, capture_output=True, text=True, timeout=10)
                lines = closed.stdout.splitlines()
                if (closed.returncode == 0 or not {'DOCUMENT_OPEN_FAILED errno=Some(2)',
                                                   'DOCUMENT_OPEN_FAILED errno=Some(13)'}.intersection(lines)
                        or any(line.startswith('DOCUMENT_ENTRY ') for line in lines)):
                    raise RuntimeError(f'Fresh Flatpak did not observe the revoked parent: {lines}')
                if (backing / marker).read_bytes() != contents:
                    raise RuntimeError('The host marker changed during permission revocation')
                record('revoked-saved-subfolder', {'access': str(saved), 'exit': closed.returncode,
                                                   'client': lines, 'backing_entry': marker})

        def simple(action):
            task, log = app(action)
            lines = outcome(task, log)
            record(action, lines)
            return lines
        bg = simple('background')
        auto = Path.home() / '.config/autostart' / (APP + '.desktop')
        enabled = any(('autostart=true' in line for line in bg))
        if enabled != auto.exists():
            raise RuntimeError('Autostart response and private entry disagree')
        record('autostart', {'enabled': enabled, 'private_entry': auto.exists()})
        simple('notify')
        events_path = Path('/qa/notification-events.json')

        def events():
            return json.loads(events_path.read_text()) if events_path.exists() else []
        got = wait_for(lambda: next((e for e in events() if e['method'] == 'Notify'), None), 5,
            'Missing real GTK notification relay')
        if got['sender'] != gtk or got['title'] != 'Synthetic notification' or got['body'] != 'Private portal delivery test':
            raise RuntimeError(f'Unexpected notification data: {got}')
        simple('withdraw')
        closed = wait_for(lambda: next((e for e in events() if e['method'] == 'CloseNotification'), None), 5,
            'Missing real GTK withdrawal')
        if closed['sender'] != gtk or closed['id'] != 73:
            raise RuntimeError('Unexpected notification withdrawal')
        record('notification_relay', {'delivery': got, 'withdrawal': closed})
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend', choices=('x11', 'wayland'))
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--flatpak', action='store_true',
        help='Install and run a synthetic offline Flatpak in the private home')
    parser.add_argument('--host-chooser-only', action='store_true',
        help='Check only host FileChooser selection and cancellation without the optional Registry API')
    parser.add_argument('--hosted-runtime', type=Path, metavar='DEPLOYMENT',
        help='Use the signed native Platform deployment prepared in this GitHub runner temp directory')
    parser.add_argument('--gnome', action='store_true',
        help='Assess the actual GNOME Shell notification and background services')
    parser.add_argument('--notification-only', action='store_true',
        help='Observe posting and withdrawal on the private GNOME Shell')
    args = parser.parse_args()
    if args.host_chooser_only and args.flatpak:
        parser.error('--host-chooser-only and --flatpak select different application identities')
    if args.hosted_runtime and (not args.flatpak or args.inside):
        parser.error('--hosted-runtime requires the outer --flatpak launcher')
    if args.gnome and (not args.flatpak or args.backend != 'wayland'):
        parser.error('--gnome requires wayland --flatpak')
    if args.notification_only and not args.gnome:
        parser.error('--notification-only requires --gnome')
    if args.inside:
        inside(args.backend, args.flatpak, args.gnome, args.host_chooser_only, args.notification_only)
    else:
        sys.exit(launch(args.backend, args.flatpak, args.gnome, args.host_chooser_only, args.hosted_runtime,
                        args.notification_only))
