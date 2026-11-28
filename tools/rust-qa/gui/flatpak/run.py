"""Observe ordinary and background second launches of an installed native x64 or ARM64 GUI on private X11.

From the repository root, run python3 -B tools/rust-qa/gui/flatpak/run.py linux-second-fixed-owner.
The argument names a staged Linux GUI under artifacts/rust/performance/subjects, or use --gui-build
to select a scratch build from tools/rust-qa/gui/build.py. The local system must already have
the pinned native Platform and GL.default deployments. On a disposable hosted runner use
--hosted-runtime PATH to its signed Platform deployment and staged GL.default sibling.
Each trial uses a fresh offline user
installation under tmpfs. The result and raw inputs go to artifacts/rust/flatpak-gui-launch-assessment.
Add --tray-menu to replace the watcher and exercise Open and Quit through the installed bus proxy.
"""

import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED


HERE = Path(__file__).resolve().parent
APP = 'org.example.IfwGuiProbe'
PERMISSIONS = ['--share=ipc', '--socket=x11', '--talk-name=org.kde.StatusNotifierWatcher']
NS = ('net', 'mnt', 'pid', 'ipc', 'user')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def mesa_inputs(runtime, gl, arch, elf_machine):
    metadata = configparser.ConfigParser(interpolation=None, strict=False)
    metadata.read(runtime / 'metadata', encoding='utf-8')
    extension = metadata['Extension org.freedesktop.Platform.GL']
    directory = f'lib/{arch}-linux-gnu/GL'
    if extension['directory'] != directory or 'vulkan/icd.d' not in extension['merge-dirs'].split(';'):
        raise ValueError('The native Platform does not advertise its expected Vulkan extension mount')
    files = gl / 'files'
    icd, = [p.resolve(strict=True) for p in (files / 'vulkan/icd.d').glob('lvp_icd*.json')]
    icd.relative_to(files)
    data = json.loads(icd.read_bytes())['ICD']
    mount = Path('/usr') / directory / 'default'
    driver = files / 'lib/libvulkan_lvp.so'
    driver.resolve(strict=True).relative_to(files)
    if data['library_path'] != str(mount / driver.relative_to(files)) or data.get('library_arch') != '64':
        raise ValueError('The llvmpipe ICD does not identify the native Flatpak GL library')
    return {'driverPath': str(driver), 'driverSha256': sha(driver), 'driverElfMachine': elf_machine(driver, arch),
            'driverSandboxPath': data['library_path'], 'icdPath': str(icd), 'icdSha256': sha(icd),
            'icdSandboxPath': str(mount / 'vulkan/icd.d' / icd.name)}


def archive_deployments(out, runtime, platform_receipt, gl, graphics, work):
    records = {}
    for root, name, source in ((runtime, 'platform', platform_receipt), (gl, 'graphics', graphics)):
        metadata = out / (name + '.metadata')
        shutil.copyfile(root / 'metadata', metadata)
        records[metadata.name] = sha(metadata)
        if records[metadata.name] != source['metadata_sha256']:
            raise ValueError('The private evidence differs from the verified deployment metadata')
        if work is not None:
            signature, receipt = (('signature.txt', 'verified.json') if name == 'platform'
                                  else ('graphics-signature.txt', 'verified-graphics.json'))
            for filename in (signature, receipt):
                shutil.copyfile(work / filename, out / filename)
                records[filename] = sha(out / filename)
            if (json.loads((out / receipt).read_bytes()) != source['acquisition']
                    or records[signature] != source['acquisition']['signature_sha256']):
                raise ValueError('The archived signature or acquisition receipt changed')
    return records


