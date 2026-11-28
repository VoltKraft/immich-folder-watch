"""Observe a disposable MSI cutover from the original profile owner's RDP session."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from observe_installed_writer import (ADMIN, APP, APP_SHA, DECISION, HERE, Accounts, Win32,
                                      desktop_state, identify_window, instance, interactive,
                                      ordinary, qualifies, require, stage, wpf_tray_receiver, write)

ARCHIVE = '0f19d7e208bb84aa0aa9839da944cafc0cdf17ea91a3e47bae222af4bdf4b634'
PROFILE_ARCHIVE = '0f30bc04dfe0337bf4bb5cab177d1ee048a314d342618f59719343c4d42dbcae'
PROFILE_FILES = ('config.yaml', 'sync-state.db', 'sync-state.db-wal', 'sync-state.db-shm')
CANDIDATE = Path(r'C:\Program Files\IFW Cutover QA\msi-session-endpoint.exe')
PHASES = ('baseline', 'rolled-back', 'committed', 'restored')


def stock_launch(accounts, own, sid, work):
    with (work / 'wpf.log').open('xb') as output:
        proc = subprocess.Popen([APP], cwd=APP.parent, stdout=output, stderr=subprocess.STDOUT)
        try:
            token = ordinary(accounts, proc.pid, sid, APP, own['sessionId'])
            deadline = time.monotonic() + 45
            while proc.poll() is None and time.monotonic() < deadline:
                if identify_window(proc.pid) and wpf_tray_receiver(proc.pid):
                    break
                time.sleep(.15)
            active = desktop_state(Win32(), proc)
            subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-STA', '-File', HERE / 'handover_quit.ps1',
                            '-ProcessId', str(proc.pid), '-Created', str(token['created100ns']),
                            '-Root', str(active['window']), '-Receiver', str(active['receiver']),
                            '-ThreadId', str(active['thread']), '-Evidence', work / 'quit-menu.json'],
                           stdout=output, stderr=subprocess.STDOUT, timeout=45, check=True)
            code = proc.wait(timeout=30)
            require(code == 0, 'The restored WPF failed its ordinary tray Quit')
            return {'token': token, 'window': active, 'exit': code}
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=15)


def run(disc, work):
    profile = Path(os.environ['LOCALAPPDATA']) / 'Immich Folder Watch'
    require(os.name == 'nt' and os.environ['COMPUTERNAME'] == 'IFW-QA25'
            and profile.parent == Path(r'C:\Users\ifw-test\AppData\Local')
            and work == profile.parent / 'IFW-MsiSessions' / 'trial-transaction-01'
            and not os.path.lexists(profile), 'Expected the fresh synthetic profile of the disposable x64 guest')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(qualifies(own) and desktop['connectionState'] == 0 and desktop['clientProtocol'] == 2
            and (ADMIN / 'marker.txt').read_bytes() == f'IFW disposable installed MSI session test\n{sid}\n'.encode(),
            'Expected the standard user in an active native RDP session')
    work.mkdir()
    native = stage(disc / 'endpoint.zip', ARCHIVE, work)
    require(instance.sha(disc / 'handover.zip') == PROFILE_ARCHIVE, 'Unexpected profile archive')
    profile.mkdir()
    with ZipFile(disc / 'handover.zip') as archive:
        for name in PROFILE_FILES:
            (profile / name).write_bytes(archive.read('wpf-handover\\finished-profile\\' + name))
    original = {name: instance.sha(profile / name) for name in PROFILE_FILES}
    result = {'identity': own, 'desktop': desktop, 'profileInput': PROFILE_ARCHIVE, 'files': original, 'phases': {}}
    for phase in PHASES:
        if phase != 'baseline':
            gate = ADMIN / 'transaction' / (phase + '.ready')
            deadline = time.monotonic() + 420
            while not gate.is_file():
                require(not (gate.parent / 'failure.log').is_file(), f'The installer failed before {phase}')
                require(time.monotonic() < deadline, f'Timed out waiting for {phase}')
                time.sleep(.25)
        require(not any(image.lower() == APP.name.lower() for _, image in Win32().processes().values()),
                f'An old worker was active at {phase}')
        absent = phase == 'committed'
        require(CANDIDATE.is_file() == absent and APP.is_file() != absent, f'Unexpected installed paths at {phase}')
        if absent:
            require(instance.sha(CANDIDATE) == instance.sha(native), 'Installed Rust code differs from its compiler archive')
            try:
                unexpected = subprocess.Popen([APP])
            except FileNotFoundError as error:
                require(error.winerror == 2, 'Unexpected Win32 ordinary launch failure')
            else:
                unexpected.terminate()
                unexpected.wait(timeout=15)
                raise RuntimeError('The removed WPF application could still start')
        else:
            require(instance.sha(APP) == APP_SHA, 'Installed WPF differs from the original MSI')
        command = CANDIDATE if absent else native
        preflight = subprocess.run([command, '--preflight-installed-writer'], capture_output=True, timeout=15)
        (work / (phase + '.stdout')).write_bytes(preflight.stdout)
        (work / (phase + '.stderr')).write_bytes(preflight.stderr)
        expected = 'VETO related-registration' if absent else DECISION
        require(preflight.returncode == (21 if absent else 20) and not preflight.stderr
                and preflight.stdout.decode().splitlines() == [expected], f'Unexpected native preflight at {phase}')
        hashes = {name: instance.sha(profile / name) for name in PROFILE_FILES}
        require(hashes == original, f'The installation changed the application profile at {phase}')
        snapshot = {'profile': hashes, 'preflight': preflight.returncode, 'probeSha256': instance.sha(command),
                    'oldExeSha256': None if absent else APP_SHA, 'oldLaunchWin32Error': 2 if absent else None}
        result['phases'][phase] = snapshot
        if phase == 'restored':
            result['restoredWpf'] = stock_launch(accounts, own, sid, work)
        write(work / 'result.json', result)
        (work / (phase + '.ok')).touch(exist_ok=False)
    for f in (ADMIN / 'transaction').iterdir():
        if f.suffix in ('.log', '.json', '.msi'):
            shutil.copyfile(f, work / f.name)


if __name__ == '__main__':
    run(Path(sys.argv[1]), Path(sys.argv[2]))
