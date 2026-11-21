"""Install a temporary application ref using the real offline Flatpak CLI in a private profile."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
from runtime_pin import COMMITS
APP = 'org.example.IfwPortalDialog'
LAUNCH_BUS = 'unix:path=/tmp/flatpak-launch-bus'
SYS_DIRS = ('/sys/block', '/sys/bus', '/sys/class', '/sys/dev', '/sys/devices')


def start_launch_bus(stack, desktop):
    """Provide the distribution's Flatpak launcher with a private system bus."""
    from gi.repository import Gio
    from session import check_alive, checked_start, wait_for

    config = Path('/tmp/flatpak-launch-bus.conf')
    config.write_text(f'''<busconfig>
  <type>system</type><listen>{LAUNCH_BUS}</listen><auth>EXTERNAL</auth>
  <policy context="default"><allow user="*"/><allow send_destination="*"/>
    <allow receive_sender="*"/></policy>
</busconfig>
''')
    log = Path('/qa/flatpak-launch-bus.log')
    daemon = checked_start(stack, ['dbus-daemon', '--nofork', '--nopidfile', '--config-file', str(config)], log)
    wait_for(lambda: check_alive(daemon, log) or Path('/tmp/flatpak-launch-bus').is_socket(), 5,
             'The isolated Flatpak launch bus did not start')
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    launch = Gio.DBusConnection.new_for_address_sync(LAUNCH_BUS, flags, None, None)
    stack.callback(launch.close_sync, None)

    def call(bus, method):
        return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', method,
                             None, None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]

    bus_id = call(launch, 'GetId')
    activatable = sorted(call(launch, 'ListActivatableNames'))
    if bus_id == call(desktop, 'GetId') or set(activatable) - {'org.freedesktop.DBus'}:
        raise RuntimeError('Flatpak requires an independent private launch bus without service activation')
    return {'address': LAUNCH_BUS, 'bus_id': bus_id, 'activatable': activatable}


def prepare(commit):
    # This root is private tmpfs. The launcher binds only the public 26.08 platform deployment read-only.
    if any(any(Path(name).iterdir()) for name in SYS_DIRS):
        raise RuntimeError('Expected empty synthetic device directories in the private Flatpak desktop')
    system = Path('/tmp/private-flatpak-system')
    private_home = Path('/tmp/home')
    arch = platform.machine()
    platform_ref = system / 'runtime/org.freedesktop.Platform' / arch / '26.08'
    deployment = platform_ref / commit
    mounts = Path('/proc/self/mountinfo').read_text().splitlines()
    private_tmp = any(row.split()[4] == '/tmp' and ' - tmpfs ' in row for row in mounts)
    readonly = any(row.split()[4] == str(deployment) and 'ro' in row.split()[5].split(',') for row in mounts)
    if (Path.home() != private_home or os.environ.get('FLATPAK_SYSTEM_DIR') != str(system)
            or Path('/var/lib/flatpak').exists() or not (deployment / 'files').is_dir() or not private_tmp
            or commit != COMMITS.get(arch) or not readonly):
        raise RuntimeError('Missing dedicated Flatpak environment')
    out = Path('/qa/flatpak-prepare.log')

    def run(args):
        with out.open('a') as log:
            log.write('+ ' + ' '.join((str(n) for n in args)) + '\n')
            log.flush()
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, text=True, check=True, timeout=25)
    # Flatpak requires the checksum-named deployment itself to be a real directory.
    (platform_ref / 'active').symlink_to(commit, target_is_directory=True)
    run(['ostree', '--repo=/tmp/private-flatpak-system/repo', 'init', '--mode=bare-user-only'])
    app = Path('/tmp/app-build')
    (app / 'files/bin').mkdir(parents=True)
    desktop = app / 'files/share/applications'
    desktop.mkdir(parents=True)
    (app / 'var').mkdir()
    (app / 'metadata').write_text(f'[Application]\nname={APP}\nruntime=org.freedesktop.Platform/{arch}/26.08\nsdk=org.freedesktop.Sdk/{arch}/26.08\n')
    shutil.copy2('/probe/portal-dialog-assessment', app / 'files/bin/portal-dialog-assessment')
    (desktop / (APP + '.desktop')).write_text('[Desktop Entry]\nType=Application\nName=Synthetic Portal Dialog\nExec=portal-dialog-assessment\n')
    run(['flatpak', 'build-finish', '--command=portal-dialog-assessment', '--socket=x11', '--socket=wayland',
        str(app)])
    run(['flatpak', 'build-export', '--arch=' + arch, '/tmp/app-ref', str(app), 'test'])
    run(['flatpak', '--user', 'remote-add', '--no-gpg-verify', 'fixture', 'file:///tmp/app-ref'])
    run(['flatpak', '--user', 'install', '--noninteractive', '--no-deps', '--no-related', 'fixture',
        f'app/{APP}/{arch}/test'])
    info = subprocess.check_output(['flatpak', '--user', 'info', '--show-commit', APP + '//test'], text=True).strip()
    runtime = (system / 'runtime/org.freedesktop.Platform' / arch / '26.08/active').readlink()
    return {'installed_ref': f'app/{APP}/{arch}/test', 'commit': info, 'runtime': str(runtime),
            'empty_device_directories': SYS_DIRS}


def command(action, *arguments):
    return ['env', 'DBUS_SYSTEM_BUS_ADDRESS=' + LAUNCH_BUS, 'flatpak', '--verbose', 'run', '--user',
            '--branch=test', '--env=IFW_QA_ISOLATED=1', APP, action, *arguments]
