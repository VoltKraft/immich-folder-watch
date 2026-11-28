"""Observe the read-only native MSI preflight before and during an ordinary installed WPF session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

from config_guard_msi import identify_window
from fixture import HERE, ROOT, instance, read, write
from msi_sessions import ADMIN, APP, APP_SHA, Accounts, interactive, ordinary, qualifies, require
from native import Win32, wpf_tray_receiver

PRODUCT = '{50554B02-DB63-4388-A959-8F0B25856F5A}'
PACKAGE = '{19DC3747-2CBD-4D6A-9960-AB0AA4B65947}'
MSI = '419938c3fec0c113bf0f33dbf1a9bd4a6748df1e7930acb20fec5fc3f265a187'
DECISION = f'VETO installed=3.0.4 context=machine state=5 architecture=x64 product={PRODUCT} package={PACKAGE}'
SOURCES = {f'tools/rust-qa/instance/cross-session/{name}' for name in (
    'msi_endpoint.rs', 'installed_writer.rs', 'atomic_config.rs', 'build_msi_endpoint.py')} | {
        'tools/rust-qa/gui/src/win32_instance.rs'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stage(archive, checksum, work):
    require(instance.sha(archive) == checksum, 'Original Actions archive digest differs')
    with ZipFile(archive) as z:
        require(sorted(z.namelist()) in (['build.json', 'msi-session-endpoint.exe'],
                ['build.json', 'msi-session-endpoint.exe', 'msi-session-endpoint.pdb']), 'Unexpected compiler archive')
        receipt = json.loads(z.read('build.json'))
        binary = z.read('msi-session-endpoint.exe')
        require(receipt['target'] == 'x86_64-pc-windows-msvc' and digest(binary) == receipt['executableSha256']
                and 'host: x86_64-pc-windows-msvc' in receipt['rustc'] and binary[:2] == b'MZ'
                and binary[int.from_bytes(binary[60:64], 'little'):][:6] == b'PE\0\0\x64\x86'
                and set(receipt['sources']) == SOURCES and all(instance.sha(ROOT / name) == h for name, h in receipt['sources'].items()),
                'Compiler inputs or executable differ from the original checkout')
        (work / 'build.json').write_bytes(z.read('build.json'))
    exe = work / 'msi-session-endpoint.exe'
    exe.write_bytes(binary)
    return exe


def registered():
    import winreg
    key = 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + PRODUCT
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
        return {name: winreg.QueryValueEx(k, name)[0] for name in ('DisplayName', 'DisplayVersion', 'Publisher', 'WindowsInstaller')}


def desktop_state(api, wpf=None):
    pids = sorted(pid for pid, (_, image) in api.processes().items() if image.lower() == APP.name.lower())
    expected = [] if wpf is None else [wpf.pid]
    require(pids == expected, 'Unexpected installed process inventory')
    result = {'wpfPids': pids, 'registered': registered()}
    if wpf is not None:
        windows = identify_window(wpf.pid)
        receiver = wpf_tray_receiver(wpf.pid)
        require(wpf.poll() is None and len(windows) == 1 and receiver, 'The launched WPF process has no ordinary editor or tray receiver')
        result.update(window=windows[0], receiver=receiver[0], thread=receiver[1])
    return result


def observe(work, label, api, accounts, sid, own, exe, wpf=None):
    before = desktop_state(api, wpf)
    with (work / (label + '.stdout')).open('xb') as out, (work / (label + '.stderr')).open('xb') as err:
        proc = subprocess.Popen([exe, '--preflight-installed-writer'], creationflags=4, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            identity = ordinary(accounts, proc.pid, sid, exe, own['sessionId'])
            api.resume_owned_process(proc.pid)
            status = proc.wait(timeout=20)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
    after = desktop_state(api, wpf)
    require(status == 20 and (work / (label + '.stdout')).read_text().splitlines() == [DECISION]
            and not (work / (label + '.stderr')).read_bytes() and before == after,
            'Missing the registered-product veto or stable original WPF inventory')
    return {'before': before, 'after': after, 'native': identity, 'exit': status}


def run(archive, checksum, work):
    profile = Path(r'C:\Users\ifw-test\AppData\Local\Immich Folder Watch')
    require(os.name == 'nt' and os.environ.get('COMPUTERNAME') == 'IFW-QA25'
            and Path(os.environ['LOCALAPPDATA']) == profile.parent and work.parent == profile.parent / 'IFW-MsiSessions'
            and work.name.startswith('trial-') and not os.path.lexists(profile), 'Expected a fresh disposable application profile')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(qualifies(own) and desktop['clientProtocol'] == 2 and desktop['connectionState'] == 0
            and (ADMIN / 'marker.txt').read_bytes() == f'IFW disposable installed MSI session test\n{sid}\n'.encode('ascii'),
            'Expected the premarked standard test account on an active RDP desktop')
    work.mkdir(exist_ok=False, parents=True)
    exe = stage(archive, checksum, work)
    for name in ('installed.json', 'install.log'):
        shutil.copyfile(ADMIN / name, work / name)
    installed = read(work / 'installed.json')
    require(installed['packageSha256'].lower() == MSI and installed['installExit'] == 0 and installed['exeSha256'].lower() == APP_SHA
            and instance.sha(APP) == APP_SHA and instance.sha(work / 'install.log') == installed['installLogSha256'].lower(),
            'Wrong original installation, executable or installer log')
    api = Win32()
    result = {'compilerArchiveSha256': checksum, 'observer': own, 'desktop': desktop,
              'observerRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    result['idle'] = observe(work, 'idle', api, accounts, sid, own, exe)
    require(not os.path.lexists(profile), 'The read-only idle trial created the application profile')
    result['idleProfileAbsent'] = True
    # The original application owns its new synthetic profile and ordinary window on this desktop.
    with (work / 'wpf.log').open('xb') as log:
        wpf = subprocess.Popen([APP], cwd=APP.parent, stdout=log, stderr=subprocess.STDOUT)
        try:
            original = result['wpf'] = ordinary(accounts, wpf.pid, sid, APP, own['sessionId'])
            deadline = time.monotonic() + 45
            while wpf.poll() is None and time.monotonic() < deadline:
                if identify_window(wpf.pid) and wpf_tray_receiver(wpf.pid):
                    break
                time.sleep(.15)
            result['active'] = observe(work, 'active', api, accounts, sid, own, exe, wpf)
            state = result['active']['after']
            area = work / 'wpf-handover'
            area.mkdir()
            with (area / 'quit-helper.log').open('xb') as output:
                subprocess.run(['pwsh', '-NoProfile', '-NoLogo', '-NonInteractive', '-STA', '-File', HERE / 'handover_quit.ps1',
                                '-ProcessId', str(wpf.pid), '-Created', str(original['created100ns']), '-Root', str(state['window']),
                                '-Receiver', str(state['receiver']), '-ThreadId', str(state['thread']), '-Evidence', area / 'quit-menu.json'],
                               stdout=output, stderr=subprocess.STDOUT, timeout=45, check=True)
            result['wpfExit'] = wpf.wait(timeout=30)
            require(result['wpfExit'] == 0 and desktop_state(api)['wpfPids'] == [], 'The installed process did not exit normally')
        finally:
            if wpf.poll() is None:
                wpf.terminate()
                write(work / 'failed-wpf-cleanup.json', {'pid': wpf.pid, 'exit': wpf.wait(timeout=15)})
    paths = {Path(__file__).resolve(), HERE / 'handover_quit.ps1', ROOT / 'tools/rust-qa/windows-msi-interop/reverse/quit-source.ps1',
             ROOT / 'packaging/windows/Test-InstalledUpgrade.ps1'}
    # Record directly loaded file-based modules as well as ordinary imports used by the observer.
    from shared import peer, backup
    for module in (*sys.modules.values(), instance, peer, backup):
        name = getattr(module, '__file__', None)
        if name:
            p = Path(name).resolve()
            if p.is_relative_to(ROOT / 'tools') and p.suffix == '.py':
                paths.add(p)
    result['sources'] = {p.relative_to(ROOT).as_posix(): instance.sha(p) for p in sorted(paths)}
    write(work / 'result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('digest')
    parser.add_argument('work', type=Path)
    args = parser.parse_args()
    run(args.archive.resolve(strict=True), args.digest, args.work.resolve())
