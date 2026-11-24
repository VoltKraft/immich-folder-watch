"""Check the XDG path and process identity prerequisites of the installed old/new Linux pairing.

Run python3 -B tools/RustCompatibilityOracle/installed/interop/assess.py --same-id or --different-id.
Use --gui-build artifacts/rust/GUI_BUILD to exercise the actual candidate against the installed old GUI.
Use the published 3.0.4 bundle and detached signature described by ../launch/run.py and its
pinned x64 Platform and GL runtimes. No previous trial output is required.
"""

from contextlib import ExitStack
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import select
import shutil
import subprocess
import stat
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
PROBE = 'org.example.IfwInteropProbe'
EXPECTED_PROBE = '941d9567ad6c827e1b3b668aef6933d93133421b1de25c87c73f7fad75cb341b'
QUALIFIED_SOURCES = {
    'main.rs': 'e93bde61c0577364043dbdfd55f9693358558d5099898942fc8d91afe6e67ecc',
    'unix.rs': '4feef97f3358d45b344bd93a83f4358df07be284e07103b0957609aad2646092',
}


def sha(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def verify_paths(same_id, first_directory, second_directory, first_socket, observation):
    visible = re.fullmatch(r'NORMAL_ENDPOINT visible (\d+) (\d+)', observation)
    if same_id:
        require(first_directory == second_directory and visible and list(map(int, visible.groups())) == first_socket,
                'The two branches of the same application ID did not see the same runtime directory and socket')
    else:
        require(first_directory != second_directory and observation == 'NORMAL_ENDPOINT absent',
                'The control application ID must have a distinct runtime directory and no shipping endpoint')


def verify_siblings(observer, first, second):
    for process in (first, second):
        pids = process['namespacePids']
        require(len(pids) == 2 and pids[0] == process['gui']['pid'] and pids[1] > 0,
                'Expected a process in a direct child PID namespace of the common observer')
        require(all(process['namespaces'][n] != observer[n] for n in ('mnt', 'pid'))
                and process['namespaces']['net'] == observer['net'], 'Expected private PID and mount namespaces on the isolated network')
    require(first['gui']['pid'] != second['gui']['pid'] and first['instance'] != second['instance']
            and all(first['namespaces'][n] != second['namespaces'][n] for n in ('mnt', 'pid')),
            'The two live refs must be in distinct sibling namespaces')


def pidfd(stack, pid):
    descriptor = os.pidfd_open(pid)
    stack.callback(os.close, descriptor)
    poll = select.poll()
    poll.register(descriptor, select.POLLIN)
    return poll


def gui_source_snapshot(root, recorded):
    qa = root / 'tools/rust-qa/gui'
    paths = [*sorted((qa / 'src').glob('*.rs')), qa / 'src/tray-icon.argb',
             qa / 'Cargo.toml', qa / 'Cargo.lock', root / 'rust/Cargo.toml',
             root / 'rust/crates/desktop-lifecycle/Cargo.toml', root / 'rust/crates/desktop-lifecycle/src/lib.rs']
    allowed = {p.relative_to(root).as_posix(): p for p in paths}
    require(isinstance(recorded, dict) and recorded.keys() == allowed.keys()
            and 'tools/rust-qa/gui/src/linux_legacy.rs' in allowed,
            'The native GUI source inventory differs from the expected local sources')
    snapshot = {}
    for name, path in allowed.items():
        require(path.resolve(strict=True) == path and path.is_file(), 'Expected a regular local GUI source')
        contents = path.read_bytes()
        require(hashlib.sha256(contents).hexdigest() == recorded[name], 'The native GUI source binding differs')
        snapshot[name] = contents
    return snapshot


def outer(same_id, gui_build=None):
    root = HERE.parents[3]
    art = root / 'artifacts/rust'
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    result_dir = art / 'shipping-flatpak-interop'
    result_dir.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='same-id-' if same_id else 'different-id-', dir=result_dir))
    print(out, flush=True)
    frozen = out / 'source'
    shared = ['packaging/flatpak/repository-signing-key.asc', 'rust/toolchain-inputs.json',
              'tools/RustCompatibilityOracle/installed/release.json',
              *(f'tools/RustCompatibilityOracle/installed/launch/{name}.py' for name in ('run', 'observe')),
              *(f'tools/rust-qa/{name}' for name in ('instance/main.rs', 'instance/unix.rs', 'check-toolchain.py',
                'gui/flatpak/run.py', 'gui/watcher.py', 'portal-dialog/flatpak_fixture.py', 'portal-dialog/runtime_pin.py',
                'performance/session.py', 'performance/linux.py', 'performance/observations.py',
                'performance/x11.py', 'performance/worker/second_launch.py'))]
    snapshot = {}
    with ZipFile(out / 'observer-source.zip', 'x', ZIP_DEFLATED) as archive:
        for name in shared:
            path = frozen / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(['git', 'show', f'{revision}:{name}'], cwd=root))
            archive.write(path, name)
            snapshot[name] = sha(path)
        driver_names = ['assess.py', 'hold.sh', 'test_assess.py']
        if gui_build is not None:
            driver_names.extend(['gui_refusal.py', 'gui-launch.sh'])
        for name in driver_names:
            driver = HERE / name
            relative = driver.relative_to(root).as_posix()
            dest = frozen / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(driver, dest)
            archive.write(dest, relative)
            snapshot[relative] = sha(dest)
    frozen_qa = frozen / 'tools/rust-qa'
    legacy = frozen / 'tools/RustCompatibilityOracle/installed/launch'
    sys.path[:0] = [str(legacy), str(frozen_qa / 'portal-dialog'), str(frozen_qa / 'performance')]
    from run import save, namespaces, APP, SIGNATURE
    from linux import namespace
    from flatpak_fixture import SYS_DIRS
    from runtime_pin import deployment

    release = json.loads((legacy.parent / 'release.json').read_bytes())
    asset = release['assets']['linux-x64']
    bundle = art / 'legacy-installer-inputs/v3.0.4' / asset['name']
    signed = art / 'shipping-flatpak-launch/signature/3.0.4.commitmeta'
    key = frozen / 'packaging/flatpak/repository-signing-key.asc'
    require(sha(bundle) == asset['sha256'] and bundle.stat().st_size == asset['bytes'] and sha(signed) == SIGNATURE,
            'The original release asset and its public detached signature are required')
    runtime, platform = deployment(None)
    graphics = runpy.run_path(str(frozen_qa / 'gui/flatpak/run.py'))
    pins = dict(asset=asset, release=release['commit'], platform=platform, signature=SIGNATURE, publicKey=sha(key),
                glRef=f"runtime/{graphics['GL']}/x86_64/26.08", glCommit=graphics['GL_COMMIT'], glMetadata=graphics['GL_METADATA'])
    gl = Path('/var/lib/flatpak') / pins['glRef'] / pins['glCommit']
    require(gl.resolve(strict=True) == gl and sha(gl / 'metadata') == pins['glMetadata'], 'Unexpected public GL deployment')
    compiler = art / 'toolchain/bin/rustc'
    probe_sources = frozen_qa / 'instance'
    require(all(sha(probe_sources / name) == expected for name, expected in QUALIFIED_SOURCES.items()),
            'Source of the prior Fedora interoperability probe changed')
    subprocess.run([sys.executable, frozen_qa / 'check-toolchain.py', 'x86_64-unknown-linux-gnu', '--rustc', compiler], check=True)
    binary = out / 'instance'
    # Relative source names keep compiler diagnostics embedded in the executable independent of the clone's path.
    subprocess.run([compiler, '--edition=2024', '-Dwarnings', '-O', 'main.rs', '-o', binary], cwd=probe_sources, check=True)
    require(sha(binary) == EXPECTED_PROBE, 'The compiler did not reproduce the path-independent probe binary')
    gui_hash = None
    gui_files = None
    if gui_build is not None:
        build = gui_build.resolve(strict=True)
        require(build.is_relative_to(art.resolve()) and build != art, 'Expected an isolated GUI build')
        gui = build / 'release/native-gui-assessment'
        receipt = gui.with_suffix('.inputs.json')
        require(all(p.resolve(strict=True) == p and p.is_file() for p in (gui, receipt)), 'Expected local build files')
        evidence = json.loads(receipt.read_bytes())
        require(evidence['target'] == 'x86_64-unknown-linux-gnu' and evidence['binary_sha256'] == sha(gui), 'The native GUI binary differs')
        gui_sources = gui_source_snapshot(root, evidence['sources'])
        with ZipFile(out / 'gui-sources.zip', 'x', ZIP_DEFLATED) as archive:
            for name, contents in sorted(gui_sources.items()):
                archive.writestr(name, contents)
        shutil.copyfile(receipt, out / 'gui-build.json')
        gui_hash = sha(gui)
        gui_files = {name: sha(out / name) for name in ('gui-build.json', 'gui-sources.zip')}
    save(out / 'inputs.json', dict(base=pins, guiHash=gui_hash, guiEvidence=gui_files, namespaces=namespaces(), probeAppId=APP if same_id else PROBE,
                                   sameId=same_id, revision=revision, rustc=sha(compiler), probe=EXPECTED_PROBE,
                                   sources=snapshot, archive=sha(out / 'observer-source.zip')))
    command = namespace(out, frozen / HERE.relative_to(root), None)
    (out / 'etc/passwd').write_text('root:x:0:0:Synthetic user:/tmp/home:/bin/false\n')
    (out / 'etc/group').write_text('root:x:0:\n')
    private = Path('/tmp/private-flatpak-system')
    command[command.index('--chdir'):] = ['--uid', '0', '--gid', '0', '--cap-add', 'CAP_SYS_ADMIN', '--cap-add', 'CAP_SETFCAP', '--cap-add', 'CAP_NET_ADMIN',
        '--dev-bind', '/dev/fuse', '/dev/fuse', '--tmpfs', '/sys', '--dir', '/var/tmp', *(arg for p in SYS_DIRS for arg in ('--dir', p)),
        '--ro-bind', str(runtime), str(private / platform['ref'] / platform['commit']), '--ro-bind', str(gl), str(private / pins['glRef'] / pins['glCommit']),
        '--ro-bind', str(bundle), '/original.flatpak', '--ro-bind', str(signed), '/original.commitmeta',
        '--ro-bind', str(key), '/public-key.asc', '--ro-bind', str(legacy), '/legacy-launch',
        '--ro-bind', str(frozen_qa / 'gui/watcher.py'), '/watcher.py', '--ro-bind', str(frozen_qa / 'portal-dialog'), '/portal-fixture',
        '--setenv', 'FLATPAK_SYSTEM_DIR', str(private), '--setenv', 'FLATPAK_USER_DIR', '/tmp/home/.local/share/flatpak',
        '--dir', '/run/user/0', '--setenv', 'XDG_RUNTIME_DIR', '/run/user/0', '--chdir', '/qa', '--', '/usr/bin/python3', '-B', '/app/assess.py', '--inside']
    try:
        if gui_build is not None:
            location = command.index('--chdir')
            command[location:location] = ['--ro-bind', str(gui), '/candidate-gui']
        subprocess.run(command, timeout=125, check=True)
    finally:
        (out / 'evidence.sha256').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file()))


