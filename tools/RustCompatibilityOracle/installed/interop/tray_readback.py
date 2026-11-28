"""Replay the installed Rust worker's two tray commands from the original Flatpak handover directory."""

import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from gi.repository import Gio
from assess import require, sha


def read_packet(out, record, suffix):
    name = f"candidate-menu-{record['id']}-{suffix}.dbus"
    payload = (out / name).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == record['frames'][name], 'The archived menu packet changed')
    return Gio.DBusMessage.new_from_blob(payload, Gio.DBusCapabilityFlags.NONE)


def verify(out):
    manifest = {}
    for line in (out / 'evidence.sha256').read_text().splitlines():
        digest, filename = line.split('  ', 1)
        require(Path(filename).name == filename and filename not in manifest and re.fullmatch('[0-9a-f]{64}', digest),
                'Invalid handover manifest entry')
        manifest[filename] = digest
    require(manifest == {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'evidence.sha256'},
            'The original handover evidence files changed')
    r = json.loads((out / 'result.json').read_bytes())
    build = json.loads((out / 'inputs.json').read_bytes())
    with ZipFile(out / 'observer-source.zip') as source:
        require(sorted(source.namelist()) == sorted(build['sources']) and
                all(hashlib.sha256(source.read(name)).hexdigest() == digest for name, digest in build['sources'].items()),
                'The archived handover observers differ from their original source manifest')
    require(build['trayWorkerRestart'] and r['inputs'] == manifest['inputs.json'] and r['passed'] and r['candidateExit'] == 0
            and r['restoredShippingExit'] == 0 and r['userInstallationEmpty'] and r['endpointAbsentAfterRustQuit']
            and r['refused']['profileAfter'] == r['profileBefore'] == r['profileAfterQuit']
            and r['original']['directoryIdentity'] == r['shippingAfterRustQuit']['directoryIdentity']
            and r['original']['gui']['pid'] != r['shippingAfterRustQuit']['gui']['pid'],
            'The installed original did not return cleanly to its unchanged profile')
    phases = r['laterLaunches']
    require(phases['exclusive'] and phases['shippingExited'] and phases['rustSecondaryExit'] == phases['shippingExit'] == 0
            and phases['candidateOwner'] == phases['ownerAfterRust']
            and phases['primaryAfterRust'] == r['runningAfterRelease']['gui'], 'The ordinary follow-up launches differ')
    inventory = r['inventory']
    primary = inventory['primary']['pid']
    replacement = inventory['replacement']
    mounts = {'/qa/files', '/qa/worker-profile/config'}
    require(all(replacement[k] == inventory[k] for k in ('mounts', 'inputsByInode', 'environment', 'pidNamespace',
                                                         'mountNamespace', 'privateNetwork', 'binarySha256'))
            and inventory['binarySha256'] == build['inventory']['binary']
            and all('ro' in opt.split(',') for opt in inventory['mounts'].values())
            and set(inventory['mounts']) == set(inventory['inputsByInode']) == mounts
            and inventory['configSha256'] == sha(out / 'worker-profile/config/immich-folder-watch/config.yaml')
            and replacement['originalPidfdExited'] and inventory['workerExited'], 'The worker sources, mounts or exits differ')
    for worker in (inventory, replacement):
        identity = worker['worker']
        require(identity['pid'] == worker['namespacePids'][0] and len(worker['namespacePids']) == 2
                and identity['executable'] == '/app/bin/ifw-performance-worker' and identity['parent'] == primary,
                'Expected the actual inventory child in the original Flatpak')
    old, new = inventory['namespacePids'][-1], replacement['namespacePids'][-1]
    require(old != new and inventory['worker']['pid'] != replacement['worker']['pid'], 'Restart reused the worker identity')
    menus = r['candidateTray']
    log = (out / 'released.log').read_text().splitlines()
    old_exit = f'WORKER_EXIT pid={old} reason=restart success=true'
    events = [f'INVENTORY_WORKER pid={old}', old_exit, f'INVENTORY_WORKER pid={new}', f'WORKER_RESTARTED old={old} new={new}',
              f'WORKER_EXIT pid={new} reason=quit success=true']
    require([s for s in log if s.startswith(('INVENTORY_WORKER ', 'WORKER_EXIT ', 'WORKER_RESTARTED '))] == events
            and menus['workerLifecycle'] == events and log.count('INVENTORY_STARTED') == 2, 'The supervisor lifecycle differs')
    new_sweeps = [line for line in log[log.index(old_exit) + 1:] if line.startswith('INVENTORY_COMPLETE ')]
    require(new_sweeps[:2] == ['INVENTORY_COMPLETE files=2 changed=2 pass=0', 'INVENTORY_COMPLETE files=2 changed=0 pass=1']
            and replacement['initialSweeps'] == [[2, 2, 0], [2, 0, 1]], 'The replacement did not reconcile both existing files')
    require(menus['restart']['serial'] < menus['quit']['serial'] and menus['restart']['proxy'] == menus['quit']['proxy'],
            'The ordered menu clicks did not use a single original proxy')
    for key, ident in (('restart', 2), ('quit', 3)):
        row = menus[key]
        query, reply = read_packet(out, row, 'request'), read_packet(out, row, 'reply')
        require(row['id'] == ident and row['labels'] in (['Open GUI', 'Restart', 'Quit'], ['GUI öffnen', 'Neustart', 'Beenden'])
                and row['label'] == row['labels'][ident-1] and row['layoutRevision'] > 0
                and row['gui'] == primary and row['proxy']['pid'] == row['busReportedPid']
                and row['proxy']['executable'] == '/usr/bin/xdg-dbus-proxy'
                and row['receiver'] == phases['candidateOwner'] == query.get_destination()
                and query.get_message_type() == Gio.DBusMessageType.METHOD_CALL and query.get_member() == 'Event'
                and query.get_path() == row['menuPath'] == '/StatusNotifierItem/Menu' and query.get_interface() == 'com.canonical.dbusmenu'
                and query.get_body().unpack() == (ident, 'clicked', '', 0)
                and query.get_serial() == row['serial'] == reply.get_reply_serial() and reply.get_destination() == row['sender'],
                'The archived packets do not identify the menu click and its proxy')
        if row['delivered'] == 'menu-reply':
            require(reply.get_message_type() == Gio.DBusMessageType.METHOD_RETURN and reply.get_sender() == row['receiver']
                    and not reply.get_signature(), 'The archived reply differs from the original receiver')
        else:
            require(ident == 3 and row['delivered'] == 'recipient-disconnected' and reply.get_sender() == 'org.freedesktop.DBus'
                    and reply.get_error_name() == 'org.freedesktop.DBus.Error.NoReply'
                    and reply.get_body().unpack() == ('Message recipient disconnected from message bus without replying',),
                    'Unexpected broker reply to the original Quit')
    return dict(resultSha256=manifest['result.json'], entries=len(manifest), primary=primary,
                old=inventory['namespacePids'], new=replacement['namespacePids'], restored=r['shippingAfterRustQuit']['gui']['pid'])


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Pass the original installed tray-worker handover result directory')
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
