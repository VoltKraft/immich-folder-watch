"""Recheck Windows Apply receipts, original peer traffic and the installed worker's SQLite data."""
import argparse
import json
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
from zipfile import ZipFile

from apply_msi import ALBUM_ID
from msi_sessions import APP_SHA, decode_connection, peer, qualifies, require
from replay_msi_sessions import GuestArchive, check_identity, digest, read


def replay(guest, endpoint, source, expected):
    require(digest(endpoint.read_bytes()) == expected, 'Actions ZIP digest differs')
    with ZipFile(guest) as original, ZipFile(endpoint) as native:
        require(original.testzip() is None, 'Damaged guest ZIP')
        z = GuestArchive(original)
        record = read(z, 'apply/apply.json')
        observer = read(z, 'observer.json')
        require(digest(source.read_bytes()) == observer['checkoutSha256'], 'Observer checkout digest differs')
        with ZipFile(source) as checkout:
            require(checkout.read('.git/HEAD').decode().strip() == observer['observerRevision'], 'Observer revision differs')
        witnesses = read(z, 'source-witness.json')
        required = {'tools/rust-qa/instance/cross-session/' + f for f in
                    ('apply_msi.py', 'apply_window.ps1', 'config_guard_msi.py', 'msi_sessions.py', 'fixture.py', 'standard.py')}
        require(required.issubset(witnesses) and all(digest(subprocess.check_output(
                ['git', 'show', observer['observerRevision'] + ':' + p])) == h for p, h in witnesses.items()),
                'Observer source differs')
        installed = read(z, 'installed.json')
        require(installed['installExit'] == 0 and installed['packageSha256'].lower() == '419938c3fec0c113bf0f33dbf1a9bd4a6748df1e7930acb20fec5fc3f265a187'
                and installed['exeSha256'].lower() == APP_SHA and digest(z.read('install.log')) == installed['installLogSha256'].lower(),
                'The original MSI and installer log differ')
        build = read(native, 'build.json')
        require(build['executableSha256'] == digest(z.read('bin/msi-session-endpoint.exe'))
                and native.read('msi-session-endpoint.exe') == z.read('bin/msi-session-endpoint.exe')
                and all(digest(subprocess.check_output(['git', 'show', build['revision'] + ':' + p])) == h
                        for p, h in build['sources'].items()), 'The Rust guard or compiled input differs')
        console, rdp = (read(z, name + '-session.json') for name in ('controller', 'peer'))
        require(qualifies(console['identity']) and qualifies(rdp['identity'])
                and console['identity']['sidSha256'] == rdp['identity']['sidSha256']
                and console['desktop']['sessionId'] != rdp['desktop']['sessionId']
                and [s['desktop']['clientProtocol'] for s in (console, rdp)] == [0, 2]
                and all(s['desktop']['connectionState'] == 0 for s in (console, rdp)), 'Different account, session or authority')
        require(record['passed'] and all(z.read(s + '-finished') == b'0' for s in ('controller', 'peer')),
                'A guest process did not finish cleanly')
        start = read(z, 'apply/started.json')
        gui = start['identity']
        require(start == record['started'], 'WPF startup readbacks differ')
        require(installed['exePath'] == r'C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.exe', 'Incorrect installed location')
        check_identity(gui, rdp['identity'], PureWindowsPath(installed['exePath']).name)
        check_identity(record['holder'], console['identity'], 'msi-session-endpoint.exe')
        held, released = (read(z, 'apply/' + name + '-window.json') for name in ('held', 'released'))
        for window in (held, released):
            require((window['pid'], window['hwnd'], window['created']) == (gui['pid'], start['hwnd'], gui['created100ns'])
                    and window['issued'] and window['startQpc'] < window['observedQpc'], 'Changed WPF window or missing button action')
        require(held['emptyUrl'] and held['emptyKey'] and 'config.yaml' in held['loadMessage']
                and held == record['heldWindow'] and released == record['releasedWindow'] and held['outcome'] == 'save-failed'
                and released['outcome'] == 'saved-applied' and held['observedQpc'] < released['startQpc']
                and held['buttonName'] == released['buttonName'] == 'Speichern und Anwenden'
                and held['buttonRuntimeId'] == released['buttonRuntimeId'] and held['folderFocus']['hwnd'] == start['hwnd']
                and 'config.yaml' in held['message'] and 'used by another process' in held['message']
                and released['message'] == 'Konfiguration gespeichert und angewendet.',
                'The same WPF button did not report its two distinct outcomes')
        original_config = z.read('apply/original.yaml')
        saved = z.read('apply/saved.yaml')
        launch = read(z, 'apply/launch.json')
        require(record['before'] == record['afterRelease'] and record['before']['sha256'] == digest(original_config)
                and saved == z.read('apply/finished-profile/config.yaml') and record['afterApply']['sha256'] == digest(saved)
                and original_config != saved and launch['url'].encode() in saved and launch['media'].encode() in saved,
                'The held or released config bytes differ')
        require(record['initialDenial'] == record['finalDenial'] == 32 and not record['heldDatabase']
                and not record['initialConfigRequests'] and record['heldObservationEnd'] - record['heldObservationStart'] >= 12_000_000_000,
                'Original config was accessible or the protected interval was incomplete')
        peer.verify_asset_posts(record['heldPosts'], [])
        peer.verify_asset_posts(record['posts'], [('released', peer.FILENAME)])
        for phase in ('held', 'released'):
            checks = [p for p in record['posts'] if p['kind'] == 'permission-probe' and p['phase'] == phase]
            require(checks, 'Apply did not reach permission validation in both phases')
        for post in record['posts']:
            body = z.read('apply/' + post['bodyFile'])
            require(digest(body) == post['bodySha256'], 'Different original peer bytes')
            if post['kind'] == 'matched-image':
                require(peer.multipart_image(post['contentType'], body) and post['status'] == 201, 'Incorrect uploaded PNG')
            else:
                require(peer.empty_permission_probe(post['contentType'], body) and post['status'] == 400, 'Unexpected permission request')
        tcp = decode_connection(bytes.fromhex(record['owner']['raw']))
        upload = record['upload']
        require(tcp == record['owner']['owner'] and tcp['pid'] == gui['pid'] and tcp['state'] == 5
                and tcp['client'] == upload['client'] and tcp['server'] == upload['server']
                and tcp['client'][0] == tcp['server'][0] == '127.0.0.1' and launch['url'] == f"https://127.0.0.1:{tcp['server'][1]}/api",
                'The installed PID did not own the accepted local TLS connection')
        ready = record['workerReady']
        polls = [r for r in record['requests'] if r['method'] == 'GET' and r['phase'] == 'released'
                 and r['path'].startswith('/socket.io/?EIO=4&transport=polling') and r['requestNs'] <= ready['timeNs']]
        image = next(p for p in record['posts'] if p['kind'] == 'matched-image')
        require(ready['database']['bytes'] > 0 and polls and polls == ready['requests']
                and ready['timeNs'] <= record['mediaCreatedNs'] < image['entryNs'] <= upload['requestNs']
                and image['bodySha256'] == upload['bodySha256'] and image['client'] == upload['client']
                and upload['requestNs'] <= upload['responseNs'] <= image['answeredNs'],
                'The published file was not created after the observed worker start')
        require(json.loads(z.read('apply/album-membership.json')) == {'ids': [peer.ASSET_ID]}
                and any(r['phase'] == 'released' and r['method'] == 'PUT' and r['status'] == 200
                        and r['path'] == f'/api/albums/{ALBUM_ID}/assets' for r in record['requests']),
                'The fixture did not receive the uploaded asset in the expected album')
        require(z.read('apply/media/' + peer.FILENAME) == peer.IMAGE and record['exit']['pid'] == gui['pid'], 'Changed app or media')
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'sync-state.db'
            for name in ('sync-state.db', 'sync-state.db-wal'):
                path = 'apply/finished-profile/' + name
                if path in z.files:
                    (Path(tmp) / name).write_bytes(z.read(path))
            rows = [list(row) for row in peer.rows(db)]
        require(rows == record['rows'] == [[launch['media'], peer.FILENAME, peer.ASSET_ID, len(peer.IMAGE), 0, 0]], 'Different installed SQLite row')
        interval = (record['heldObservationEnd'] - record['heldObservationStart']) / 1e9
        return {
            'guestSha256': digest(guest.read_bytes()), 'observerRevision': observer['observerRevision'],
            'console': console['desktop']['sessionId'], 'rdp': rdp['desktop']['sessionId'],
            'wpf': gui['pid'], 'hwnd': start['hwnd'], 'guard': record['holder']['pid'],
            'heldSeconds': interval, 'permissionProbes': len(record['posts']) - 1,
            'uploadResponses': [p['status'] for p in record['posts'] if p['kind'] == 'matched-image'],
            'sqliteRows': len(rows), 'originalConfig': digest(original_config), 'savedConfig': digest(saved),
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('guest', 'endpoint', 'source'):
        parser.add_argument(name, type=Path)
    parser.add_argument('expected')
    args = parser.parse_args()
    print(json.dumps(replay(args.guest, args.endpoint, args.source, args.expected), indent=2))
