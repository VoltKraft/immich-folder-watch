"""Reopen the MSI evidence and compare the restored WPF field with the native Rust output."""
import argparse
import json
import io
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
          and ui['status'] == 'read' and ui['sourceCount'] == 1 , 'The original WPF did not show the edited Rust album')


    if ui['method'] == 'Owned WPF field pixels':
        check(ui['hit']['pid'] == ui['pid'] and len(ui['point']) == 2 and ui['albumPixels'] == PIXELS,
              'The owned WPF field pixels differ')
    else:
        check(ui['method'] == 'UIA FromPoint' and ui['label'] == 'Immich-Albumname' and ui['album'] == ALBUM
              and ui['fieldPid'] == ui['pid'] and bool(ui['runtimeId']), 'Missing original UIA field')


PIXELS = '7181b9d5d68560c9e75f52c349f033a299c5f038aef23a89271adbb86bff6bb6'
REFERENCE = 'ce9de4337ed2f7cca54a8029bd569768ea8a7dba3854ddb203b803d492b761a7'


def compare_pixels(image, reference_path):
    from PIL import Image

    check(digest(reference_path.read_bytes()) == REFERENCE, 'Different native WPF capture reference')
    with ZipFile(reference_path) as reference:
        original = GuestArchive(reference)
        proof = read(original, 'rust-return/uia.json')
        check(proof['album'] == ALBUM and proof['clipboard']['pid'] == proof['pid'] == proof['focus']['pid']
              and proof['clipboard']['after'] != proof['clipboard']['before']
              and proof['error'] == 'Original clipboard owner or sequence changed during readback',
              'Missing the original observed WPF album text and its initial owner')
        reference_image = original.read('rust-return/returned-window.png')
    for buffer in (reference_image, image):
        with Image.open(io.BytesIO(buffer)) as capture:
            check(capture.size == (1080, 760) and digest(capture.convert('RGB').crop((454, 394, 690, 431)).tobytes()) == PIXELS,
                  'Different native album field')



def returned(guest, compiler, donor, checkout, yaml, reference):
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
        if ui['method'] == 'Owned WPF field pixels':
            compare_pixels(z.read('rust-return/returned-window.png'), reference)
        check(z.read('rust-return/returned-window.png').startswith(b'\x89PNG\r\n\x1a\n'),
              'Missing native WPF editor capture')
        receipt['rustYamlReturn'] = {'producer': REVISION, 'archive': ARCHIVE, 'sourceDocuments': MEMBERS,
                                     'window': ui['hwnd'], 'album': ALBUM, 'sourceCount': ui['sourceCount'],
                                     'readMethod': ui['method'], 'afterQuit': saved['afterQuit'], 'originalReturned': True}
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('guest', 'compiler', 'donor', 'checkout', 'yaml', 'reference'):
        parser.add_argument(name, type=Path)
    print(json.dumps(returned(**vars(parser.parse_args())), ensure_ascii=False, indent=2))
