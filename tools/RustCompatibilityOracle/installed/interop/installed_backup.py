"""Return a live backup from the checked Rust executable to the signed worker on its private desktop."""

import base64
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

from assess import require, sha


TABLES = ('owned_albums', 'sync_entries', 'sync_account_status', 'sync_timestamp_repairs')
NEW_NAME = 'after-restore.png'
NEW_IMAGE = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOYYaIBAAJcAPX1O4XIAAAAAElFTkSuQmCC')
NEW_ID = '07902e81-208e-4989-ac89-f3a61debaef2'


def build_input(build, root, revision, out, target):
    directory = build.absolute()
    require(directory.resolve(strict=True) == directory and directory.parent == root / 'artifacts/rust/storage-native',
            'Expected a completed, local native storage assessment')
    executable = directory / 'installed_upload_backup'
    storage = json.loads((directory / 'result.json').read_bytes())
    inputs = json.loads((root / 'tools/rust-qa/storage/inputs.json').read_bytes())
    binary = storage.get('installedUploadBackup')
    require(storage['target'] == target and storage['status'] == 'passed' and storage['offline'] is True and
            storage['modifiedSources'] == [] and storage['lockSha256'] == inputs['lock_sha256'] and
            json.loads((directory / 'native-graph.json').read_bytes()) == inputs['target_graphs'][target] and
            storage['rust']['SQLiteSourceId'] == inputs['sqlite']['source_id'] and
            storage['nativeBuildLogs'] == 2 and storage['verifiedArchives'] == len(inputs['packages']) and
            storage['steps']['installed-backup-build']['exitCode'] == 0 and sha(executable) == binary and
            executable.resolve(strict=True) == executable, 'Rust backup executable or audited build receipt differs')
    hashes = json.loads((directory / 'first-party-source-hashes.json').read_bytes())
    sources = ['rust/Cargo.toml', 'rust/toolchain-inputs.json', 'tools/rust-qa/check-toolchain.py',
               *('tools/rust-qa/storage/' + n for n in ('Cargo.toml', 'Cargo.lock', 'src/lib.rs', 'inputs.json',
                 'examples/installed_upload_backup.rs', 'run.py', 'evidence.py'))]
    sources.extend(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', revision, '--', 'rust/crates/ifw-legacy'],
                                          cwd=root, text=True).splitlines())
    with ZipFile(out / 'installed-backup-build.zip', 'x', ZIP_DEFLATED) as archive:
        for name in sorted(sources):
            path = directory / 'first-party-sources' / name
            require(sha(path) == hashes[name] and path.read_bytes() ==
                    subprocess.check_output(['git', 'show', f'{revision}:{name}'], cwd=root),
                    'Rust backup sources changed since the recorded native build')
            archive.write(path, 'source/' + name)
        originals = ['result.json', 'first-party-source-hashes.json', 'native-graph.json', 'native-compiler.log',
                     'installed-backup-build.log', 'c-compiler-version.log']
        originals += [p.relative_to(directory).as_posix() for p in sorted((directory / 'native-build-logs').rglob('std*'))]
        for name in originals:
            archive.write(directory / name, name)
    return executable, dict(binary=binary, buildRevision=storage['source'], target=target, sqlite=inputs['sqlite']['source_id'],
                            archive=sha(out / 'installed-backup-build.zip'))


def snapshot(path, *, standalone=False):
    with closing(sqlite3.connect(path.as_uri() + ('?mode=ro&immutable=1' if standalone else '?mode=ro'), uri=True)) as db:
        db.execute('BEGIN')
        require(db.execute('PRAGMA integrity_check').fetchone() == ('ok',) and
                db.execute('PRAGMA user_version').fetchone() == (1,), 'Invalid shipping SQLite schema or integrity')
        schema = db.execute('SELECT type,name,tbl_name,rootpage,sql FROM sqlite_schema ORDER BY type,name').fetchall()
        require(sorted(row[1] for row in schema if row[0] == 'table') == sorted(TABLES), 'Unexpected shipping tables')
        return dict(schema=schema, tables={table: db.execute(f'SELECT rowid,* FROM {table} ORDER BY rowid').fetchall()
                                           for table in TABLES})


