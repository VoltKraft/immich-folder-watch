"""Compare the guest's two MSI preflight decisions with original compiler, installer, and WPF evidence."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from zipfile import ZipFile

from observe_installed_writer import APP_SHA, DECISION, MSI, PACKAGE, PRODUCT, SOURCES
from replay_msi_sessions import GuestArchive, check_identity, digest, qualifies, read, require
from handover_receipts import QUIT_SOURCE, verify_menu_anchor

HERE = 'tools/rust-qa/instance/cross-session/'


def sources(revision, observed, required):
    require(re.fullmatch('[a-f0-9]{40}', revision) and required <= observed.keys(), 'Missing pinned source revision or files')
    for name, checksum in observed.items():
        require(name.startswith(('tools/', 'packaging/windows/')) and '..' not in PurePosixPath(name).parts
                and digest(subprocess.check_output(['git', 'show', revision + ':' + name])) == checksum,
                'Source differs from the recorded revision: ' + name)


def replay(original, compiler, expected, checkout=None):
    require(digest(compiler.read_bytes()) == expected, 'Compiler ZIP differs from Actions digest')
    with ZipFile(compiler) as native, ZipFile(original) as arc:
        require(native.testzip() is None and arc.testzip() is None, 'Invalid ZIP checksum')
        z = GuestArchive(arc)
        b = read(native, 'build.json')
        r = read(z, 'result.json')
        guest = read(z, 'guest.json')
        require(guest['observerExit'] == 0 and guest['host'] == 'IFW-QA25' and guest['user'] == 'ifw-test'
                and guest['session'] == r['observer']['sessionId'] and guest['observerRevision'] == r['observerRevision']
                and guest['compilerRevision'] == b['revision'] and guest['compilerArchiveSha256'] == expected
                and guest['obsdvdFiles']['endpoint.zip'] == expected and guest['obsdvdFiles']['checkout.zip'] == guest['checkoutArchiveSha256'],
                'Guest launcher and original execution disagree')
        if checkout:
            with ZipFile(checkout) as source:
                require(digest(checkout.read_bytes()) == guest['checkoutArchiveSha256'] and
                        source.read('.git/HEAD').decode().strip() == r['observerRevision'], 'Delivered source checkout differs')
        exe = native.read('msi-session-endpoint.exe')
        require(sorted(native.namelist()) in (['build.json', 'msi-session-endpoint.exe'],
                ['build.json', 'msi-session-endpoint.exe', 'msi-session-endpoint.pdb']) and r['compilerArchiveSha256'] == expected
                and native.read('build.json') == z.read('build.json') and z.read('msi-session-endpoint.exe') == exe
                and b['executableSha256'] == digest(exe) and b['target'] == 'x86_64-pc-windows-msvc'
                and 'host: x86_64-pc-windows-msvc' in b['rustc'] and exe[:2] == b'MZ'
                and exe[int.from_bytes(exe[60:64], 'little'):][:6] == b'PE\0\0\x64\x86', 'Changed original native executable')
        require(set(b['sources']) == SOURCES, 'Unexpected native compiler sources')
        sources(b['revision'], b['sources'], SOURCES)
        observers = {HERE + name for name in ('observe_installed_writer.py', 'handover_quit.ps1', 'msi_sessions.py',
                     'config_guard_msi.py', 'fixture.py', 'standard.py', 'existing.py')} | {
                     'tools/rust-qa/windows-performance/native.py', 'tools/rust-qa/instance/run.py',
                     'tools/rust-qa/windows-msi-interop/reverse/quit-source.ps1', 'packaging/windows/Test-InstalledUpgrade.ps1'}
        sources(r['observerRevision'], r['sources'], observers)
        installed = read(z, 'installed.json')
        raw = z.read('install.log')
        require(digest(raw) == installed['installLogSha256'].lower() and installed['installExit'] == 0
                and installed['exeSha256'].lower() == APP_SHA and installed['packageSha256'].lower() == MSI,
                'Original installation or installed application digest differs')
        lines = set(raw.decode('utf-16').splitlines())
        required = {'ProductCode': PRODUCT, 'PackageCode': PACKAGE, 'ProductName': 'Immich Folder Watch', 'ProductVersion': '3.0.4',
                    'UpgradeCode': '{F82E51D6-6D61-4A5D-B8AA-9D84A5D0D57D}', 'ALLUSERS': '1'}
        require(all('Property(S): ' + key + ' = ' + value in lines for key, value in required.items()),
                'Missing original machine installation properties')
        own, wpf = r['observer'], r['wpf']
        require(qualifies(own) and r['desktop']['connectionState'] == 0 and r['desktop']['clientProtocol'] == 2
                and own['sessionId'] == own['tokenSessionId'] == r['desktop']['sessionId'] and r['idleProfileAbsent'] is True,
                'Wrong session, standard-user authority or original profile')
        check_identity(wpf, own, 'ImmichFolderWatch.exe')
        arp = {'DisplayName':'Immich Folder Watch', 'DisplayVersion':'3.0.4', 'Publisher':'VoltKraft', 'WindowsInstaller':1}
        for label, running in [('idle', []), ('active', [wpf['pid']])]:
            result = r[label]
            state = result['before']
            require(state == result['after'] and state['wpfPids'] == running and state['registered'] == arp
                    and result['exit'] == 20 and z.read(label + '.stdout').decode('ascii').splitlines() == [DECISION]
                    and z.read(label + '.stderr') == b'', 'WPF inventory, registration or native transcript differs: ' + label)
            check_identity(result['native'], own, 'msi-session-endpoint.exe')
        require(r['idle']['native']['created100ns'] < wpf['created100ns'] < r['active']['native']['created100ns'],
                'Wrong order of native preflight and original WPF process creation')
        state = r['active']['after']
        menu = read(z, 'wpf-handover/quit-menu.json')
        verify_menu_anchor(menu, {'hwnd': state['window'], 'pid': wpf['pid'], 'tid': state['thread']})
        popup = menu['menuHwnd']
        require(menu['sourceSha256'] == QUIT_SOURCE and menu['status'] == 'invoked' and popup > 0 and
                menu['rawInteraction'] == f'tray-menu-quit; popup={popup}; verifiedHighlightedCommandId=3; nativeMouseClick'
                and [menu[k] for k in ('pid', 'created', 'root', 'receiver', 'tid')] ==
                    [wpf['pid'], wpf['created100ns'], state['window'], state['receiver'], state['thread']]
                and r['wpfExit'] == 0 and 'failed-wpf-cleanup.json' not in z.files, 'Incomplete original WPF menu shutdown')
        return {'guestSha256': digest(original.read_bytes()), 'compilerArchiveSha256': expected, 'compilerExecutableSha256': digest(exe),
                'compilerRevision': b['revision'], 'observerRevision': r['observerRevision'], 'observerSources': len(r['sources']),
                'session': own['sessionId'], 'wpfPid': wpf['pid'], 'editorHwnd': state['window'], 'receiverHwnd': state['receiver'],
                'preflightPids': [r[label]['native']['pid'] for label in ('idle', 'active')],
                'wpfExit': r['wpfExit'], 'idleProfileAbsent': True, 'idleAndActiveDecision': DECISION, 'exit': 20}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('expected_digest')
    parser.add_argument('--checkout', type=Path, help='original compact Git checkout delivered on the guest DVD')
    args = parser.parse_args()
    print(json.dumps(replay(args.original, args.compiler, args.expected_digest, args.checkout), indent=2))
