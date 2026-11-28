import ctypes as c
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
VENUE = runpy.run_path(str(HERE / "venue.py"))


class VenueTests(unittest.TestCase):
    def test_session_results_drop_names_and_ids_and_free_native_buffers(self):
        session = VENUE["Session"]
        rows = (session * 4)(session(41, 0x100, 0), session(42, 0x108, 0), session(43, 0x110, 4), session(987, 0x118, 6))
        values = {41: c.c_uint16(0), 42: c.c_uint16(0), 43: c.c_uint16(2)}
        dll = Mock()
        def enumerate_sessions(server, reserved, version, data, count):
            self.assertEqual((server, reserved, version), (None, 0, 1))
            c.cast(data, c.POINTER(c.POINTER(session)))[0] = c.cast(rows, c.POINTER(session))
            count._obj.value = len(rows)
            return True
        def protocol(server, session_id, info, data, size):
            self.assertEqual((server, info), (None, 16))
            if session_id not in values:
                return False
            data._obj.value = c.addressof(values[session_id])
            size._obj.value = 2
            return True
        dll.WTSEnumerateSessionsW.side_effect = enumerate_sessions
        dll.WTSQuerySessionInformationW.side_effect = protocol
        with patch.object(c, "WinDLL", return_value=dll, create=True):
            result = VENUE["session_counts"]()
            self.assertEqual(result, dict(status="observed", counts=[
                dict(state="active", protocol="console", count=2), dict(state="disconnected", protocol="rdp", count=1),
                dict(state="listen", protocol="unavailable", count=1)]))
            self.assertEqual(dll.WTSFreeMemory.call_count, 4)
            dll.WTSEnumerateSessionsW.side_effect = None
            dll.WTSEnumerateSessionsW.return_value = False
            self.assertEqual(VENUE["session_counts"](), dict(status="unavailable", counts=[]))

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is required for the listener controls")
    def test_native_listener_classification_excludes_uncorrelated_ports_and_raw_addresses(self):
        command = """
        $ErrorActionPreference='Stop'
        $ast=[Management.Automation.Language.Parser]::ParseFile($env:IFW_LISTENER_SCRIPT,[ref]$null,[ref]$null)
        $function=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-ListenerClass'},$false)
        . ([scriptblock]::Create($function.Extent.Text))
        $service=@{State='Running';ProcessId=11}
        function Row($address,$owner=11) { @{LocalAddress=$address;OwningProcess=$owner} }
        @((Get-ListenerClass @() $null),
          (Get-ListenerClass @((Row '127.0.0.2'),(Row '::1'),(Row '::ffff:127.0.0.1')) $service),
          (Get-ListenerClass @((Row '127.0.0.1'),(Row '::')) $service),
          (Get-ListenerClass @((Row '192.0.2.1')) $service),
          (Get-ListenerClass @((Row '127.0.0.1' 15)) $service),
          (Get-ListenerClass @((Row 'invalid')) $service),
          (Get-ListenerClass @((Row '::1')) $null)) | ConvertTo-Json -Compress
        """
        output = subprocess.check_output([shutil.which("pwsh"), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                                         env={**os.environ, "IFW_LISTENER_SCRIPT": str(HERE / "venue.ps1")}, timeout=30)
        self.assertEqual(json.loads(output), ["none", "loopback-only", "other-or-any", "other-or-any",
                                              "unavailable", "unavailable", "unavailable"])
