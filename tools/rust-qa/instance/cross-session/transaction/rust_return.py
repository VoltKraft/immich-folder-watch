"""Return original native Rust YAML bytes through a separate synthetic profile copy."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

ARCHIVE = '5694b3ee33b8709ac80bc535759df60cbfefa95d6594945579e3480f9e4a450b'
REVISION = '0bb39bff547b649e4b4f4bf7647e8cbd1b91fe47'
EXECUTABLE = '0c97f2e732b8ff2af6bffda9e46fc64106f12d7dd3127e531f1bccef927f52a2'
MEMBERS = {
    'roundtrip': '0bfcc2e0725f00113be63ad27ae63717cbfd677927b862d4ddc81a1f5d174405',
    'changed': '6ab08acb18046139ddeee1aa46c8bb7e7ebb4fcd9a8d637108236d162bc6a654',
}
ALBUM = 'Rust – Grüße 日本語 😀: # null'
HERE = Path(__file__).resolve().parent
SCRIPTS = ('standard.py', 'rust_return.py', 'read_return.ps1')


def check(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return sha256(data).hexdigest()


def documents(path):
    check(digest(path.read_bytes()) == ARCHIVE, 'Unexpected Windows AMD64 YAML archive')
    with ZipFile(path) as z:
        index = json.loads(z.read('evidence-hashes.json'))
        report = json.loads(z.read('result.json'))
        check(report['target'] == 'x86_64-pc-windows-msvc' and report['source'] == REVISION
              and report['modifiedSources'] == [] and report['status'] == 'passed'
              and report['rustExecutableSha256'] == EXECUTABLE
              and report['workflowRun'] == '45874234228', 'Unexpected original Rust producer')
        output = {}
        for key, expected in MEMBERS.items():
            name = 'rust-output/defaults.input.' + key + '.yaml'
            output[key] = z.read(name)
            check(index[name] == digest(output[key]) == expected, 'Original Rust output differs')
        check(ALBUM.encode() in output['changed'] and ALBUM.encode() not in output['roundtrip'],
              'The initial and edited documents do not distinguish the album')
        return output


def hashes(directory, names):
    return {name: digest((directory / name).read_bytes()) for name in names}


def prepare(disc, profile, work, original):
    from fixture import write

    docs = documents(disc / 'yaml.zip')
    area = work / 'rust-return'
    area.mkdir()
    staged = area / 'prepared'
    staged.mkdir()
    for name in original:
        if name != 'config.yaml':
            shutil.copyfile(profile / name, staged / name)
    for name, data in docs.items():
        (area / (name + '.yaml')).write_bytes(data)
    (staged / 'config.yaml').write_bytes(docs['changed'])
    check(hashes(profile, original) == original and hashes(staged, original) == {**original, 'config.yaml': MEMBERS['changed']},
          'Unexpected original or prepared profile')
    write(area / 'prepared.json', {'archive': ARCHIVE, 'producer': REVISION, 'executable': EXECUTABLE,
                                   'original': original, 'prepared': hashes(staged, original),
                                   'scripts': hashes(HERE, SCRIPTS)})


def observe_wpf(work, proc, token, window):
    script = HERE / 'read_return.ps1'
    subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-STA', '-File', script,
                    '-ProcessId', str(proc.pid), '-Created', str(token['created100ns']),
                    '-Hwnd', str(window['window']), '-Work', work], check=True, timeout=60)


def reopen(accounts, own, sid, profile, work, original, launch):
    from fixture import write

    area = work / 'rust-return'
    donor = area / 'donor'
    check(hashes(profile, original) == original and not donor.exists(), 'Original donor changed')
    profile.rename(donor)
    try:
        (area / 'prepared').rename(profile)
        try:
            before = hashes(profile, original)
            check(before == {**original, 'config.yaml': MEMBERS['changed']}, 'Unexpected handback profile')
            result = launch(accounts, own, sid, work, observer=observe_wpf)
            after = {name: digest((profile / name).read_bytes()) if (profile / name).is_file() else None
                     for name in original}
            check(after['config.yaml'] == before['config.yaml'], 'WPF rewrote the reviewed configuration')
            write(area / 'readback.json', {'before': before, 'afterQuit': after, 'preserved': hashes(donor, original)})
        finally:
            profile.rename(area / 'read-by-wpf')
    finally:
        donor.rename(profile)
    check(hashes(profile, original) == original, 'Original profile was not returned intact')
    write(area / 'returned.json', hashes(profile, original))
    return result
