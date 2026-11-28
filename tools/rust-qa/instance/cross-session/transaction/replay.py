"""Replay the original MSI logs, installed paths, profile digests and ordinary RDP launch."""
import argparse
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_installed_writer import (APP_SHA, DECISION, MSI, PRODUCT, SOURCES, GuestArchive, check_identity,
                                     digest, qualifies, read, require, sources, verify_menu_anchor, QUIT_SOURCE)

SUCCESSOR = '{C09DB689-221F-4AE3-8C72-2D5B5C92DD82}'
COMPILER = '0f19d7e208bb84aa0aa9839da944cafc0cdf17ea91a3e47bae222af4bdf4b634'
HANDOVER = '0f30bc04dfe0337bf4bb5cab177d1ee048a314d342618f59719343c4d42dbcae'
WIX = 'bbb8627d4914333b6b4b91e6d1fc94eea96e28349968550248d8da95cfe80ca0'


def ordered(log, fragments):
    start = 0
    for fragment in fragments:
        found = log.find(fragment, start)
        require(found >= 0, 'Missing or out-of-order native installer action: ' + fragment)
        start = found + len(fragment)


def transaction_actions(log):
    actions = re.findall(r'MSI \(s\) \(([0-9A-F]+:[0-9A-F]+)\) \[[^\]]+\]: Doing action: ([A-Za-z0-9_]+)', log)
    outer = next((thread for thread, action in actions if action == 'RemoveExistingProducts'), None)
    require(outer is not None, 'The installer did not execute RemoveExistingProducts')
    return '\n'.join(action for thread, action in actions if thread == outer)


