"""Launch the unmodified Fedora x64 Flatpak 3.0.4 twice on an offline private X11 desktop.

Run from the checkout with python3 -B tools/RustCompatibilityOracle/installed/launch/run.py.
Place the release bundle in artifacts/rust/legacy-installer-inputs/v3.0.4 and the public
Pages commit metadata in artifacts/rust/shipping-flatpak-launch/signature/3.0.4.commitmeta.
"""

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
APP = 'io.github.voltkraft.immich-folder-watch'
COMMIT = 'abeebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da'
SIGNATURE = '739b5ddb83a090eab38111bdeb5a7a55e7dbb803622bf883061136adbca8b426'
KEY = '4ED65AC1C14D559C721C7A8B44B33451708EAD7D'
NS = ('mnt', 'net', 'user', 'ipc', 'pid')


def sha(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def namespaces():
    return {n: os.readlink('/proc/self/ns/' + n) for n in NS}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def require_original_reopen(report):
    first, launch, reopened = report['first'], report['secondLaunch'], report['second']
    require(report['firstHidden'] and report['outcome'] == 'existing-primary-reopened'
            and reopened['window']['xid'] == first['window']['xid']
            and reopened['gui'] == first['gui'] and reopened['instance'] == first['instance'],
            'The second ordinary launch did not reopen the original process and X window')
    require({'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME'} <= first['directoryIdentity'].keys()
            and first['directoryIdentity'] == launch['directoryIdentity'] == reopened['directoryIdentity'],
            'The observed runtime or configuration directory identity differs')
    require(report['firstExit'] == report['secondExit'] == 0 and report['originalGuiExited']
            and report['secondGuiExited'] and report['allInstancesExited'] and report['userInstallationEmpty'],
            'Both ordinary exits and removal of the private installation are required')


def outer():
    root = HERE.parents[3]
    qa = root / 'tools/rust-qa'
    sys.path[:0] = [str(qa / 'portal-dialog'), str(qa / 'performance')]
    from linux import namespace
    from flatpak_fixture import SYS_DIRS
    from runtime_pin import deployment
    import runpy
    gl_driver = runpy.run_path(str(qa / 'gui/flatpak/run.py'))
    release = json.loads((HERE.parent / 'release.json').read_bytes())
    asset = release['assets']['linux-x64']
    art = root / 'artifacts/rust'
    original = art / 'legacy-installer-inputs/v3.0.4' / asset['name']
    dest = art / 'shipping-flatpak-launch'
    metadata = dest / 'signature/3.0.4.commitmeta'
    key = root / 'packaging/flatpak/repository-signing-key.asc'
    require(platform.machine() == 'x86_64' and sha(original) == asset['sha256'] and original.stat().st_size == asset['bytes']
            and sha(metadata) == SIGNATURE, 'Original release or detached signature differs from the source pins')
    runtime, runtime_receipt = deployment(None)
    gl_ref = Path('runtime', gl_driver['GL'], 'x86_64/26.08')
    gl = Path('/var/lib/flatpak') / gl_ref / gl_driver['GL_COMMIT']
    require(gl.resolve(strict=True) == gl and sha(gl / 'metadata') == gl_driver['GL_METADATA'], 'Unexpected GL extension')
    drivers = [HERE / 'run.py', HERE / 'observe.py', HERE.parent / 'release.json', key, qa / 'gui/flatpak/run.py', qa / 'gui/watcher.py',
               *(qa / 'performance' / p for p in ('linux.py', 'session.py', 'observations.py', 'x11.py', 'worker/second_launch.py')),
               *(qa / 'portal-dialog' / p for p in ('runtime_pin.py', 'flatpak_fixture.py'))]
    out = Path(tempfile.mkdtemp(dir=dest, prefix='x11-'))
    print(out, flush=True)
    with ZipFile(out / 'observer-source.zip', 'x', ZIP_DEFLATED) as archive:
        for path in drivers:
            archive.write(path, path.relative_to(root))
    inputs = dict(revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                  sources={str(p.relative_to(root)): sha(p) for p in drivers}, observerArchive=sha(out / 'observer-source.zip'),
                  release=release['commit'], tag=release['tag'], asset=asset, ostree=COMMIT, outerNamespaces=namespaces(),
                  signatureUrl='https://voltkraft.github.io/immich-folder-watch/repo/objects/' + COMMIT[:2] + '/' + COMMIT[2:] + '.commitmeta',
                  signatureSha256=SIGNATURE, publicKeySha256=sha(key), platform=runtime_receipt,
                  glRef=str(gl_ref), glCommit=gl_driver['GL_COMMIT'], glMetadata=gl_driver['GL_METADATA'])
    save(out / 'inputs.json', inputs)
    command = namespace(out, HERE, None)
    (out / 'etc/passwd').write_text('root:x:0:0:Synthetic user:/tmp/home:/bin/false\n')
    (out / 'etc/group').write_text('root:x:0:\n')
    private = Path('/tmp/private-flatpak-system')
    command[command.index('--chdir'):] = ['--uid', '0', '--gid', '0', '--cap-add', 'CAP_SYS_ADMIN', '--cap-add', 'CAP_SETFCAP',
        '--cap-add', 'CAP_NET_ADMIN', '--dev-bind', '/dev/fuse', '/dev/fuse', '--tmpfs', '/sys', '--dir', '/var/tmp',
        *(arg for d in SYS_DIRS for arg in ('--dir', d)),
        '--ro-bind', str(runtime), str(private / runtime_receipt['ref'] / runtime_receipt['commit']),
        '--ro-bind', str(gl), str(private / gl_ref / gl_driver['GL_COMMIT']), '--ro-bind', str(original), '/original.flatpak',
        '--ro-bind', str(metadata), '/original.commitmeta', '--ro-bind', str(key), '/public-key.asc',
        '--ro-bind', str(qa / 'gui/watcher.py'), '/watcher.py', '--ro-bind', str(qa / 'portal-dialog'), '/portal-fixture', '--setenv', 'FLATPAK_SYSTEM_DIR', str(private),
        '--setenv', 'FLATPAK_USER_DIR', '/tmp/home/.local/share/flatpak', '--dir', '/run/user/0',
        '--setenv', 'XDG_RUNTIME_DIR', '/run/user/0', '--chdir', '/qa', '--', '/usr/bin/python3', '-B', '/app/run.py', '--inside']
    try:
        subprocess.run(command, timeout=175, check=True)
    finally:
        (out / 'evidence.sha256').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file()))