def execute_backup(out, port, receipt, config_hash, label):
    executable = Path('/installed-backup')
    require(sha(executable) == receipt['binary'], 'Different mounted Rust storage executable')
    result = subprocess.run([str(executable), str(port), config_hash], cwd=out, capture_output=True, timeout=10)
    (out / (label + '.stdout')).write_bytes(result.stdout)
    (out / (label + '.stderr')).write_bytes(result.stderr)
    return result


def start_snapshot(database, out, port, receipt, config_hash):
    reader = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        reader.execute('BEGIN')
        require(reader.execute('PRAGMA journal_mode').fetchone() == ('wal',) and
                reader.execute('SELECT count(*) FROM sync_entries').fetchone() == (0,),
                'Expected the shipping SQLite reader to pin its pre-upload WAL snapshot')
        refused = execute_backup(out, port, receipt, config_hash, 'rust-pre-upload')
        require(refused.returncode != 0 and b"expected the signed worker's committed upload" in refused.stderr and
                not (out / 'installed-returned.db').exists(), 'Rust accepted uncommitted upload history')
        return reader
    except BaseException:
        reader.close()
        raise


def capture(database, out, port, receipt, config_hash, reader):
    from session import wait_for
    wait_for(lambda: len(snapshot(database)['tables']['sync_account_status']) == 1,
             6, 'The signed worker did not persist its account history')
    before = snapshot(database)
    require(len(before['tables']['sync_entries']) == len(before['tables']['sync_account_status']) == 1
            and reader.execute('SELECT count(*) FROM sync_entries').fetchone() == (0,),
            'Expected the committed upload and the independently retained earlier read view')
    wal = database.with_name(database.name + '-wal')
    raw = out / 'live-source.db'
    with wal.open('rb') as stream:
        require(os.fstat(stream.fileno()).st_size > 32, 'The live WAL has no frames')
    copy_wal = out / 'live-source.db-wal'
    shutil.copyfile(database, raw)
    shutil.copyfile(wal, copy_wal)
    result = execute_backup(out, port, receipt, config_hash, 'rust-live-upload')
    require(result.returncode == 0 and sha(raw) == sha(database) and sha(copy_wal) == sha(wal),
            'The live Rust backup failed or the retained source main/WAL changed during capture')
    response = json.loads(result.stdout)
    returned = out / 'installed-returned.db'
    require(response['sqliteSourceId'] == receipt['sqlite'] and response['returnedSha256'] == sha(returned) and
            before == snapshot(returned, standalone=True) and before == snapshot(database) and
            not any(out.glob('installed-returned.db-*')), 'Rust returned an incomplete standalone snapshot')
    # Read the copied main file alone; the live connection always reads its committed WAL.
    with closing(sqlite3.connect(raw.as_uri() + '?mode=ro&immutable=1', uri=True)) as main:
        exists = main.execute("SELECT count(*) FROM sqlite_schema WHERE name='sync_entries'").fetchone()[0]
        main_count = main.execute('SELECT count(*) FROM sync_entries').fetchone()[0] if exists else 0
    require(main_count == 0, 'The retained main file already contains the upload')
    with TemporaryDirectory() as tmp:
        replay = Path(tmp) / 'source.db'
        shutil.copyfile(raw, replay)
        shutil.copyfile(copy_wal, replay.with_name('source.db-wal'))
        require(snapshot(replay) == before, 'Original main and WAL do not reconstruct the live view')
    reader.close()
    return dict(**response, walBytes=copy_wal.stat().st_size, walSha256=sha(copy_wal), mainSha256=sha(raw),
                mainAloneRows=main_count, liveRows=len(before['tables']['sync_entries']), schemaEntries=len(before['schema']))


