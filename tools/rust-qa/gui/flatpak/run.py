"""Observe ordinary and background second launches of an installed native x64 GUI on private X11.

From the repository root, run python3 -B tools/rust-qa/gui/flatpak/run.py linux-second-fixed-owner.
The argument names a staged Linux GUI under artifacts/rust/performance/subjects, or use --gui-build
to select a scratch build from tools/rust-qa/gui/build.py. The local system must already have
the pinned public x64 Platform and GL.default deployments. Each trial uses a fresh offline user
installation under tmpfs. The result and raw inputs go to artifacts/rust/flatpak-gui-launch-assessment.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED


HERE = Path(__file__).resolve().parent
APP = 'org.example.IfwGuiProbe'
GL = 'org.freedesktop.Platform.GL.default'
GL_COMMIT = '5aec1b8281d53c91bdac451eb577ec5331ca0e34d89cf0dcc8dba2360171eae6'
GL_METADATA = '8802a8c0a93df4c521a62b9be924574c2c40bc8c03e48075387c795d308d781b'
PERMISSIONS = ['--share=ipc', '--socket=x11', '--talk-name=org.kde.StatusNotifierWatcher']
NS = ('net', 'mnt', 'pid', 'ipc', 'user')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main(args):
    qa = HERE.parents[1]
    root = qa.parents[1]
    art = root / 'artifacts/rust'
    sys.path[:0] = [str(qa / 'performance'), str(qa / 'portal-dialog')]
    from linux import namespace
    from runtime_pin import deployment, BRANCH
    from flatpak_fixture import SYS_DIRS

    if platform.machine() != 'x86_64':
        raise ValueError('Only the local native x64 GL deployment is pinned')
    if args.gui_build:
        subject = args.gui_build.resolve(strict=True)
        if not subject.is_relative_to(art) or subject == art:
            raise ValueError('Use an existing isolated GUI build under artifacts/rust')
        subject = subject / 'release'
    else:
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', args.stage):
            raise ValueError('Expected a staged subject name')
        subject = art / 'performance/subjects' / args.stage
    binary = subject / 'native-gui-assessment'
    receipt = binary.with_suffix('.inputs.json')
    gui = json.loads(receipt.read_bytes())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    source_paths = [*sorted((qa / 'gui/src').glob('*.rs')), qa / 'gui/src/tray-icon.argb',
                    qa / 'gui/Cargo.toml', qa / 'gui/Cargo.lock', root / 'rust/Cargo.toml',
                    root / 'rust/crates/desktop-lifecycle/Cargo.toml', root / 'rust/crates/desktop-lifecycle/src/lib.rs']
    sources = {p.relative_to(root).as_posix(): sha(p) for p in source_paths}
    if (gui['target'] != 'x86_64-unknown-linux-gnu' or gui['binary_sha256'] != sha(binary)
            or sources != gui['sources']):
        raise ValueError('The staged x64 executable and its exact compiled first-party sources must match')
    subprocess.run(['git', 'ls-files', '--error-unmatch', '--', *sources], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['git', 'diff', '--quiet', revision, '--', *sources], cwd=root, check=True)
    runtime, platform_receipt = deployment(None)
    system = Path('/var/lib/flatpak')
    gl_ref = Path('runtime', GL, 'x86_64', BRANCH)
    gl = system / gl_ref / GL_COMMIT
    if gl.resolve(strict=True) != gl or not (gl / 'files').is_dir() or sha(gl / 'metadata') != GL_METADATA:
        raise ValueError('Missing or changed pinned public GL.default deployment')
    manifest = root / 'packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml'
    finish = manifest.read_text().split('\nfinish-args:\n', 1)[1].split('\n\n', 1)[0].splitlines()
    shipping = [line.removeprefix('  - ') for line in finish]
    if set(shipping) != set(PERMISSIONS + ['--share=network', '--device=dri']):
        raise ValueError('Review the current shipping sandbox permissions')
    drivers = [HERE / n for n in ('run.py', 'observe.py', 'launch.sh')]
    drivers += [qa / 'gui/watcher.py', *(qa / 'performance' / n for n in
                ('linux.py', 'session.py', 'observations.py', 'x11.py', 'worker/second_launch.py')),
                qa / 'portal-dialog/flatpak_fixture.py', qa / 'portal-dialog/runtime_pin.py']
    dest = art / 'flatpak-gui-launch-assessment'
    dest.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='x11-', dir=dest))
    print(out, flush=True)
    shutil.copyfile(receipt, out / 'gui-build.json')
    archive = out / 'observer-source.zip'
    with ZipFile(archive, 'x', ZIP_DEFLATED) as bundle:
        for p in [*drivers, manifest]:
            bundle.write(p, p.relative_to(root))
    software_driver = gl / 'files/lib/libvulkan_lvp.so'
    icd = gl / 'files/lib/vulkan/icd.d/lvp_icd.x86_64.json'
    commands = ('bwrap', 'dbus-daemon', 'flatpak', 'ostree', 'xprop', 'xdg-dbus-proxy')
    save(out / 'inputs.json', {'sourceRevision': revision, 'guiPath': str(binary), 'guiSha256': sha(binary),
         'buildReceiptPath': str(receipt), 'buildReceiptSha256': sha(receipt), 'compilerSources': sources,
         'driverInputs': {p.relative_to(root).as_posix(): sha(p) for p in drivers},
         'observerArchiveSha256': sha(archive),
         'commands': {str(path): sha(path) for name in commands for path in [Path('/usr/bin') / name]},
         'platform': {**platform_receipt, 'path': str(runtime)},
         'gl': {'ref': str(gl_ref), 'commit': GL_COMMIT, 'metadataSha256': GL_METADATA, 'path': str(gl),
                'driverPath': str(software_driver), 'driverSha256': sha(software_driver),
                'icdPath': str(icd), 'icdSha256': sha(icd)},
         'shipping': {'file': manifest.relative_to(root).as_posix(), 'sha256': sha(manifest), 'finishArgs': shipping},
         'testFinishArgs': PERMISSIONS, 'outerNamespaces': {n: os.readlink('/proc/self/ns/' + n) for n in NS}})
    cmd = namespace(out, qa / 'gui', None)
    (out / 'etc/passwd').write_text('root:x:0:0:Synthetic user:/tmp/home:/bin/false\n')
    (out / 'etc/group').write_text('root:x:0:\n')
    private = Path('/tmp/private-flatpak-system')
    cmd[cmd.index('--chdir'):] = [
        '--uid', '0', '--gid', '0', '--cap-add', 'CAP_SYS_ADMIN', '--cap-add', 'CAP_SETFCAP',
        '--cap-add', 'CAP_NET_ADMIN', '--dev-bind', '/dev/fuse', '/dev/fuse', '--tmpfs', '/sys',
        *(arg for path in SYS_DIRS for arg in ('--dir', path)),
        '--ro-bind', str(runtime), str(private / platform_receipt['ref'] / platform_receipt['commit']),
        '--ro-bind', str(gl), str(private / gl_ref / GL_COMMIT), '--ro-bind', str(binary), '/binary',
        '--ro-bind', str(qa / 'portal-dialog'), '/portal-fixture', '--setenv', 'FLATPAK_SYSTEM_DIR', str(private),
        '--setenv', 'FLATPAK_USER_DIR', '/tmp/home/.local/share/flatpak', '--dir', '/run/user/0',
        '--setenv', 'XDG_RUNTIME_DIR', '/run/user/0', '--chdir', '/qa', '--', '/usr/bin/python3', '-B',
        '/app/flatpak/run.py', '--inside']
    result = subprocess.run(cmd, timeout=180)
    files = sorted(p for p in out.iterdir() if p.is_file())
    (out / 'evidence.sha256').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files))
    if result.returncode or not json.loads((out / 'result.json').read_bytes()).get('passed'):
        raise RuntimeError(f'Installed Flatpak observation failed in {out}')


def inside():
    sys.path[:0] = ['/driver', '/portal-fixture']
    from flatpak_fixture import export_install, prepare_runtime, setup_command
    import observe

    out = Path('/qa')
    inputs = json.loads((out / 'inputs.json').read_bytes())
    report = {'passed': False, 'inputsSha256': sha(out / 'inputs.json'), 'workerEnabled': False}
    try:
        private = Path('/tmp/private-flatpak-system')
        ns = {n: os.readlink('/proc/self/ns/' + n) for n in NS}
        if (Path.home() != Path('/tmp/home') or os.getuid() != 0 or os.environ.get('XDG_RUNTIME_DIR') != '/run/user/0'
                or os.getenv('FLATPAK_USER_DIR') != '/tmp/home/.local/share/flatpak'
                or any(ns[n] == inputs['outerNamespaces'][n] for n in NS)
                or Path('/proc/net/route').read_text().splitlines()[1:] or sha(Path('/binary')) != inputs['guiSha256']):
            raise RuntimeError('Expected the isolated native assessment and an empty network namespace')
        report['namespaces'] = ns
        os.umask(0o077)
        Path.home().mkdir()
        Path('/run/user/0').chmod(0o700)
        gl = private / inputs['gl']['ref'] / GL_COMMIT
        if not any(row.split()[4] == str(gl) and 'ro' in row.split()[5].split(',')
                   for row in Path('/proc/self/mountinfo').read_text().splitlines()) or sha(gl / 'metadata') != GL_METADATA:
            raise RuntimeError('GL extension must be the pinned read-only deployment')
        prepare_runtime(inputs['platform']['commit'])
        (gl.parent / 'active').symlink_to(GL_COMMIT)
        app = Path('/tmp/gui-build')
        files = app / 'files/bin'
        files.mkdir(parents=True)
        (app / 'var').mkdir()
        runtime = inputs['platform']['ref'].removeprefix('runtime/')
        (app / 'metadata').write_text(f'[Application]\nname={APP}\nruntime={runtime}\nsdk=org.freedesktop.Sdk/x86_64/26.08\n')
        shutil.copy2('/binary', files / 'native-gui-assessment')
        shutil.copyfile(HERE / 'launch.sh', files / 'launch')
        (files / 'launch').chmod(0o755)
        installed = report['installation'] = export_install(app, APP, ['--command=launch', *PERMISSIONS])
        try:
            observe.run(report, inputs, out)
        finally:
            setup_command(['flatpak', '--user', 'uninstall', '--noninteractive', installed['installed_ref']])
            setup_command(['flatpak', '--user', 'remote-delete', 'fixture'])
            remaining = subprocess.check_output(['flatpak', '--user', 'list', '--app', '--columns=ref'],
                                                text=True, timeout=10).strip()
            report['userInstallationEmpty'] = not remaining
            if remaining:
                raise RuntimeError('The application remains in the private user installation')
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        save(out / 'result.json', report)


if __name__ == '__main__':
    if sys.argv[1:] == ['--inside']:
        inside()
    else:
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument('stage', nargs='?')
        source.add_argument('--gui-build', type=Path)
        main(parser.parse_args())
