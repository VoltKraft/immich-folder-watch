"""Verify preserved local Windows migration observations and their original native compiler archives."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import tempfile
from zipfile import ZipFile

from msi_sessions import APP_SHA, ORDERS, WRITER_SHA, configuration, decode_connection, peer, qualifies, require


def digest(data):
    return hashlib.sha256(data).hexdigest()


class GuestArchive:
    """Read a .NET Framework ZIP by logical relative path without unpacking it."""

    def __init__(self, archive):
        self.archive = archive
        self.files = {}
        for entry in archive.infolist():
            name = entry.filename.replace('\\', '/')
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and name not in self.files,
                    'Ambiguous guest ZIP member')
            self.files[name] = entry

    def read(self, name):
        return self.archive.read(self.files[name])


def read(z, name):
    return json.loads(z.read(name).decode('utf-8-sig'))


def check_identity(value, own, image):
    require(qualifies(value) and value['image'].lower() == image.lower() and value['created100ns'] > 0
            and value['sidSha256'] == own['sidSha256'] and value['sessionId'] == value['tokenSessionId'] == own['sessionId'],
            'Incorrect native identity, session, or process image')


def check_upload(z, order, result, pid, socket_record, config_sha, media):
    upload = result['upload']
    tcp = decode_connection(bytes.fromhex(socket_record['raw']))
    require(tcp == socket_record['owner'] and tcp['pid'] == pid and tcp['state'] == 5
            and tcp['client'] == upload['client'] and tcp['server'] == upload['server']
            and tcp['client'][0] == tcp['server'][0] == '127.0.0.1', 'Different owner of the held image upload')
    peer.verify_asset_posts(result['posts'], [(order, peer.FILENAME)])
    for post in result['posts']:
        body = z.read(order + '/' + post['bodyFile'])
        require(digest(body) == post['bodySha256'], 'Asset POST digest differs')
        if post['kind'] == 'matched-image':
            require(peer.multipart_image(post['contentType'], body) and digest(body) == upload['bodySha256'],
                    'WPF multipart body differs from the synthetic image')
        else:
            require(peer.empty_permission_probe(post['contentType'], body), 'Unrecognized permission probe')
    profile = order + '/finished-profile/'
    require(digest(z.read(profile + 'config.yaml')) == config_sha and z.read(media + '/media/' + peer.FILENAME) == peer.IMAGE,
            'Image or YAML configuration differs')
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / 'sync-state.db'
        db.write_bytes(z.read(profile + db.name))
        if profile + db.name + '-wal' in z.files:
            Path(str(db) + '-wal').write_bytes(z.read(profile + db.name + '-wal'))
        rows = [list(row) for row in peer.rows(db)]
    require(len(rows) == 1 and rows == result['rows'] and rows[0][1:] == [peer.FILENAME, peer.ASSET_ID, len(peer.IMAGE), 0, 0],
            'Original installed database does not contain the committed WPF upload')
    expected_config = configuration(PureWindowsPath(rows[0][0]), f'http://127.0.0.1:{tcp["server"][1]}')
    require(z.read(profile + 'config.yaml') == expected_config.replace('\n', '\r\n').encode('utf-8'),
            'Stored config does not name the original synthetic media and loopback endpoint')


def case(z, result, own, other):
    order = result['order']
    check_identity(result['installedWpf'], other, 'ImmichFolderWatch.exe')
    check_identity(result['rustProcess'], own, 'msi-session-endpoint.exe')
    pid = result['installedWpf']['pid']
    upload = result['upload']
    check_upload(z, order, result, pid, result['heldSocket'], result['configSha256'], order)
    if order == 'rust-first':
        check_identity(result['guardWriter'], own, 'instance.exe')
        require(result['rustPrimaryNs'] < upload['requestNs'] <= result['bothRustOwnersAliveNs'] < upload['responseNs'],
                'Rust ownership does not overlap the WPF upload')
    else:
        require(result['pipeRefusalWin32'] in (5, 231) and result['existingPipePid'] == pid and upload['requestNs'] <= result['rustRefusedNs'] < upload['responseNs'],
                'Rust did not refuse the installed WPF pipe during its upload')
    return {'order': order, 'wpfPid': pid, 'rustPid': result['rustProcess']['pid'], 'assetSha256': digest(peer.IMAGE),
            'guardPid': result.get('guardWriter', {}).get('pid'), 'observedPipePid': result.get('existingPipePid'),
            'pipeRefusalWin32': result.get('pipeRefusalWin32')}


def guarded(z, own, other):
    report = read(z, 'config-guard.json')
    check_identity(report['guardProcess'], own, 'msi-session-endpoint.exe')
    protected, control = (report[name]['identity'] for name in ('protectedWpf', 'controlWpf'))
    for token, area, field in ((protected, 'protected', 'protectedWpf'), (control, 'released', 'controlWpf')):
        check_identity(token, other, 'ImmichFolderWatch.exe')
        require(read(z, area + '/started.json') == report[field] and report[field]['hwnd'] > 0
                and read(z, area + '/exit.json')['pid'] == token['pid'], 'Missing original WPF window or process exit')
    require(protected['created100ns'] < control['created100ns'] and
            report['heldNs'] < report['windowObservedNs'] <= report['protectedEndNs'] < report['releasedNs']
            < report['upload']['requestNs'] < report['upload']['responseNs']
            and report['protectedEndNs'] - report['windowObservedNs'] >= 12_000_000_000, 'Incorrect observation interval')
    require(report['passed'] and report['readWin32'] == report['readWriteWin32'] == 32 and report['protectedDatabasePresent'] is False
            and report['protectedAssetPosts'] == [] and report['before'] == report['afterRelease'] == report['afterControl']
            and report['before']['fileId'] > 0 and report['before']['volume'] > 0, 'Missing protected config or unexpected activity')
    check_upload(z, 'released', report, control['pid'], report['controlSocket'], report['before']['sha256'], 'protected')
    return {'protectedWpfPid': protected['pid'], 'controlWpfPid': control['pid'], 'guardPid': report['guardProcess']['pid'],
            'windowObservedSeconds': (report['protectedEndNs'] - report['windowObservedNs']) / 1e9,
            'originalConfig': report['before'], 'releasedControlHttpStatus': 201, 'committedRows': len(report['rows'])}


def unmarked(z):
    denied = read(z, 'unmarked.json')
    diagnostic = denied['diagnostic']
    if isinstance(diagnostic, dict):
        diagnostic = diagnostic['value']
    require(denied['status'] == 'refused' and denied['exitCode'] != 0
            and denied['session'] == read(z, 'peer-session.json')['desktop']['sessionId']
            and diagnostic == z.read('unmarked.stderr').decode('utf-8') and 'expected disposable MSI test VM marker' in diagnostic
            and not z.read('unmarked.stdout'), 'Missing ordinary unmarked refusal')


def replay(guest, endpoint, expected, order, prior):
    require(digest(endpoint.read_bytes()) == expected, 'Native Actions ZIP digest differs')
    with ZipFile(guest) as original, ZipFile(endpoint) as native:
        z = GuestArchive(original)
        build = read(native, 'build.json')
        info = read(z, 'endpoint-info.json')
        observer = read(z, 'observer.json')
        required_sources = {'tools/rust-qa/instance/cross-session/msi_sessions.py', 'tools/rust-qa/instance/cross-session/fixture.py',
                            'tools/rust-qa/windows-msi-interop/upload/owners.py', 'tools/RustCompatibilityOracle/installed/interop/shipping_upload.py'}
        if order == 'config-only':
            required_sources.add('tools/rust-qa/instance/cross-session/config_guard_msi.py')
        require(required_sources.issubset(observer['sources']) and all(digest(subprocess.check_output(
                ['git', 'show', observer['revision'] + ':' + path])) == h for path, h in observer['sources'].items()),
                'Changed guest observer sources')
        require(info['archiveSha256'] == expected and info['build'] == build and all(digest(subprocess.check_output(
                ['git', 'show', build['revision'] + ':' + path])) == h for path, h in build['sources'].items()), 'Changed native build sources')
        require(native.read('msi-session-endpoint.exe') == z.read('bin/msi-session-endpoint.exe') and
                digest(z.read('bin/msi-session-endpoint.exe')) == build['executableSha256'] and digest(z.read('bin/instance.exe')) == WRITER_SHA,
                'Native writer or endpoint image differs')
        installed = read(z, 'installed.json')
        require(installed['exeSha256'].lower() == APP_SHA and installed['packageSha256'].lower() == '419938c3fec0c113bf0f33dbf1a9bd4a6748df1e7930acb20fec5fc3f265a187'
                and installed['installExit'] == 0 and digest(z.read('install.log')) == installed['installLogSha256'].lower(), 'Unverified original installation')
        controller, other = [read(z, role + '-session.json') for role in ('controller', 'peer')]
        require(all(r['desktop']['connectionState'] == 0 and r['desktop']['clientProtocol'] == protocol and qualifies(r['identity'])
                    and r['desktop']['sessionId'] == r['identity']['sessionId'] for r, protocol in ((controller, 0), (other, 2)))
                and controller['identity']['sidSha256'] == other['identity']['sidSha256']
                and controller['desktop']['sessionId'] != other['desktop']['sessionId'], 'Different SID or inactive desktop')
        if prior:
            require(order == 'config-only', 'Prior marker observation is only used on the same guest for a config retry')
            with ZipFile(prior) as previous:
                first = GuestArchive(previous)
                require(first.read('installed.json') == z.read('installed.json') and first.read('bin/msi-session-endpoint.exe') ==
                        z.read('bin/msi-session-endpoint.exe') and first.read('install.log') == z.read('install.log') and
                        read(first, 'peer-session.json')['identity']['sidSha256'] == other['identity']['sidSha256'],
                        'The original MSI, standard account or native image changed between the two local trials')
                unmarked(first)
        else:
            unmarked(z)
        observation, config_guard = None, None
        if order == 'config-only':
            config_guard = guarded(z, controller['identity'], other['identity'])
        else:
            result = read(z, order + '/result.json')
            require(result['order'] == order, 'Wrong admission order')
            observation = case(z, result, controller['identity'], other['identity'])
        return {'guestSha256': digest(guest.read_bytes()), 'endpointSha256': expected, 'observerRevision': observer['revision'],
                'observerSourceHashes': len(observer['sources']), 'nativeSourceHashes': len(build['sources']),
                'controllerSession': controller['desktop']['sessionId'], 'peerSession': other['desktop']['sessionId'],
                'case': observation, 'configGuard': config_guard, 'priorUnmarkedArchiveSha256': digest(prior.read_bytes()) if prior else None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('guest', type=Path)
    parser.add_argument('endpoint', type=Path)
    parser.add_argument('actions_sha256')
    parser.add_argument('order', choices=(*ORDERS, 'config-only'))
    parser.add_argument('--prior-unmarked', type=Path, help='Original observation ZIP from before the same guest was marked')
    args = parser.parse_args()
    print(json.dumps(replay(args.guest, args.endpoint, args.actions_sha256, args.order, args.prior_unmarked), indent=2))