def main(args):
    qa = HERE.parents[1]
    root = qa.parents[1]
    art = root / 'artifacts/rust'
    launch = root / 'tools/RustCompatibilityOracle/installed/launch'
    sys.path[:0] = [str(qa / 'performance'), str(qa / 'portal-dialog'), str(launch)]
    from linux import namespace
    from runtime_pin import deployment, COMMITS
    from flatpak_fixture import SYS_DIRS
    from graphics import graphics_deployment, hosted_work

    arch = platform.machine()
    if arch not in COMMITS:
        raise ValueError('A native x64 or ARM64 Linux host is required')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if args.startup_gui:
        from installed_language import compiler_input, reference_images
        references = reference_images(args.startup_pixels.resolve(strict=True), art)
        binary, receipt, sources = compiler_input(args.startup_gui, args.startup_receipt, art, arch,
                                                   candidate=args.screen_reader == 'candidate')
    else:
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
        source_paths = [*sorted((qa / 'gui/src').glob('*.rs')), qa / 'gui/src/tray-icon.argb',
                        qa / 'gui/Cargo.toml', qa / 'gui/Cargo.lock', root / 'rust/Cargo.toml',
                        root / 'rust/crates/desktop-lifecycle/Cargo.toml', root / 'rust/crates/desktop-lifecycle/src/lib.rs']
        sources = {p.relative_to(root).as_posix(): sha(p) for p in source_paths}
        if (gui['target'] != f'{arch}-unknown-linux-gnu' or gui['binary_sha256'] != sha(binary)
                or sources != gui['sources']):
            raise ValueError('The staged native executable and its exact compiled first-party sources must match')
        subprocess.run(['git', 'ls-files', '--error-unmatch', '--', *sources], cwd=root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'diff', '--quiet', revision, '--', *sources], cwd=root, check=True)
    runtime, platform_receipt = deployment(args.hosted_runtime)
    gl, graphics = graphics_deployment(args.hosted_runtime)
    work = hosted_work(args.hosted_runtime) if args.hosted_runtime else None
    elf_machine = runpy.run_path(str(launch / 'run.py'))['native_elf_machine']
    gui_machine = elf_machine(binary, arch)
    mesa = mesa_inputs(runtime, gl, arch, elf_machine)
    manifest = root / 'packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml'
    finish = manifest.read_text().split('\nfinish-args:\n', 1)[1].split('\n\n', 1)[0].splitlines()
    shipping = [line.removeprefix('  - ') for line in finish]
    if set(shipping) != set(PERMISSIONS + ['--share=network', '--device=dri']):
        raise ValueError('Review the current shipping sandbox permissions')
    drivers = [HERE / n for n in ('run.py', 'observe.py', 'tray_menu.py', 'launch.sh')]
    if args.startup_gui:
        drivers += [HERE / 'installed_language.py', HERE / 'accessibility-readback.sh',
                    qa / 'gui/desktop_input.py', qa / 'gui/native.py']
    if args.screen_reader:
        drivers += [HERE / 'reader.py', qa / 'gui/screen_reader.py']
    if args.screen_reader == 'candidate':
        drivers += [qa / 'gui/source_profile.py', qa / 'gui/flatpak-accessibility/application-bus.patch',
                    qa / 'gui/flatpak-accessibility/build.py']
    drivers += [qa / 'gui/watcher.py', *(qa / 'performance' / n for n in
                ('linux.py', 'session.py', 'observations.py', 'x11.py', 'worker/second_launch.py')),
                qa / 'portal-dialog/flatpak_fixture.py', qa / 'portal-dialog/runtime_pin.py',
                launch / 'graphics.py', launch / 'run.py']
    dest = art / 'flatpak-gui-launch-assessment'
    dest.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='x11-', dir=dest))
    print(out, flush=True)
    shutil.copyfile(receipt, out / 'gui-build.json')
    if args.screen_reader == 'candidate':
        shutil.copyfile(receipt.parent / 'adapter.json', out / 'adapter.json')
    archive = out / 'observer-source.zip'
    with ZipFile(archive, 'x', ZIP_DEFLATED) as bundle:
        for p in [*drivers, manifest]:
            bundle.write(p, p.relative_to(root))
    receipts = archive_deployments(out, runtime, platform_receipt, gl, graphics, work)
    commands = ('bwrap', 'dbus-daemon', 'flatpak', 'ostree', 'xprop', 'xdg-dbus-proxy')
    if args.screen_reader:
        commands += ('orca', 'speech-dispatcher')
    if args.tray_menu:
        commands += ('dbus-monitor', 'stdbuf')
    save(out / 'inputs.json', {'sourceRevision': revision, 'guiPath': str(binary), 'guiSha256': sha(binary),
         'architecture': arch, 'guiElfMachine': gui_machine, 'deploymentFiles': receipts,
         'buildReceiptPath': str(receipt), 'buildReceiptSha256': sha(receipt), 'compilerSources': sources,
         'driverInputs': {p.relative_to(root).as_posix(): sha(p) for p in drivers},
         'observerArchiveSha256': sha(archive),
         'commands': {str(path): sha(path) for name in commands for path in [Path('/usr/bin') / name]},
         'platform': {**platform_receipt, 'path': str(runtime)},
         'gl': {**graphics, 'path': str(gl), **mesa},
         'shipping': {'file': manifest.relative_to(root).as_posix(), 'sha256': sha(manifest), 'finishArgs': shipping},
         'testFinishArgs': PERMISSIONS, 'trayMenu': args.tray_menu, 'savedLanguageCases': bool(args.startup_gui),
         'screenReader': args.screen_reader,
         'outerNamespaces': {n: os.readlink('/proc/self/ns/' + n) for n in NS}})
    cmd = namespace(out, qa / 'gui', None)
    (out / 'etc/passwd').write_text('root:x:0:0:Synthetic user:/tmp/home:/bin/false\n')
    (out / 'etc/group').write_text('root:x:0:\n')
    private = Path('/tmp/private-flatpak-system')
    cmd[cmd.index('--chdir'):] = [
        '--uid', '0', '--gid', '0', '--cap-add', 'CAP_SYS_ADMIN', '--cap-add', 'CAP_SETFCAP',
        '--cap-add', 'CAP_NET_ADMIN', '--dev-bind', '/dev/fuse', '/dev/fuse', '--tmpfs', '/sys', '--dir', '/var/tmp',
        *(arg for path in SYS_DIRS for arg in ('--dir', path)),
        '--ro-bind', str(runtime), str(private / platform_receipt['ref'] / platform_receipt['commit']),
        '--ro-bind', str(gl), str(private / graphics['ref'] / graphics['commit']), '--ro-bind', str(binary), '/binary',
        '--dir', '/graphics-pin', '--ro-bind', str(launch / 'graphics.py'), '/graphics-pin/graphics.py',
        '--ro-bind', str(qa / 'portal-dialog'), '/portal-fixture', '--setenv', 'FLATPAK_SYSTEM_DIR', str(private),
        '--setenv', 'FLATPAK_USER_DIR', '/tmp/home/.local/share/flatpak', '--dir', '/run/user/0',
        '--setenv', 'XDG_RUNTIME_DIR', '/run/user/0', '--chdir', '/qa', '--', '/usr/bin/python3', '-B',
        '/app/flatpak/run.py', '--inside']
    if args.startup_gui:
        position = cmd.index('--chdir')
        cmd[position:position] = ['--dir', '/references', *(item for lang, path in references.items()
                                 for item in ('--ro-bind', str(path), '/references/' + lang + '.bgra'))]
    result = subprocess.run(cmd, timeout=180)
    files = sorted(p for p in out.rglob('*') if p.is_file())
    (out / 'evidence.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(out)}\n' for p in files))
    if result.returncode or not json.loads((out / 'result.json').read_bytes()).get('passed'):
        raise RuntimeError(f'Installed Flatpak observation failed in {out}')


