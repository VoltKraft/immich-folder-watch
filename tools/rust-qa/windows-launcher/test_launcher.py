"""Exercise the ordinary secondary invocation and the evidence required to attribute its window."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

import observe


class LauncherTests(unittest.TestCase):
    def test_secondary_runs_the_same_image_without_arguments_or_input_pipe(self):
        api, desk = Mock(), Mock()
        desk.name.return_value = "IfwQa_test"
        desk.receiving_input.return_value = False
        image = Path("native-gui-assessment.exe")
        with (patch.object(subprocess, "STARTUPINFO", create=True),
              patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True),
              patch.object(subprocess, "Popen") as launch):
            launch.return_value.stdin = None
            with observe.child(api, desk, "IfwQa_test", image, [], Path("case"), {}, None, False):
                pass
        self.assertEqual(launch.call_args.args, ([image],))
        self.assertNotIn("stdin", launch.call_args.kwargs)
        api.assign_suspended.assert_called_once_with(api.new_job.return_value, launch.return_value, image)

    def test_receipt_requires_the_original_primary_and_its_worker(self):
        secondary = ["LAUNCHER_SECONDARY server=12"]
        primary = ["LAUNCHER_OPEN client=15"]
        receipt = dict(primaryPid=12, secondaryPid=15, initialWindowPid=12, reopenedWindowPid=12,
                       hiddenBeforeLaunch=True, workerBefore=[13, 1234], workerAfter=[13, 1234],
                       secondaryExit=0, secondaryJobEmpty=True, secondaryTotalProcesses=1)
        observe.qualify(secondary, primary, receipt)
        for key, value in (("hiddenBeforeLaunch", False), ("reopenedWindowPid", 15),
                           ("workerAfter", [13, 4321]), ("secondaryTotalProcesses", 2)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                observe.qualify(secondary, primary, dict(receipt, **{key: value}))
        for wrong_secondary, wrong_primary in [
            (["READY Visible Unavailable"], primary), (secondary, []),
            (secondary, ["LAUNCHER_OPEN"]), (secondary, primary * 2),
        ]:
            with self.assertRaises(ValueError):
                observe.qualify(wrong_secondary, wrong_primary, receipt)


if __name__ == "__main__":
    unittest.main()