def verify_uninstalled(report):
    report['userInstallationEmpty'] = not subprocess.check_output(['flatpak', '--user', 'list', '--app', '--columns=ref'], text=True, timeout=6).strip()
    require(report['userInstallationEmpty'], 'Installed application remained')
    report['passed'] = True


def inside():
    sys.path[:0] = ['/legacy-launch', '/driver', '/portal-fixture']
    from run import require, save, sha, namespaces, COMMIT, APP, KEY
    from observe import identity, window, witness
    from session import checked_start, check_alive, wait_for, private_session, stop
    from flatpak_fixture import prepare_runtime, export_install, setup_command, start_launch_bus, LAUNCH_BUS
    from gi.repository import Gio, GLib

    out = Path('/qa')
    i = json.loads((out / 'inputs.json').read_bytes())
    pins = i['base']
    probe_app = i['probeAppId']
    r = dict(passed=False, inputs=sha(out / 'inputs.json'), namespaces=namespaces(), sameId=i['sameId'],
             observerSentLegacySignal=False, installedHandoverQualified=False, peerCredentialsMeasured=False)
    try:
        require(os.getuid() == 0 and Path.home() == Path('/tmp/home') and not Path.home().exists() and not Path('/var/lib/flatpak').exists()
                and all(v != i['namespaces'][k] for k, v in r['namespaces'].items()) and not Path('/proc/net/route').read_text().splitlines()[1:]
                and sha(Path('/original.flatpak')) == pins['asset']['sha256'] and sha(out / 'instance') == EXPECTED_PROBE, 'Invalid isolated inputs')
        os.umask(0o077)
        Path.home().mkdir()
        Path('/run/user/0').chmod(0o700)
        prepare_runtime(pins['platform']['commit'])
        gl = Path('/tmp/private-flatpak-system') / pins['glRef'] / pins['glCommit']
        require(sha(gl / 'metadata') == pins['glMetadata'], 'Unexpected GL deployment')
        (gl.parent / 'active').symlink_to(gl.name)
        with ExitStack() as stack:
            display, r['xserver'] = private_session(stack)
            bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            r['launchBus'] = start_launch_bus(stack, bus)
            os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = LAUNCH_BUS
            oldref = 'app/' + APP + '/x86_64/master'
            setup_command(['flatpak', '--user', 'install', '--noninteractive', '--no-deps', '--no-related', '--bundle', '/original.flatpak'])
            stack.callback(setup_command, ['flatpak', '--user', 'uninstall', '--noninteractive', oldref])
            require(subprocess.check_output(['flatpak', '--user', 'info', '--show-commit', oldref], text=True).strip() == COMMIT, 'Unexpected installed old ref')
            repo = Path(os.environ['FLATPAK_USER_DIR']) / 'repo/objects' / COMMIT[:2]
            commit = repo / (COMMIT[2:] + '.commit')
            require(sha(commit) == COMMIT and sha(Path('/original.commitmeta')) == pins['signature']
                    and sha(Path('/public-key.asc')) == pins['publicKey'], 'Installed commit or trust inputs changed')
            metadata = GLib.Variant.new_from_bytes(GLib.VariantType.new('a{sv}'), GLib.Bytes.new(Path('/original.commitmeta').read_bytes()), False)
            signature, = metadata.unpack()['ostree.gpgsigs']
            (out / 'commit.sig').write_bytes(bytes(signature))
            (out / 'original.commit').write_bytes(commit.read_bytes())
            setup_command(['gpg', '--batch', '--dearmor', '--output', '/tmp/keyring.gpg', '/public-key.asc'])
            status = subprocess.check_output(['gpgv', '--status-fd=1', '--keyring', '/tmp/keyring.gpg', str(out / 'commit.sig'), str(commit)],
                                             text=True, stderr=subprocess.STDOUT, timeout=8)
            (out / 'signature.log').write_text(status)
            signatures = [line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
            require(len(signatures) == 1 and len(signatures[0]) == 12 and signatures[0][2] == signatures[0][-1] == KEY,
                    'The installed original commit does not have the expected signing and primary key')
            r['verifiedSigningKey'] = KEY
            deployment = Path(subprocess.check_output(['flatpak', '--user', 'info', '--show-location', oldref], text=True).strip())
            r['apphost'] = sha(deployment / 'files/lib/immich-folder-watch/immich-folder-watch')
            app = Path('/tmp/interop-build')
            bin_dir = app / 'files/bin'
            bin_dir.mkdir(parents=True)
            (app / 'var').mkdir()
            (app / 'metadata').write_text(f'[Application]\nname={probe_app}\nruntime=org.freedesktop.Platform/x86_64/26.08\nsdk=org.freedesktop.Sdk/x86_64/26.08\n')
            if i['guiHash']:
                require(sha(Path('/candidate-gui')) == i['guiHash'], 'Unexpected staged GUI')
                shutil.copy2('/candidate-gui', bin_dir / 'native-gui-assessment')
                shutil.copyfile('/app/gui-launch.sh', bin_dir / 'launch')
            else:
                shutil.copy2(out / 'instance', bin_dir / 'instance')
                shutil.copyfile('/app/hold.sh', bin_dir / 'launch')
            (bin_dir / 'launch').chmod(0o755)
            finish = ['--command=launch', '--share=ipc', '--share=network', '--socket=x11', '--device=dri', '--talk-name=org.kde.StatusNotifierWatcher']
            installed = r['probeRef'] = export_install(app, probe_app, finish)
            stack.callback(setup_command, ['flatpak', '--user', 'remote-delete', 'fixture'])
            stack.callback(setup_command, ['flatpak', '--user', 'uninstall', '--noninteractive', installed['installed_ref']])
            if i['guiHash']:
                from gui_refusal import run as observe_refusal
                observe_refusal(stack, bus, display, pins, r, out, i['guiHash'])
                stack.close()
                verify_uninstalled(r)
                return
            tray = out / 'watcher.log'
            peer = checked_start(stack, ['/usr/bin/python3', '-B', '/watcher.py'], tray)
            wait_for(lambda: check_alive(peer, tray) or 'WATCHER_READY' in tray.read_text(), 5, 'Private status watcher unavailable')
            oldlog = out / 'shipping.log'
            old = checked_start(stack, ['flatpak', 'run', '--user', '--branch=master', APP], oldlog)
            xid = wait_for(lambda: check_alive(old, oldlog) or display.visible(), 20, 'Missing original window')
            original = r['original'] = witness(old, window(display, xid), pins, r, out, 'shipping')
            original_lifetime = pidfd(stack, original['gui']['pid'])
            wait_for(lambda: check_alive(old, oldlog) or 'REGISTERED ' in tray.read_text(), 10, 'No original status menu')
            log = out / 'probe.log'
            output = stack.enter_context(log.open('w'))
            probe = subprocess.Popen(['flatpak', 'run', '--user', '--branch=test', probe_app], stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT, text=True)
            stack.callback(stop, probe)
            stack.callback(probe.stdin.close)
            wait_for(lambda: check_alive(probe, log) or 'WRITER_HELD' in log.read_text().splitlines(), 10, 'Rust writer did not hold its synthetic guard')
            rows = subprocess.check_output(['flatpak', 'ps', '--columns=instance,pid,child-pid,application'], text=True).splitlines()
            instance_row, = [row.split('\t') for row in rows if row.split('\t')[1] == str(probe.pid)]
            instance, wrap, sandbox, app_name = instance_row
            require(app_name == probe_app, 'Unexpected application ID in the process table')
            require(int(wrap) == probe.pid, 'Unexpected probe wrapper')
            children = Path(f'/proc/{sandbox}/task/{sandbox}/children').read_text().split()
            rust, = [Path('/proc') / p for p in children if os.readlink(f'/proc/{p}/exe') == '/app/bin/instance']
            probe_lifetime = pidfd(stack, int(rust.name))
            require(sha(rust / 'exe') == EXPECTED_PROBE, 'Unexpected running probe executable')
            pid_path = [int(p) for p in next(line for line in (rust / 'status').read_text().splitlines() if line.startswith('NSpid:')).split()[1:]]
            info = configparser.ConfigParser(interpolation=None)
            contents = (rust / 'root/.flatpak-info').read_bytes()
            (out / 'probe.flatpak-info').write_bytes(contents)
            info.read_string(contents.decode())
            require(info['Application']['name'] == probe_app and info['Instance']['branch'] == 'test' and
                    info['Instance']['app-commit'] == installed['commit'] and info['Instance']['instance-id'] == instance,
                    'Rust process is outside the installed probe ref')
            directory = re.fullmatch(r'XDG_RUNTIME_DIR (\d+) (\d+) (\d+)', log.read_text().splitlines()[0])
            require(directory, 'Missing in-sandbox runtime directory readback')
            dirs = [int(directory[1]), int(directory[2])]
            subject = r['probe'] = dict(gui=identity(int(rust.name)), namespacePids=pid_path, instance=instance,
                                       namespaces={n: os.readlink(rust / 'ns' / n) for n in ('pid', 'mnt', 'net')},
                                       runtimeDirectory=dirs, runtimeMode=directory[3], normalEndpoint=log.read_text().splitlines()[1],
                                       flatpakPs=rows)
            shipping_proc = Path('/proc') / str(original['gui']['pid']) / 'root'
            socket_path = shipping_proc / original['paths']['XDG_RUNTIME_DIR'].lstrip('/') / 'immich-folder-watch.sock'
            original_socket = socket_path.lstat()
            r['originalEndpoint'] = [original_socket.st_dev, original_socket.st_ino]
            r['firstAndSecondStillRunning'] = [not bool(original_lifetime.poll(0)), not bool(probe_lifetime.poll(0))]
            r['unchangedGuiIdentity'] = [identity(original['gui']['pid']) == original['gui'], identity(int(rust.name)) == subject['gui']]
            r['originalEndpointIsSocket'] = stat.S_ISSOCK(original_socket.st_mode)
            require(r['originalEndpointIsSocket'] and directory[3] == '700' and all(r['firstAndSecondStillRunning'])
                    and all(r['unchangedGuiIdentity']), 'The original socket and both exact native processes must still be present')
            verify_paths(i['sameId'], original['directoryIdentity']['XDG_RUNTIME_DIR'], dirs, r['originalEndpoint'], subject['normalEndpoint'])
            verify_siblings(r['namespaces'], original, subject)
            r['sameEndpointObserved'] = i['sameId']
            r['outcome'] = 'From both live NSpid paths and their distinct PID namespaces, the sibling peer has no positive local PID. '
            r['outcome'] += 'The reviewed activation requires an authenticated positive PID. No connection was attempted.'
            probe.stdin.write('RELEASE\n')
            probe.stdin.flush()
            r['probeExit'] = probe.wait(timeout=8)
            r['probeExitedBeforeOriginalQuit'] = bool(probe_lifetime.poll(1000)) and not original_lifetime.poll(0)
            bus.call_sync(APP + '.Tray', '/StatusNotifierItem/Menu', 'com.canonical.dbusmenu', 'Event', GLib.Variant('(isvu)', (3, 'clicked', GLib.Variant('i', 0), 0)), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
            r['originalExit'] = old.wait(timeout=12)
            r['originalNativeExited'] = bool(original_lifetime.poll(1000))
            require(r['originalNativeExited'] and r['probeExitedBeforeOriginalQuit'] and r['originalExit'] == r['probeExit'] == 0 and 'WRITER_RELEASED' in log.read_text().splitlines(), 'Original or probe did not quit normally')
            wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=3).strip(), 6, 'Installed instance remained after quit')
        verify_uninstalled(r)
    except Exception as error:
        r['error'] = str(error)
        raise
    finally:
        save(out / 'result.json', r)


if __name__ == '__main__':
    if sys.argv[1:] == ['--inside']:
        inside()
    elif len(sys.argv) == 3 and sys.argv[1] == '--gui-build':
        outer(True, Path(sys.argv[2]))
    elif sys.argv[1:] in (['--same-id'], ['--different-id']):
        outer(sys.argv[1] == '--same-id')
    else:
        raise SystemExit(__doc__)
