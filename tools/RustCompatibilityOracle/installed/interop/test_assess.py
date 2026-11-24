"""Check that the two Flatpak prerequisite outcomes cannot be interchanged."""

from copy import deepcopy
import unittest

from assess import verify_paths, verify_siblings


class IdentityTests(unittest.TestCase):
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
