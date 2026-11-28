"""Reopen the MSI evidence and compare the restored WPF field with the native Rust output."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from replay import GuestArchive, read, replay, sources
from rust_return import ALBUM, ARCHIVE, EXECUTABLE, MEMBERS, REVISION, SCRIPTS, check, digest, documents


def verify_ui(ui, wpf, script_hash):
    token, window = wpf['token'], wpf['window']
    check(ui['pid'] == token['pid'] and ui['created'] == token['created100ns']
          and ui['hwnd'] == window['window'] and ui['session'] == token['sessionId']
          and ui['image'].lower() == r'c:\program files\immich folder watch\bin\immichfolderwatch.exe'
          and ui['windowName'] == 'Immich Folder Watch' and ui['sourceSha256'] == script_hash
          and ui['status'] == 'read' and ui['sourceCount'] == 1 and ui['album'] == ALBUM, 'The original WPF did not show the edited Rust album')


    if ui['method'] == 'WPF Copy on original window':
        clip = ui['clipboard']
        check(ui['focus']['pid'] == ui['pid'] == clip['pid'] and len(ui['point']) == 2 and clip['owner'] > 0
              and clip['before'] != clip['after'], 'Missing WPF clipboard ownership or pointer evidence')
    else:
        check(ui['method'] in ('UIA FromPoint', 'UIA FocusedElement') and ui['label'] == 'Immich-Albumname'
              and ui['fieldPid'] == ui['pid'] and bool(ui['runtimeId']), 'Missing original UIA field')


def returned(guest, compiler, donor, checkout, yaml):
    receipt = replay(guest, compiler, donor, checkout, require_running_veto=True)
    docs = documents(yaml)
    with ZipFile(donor) as donor_zip:
        donor_yaml = GuestArchive(donor_zip).read('wpf-handover/finished-profile/config.yaml')
        check(ALBUM.encode() not in donor_yaml and donor_yaml not in docs.values(),
              'The original WPF donor already contained the returned value')
    with ZipFile(guest) as archive:
        z = GuestArchive(archive)
        manifest = read(z, 'guest.json')['obsdvdFiles']
        prepared = read(z, 'rust-return/prepared.json')
        saved = read(z, 'rust-return/readback.json')
        original = receipt['profileSha256']
        changed = {**original, 'config.yaml': MEMBERS['changed']}
        check(manifest['yaml.zip'] == prepared['archive'] == ARCHIVE and prepared['producer'] == REVISION
              and prepared['executable'] == EXECUTABLE and prepared['original'] == saved['preserved'] == original
              and read(z, 'rust-return/returned.json') == original and prepared['prepared'] == saved['before'] == changed,
              'The separate handback copy or retained original profile differs')
        prefix = 'tools/rust-qa/instance/cross-session/transaction/'
        scripts = {prefix + name: prepared['scripts'][name] for name in SCRIPTS}
        sources(receipt['revision'], scripts, set(scripts))
        for key, expected in docs.items():
            check(z.read('rust-return/' + key + '.yaml') == expected, 'Guest YAML differs from Windows writer output')
        for name, checksum in saved['afterQuit'].items():
            member = 'rust-return/read-by-wpf/' + name
            check((member in z.files) == (checksum is not None)
                  and (checksum is None or digest(z.read(member)) == checksum), 'Closed user profile readback differs')
        check(saved['afterQuit'].keys() == original.keys() and saved['afterQuit']['config.yaml'] == MEMBERS['changed'],
              'The WPF configuration after Quit differs')
        ui = read(z, 'rust-return/uia.json')
        verify_ui(ui, read(z, 'result.json')['restoredWpf'], prepared['scripts']['read_return.ps1'])
        check(z.read('rust-return/returned-window.png').startswith(b'\x89PNG\r\n\x1a\n'),
              'Missing native WPF editor capture')
        receipt['rustYamlReturn'] = {'producer': REVISION, 'archive': ARCHIVE, 'sourceDocuments': MEMBERS,
                                     'window': ui['hwnd'], 'album': ui['album'], 'sourceCount': ui['sourceCount'],
                                     'readMethod': ui['method'], 'afterQuit': saved['afterQuit'], 'originalReturned': True}
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('guest', 'compiler', 'donor', 'checkout', 'yaml'):
        parser.add_argument(name, type=Path)
    print(json.dumps(returned(**vars(parser.parse_args())), ensure_ascii=False, indent=2))
