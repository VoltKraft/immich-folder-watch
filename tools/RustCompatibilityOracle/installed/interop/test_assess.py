"""Check that the two Flatpak prerequisite outcomes cannot be interchanged."""

from contextlib import ExitStack
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from assess import gui_source_snapshot, inventory_inputs, verify_paths, verify_siblings
from installed_backup import build_input, open_database_handle, snapshot
from shipping_upload import empty_permission_probe, endpoint_tuple, FILENAME, IMAGE, multipart_image, verify_asset_posts


class ShippingQuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        here = Path(__file__).resolve().parent
        performance = here.parents[2] / 'rust-qa/performance'
        with patch.object(sys, 'path', [str(here.parent / 'launch'), str(performance), str(performance / 'worker'), *sys.path]):
            import gui_refusal
        cls.observer = gui_refusal

    def test_private_bus_routes_the_exact_click_before_the_recipient_disconnects(self):
        gio = self.observer.Gio
        with TemporaryDirectory() as temp, ExitStack() as stack:
            address = 'unix:path=' + str(Path(temp) / 'bus')
            broker = stack.enter_context(subprocess.Popen(
                ['dbus-daemon', '--session', '--nofork', '--print-address=1', '--address=' + address],
                stdout=subprocess.PIPE, text=True))
            stack.callback(broker.terminate)
            self.assertEqual(broker.stdout.readline().strip().split(',')[0], address)
            flags = gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
            bus = gio.DBusConnection.new_for_address_sync(address, flags, None, None)
            stack.callback(bus.close_sync, None)
            peer = gio.DBusConnection.new_for_address_sync(address, flags, None, None)
            receiver = peer.get_unique_name()
            received = []
            clicked = threading.Event()

            def read_click(connection, message, incoming):
                if incoming and message.get_member() == 'Event':
                    received.append((message.get_serial(), message.get_sender(), message.get_destination(),
                                     message.get_path(), message.get_interface(), message.get_body().unpack()))
                    clicked.set()
                    return None
                return message

            def disconnect():
                if clicked.wait(4):
                    peer.close_sync(None)

            peer.add_filter(read_click)
            thread = threading.Thread(target=disconnect)
            thread.start()
            stack.callback(thread.join)
            process = Mock()
            process.wait.return_value = 0
            lifetime = Mock()
            lifetime.poll.return_value = [(7, 1)]
            with patch.object(self.observer, 'shipping_menu', return_value={'receiver': receiver}):
                result = self.observer.quit_shipping(bus, process, lifetime, {}, Path(temp))
            self.assertEqual(result['delivery'], 'recipient-disconnected')
            self.assertEqual(received, [(result['serial'], bus.get_unique_name(), receiver, '/StatusNotifierItem/Menu',
                                         'com.canonical.dbusmenu', (3, 'clicked', 0, 0))])

    def test_reply_must_match_the_click_and_the_expected_application_or_broker(self):
        gio, glib = self.observer.Gio, self.observer.GLib
        receiver, sender = ':1.7', ':1.8'
        click = gio.DBusMessage.new_method_call(receiver, '/Menu', 'com.canonical.dbusmenu', 'Event')
        click.set_sender(sender)
        click.set_serial(19)
        reply = click.new_method_reply()
        reply.set_sender(receiver)
        self.assertEqual(self.observer.quit_delivery(reply, 19, receiver, sender), 'menu-reply')
        error = click.new_method_error_literal('org.freedesktop.DBus.Error.NoReply',
                                              'Message recipient disconnected from message bus without replying')
        error.set_sender('org.freedesktop.DBus')
        for original, change, value in (
            (reply, 'set_sender', ':1.9'), (reply, 'set_body', glib.Variant('(i)', (3,))),
            (error, 'set_sender', receiver), (error, 'set_reply_serial', 18), (error, 'set_destination', ':1.9'),
            (error, 'set_error_name', 'org.freedesktop.DBus.Error.ServiceUnknown'),
            (error, 'set_body', glib.Variant('(s)', ('Did not receive a reply.',))),
        ):
            with self.subTest(field=change, value=value):
                changed = original.copy()
                getattr(changed, change)(value)
                with self.assertRaises(RuntimeError):
                    self.observer.quit_delivery(changed, 19, receiver, sender)

    def test_menu_peer_must_match_the_proxy_serving_the_original_sandbox_socket(self):
        with TemporaryDirectory() as temp, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            proc = Path(temp)
            directory = proc / 'root/run/flatpak'
            directory.mkdir(parents=True)
            (proc / 'environ').write_bytes(b'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/flatpak/bus\0')
            listener.bind(str(directory / 'bus'))
            listener.listen(3)
            bus = Mock()
            for reported, executable in ((os.getpid() + 1, '/usr/bin/xdg-dbus-proxy'), (os.getpid(), '/another')):
                bus.call_sync.return_value = self.observer.GLib.Variant('(u)', (reported,))
                with self.subTest(pid=reported, executable=executable), patch.object(
                        self.observer, 'identity', return_value={'executable': executable}) as observed:
                    with self.assertRaisesRegex(RuntimeError, 'session bus proxy'):
                        self.observer.installed_proxy(bus, ':1.4', proc)
                    observed.assert_called_once_with(os.getpid())
                    self.assertEqual(bus.call_sync.call_args.args[4].unpack(), (':1.4',))

    def test_restart_only_accepts_the_two_new_passes_after_the_observed_old_worker_exit(self):
        read = self.observer.restarted_sweeps
        first = 'INVENTORY_COMPLETE files=2 changed=2 pass=0'
        next_pass = 'INVENTORY_COMPLETE files=2 changed=0 pass=1'
        exited = 'WORKER_EXIT pid=12 reason=restart success=true'
        changed = 'WORKER_RESTARTED old=12 new=63'
        self.assertEqual(read([first, next_pass, exited, changed, first, next_pass], 12, 63), [(2, 2, 0), (2, 0, 1)])
        for lines, new in [([first, next_pass, exited, changed], 63), ([exited, changed, next_pass], 63),
                           ([exited, changed, first, next_pass], 12), ([exited, changed, first, next_pass], 42),
                           ([exited, exited, changed, first, next_pass], 63),
                           ([exited.replace('true', 'false'), changed, first, next_pass], 63)]:
            with self.subTest(lines=lines, new=new):
                self.assertIsNone(read(lines, 12, new))

    def test_routed_click_still_requires_clean_original_exit_and_fresh_worker_shutdown(self):
        bus, process, lifetime = Mock(), Mock(), Mock()
        bus.send_message_with_reply_sync.return_value = (Mock(), 4)
        with TemporaryDirectory() as temp, ExitStack() as stack:
            log = Path(temp) / 'worker.log'
            log.write_text('Folder watch worker received shutdown signal.\n')
            stack.enter_context(patch.object(self.observer, 'shipping_menu', return_value={'receiver': ':1.7'}))
            stack.enter_context(patch.object(self.observer, 'quit_delivery', return_value='recipient-disconnected'))
            stack.enter_context(patch.object(self.observer, 'owner', return_value=False))
            for exit_code, exited, error in ((1, True, 'exit normally'), (0, False, 'exit normally'),
                                              (0, True, 'acknowledge shutdown')):
                process.wait.return_value = exit_code
                lifetime.poll.return_value = exited
                with self.subTest(exit_code=exit_code, exited=exited), self.assertRaisesRegex(RuntimeError, error):
                    self.observer.quit_shipping(bus, process, lifetime, {}, Path(temp), log)


