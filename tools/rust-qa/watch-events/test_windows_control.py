"""Check control eligibility without substituting data for native Windows I/O."""

import unittest

from windows_control import idle_cancel_passed, require_file_id


class WindowsControlTests(unittest.TestCase):
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
