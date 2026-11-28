"""Read the original Windows file identities, independently observed sharing and released bytes."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile

from observe_atomic_config import FINAL, TEMP, expected
from replay_msi_sessions import GuestArchive, check_identity, digest, qualifies, read, require


def replay(original, compiler, checkout, expected_digest):
    require(digest(compiler.read_bytes()) == expected_digest, 'Actions digest differs')
    with ZipFile(original) as archive, ZipFile(compiler) as compiled, ZipFile(checkout) as source:
        guest = GuestArchive(archive)
        r = read(guest, 'result.json')
        inputs = read(guest, 'inputs.json')
        build = read(compiled, 'build.json')
        require(read(guest, 'guest.json')['observerExit'] == 0 and r['profileRemoved'] is True, 'Incomplete trial')
        require(r['archiveSha256'] == inputs['digest'] == expected_digest and r['compiler'] == build['revision']
                and inputs['checkoutSha256'] == digest(checkout.read_bytes()) and
                source.read('.git/HEAD').decode().strip() == inputs['observerRevision'], 'Guest inputs differ')
        exe = compiled.read('msi-session-endpoint.exe')
        require(compiled.read('build.json') == guest.read('build.json') and exe == guest.read('msi-session-endpoint.exe')
                and digest(exe) == build['executableSha256'] and build['target'] == 'x86_64-pc-windows-msvc'
                and exe[int.from_bytes(exe[60:64], 'little'):][:6] == b'PE\0\0\x64\x86', 'Native executable differs')
        for name, checksum in build['sources'].items():
            require(digest(subprocess.check_output(['git', 'show', build['revision'] + ':' + name])) == checksum,
                    'Compiled source differs')
        own = r['observer']
        require(qualifies(own) and r['desktop']['connectionState'] == 0 and own['sessionId'] == r['desktop']['sessionId'],
                'Expected an active ordinary desktop')
        check_identity(r['native'], own, 'msi-session-endpoint.exe')
        prepared = re.fullmatch(r'ATOMIC_PREPARED volume=(\d+) old=(\d+) new=(\d+)', r['prepared'])
        require(prepared, 'No native handle identities')
        vol, old, new = map(int, prepared.groups())
        require(old != new and set(r['before']) == {FINAL, TEMP}, 'Expected two different files')
        def verify_id(identity, ident):
            raw = bytes.fromhex(identity['raw'])
            require(len(raw) == 24 and int.from_bytes(raw[:8], 'little') == identity['volume'] == vol
                    and int.from_bytes(raw[8:], 'little') == identity['id'] == ident, 'Different raw Windows file ID')
        for name, ident in ((FINAL, old), (TEMP, new)):
            seen = r['before'][name]
            verify_id(seen['identity'], ident)
            require(seen['read'] == seen['write'] == 32, 'Missing Win32 sharing violations')
        if r['response'] == 'ATOMIC_SAVED':
            require(r['exit'] == 0 and r['heldAfter']['read'] == r['heldAfter']['write'] == 32, 'Missing save result')
            verify_id(r['heldAfter']['identity'], new)
            files = {FINAL: ('new', new)}
        else:
            require(r['exit'] != 0 and re.fullmatch(r'ATOMIC_REFUSED code=Some\(\d+\)', r['response']), 'Unclassified result')
            files = {FINAL: ('old', old), TEMP: ('new', new)}
        require(set(r['released']) == set(files), 'Unexpected released filenames')
        for name, (version, ident) in files.items():
            saved = r['released'][name]
            verify_id(saved['identity'], ident)
            data = guest.read(version + '.yaml')
            require(data == expected(version) and saved['bytes'] == len(data) and saved['sha256'] == digest(data),
                    'Released contents differ from the original fixture bytes')
        return {'guestSha256': digest(original.read_bytes()), 'compilerRevision': build['revision'], 'response': r['response'],
                'volume': vol, 'oldId': old, 'newId': new, 'released': r['released'], 'profileRemoved': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'compiler', 'checkout'):
        parser.add_argument(name, type=Path)
    parser.add_argument('expected_digest')
    args = parser.parse_args()
    print(json.dumps(replay(args.original, args.compiler, args.checkout, args.expected_digest), indent=2))
