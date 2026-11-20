"""Install a temporary application ref using the real offline Flatpak CLI in a private profile."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
from runtime_pin import COMMITS
APP = 'org.example.IfwPortalDialog'


def prepare(commit):
    # This root is private tmpfs. The launcher binds only the public 26.08 platform deployment read-only.
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
    return {'installed_ref': f'app/{APP}/{arch}/test', 'commit': info, 'runtime': str(runtime)}


def command(action, *arguments):
    return ['flatpak', 'run', '--user', '--branch=test', '--env=IFW_QA_ISOLATED=1', APP, action, *arguments]
