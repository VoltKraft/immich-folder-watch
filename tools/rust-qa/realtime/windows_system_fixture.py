"""Exercise the current user's Windows proxy on a disposable local test guest."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# Embedded Python's isolated search path can omit the invoked script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import make_trust, peer, proxy_environment, run_http_proxy_scenario, run_proxy_scenario


class Value(ctypes.Union):
    _fields_ = [("flags", wintypes.DWORD), ("pointer", ctypes.c_void_p), ("time", wintypes.FILETIME)]


class Option(ctypes.Structure):
    _fields_ = [("option", wintypes.DWORD), ("value", Value)]


class OptionList(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("connection", ctypes.c_void_p), ("count", wintypes.DWORD),
                ("error", wintypes.DWORD), ("options", ctypes.POINTER(Option))]


class Connection:
    def __init__(self):
        if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") or os.environ.get("COMPUTERNAME", "").upper() != "IFW-QA25":
            raise RuntimeError("System proxy trials require the provisioned local IFW-QA25 guest")
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference='Stop'; $vm=Get-CimInstance Win32_ComputerSystem; "
             "if ($vm.Name -ine 'IFW-QA25' -or !$vm.HypervisorPresent) { exit 1 }"],
            capture_output=True, timeout=20,
        )
        if result.returncode:
            raise RuntimeError("The live computer identity and hypervisor must match the provisioned QA guest")
        self.wininet = ctypes.WinDLL("wininet", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.GlobalFree.argtypes = [ctypes.c_void_p]
        self.kernel.GlobalFree.restype = ctypes.c_void_p
        self.wininet.InternetQueryOptionW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                                      ctypes.POINTER(wintypes.DWORD)]
        self.wininet.InternetSetOptionW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    def settings(self, values=None):
        # Query FLAGS_UI, PROXY_SERVER, PROXY_BYPASS and AUTOCONFIG_URL.
        # WinINet requires FLAGS, rather than FLAGS_UI, when restoring.
        keys = [10 if values is None else 1, 2, 3, 4]
        options = (Option * len(keys))()
        strings = []
        for index, key in enumerate(keys):
            options[index].option = key
            if values is not None:
                if index == 0:
                    options[index].value.flags = values[index]
                elif values[index] is not None:
                    buf = ctypes.create_unicode_buffer(values[index])
                    strings.append(buf)
                    options[index].value.pointer = ctypes.addressof(buf)
        data = OptionList(ctypes.sizeof(OptionList), None, len(keys), 0, options)
        if values is None:
            size = wintypes.DWORD(ctypes.sizeof(data))
            if not self.wininet.InternetQueryOptionW(None, 75, ctypes.byref(data), ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            pointers = [o.value.pointer for o in options[1:]]
            try:
                return [options[0].value.flags] + [ctypes.wstring_at(p) if p else None for p in pointers]
            finally:
                for pointer in pointers:
                    if pointer:
                        self.kernel.GlobalFree(pointer)
        for flag, value, size in [(75, ctypes.byref(data), ctypes.sizeof(data)), (39, None, 0), (37, None, 0)]:
            if not self.wininet.InternetSetOptionW(None, flag, value, size):
                raise ctypes.WinError(ctypes.get_last_error())


def exercise(subject, result):
    settings = Connection()
    original = settings.settings()
    try:
        with tempfile.TemporaryDirectory(prefix="ifw-system-proxy-") as temp, peer("redirect-destination") as redirect:
            directory = Path(temp)
            contexts, result["certificates"] = make_trust(directory)
            other = f"127.0.0.1:{redirect.server_port}"
            for scheme in ("http", "https"):
                for mode in ("direct", "manual", "bypass", "wildcard", "local", "protocol", "environment-first"):
                    def configure(endpoint):
                        relay = endpoint.removeprefix("http://")
                        named = f"http={relay};https={other}" if scheme == "http" else f"http={other};https={relay}"
                        cases = {"direct": [1, None, None, None], "manual": [3, relay, None, None],
                                 "bypass": [3, relay, "127.0.0.1", None], "wildcard": [3, relay, "127.0.*", None],
                                 "local": [3, relay, "<local>", None], "protocol": [3, named, None, None],
                                 "environment-first": [3, other, None, None]}
                        settings.settings(cases[mode])
                        return {f"{scheme.upper()}_PROXY": endpoint} if mode == "environment-first" else {}
                    direct = mode in ("direct", "bypass", "wildcard", "local")
                    wire_case = f"{scheme}-proxy" + ("-bypass" if direct else "")
                    if scheme == "http":
                        observed = run_http_proxy_scenario(subject, "windows", wire_case, directory, redirect, configure)
                    else:
                        observed = run_proxy_scenario(subject, "windows", wire_case, directory, contexts, redirect, configure)
                    result["cases"][f"{scheme}-{mode}"] = observed
            # The adapter recognizes automatic configuration explicitly, without
            # performing discovery, contacting a PAC server or authenticating.
            for mode, config in [("pac", [5, None, None, f"http://{other}/fixture.pac"]), ("wpad", [9, None, None, None])]:
                settings.settings(config)
                with peer("tls") as origin:
                    proc = subprocess.run([subject, f"https://127.0.0.1:{origin.server_port}/api", "https-windows-system-proxy",
                                           "-", "300", "100", "100", f"http://{other}"],
                                          env=proxy_environment(directory), capture_output=True, text=True, timeout=8)
                    assert proc.returncode == 1 and proc.stderr.strip() == "AutomaticProxy" and not proc.stdout
                    assert not origin.accepted_connections and not redirect.accepted_connections
                    result["cases"][mode] = {"selection": "AutomaticProxy", "originConnections": 0, "relayConnections": 0}
    finally:
        settings.settings(original)
        current = settings.settings()
        result["settingsRestored"] = [v or None for v in original] == [v or None for v in current]
        if not result["settingsRestored"]:
            raise RuntimeError("Windows user proxy settings were not restored")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or not __debug__:
        raise RuntimeError("This fixture requires a disposable Windows guest and Python assertions")
    subject = args.probe.resolve(strict=True)
    with subject.open("rb") as stream:
        result = {"cases": {}, "probeSha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    try:
        exercise(subject, result)
    finally:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
