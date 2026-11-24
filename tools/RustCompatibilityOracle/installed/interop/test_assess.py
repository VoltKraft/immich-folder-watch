"""Check that the two Flatpak prerequisite outcomes cannot be interchanged."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from assess import gui_source_snapshot, inventory_inputs, verify_paths, verify_siblings
from shipping_upload import endpoint_tuple, FILENAME, IMAGE, multipart_image


class ConfiguredUploadTests(unittest.TestCase):
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
            with patch('assess.EXPECTED_WORKER', digest), patch('assess.subprocess.check_output', return_value=b'{"source":"digest"}'):
                for field, wrong in [('worker_sha256', 'another-worker'), ('gui_sha256', 'another-gui'), ('sources', {})]:
                    (subject / 'worker.inputs.json').write_text(json.dumps({**build, field: wrong}))
                    with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, 'worker, native GUI or pinned source'):
                        inventory_inputs(subject, root, 'revision', 'original-gui', 'release', root)
                    self.assertFalse((root / 'inventory-sources.zip').exists())

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