class DirectoryReadTests(unittest.TestCase):
    def test_thread_receives_one_access_from_the_held_directory_with_either_fcntl_interface(self):
        here = Path(__file__).resolve().parent
        performance = here.parents[2] / 'rust-qa/performance'
        with patch.object(sys, 'path', [str(here.parent / 'launch'), str(performance), str(performance / 'worker'), *sys.path]):
            import gui_refusal
        # Python 3.12 supplies these operations without exporting the extended ownership names.
        older = SimpleNamespace(fcntl=fcntl.fcntl, F_SETSIG=fcntl.F_SETSIG, F_NOTIFY=fcntl.F_NOTIFY, DN_ACCESS=fcntl.DN_ACCESS)
        with TemporaryDirectory() as tmp:
            original = Path(tmp) / 'album'
            original.mkdir()
            for api in (fcntl, older):
                with self.subTest(extended_names=hasattr(api, 'F_SETOWN_EX')), patch.object(gui_refusal, 'fcntl', api):
                    mask = {signal.SIGRTMIN}
                    saved = signal.pthread_sigmask(signal.SIG_BLOCK, mask)
                    fd = os.open(original, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
                    try:
                        gui_refusal.watch_directory_read(fd)
                        # Linux F_GETOWN_EX returns the owner type and the actual receiving thread ID.
                        owner = fcntl.fcntl(fd, getattr(fcntl, 'F_GETOWN_EX', 16), bytes(8))
                        self.assertEqual(struct.unpack('=ii', owner), (0, threading.get_native_id()))
                        os.listdir(tmp)
                        self.assertIsNone(signal.sigtimedwait(mask, 0))
                        os.listdir(fd)
                        event = signal.sigtimedwait(mask, 2)
                        self.assertIsNotNone(event)
                        self.assertEqual(event.si_signo, signal.SIGRTMIN)
                        self.assertGreater(event.si_code, 0)
                        os.listdir(fd)
                        self.assertIsNone(signal.sigtimedwait(mask, 0))
                    finally:
                        os.close(fd)
                        signal.sigtimedwait(mask, 0)
                        signal.pthread_sigmask(signal.SIG_SETMASK, saved)


class ConfiguredUploadTests(unittest.TestCase):
    def test_empty_permission_multipart_excludes_a_partial_or_unknown_upload(self):
        content_type = 'multipart/form-data; boundary=unit-boundary'
        self.assertTrue(empty_permission_probe(content_type, b'--unit-boundary\r\n\r\n--unit-boundary--\r\n'))
        self.assertTrue(empty_permission_probe(content_type, b'--unit-boundary--\r\n'))
        for body in (b'', b'--wrong--\r\n', b'--unit-boundary\r\n',
                     b'--unit-boundary\r\nContent-Disposition: form-data; name=assetData\r\n\r\n--unit-boundary--\r\n'):
            with self.subTest(body=body):
                self.assertFalse(empty_permission_probe(content_type, body))

    def test_all_asset_posts_must_finish_and_match_the_expected_worker_lifetime(self):
        original = dict(phase='original', filename=FILENAME, kind='matched-image', status=201)
        probe = dict(phase='restored', kind='permission-probe', status=400)
        expected = [('original', FILENAME)]
        verify_asset_posts([original, probe], expected)
        for extra in (original, {**original, 'phase': 'restored'}, {**original, 'status': 503},
                      {'kind': 'incomplete'}, {'kind': 'unrecognized-multipart', 'status': 400}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                verify_asset_posts([original, probe, extra], expected)

    @unittest.skipUnless(Path('/proc/self/fd').is_dir(), 'requires Linux process descriptors')
    def test_compares_the_pinned_restored_inode_after_its_path_is_replaced(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / 'state.db'
            db.write_bytes(b'original')
            with db.open('rb') as pinned:
                earlier = os.fstat(pinned.fileno())
                db.rename(db.with_suffix('.old'))
                db.write_bytes(b'new')
                match = open_database_handle(os.getpid(), earlier)
                self.assertEqual(match['inode'], earlier.st_ino)
                self.assertNotEqual(match['inode'], db.stat().st_ino)

    def test_replay_rejects_an_incomplete_schema_even_with_a_valid_version(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / 'bad.db'
            con = sqlite3.connect(db)
            con.executescript('CREATE TABLE sync_entries(entry TEXT); PRAGMA user_version=1;')
            con.close()
            with self.assertRaisesRegex(RuntimeError, 'Unexpected shipping tables'):
                snapshot(db, standalone=True)

    def test_installed_backup_rejects_another_target_and_online_acquisition(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            build = root / 'artifacts/rust/storage-native/test'
            build.mkdir(parents=True)
            spec = root / 'tools/rust-qa/storage/inputs.json'
            spec.parent.mkdir(parents=True)
            spec.write_text('{}')
            target = 'aarch64-unknown-linux-gnu'
            for recorded_target, offline in [('x86_64-unknown-linux-gnu', True), (target, False)]:
                record = {'target': recorded_target, 'offline': offline, 'status': 'passed'}
                (build / 'result.json').write_text(json.dumps(record))
                with self.subTest(target=recorded_target, offline=offline), self.assertRaisesRegex(RuntimeError, 'audited build'):
                    build_input(build, root, 'revision', root, target)
                self.assertFalse((root / 'installed-backup-build.zip').exists())

    def test_loopback_connection_matches_both_ipv4_and_mapped_socket_addresses(self):
        self.assertEqual(endpoint_tuple('0100007F:C234'), ('127.0.0.1', 49716))
        self.assertEqual(endpoint_tuple('0000000000000000FFFF00000100007F:0050'), ('127.0.0.1', 80))
        self.assertNotEqual(endpoint_tuple('0200007F:0050'), ('127.0.0.1', 80))

    def test_only_one_matching_filename_field_and_payload_qualify_as_uploaded_media(self):
        content_type = 'multipart/form-data; boundary=unit-boundary'
        part = (f'--unit-boundary\r\nContent-Disposition: form-data; name=assetData; filename="{FILENAME}"\r\n\r\n'.encode()
                + IMAGE + b'\r\n')
        end = b'--unit-boundary--\r\n'
        self.assertTrue(multipart_image(content_type, part + end))
        for content in (end, part + part + end, part.replace(IMAGE, b'other') + end,
                        part.replace(FILENAME.encode(), b'other.png') + end, part.replace(b'assetData', b'filename') + end):
            with self.subTest(content=content):
                self.assertFalse(multipart_image(content_type, content))


class IdentityTests(unittest.TestCase):
    def test_installed_worker_must_match_the_gui_binary_and_reviewed_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            subject = root / 'artifacts/rust/performance/subjects/swapped-input'
            subject.mkdir(parents=True)
            worker = b'synthetic'
            (subject / 'ifw-performance-worker').write_bytes(worker)
            digest = hashlib.sha256(worker).hexdigest()
            build = dict(worker_sha256=digest, gui_sha256='original-gui', sources={'source': 'digest'})
            with patch('assess.subprocess.check_output', return_value=b'{"source":"digest"}'):
                for field, wrong in [('worker_sha256', 'another-worker'), ('gui_sha256', 'another-gui'), ('sources', {})]:
                    (subject / 'worker.inputs.json').write_text(json.dumps({**build, field: wrong}))
                    with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, 'worker, native GUI or pinned source'):
                        inventory_inputs(subject, root, 'revision', 'original-gui', 'release', root, digest)
                    self.assertFalse((root / 'inventory-sources.zip').exists())
                (subject / 'worker.inputs.json').write_text(json.dumps(build))
                with self.assertRaisesRegex(RuntimeError, 'worker, native GUI or pinned source'):
                    inventory_inputs(subject, root, 'revision', 'original-gui', 'release', root, 'other-host-worker')

    def test_receipt_cannot_select_files_for_the_native_gui_archive(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'tools/rust-qa/gui/src'
            src.mkdir(parents=True)
            (src / 'linux_legacy.rs').touch()
            expected = {'tools/rust-qa/gui/' + p for p in ('Cargo.toml', 'Cargo.lock', 'src/linux_legacy.rs', 'src/tray-icon.argb')}
            expected.update(('rust/Cargo.toml', 'rust/crates/desktop-lifecycle/Cargo.toml', 'rust/crates/desktop-lifecycle/src/lib.rs'))
            for names in (expected | {'../outside'}, expected - {'rust/Cargo.toml'}):
                # The other required files do not exist. Reject the names before trying to open any of them.
                with self.subTest(names=names), self.assertRaisesRegex(RuntimeError, 'source inventory'):
                    gui_source_snapshot(root, dict.fromkeys(names, ''))

    def test_hosted_gui_compares_every_archived_file_with_the_selected_commit(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = {
                'tools/rust-qa/gui/src/linux_legacy.rs', 'tools/rust-qa/gui/src/tray-icon.argb',
                'tools/rust-qa/gui/Cargo.toml', 'tools/rust-qa/gui/Cargo.lock', 'rust/Cargo.toml',
                'rust/crates/desktop-lifecycle/Cargo.toml', 'rust/crates/desktop-lifecycle/src/lib.rs',
            }
            contents = {name: name.encode() for name in files}
            for name, original in contents.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            digests = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
            git_blobs = {'reference:' + name: original for name, original in contents.items()}
            with patch('assess.subprocess.check_output', side_effect=lambda cmd, cwd: git_blobs[cmd[2]]) as git:
                self.assertEqual(gui_source_snapshot(root, digests, 'reference'), contents)
                self.assertEqual({call.args[0][2] for call in git.call_args_list}, set(git_blobs))
                git_blobs['reference:tools/rust-qa/gui/src/linux_legacy.rs'] = b'different committed source'
                with self.assertRaisesRegex(RuntimeError, 'hosted revision'):
                    gui_source_snapshot(root, digests, 'reference')
                self.assertEqual(gui_source_snapshot(root, digests), contents)

    def test_shared_id_needs_both_original_identities(self):
        verify_paths(True, [21, 5], [21, 5], [21, 9], 'NORMAL_ENDPOINT visible 21 9')
        for directory, endpoint in (([21, 6], 'NORMAL_ENDPOINT visible 21 9'),
                                    ([21, 5], 'NORMAL_ENDPOINT visible 21 8'), ([21, 5], 'NORMAL_ENDPOINT absent')):
            with self.subTest(directory=directory, endpoint=endpoint), self.assertRaises(RuntimeError):
                verify_paths(True, [21, 5], directory, [21, 9], endpoint)

    def test_distinct_id_needs_separate_runtime_and_absent_endpoint(self):
        verify_paths(False, [21, 5], [21, 6], [21, 9], 'NORMAL_ENDPOINT absent')
        for directory, endpoint in (([21, 5], 'NORMAL_ENDPOINT absent'), ([21, 6], 'NORMAL_ENDPOINT visible 21 9'),
                                    ([21, 6], 'NORMAL_ENDPOINT visible 21 8')):
            with self.subTest(directory=directory, endpoint=endpoint), self.assertRaises(RuntimeError):
                verify_paths(False, [21, 5], directory, [21, 9], endpoint)

    def test_two_nested_paths_need_distinct_live_pid_and_mount_namespaces(self):
        outer = dict(pid='parent-pid', mnt='parent-mount', net='offline')
        first = dict(gui={'pid': 20}, namespacePids=[20, 2], instance='first', namespaces=dict(pid='p1', mnt='m1', net='offline'))
        other = dict(gui={'pid': 30}, namespacePids=[30, 2], instance='second', namespaces=dict(pid='p2', mnt='m2', net='offline'))
        verify_siblings(outer, first, other)
        for key, change in (('pid', 'p1'), ('mnt', 'm1'), ('net', 'another-net'), ('pid', 'parent-pid')):
            changed = deepcopy(other)
            changed['namespaces'][key] = change
            with self.subTest(key=key, change=change), self.assertRaises(RuntimeError):
                verify_siblings(outer, first, changed)
        for path in ([30], [29, 2], [30, 2, 3], [30, 0]):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                verify_siblings(outer, first, {**other, 'namespacePids': path})