def inside():
    sys.path[:0] = ['/driver', '/portal-fixture']
    from gi.repository import Gio, GLib
    from flatpak_fixture import prepare_runtime, setup_command, start_launch_bus, LAUNCH_BUS
    from session import private_session
    import observe

    out = Path('/qa')
    inputs = json.loads((out / 'inputs.json').read_bytes())
    report = dict(passed=False, inputs=sha(out / 'inputs.json'), namespaces=namespaces())
    try:
        require(os.getuid() == 0 and Path.home() == Path('/tmp/home') and not Path.home().exists()
                and not Path('/var/lib/flatpak').exists() and all(report['namespaces'][k] != inputs['outerNamespaces'][k] for k in NS)
                and not Path('/proc/net/route').read_text().splitlines()[1:], 'A fresh offline private namespace is required')
        os.umask(0o077)
        Path.home().mkdir()
        Path('/run/user/0').chmod(0o700)
        prepare_runtime(inputs['platform']['commit'])
        gl = Path('/tmp/private-flatpak-system') / inputs['glRef'] / inputs['glCommit']
        require(sha(gl / 'metadata') == inputs['glMetadata'], 'Unexpected private GL runtime')
        (gl.parent / 'active').symlink_to(gl.name)
        require(sha(Path('/original.flatpak')) == inputs['asset']['sha256'] and sha(Path('/original.commitmeta')) == SIGNATURE
                and sha(Path('/public-key.asc')) == inputs['publicKeySha256'], 'Unexpected mounted input')
        with ExitStack() as stack:
            display, report['xserver'] = private_session(stack)
            bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            report['launchBus'] = start_launch_bus(stack, bus)
            os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = LAUNCH_BUS
            setup_command(['flatpak', '--user', 'install', '--noninteractive', '--no-deps', '--no-related', '--bundle', '/original.flatpak'])
            try:
                ref = 'app/' + APP + '/x86_64/master'
                result = subprocess.check_output(['flatpak', '--user', 'info', '--show-commit', ref], text=True).strip()
                require(result == COMMIT, 'Installed commit differs from the published release')
                repo = Path(os.environ['FLATPAK_USER_DIR']) / 'repo/objects' / COMMIT[:2]
                commit = repo / (COMMIT[2:] + '.commit')
                require(sha(commit) == COMMIT, 'The installed commit object differs')
                signed = GLib.Variant.new_from_bytes(GLib.VariantType.new('a{sv}'), GLib.Bytes.new(Path('/original.commitmeta').read_bytes()), False)
                signature, = signed.unpack()['ostree.gpgsigs']
                (out / 'commit.sig').write_bytes(bytes(signature))
                (out / 'original.commit').write_bytes(commit.read_bytes())
                setup_command(['gpg', '--batch', '--dearmor', '--output', '/tmp/keyring.gpg', '/public-key.asc'])
                status = subprocess.check_output(['gpgv', '--status-fd=1', '--keyring', '/tmp/keyring.gpg', str(out / 'commit.sig'), str(commit)], stderr=subprocess.STDOUT, text=True)
                (out / 'signature.log').write_text(status)
                signatures = [line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
                require(len(signatures) == 1 and len(signatures[0]) == 12 and signatures[0][2] == signatures[0][-1] == KEY,
                        'Expected the original repository key as signer and primary key')
                report['verifiedSigningKey'] = signatures[0][2]
                files = Path(subprocess.check_output(['flatpak', '--user', 'info', '--show-location', ref], text=True).strip()) / 'files'
                report['apphost'] = sha(files / 'lib/immich-folder-watch/immich-folder-watch')
                report['managedAssembly'] = sha(files / 'lib/immich-folder-watch/immich-folder-watch.dll')
                observe.run(display, bus, inputs, report, out)
            finally:
                setup_command(['flatpak', '--user', 'uninstall', '--noninteractive', ref])
                remaining = subprocess.check_output(['flatpak', '--user', 'list', '--app', '--columns=ref'], text=True).strip()
                report['userInstallationEmpty'] = not remaining
                require(not remaining, 'Application remains after uninstall')
        require_original_reopen(report)
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        save(out / 'result.json', report)


if __name__ == '__main__':
    if sys.argv[1:] == ['--inside']:
        inside()
    elif len(sys.argv) == 1:
        outer()
    else:
        raise SystemExit(__doc__)