def inside():
    sys.path[:0] = ['/driver', '/portal-fixture', '/graphics-pin']
    from flatpak_fixture import export_install, prepare_runtime, setup_command
    from graphics import pinned_extension
    from runtime_pin import BRANCH
    import observe

    out = Path('/qa')
    inputs = json.loads((out / 'inputs.json').read_bytes())
    report = {'passed': False, 'inputsSha256': sha(out / 'inputs.json'), 'workerEnabled': False}
    try:
        private = Path('/tmp/private-flatpak-system')
        ns = {n: os.readlink('/proc/self/ns/' + n) for n in NS}
        arch = platform.machine()
        if (arch != inputs['architecture'] or Path.home() != Path('/tmp/home')
                or os.getuid() != 0 or os.environ.get('XDG_RUNTIME_DIR') != '/run/user/0'
                or os.getenv('FLATPAK_USER_DIR') != '/tmp/home/.local/share/flatpak'
                or any(ns[n] == inputs['outerNamespaces'][n] for n in NS)
                or Path('/proc/net/route').read_text().splitlines()[1:] or sha(Path('/binary')) != inputs['guiSha256']):
            raise RuntimeError('Expected the isolated native assessment and an empty network namespace')
        report['namespaces'] = ns
        os.umask(0o077)
        Path.home().mkdir()
        Path('/run/user/0').chmod(0o700)
        pin = pinned_extension()
        gl = private / pin['ref'] / pin['commit']
        mounts = Path('/proc/self/mountinfo').read_text().splitlines()
        if (any(inputs['gl'][key] != value for key, value in pin.items())
                or not any(row.split()[4] == str(gl) and 'ro' in row.split()[5].split(',') for row in mounts)
                or sha(gl / 'metadata') != pin['metadata_sha256']):
            raise RuntimeError('GL extension must be the pinned read-only deployment')
        prepare_runtime(inputs['platform']['commit'])
        (gl.parent / 'active').symlink_to(pin['commit'])
        app = Path('/tmp/gui-build')
        files = app / 'files/bin'
        files.mkdir(parents=True)
        (app / 'var').mkdir()
        runtime = inputs['platform']['ref'].removeprefix('runtime/')
        (app / 'metadata').write_text(f'[Application]\nname={APP}\nruntime={runtime}\nsdk=org.freedesktop.Sdk/{arch}/{BRANCH}\n')
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
        source.add_argument('--startup-gui', type=Path, metavar='BINARY',
                            help='exercise saved German and English using the original reviewed Linux x64 GUI')
        parser.add_argument('--startup-receipt', type=Path, metavar='NATIVE_JSON',
                            help='original source and compiler receipt from gui/startup/qualify.py')
        parser.add_argument('--startup-pixels', type=Path, metavar='PIXELS',
                            help='directory containing the reviewed German and English 640 by 400 headless GPU frames')
        parser.add_argument('--tray-menu', action='store_true')
        parser.add_argument('--screen-reader', choices=['stock', 'candidate'],
                            help='compare the installed stock or qualified candidate editor with native Orca')
        parser.add_argument('--hosted-runtime', type=Path, metavar='DEPLOYMENT',
                            help='verified native Platform deployment on a disposable hosted runner')
        args = parser.parse_args()
        if bool(args.startup_gui) != bool(args.startup_receipt) or bool(args.startup_gui) != bool(args.startup_pixels):
            parser.error('--startup-gui, --startup-receipt and --startup-pixels must be used together')
        if args.screen_reader and not args.startup_gui:
            parser.error('--screen-reader requires the source-bound installed startup GUI')
        main(args)
