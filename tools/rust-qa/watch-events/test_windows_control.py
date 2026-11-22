"""Check control eligibility without substituting data for native Windows I/O."""

import struct
import unittest

from windows_control import (decode_notifications, flat_notification_evidence,
                             idle_cancel_passed, require_file_id)


def native_buffer(*events):
    data = b""
    for index, (action, name) in enumerate(events):
        encoded = name.encode("utf-16-le")
        size = (12 + len(encoded) + 3) & ~3
        offset = size if index + 1 < len(events) else 0
        record = struct.pack("<III", offset, action, len(encoded)) + encoded
        data += record + bytes(size - len(record))
    return data


def trace_line(generation, *events):
    data = native_buffer(*events)
    return f"WATCH_NOTIFY {generation} {len(data)} {data.hex()}\n"


class WindowsControlTests(unittest.TestCase):
    def test_notification_decoder_checks_record_boundaries(self):
        events = ((3, "nested"), (1, "flat.jpg"))
        data = native_buffer(*events)
        self.assertEqual(decode_notifications(data), [{"action": a, "name": n} for a, n in events])
        invalid = (b"", bytes(11), struct.pack("<III", 0, 3, 1) + b"x",
                   struct.pack("<III", 4, 3, 2) + b"x\0",
                   struct.pack("<III", 100, 3, 2) + b"x\0",
                   native_buffer((3, "nested")) + bytes(4))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_notifications(value)

    def test_flat_scope_accepts_proven_parent_metadata_and_a_direct_child(self):
        result = flat_notification_evidence(trace_line(2, (3, "nested")) +
                                            trace_line(3, (1, "flat.jpg")), 1, 2, 3)
        self.assertTrue(result["parentMetadataObserved"])
        self.assertTrue(result["directChildObserved"])
        quiet = flat_notification_evidence(trace_line(2, (1, "flat.jpg")), 1, 1, 2)
        self.assertFalse(quiet["parentMetadataObserved"])

    def test_flat_scope_rejects_nested_names_gaps_and_unproven_direct_changes(self):
        for event in ((3, "nested/item.jpg"), (3, "nested\\item.jpg"), (1, "nested"), (3, "other")):
            with self.subTest(event=event), self.assertRaises(ValueError):
                flat_notification_evidence(trace_line(2, event) + trace_line(3, (1, "flat.jpg")), 1, 2, 3)
        for trace, before, nested, direct in (
            (trace_line(2, (3, "nested")), 1, 1, 2),
            (trace_line(3, (1, "flat.jpg")), 1, 2, 3),
            ("WATCH_NOTIFY_TRUNCATED\n", 1, 1, 2),
            ("WATCH_NOTIFY 2 12 00\n", 1, 1, 2),
        ):
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                flat_notification_evidence(trace, before, nested, direct)

    def test_missing_or_incomplete_file_identity_is_declined(self):
        for identifier in (bytes(16), b"", bytes(15), bytes(17)):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                require_file_id(identifier)

    def test_every_byte_of_a_nonzero_128_bit_identity_is_significant(self):
        for index in range(16):
            identifier = bytearray(16)
            identifier[index] = 1
            require_file_id(identifier)

    def test_idle_cancellation_requires_successful_cancel_and_aborted_completion(self):
        passed = {"sameDirectory": True, "idleWaitResult": 258,
                  "cancelError": 0, "completionError": 995}
        self.assertTrue(idle_cancel_passed(passed))
        for key, value in (("sameDirectory", False), ("idleWaitResult", 0),
                           ("cancelError", 1168), ("completionError", 0)):
            with self.subTest(key=key):
                self.assertFalse(idle_cancel_passed({**passed, key: value}))
                self.assertFalse(idle_cancel_passed({k: v for k, v in passed.items() if k != key}))


if __name__ == "__main__":
    unittest.main()