def replay(guest_zip, compiler_zip, profile_zip, checkout_zip):
    require(digest(compiler_zip.read_bytes()) == COMPILER and digest(profile_zip.read_bytes()) == HANDOVER,
            'Expected the original compiler and WPF handover archives')
    with ZipFile(guest_zip) as archive, ZipFile(compiler_zip) as compiler, ZipFile(profile_zip) as profile, ZipFile(checkout_zip) as checkout:
        for zipped in (archive, compiler, profile, checkout):
            require(zipped.testzip() is None, 'Corrupt ZIP member')
        z, original = GuestArchive(archive), GuestArchive(profile)
        guest, admin, result = (read(z, name) for name in ('guest.json', 'admin.json', 'result.json'))
        manifest = guest['obsdvdFiles']
        build = read(compiler, 'build.json')
        binary = digest(compiler.read('msi-session-endpoint.exe'))
        require(guest['host'] == 'IFW-QA25' and guest['user'] == 'ifw-test' and guest['observerExit'] == 0
                and guest['compilerRevision'] == build['revision'] and guest['compilerArchiveSha256'] == COMPILER
                and result['profileInput'] == manifest['handover.zip'] == HANDOVER and manifest['endpoint.zip'] == COMPILER
                and guest['checkoutArchiveSha256'] == manifest['checkout.zip'] == digest(checkout_zip.read_bytes())
                and checkout.read('.git/HEAD').decode().strip() == guest['observerRevision']
                and read(z, 'build.json') == build and build['executableSha256'] == binary, 'Source and executable receipts differ')
        sources(build['revision'], build['sources'], SOURCES)
        prefix = 'tools/rust-qa/instance/cross-session/transaction/'
        inputs = {prefix + name: manifest[name] for name in ('admin.ps1', 'Cutover.wxs')}
        sources(guest['observerRevision'], inputs, set(inputs))
        require(admin['compilerSha256'].lower() == manifest['wix.nupkg'] == WIX
                and admin['wixSourceSha256'].lower() == manifest['Cutover.wxs']
                and admin['candidateSha256'].lower() == digest(z.read('trial.msi'))
                and manifest['shipping.msi'] == MSI and 'failure.log' not in z.files
                and admin['exits'] == {'failedUpgrade': 1603, 'upgrade': 0, 'removeTrial': 0, 'reinstallOriginal': 0},
                'Private package identity or native install exits differ')
        stock = read(z, 'original-install.json')
        require(stock['installExit'] == 0 and stock['packageSha256'].lower() == MSI and stock['exeSha256'].lower() == APP_SHA
                and stock['installLogSha256'].lower() == digest(z.read('original-install.log')),
                'Original 3.0.4 installation receipt differs')
        own = result['identity']
        require(qualifies(own) and own['sessionId'] == guest['session'] and result['desktop']['clientProtocol'] == 2
                and result['desktop']['connectionState'] == 0, 'Expected the same ordinary user in active RDP')
        files = {name: digest(original.read('wpf-handover/finished-profile/' + name)) for name in
                 ('config.yaml', 'sync-state.db', 'sync-state.db-wal', 'sync-state.db-shm')}
        require(result['files'] == files, 'Guest profile differs from the original WPF files')
        for phase in ('baseline', 'rolled-back', 'committed', 'restored'):
            changed = phase == 'committed'
            state, observed = read(z, phase + '.json'), result['phases'][phase]
            require(state['phase'] == phase and state['product'] == (SUCCESSOR if changed else PRODUCT)
                    and state['version'] == ('3.0.5' if changed else '3.0.4') and state['runningWpf'] == 0
                    and state['sha256'].lower() == (binary if changed else APP_SHA)
                    and bool(state['shortcuts']) != changed and observed['profile'] == files
                    and observed['oldExeSha256'] == (None if changed else APP_SHA)
                    and observed['oldLaunchWin32Error'] == (2 if changed else None)
                    and observed['preflight'] == (21 if changed else 20) and observed['probeSha256'] == binary
                    and z.read(phase + '.stdout').decode('ascii').splitlines() == [('VETO related-registration' if changed else DECISION)]
                    and not z.read(phase + '.stderr'), 'Installed state or native preflight differs at ' + phase)
        failed = z.read('failed-upgrade.log').decode('utf-16')
        ordered(transaction_actions(failed), ['InstallInitialize\n', 'RemoveExistingProducts\n', 'InstallExecute\n', 'TrialFailure'])
        rollback = failed[failed.index('Doing action: TrialFailure'):]
        require('Requested private cutover rollback after InstallExecute.' in rollback
                and re.search(r'Executing op: FileCopy\(SourceName=C:\\Config\.Msi\\[^,]+\.rbf,,'
                          r'DestName=C:\\Program Files\\Immich Folder Watch\\bin\\ImmichFolderWatch\.exe,',
                          rollback, re.IGNORECASE) and 'MainEngineThread is returning 1603' in rollback,
                'No restoration of the installed WPF executable from the native rollback file')
        ordered(transaction_actions(z.read('upgrade.log').decode('utf-16')),
                ['InstallInitialize\n', 'RemoveExistingProducts\n', 'InstallExecute\n', 'InstallFinalize'])
        for name, product in [('remove-trial', SUCCESSOR), ('reinstall-original', PRODUCT)]:
            log = z.read(name + '.log').decode('utf-16')
            require(product in log and 'MainEngineThread is returning 0' in log, 'Incomplete native ' + name)
        wpf = result['restoredWpf']
        token = wpf['token']
        check_identity(token, own, 'ImmichFolderWatch.exe')
        menu = read(z, 'wpf-handover/quit-menu.json')
        windows = wpf['window']
        verify_menu_anchor(menu, {'hwnd': windows['window'], 'pid': token['pid'], 'tid': windows['thread']})
        require(wpf['exit'] == 0 and menu['status'] == 'invoked' and menu['sourceSha256'] == QUIT_SOURCE
                and menu['rawInteraction'] == f'tray-menu-quit; popup={menu["menuHwnd"]}; verifiedHighlightedCommandId=3; nativeMouseClick'
                and menu['receiver'] == windows['receiver'] and menu['created'] == token['created100ns'],
                'The original WPF did not exit through its own visible menu')
        return {'guestSha256': digest(guest_zip.read_bytes()), 'revision': guest['observerRevision'],
                'trialMsiSha256': admin['candidateSha256'].lower(), 'exits': admin['exits'],
                'ordinarySession': own['sessionId'], 'restoredWpfPid': token['pid'], 'profileSha256': files}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('guest_zip', 'compiler_zip', 'profile_zip', 'checkout_zip'):
        parser.add_argument(key, type=Path)
    print(json.dumps(replay(**vars(parser.parse_args())), indent=2))