def open_database_handle(pid, wanted):
    """Identify which descriptor of the signed apphost references the restored main file."""
    for descriptor in (Path('/proc') / str(pid) / 'fd').iterdir():
        try:
            if os.path.samestat(wanted, descriptor.stat()):
                return dict(fd=int(descriptor.name), device=wanted.st_dev, inode=wanted.st_ino)
        except FileNotFoundError:
            continue
    return None


def restart(stack, bus, display, pins, report, out, details, server, config, database, media):
    from assess import pidfd
    from gui_refusal import NAME, owner, quit_shipping
    from observe import window, witness
    from run import APP
    from session import checked_start, check_alive, wait_for
    from shipping_upload import ASSET_ID, FILENAME, IMAGE, client_socket

    returned = out / 'installed-returned.db'
    old_state = snapshot(returned, standalone=True)
    require(details['socketReleased'] and details['instancesAndNamesReleased'] and snapshot(database) == old_state,
            'Old worker did not stop at the captured state')
    # Keep the entire old journal set together on the same private filesystem.
    preserved = database.parent / 'original-pre-restore'
    preserved.mkdir(mode=0o700)
    originals = {}
    for suffix in ('', '-journal', '-wal', '-shm'):
        path = database.with_name(database.name + suffix)
        if path.exists():
            require(path.is_file() and not path.is_symlink(), 'Unexpected original SQLite companion')
            saved = preserved / path.name
            path.rename(saved)
            shutil.copyfile(saved, out / ('original-' + path.name))
            originals[path.name] = sha(saved)
    with database.open('xb') as destination, returned.open('rb') as source:
        shutil.copyfileobj(source, destination)
        destination.flush()
        os.fsync(destination.fileno())
    pinned = stack.enter_context(database.open('rb'))
    restored_identity = os.fstat(pinned.fileno())
    require(sha(database) == details['rustBackup']['returnedSha256'] == sha(returned) and
            os.path.samestat(restored_identity, database.stat()) and not list(database.parent.glob(database.name + '-*')),
            'Restored profile differs from the standalone Rust return')
    details['restart'] = restart_result = dict(inputSha256=sha(database), originalFiles=originals, uploads=[],
                                              restoredIdentity=[restored_identity.st_dev, restored_identity.st_ino])
    logs = config.parents[2] / 'data/interop-logs'
    offsets = {p: p.stat().st_size for p in logs.glob('*.log')}
    server.uploads = restart_result['uploads']
    server.phase = 'restored'
    log = out / 'restarted-shipping.log'
    process = checked_start(stack, ['flatpak', 'run', '--user', '--branch=master', APP], log)
    window_id = wait_for(lambda: check_alive(process, log) or display.visible(), 18, 'Restored shipping GUI did not show')
    native = restart_result['shipping'] = witness(process, window(display, window_id), pins, report, out, 'restarted-shipping')
    pid = native['gui']['pid']
    lifetime = pidfd(stack, pid)
    require(native['gui'] != details['shipping']['gui'] and native['instance'] != details['shipping']['instance']
            and native['paths'] == details['shipping']['paths'], 'Expected another signed apphost in the same profile')
    runtime_dir = Path(f'/proc/{pid}/root') / native['paths']['XDG_RUNTIME_DIR'].lstrip('/')
    runtime = os.open(runtime_dir, os.O_DIRECTORY | os.O_RDONLY | os.O_CLOEXEC)
    stack.callback(os.close, runtime)
    endpoint = 'immich-folder-watch.sock'
    owned_socket = os.stat(endpoint, dir_fd=runtime, follow_symlinks=False)
    require(stat.S_ISSOCK(owned_socket.st_mode), 'Restored apphost lacks its activation socket')
    restart_result['endpoint'] = [owned_socket.st_dev, owned_socket.st_ino]

    def new_log():
        check_alive(process, log)
        return b''.join(p.read_bytes()[offsets.get(p, 0):] for p in sorted(logs.glob('*.log')))

    empty_sweep = f'Persistent reconciliation for uploadAll queued 0 changed file(s) from {media}.'.encode()
    wait_for(lambda: empty_sweep in new_log(), 15, 'The restored app did not reconcile the unchanged source')
    opened = wait_for(lambda: open_database_handle(pid, restored_identity), 5, 'Signed apphost never owned an open restored SQLite handle')
    original_entries = old_state['tables']['sync_entries']
    require(not server.uploads and snapshot(database)['tables']['sync_entries'] == original_entries and
            (media / FILENAME).read_bytes() == IMAGE, 'Restored startup repeated or changed the original upload')
    restart_result['openedDatabase'] = opened
    (out / 'restart-first-reconciliation.log').write_bytes(new_log())
    server.received.clear()
    server.release.clear()
    server.assets[NEW_NAME] = (NEW_IMAGE, NEW_ID)
    (media / NEW_NAME).write_bytes(NEW_IMAGE)
    try:
        wait_for(lambda: check_alive(process, log) or server.received.is_set(), 22, 'No upload after the restored reconciliation')
        observed, = server.uploads
        require(observed['filename'] == NEW_NAME, 'The restored service sent the original file again')
        restart_result['secondClientSocket'] = client_socket(pid, observed)
        server.release.set()
        def new_entry():
            check_alive(process, log)
            current = snapshot(database)['tables']['sync_entries']
            return len(current) == 2 and current[0] == original_entries[0] and current[1][6] == NEW_ID
        wait_for(new_entry, 12, 'The second signed worker did not commit its upload')
        restart_result['quit'] = quit_shipping(bus, process, lifetime, native, out, log)
    finally:
        server.release.set()
    wait_for(lambda: not subprocess.check_output(['flatpak', 'ps', '--columns=application'], text=True, timeout=4).strip(), 5,
             'Restored Flatpak process survived Quit')
    try:
        os.stat(endpoint, dir_fd=runtime, follow_symlinks=False)
    except FileNotFoundError:
        restart_result['socketReleased'] = True
    else:
        raise RuntimeError('Restored shipping endpoint survived Quit')
    require(not owner(bus, NAME) and not owner(bus, APP + '.Tray'), 'Restored app kept its bus name after Quit')
    final = out / 'restarted-shipping.db'
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(final)) as dest:
        source.backup(dest)
        require(dest.execute('PRAGMA journal_mode=DELETE').fetchone() == ('delete',), 'Cannot finalize restarted comparison')
    final_state = snapshot(final, standalone=True)
    tables = final_state['tables']
    expected = [(FILENAME, ASSET_ID), (NEW_NAME, NEW_ID)]
    require(len(server.uploads) == 1 and [(row[4], row[6]) for row in tables['sync_entries']] == expected
            and tables['sync_entries'][0] == original_entries[0] and tables['sync_entries'][1][1] == original_entries[0][1]
            and tables['sync_entries'][1][8] == len(NEW_IMAGE) and tables['sync_entries'][1][10:12] == (0, 0)
            and final_state['schema'] == old_state['schema'] and not tables['owned_albums'] and not tables['sync_timestamp_repairs']
            and len(tables['sync_account_status']) == 1 and tables['sync_account_status'][0][:2] == old_state['tables']['sync_account_status'][0][:2]
            and tables['sync_account_status'][0][2] > old_state['tables']['sync_account_status'][0][2]
            and sha(config) == sha(out / 'shipping-upload.yaml') and (media / FILENAME).read_bytes() == IMAGE
            and (media / NEW_NAME).read_bytes() == NEW_IMAGE and sha(returned) == restart_result['inputSha256']
            and all(sha(preserved / name) == digest for name, digest in originals.items()),
            'Restored shipping history, media, original files or peer observations differ')
    restart_result.update(finalSha256=sha(final), rowIds=[row[0] for row in tables['sync_entries']], passed=True)
