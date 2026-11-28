"""Measure ordinary Win32 sharing, file identity and config bytes around the owned save."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from config_guard_msi import sharing_violation
from msi_sessions import ADMIN, Accounts, MARKER, interactive, instance, ordinary, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PROFILE = Path(r'C:\Users\ifw-test\AppData\Local\Immich Folder Watch')
TEMP = '.ifw-atomic-config.tmp'
FINAL = 'config.yaml'


def file_id(path):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [w.HANDLE, c.c_int, w.LPVOID, w.DWORD]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80, 7, None, 3, 0x00200000, None)
    if handle == w.HANDLE(-1).value:
        raise c.WinError(c.get_last_error())
    try:
        data = (c.c_ubyte * 24)()
        if not kernel.GetFileInformationByHandleEx(handle, 18, data, c.sizeof(data)):
            raise c.WinError(c.get_last_error())
        raw = bytes(data)
        return {'volume': int.from_bytes(raw[:8], 'little'), 'id': int.from_bytes(raw[8:], 'little'), 'raw': raw.hex()}
    finally:
        kernel.CloseHandle(handle)


def expected(version):
    return f'serverApiUrl: "https://127.0.0.1:1/api"\napiKey: "synthetic-atomic-{version}"\nfolders: []\n'.encode()


def held(name):
    path = PROFILE / name
    return {'identity': file_id(path), 'read': sharing_violation(path, 0x80000000),
            'write': sharing_violation(path, 0x40000000)}


def released(area, name, version, identity):
    path = PROFILE / name
    actual = file_id(path)
    data = path.read_bytes()
    require(actual == identity and data == expected(version), 'File identity or contents changed')
    (area / (version + '.yaml')).write_bytes(data)
    return {'identity': actual, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    archive, archive_sha, work = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    require(os.name == 'nt' and os.environ.get('COMPUTERNAME') == 'IFW-QA25'
            and Path(os.environ['LOCALAPPDATA']) == PROFILE.parent
            and work.resolve().is_relative_to(Path(os.environ['USERPROFILE'])), 'Expected the disposable test account')
    accounts = Accounts()
    sid, _, own = accounts.identify(os.getpid())
    desktop = interactive(own)
    require(desktop['connectionState'] == 0 and (ADMIN / 'marker.txt').read_bytes() ==
            f'IFW disposable installed MSI session test\n{sid}\n'.encode('ascii'), 'Missing active marked test desktop')
    require(instance.sha(archive) == archive_sha, 'Original Actions ZIP digest differs')
    work.mkdir(exist_ok=False)
    exe = work / 'msi-session-endpoint.exe'
    with ZipFile(archive) as z:
        b = json.loads(z.read('build.json'))
        data = z.read(exe.name)
        require(b['target'] == 'x86_64-pc-windows-msvc' and hashlib.sha256(data).hexdigest() == b['executableSha256']
                and data[:2] == b'MZ', 'Unexpected native build')
        header = int.from_bytes(data[0x3c:0x40], 'little')
        require(data[header:header+6] == b'PE\0\0\x64\x86', 'Expected the native AMD64 image')
        sources = {str(p.relative_to(ROOT)).replace('\\', '/') for p in
                   (HERE / 'msi_endpoint.rs', HERE / 'atomic_config.rs', HERE / 'installed_writer.rs', HERE / 'build_msi_endpoint.py',
                    HERE.parents[1] / 'gui/src/win32_instance.rs')}
        require(set(b['sources']) == sources and all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                for name, digest in b['sources'].items()), 'Native compile source receipt differs')
        exe.write_bytes(data)
        (work / 'build.json').write_bytes(z.read('build.json'))
    PROFILE.mkdir(exist_ok=False)
    (PROFILE / '.ifw-instance-fixture').write_bytes(MARKER)
    record = {'observer': own, 'desktop': desktop, 'archiveSha256': archive_sha, 'compiler': b['revision']}
    with instance.Child([exe, '--save-own-synthetic-config'], work, os.environ) as child:
        first = child.events.get(timeout=30)
        match = re.fullmatch(r'ATOMIC_PREPARED volume=(\d+) old=(\d+) new=(\d+)', first or '')
        require(match, f'Rust did not establish both owned handles: {first!r}')
        volume, old, new = map(int, match.groups())
        record['native'] = ordinary(accounts, child.proc.pid, sid, exe, own['sessionId'])
        record['prepared'] = first
        stage = record['before'] = {name: held(name) for name in (FINAL, TEMP)}
        require(old != new and all((s['identity']['volume'], s['identity']['id']) == (volume, ident)
                for s, ident in ((stage[FINAL], old), (stage[TEMP], new))), 'Independent identity differs from the native handle')
        child.send('SAVE')
        result = record['response'] = child.events.get(timeout=30)
        if result == 'ATOMIC_SAVED':
            after = record['heldAfter'] = held(FINAL)
            require(after['identity'] == stage[TEMP]['identity'] and not os.path.lexists(PROFILE / TEMP), 'New file not published')
            child.send('RELEASE')
            child.expect('ATOMIC_RELEASED')
            child.success()
            record['released'] = {FINAL: released(work, FINAL, 'new', after['identity'])}
        else:
            refused = re.fullmatch(r'ATOMIC_REFUSED code=Some\((\d+)\)', result or '')
            require(refused and child.proc.wait(timeout=15) != 0, f'Unclassified native failure: {result!r}')
            record['released'] = {name: released(work, name, version, stage[name]['identity'])
                                  for name, version in ((FINAL, 'old'), (TEMP, 'new'))}
        record['exit'] = child.proc.returncode
    # Only remove this test's files after the identities and bytes have been archived.
    for name in record['released']:
        require(file_id(PROFILE / name) == record['released'][name]['identity'], 'Unexpected cleanup identity')
        (PROFILE / name).unlink()
    require((PROFILE / '.ifw-instance-fixture').read_bytes() == MARKER, 'Unexpected cleanup marker')
    (PROFILE / '.ifw-instance-fixture').unlink()
    PROFILE.rmdir()
    record['profileRemoved'] = not PROFILE.exists()
    (work / 'result.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(result)


if __name__ == '__main__':
    main()
