"""Compare archived native client binaries at a single fixed synthetic HTTP proxy."""

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import quote, urlsplit


AUTHORITY = "127.0.0.1:28431"
RELAY = "127.0.0.1:28432"
MATRIX = [
    ("signed", "anonymous"), ("signed", "correct"), ("signed", "incorrect"),
    ("rust", "anonymous"), ("rust", "correct"),
]
CANDIDATE_MATRIX = [("candidate", mode) for mode in ("anonymous", "correct", "incorrect", "connect-only", "other-scheme")]
ARCHIVE_PINS = {
    "inputs.json": "a558a833ecdf7de509ebb00d93992d8d3a281b00f7bd59fba00a3016b9346237",
    "test/peer.py": "3c1153ce7e6e9ab16a19921d967e87b582cd14a084faed30ed54e74929f9c623",
    "test/wire.py": "5ac8897fb680243cddeaf6429b6f24c63806d6b18ef47d5593266cd8cc9c3ac4",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(client, mode):
    from peer import Handler  # The pinned paired 3.0.4 and Rust Socket.IO peer.

    assert socket.if_nameindex() == [(1, "lo")]
    assert len(Path("/proc/net/route").read_text().splitlines()) == 1
    secret = secrets.token_hex(16) + "@:+/"
    user = "fixture"
    expected = "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()

    class Relay(ThreadingHTTPServer):
        lang = "signed" if client == "signed" else "rust"

        def record(self, kind, **data):
            with self.lock:
                assert len(self.trace) < 500
                self.trace.append({"kind": kind, **data})

        def handle_error(self, _request, _address):
            self.record("handlerError", exception=sys.exc_info()[0].__name__)

    class FixedOriginProxy(Handler):
        # Only this listening socket exists. Once CONNECT succeeds the original
        # peer reads the actual WebSocket Upgrade and frames on the same socket.
        tunneled = False

        def route_request(self):
            values = self.headers.get_all("Proxy-Authorization", [])
            api = self.headers.get_all("x-api-key", [])
            valid = len(values) == 1 and hmac.compare_digest(values[0], expected)
            assert self.headers.get_all("Host") == [AUTHORITY]
            if self.tunneled:
                assert self.command == "GET" and self.path.startswith("/socket.io/?")
                self.server.record("innerUpgrade", proxyHeader=bool(values), apiKey=api == ["synthetic"])
                assert not values
            else:
                if self.command == "CONNECT":
                    assert self.path == AUTHORITY and not api
                    label = "connect"
                else:
                    url = urlsplit(self.path)
                    assert url.scheme == "http" and url.netloc == AUTHORITY and not url.fragment
                    assert url.path in ("/socket.io/", "/collection/api/albums")
                    self.path = url.path + ("?" + url.query if url.query else "")
                    label = "inventory" if url.path.endswith("/albums") else "polling" + self.command
                allowed = (mode == "anonymous" or mode == "connect-only" and label != "connect"
                           or mode != "other-scheme" and valid)
                self.server.record("proxy", operation=label, credentials=(
                    "correct" if valid else "incorrect" if values else "absent"),
                    apiKey=api == ["synthetic"], status="allow" if allowed else "407")
                if not allowed:
                    self.send_response(407)
                    challenge = 'Digest realm="protected, Basic realm", nonce="fixture"' if mode == "other-scheme" else 'Basic realm="fixture"'
                    self.send_header("Proxy-Authenticate", challenge)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    return
                if self.command == "CONNECT":
                    self.send_response_only(200, "Connection Established")
                    self.end_headers()
                    self.tunneled = True
                    return
                del self.headers["Proxy-Authorization"]
            if self.command == "GET":
                super().do_GET()
            else:
                super().do_POST()

        do_GET = do_POST = do_CONNECT = route_request

    relay = Relay(("127.0.0.1", 28432), FixedOriginProxy)
    relay.lock = threading.Lock()
    relay.trace = []
    relay.joined = threading.Event()
    worker = threading.Thread(target=relay.serve_forever, kwargs={"poll_interval": 0.02})
    worker.start()
    api = f"http://{AUTHORITY}/collection/api"
    proxy = f"http://{RELAY}"
    if mode != "anonymous":
        chosen = secret + "x" if mode in ("incorrect", "connect-only") else secret
        proxy = f"http://{user}:{quote(chosen, safe='')}@{RELAY}"
    env = {
        "HTTP_PROXY": proxy, "HOME": "/tmp", "PATH": "/usr/bin", "LANG": "C.UTF-8",
        "DOTNET_EnableDiagnostics": "0", "DOTNET_MULTILEVEL_LOOKUP": "0",
        "DOTNET_PROCESSOR_COUNT": "2", "TOKIO_WORKER_THREADS": "2",
    }
    if client == "signed":
        command = ["/sdk/dotnet", "exec", "--runtimeconfig", "/package/immich-folder-watch.runtimeconfig.json",
                   "--depsfile", "/package/immich-folder-watch.deps.json", "/package/proxy.dll", api]
    else:
        command = ["/candidate" if client == "candidate" else "/binprobe", api, "allow-http-linux-proxy", "-", "1400", "30000", "250", f"http://{RELAY}"]
    try:
        subject = subprocess.run(command, text=True, capture_output=True, env=env, timeout=15)
    finally:
        relay.shutdown()
        worker.join()
        relay.server_close()
    # Deliberately emit no raw process diagnostics, URLs with userinfo, or header values.
    lines = subject.stdout.splitlines()
    print(json.dumps({
        "client": client, "mode": mode, "exitCode": subject.returncode, "observations": relay.trace,
        "inventorySucceeded": any(line == "Inventory" or line == "inventory missing=True error=" for line in lines),
        "eventObserved": "Event" in lines or "stopped events=1" in lines,
        "stopped": "Stopped" in lines or any(line.startswith("stopped events=") for line in lines),
        "fixtureProtocolRejected": "Protocol" in subject.stderr.split(),
        "netDevices": socket.if_nameindex(),
    }))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls", action="store_true", help="run the HTTPS origin comparison")
    parser.add_argument("--digest", action="store_true", help="compare CONNECT Digest with a verifying TLS relay")
    parser.add_argument("--archive", type=Path, required=True, help="paired native proxy-fedora-05 archive")
    parser.add_argument("--sdk", type=Path, required=True, help="shared .NET SDK containing the dotnet host")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, help="additional native release binary")
    parser.add_argument("--candidate-sha256", help="expected digest of the additional binary")
    args = parser.parse_args()
    if args.digest and not args.tls:
        parser.error("--digest requires --tls")
    if bool(args.candidate) != bool(args.candidate_sha256):
        parser.error("supply both the candidate and its expected digest")
    archive = args.archive.resolve(strict=True)
    inputs = json.loads((archive / "inputs.json").read_text())
    pins = {**ARCHIVE_PINS, **{f"package/{k}": v for k, v in inputs["signedAssemblies"].items()},
            "package/proxy.dll": inputs["developmentDriver"], "test/proxy.cs": inputs["driverSource"],
            "target/release/ifw-realtime-probe": inputs["binary"]}
    for name, expected in pins.items():
        if digest(archive / name) != expected:
            raise ValueError(f"archive input does not match its pin: {name}")
    script = Path(__file__).resolve()
    sdk = args.sdk.resolve(strict=True)
    launch = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all", "--clearenv"]
    for path in ("/usr/bin", "/usr/lib", "/usr/lib64", "/etc/ld.so.cache"):
        launch.extend(("--ro-bind", path, path))
    launch.extend(("--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                   "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"))
    for source, target in [(sdk, "/sdk"), (archive / "package", "/package"), (archive / "test", "/fixture"),
                           (archive / "target/release/ifw-realtime-probe", "/binprobe"), (script, "/case.py")]:
        launch.extend(("--ro-bind", str(source.resolve()), target))
    if args.candidate:
        if digest(args.candidate) != args.candidate_sha256:
            raise ValueError("candidate binary does not match")
        launch.extend(("--ro-bind", str(args.candidate.resolve(strict=True)), "/candidate"))
    inner = "/case.py"
    if args.tls:
        tls_script = script.with_name("linux_tls_basic_proxy.py")
        inner = "/tls.py"
        launch.extend(("--ro-bind", str(tls_script), inner))
        if args.digest:
            digest_script = script.with_name("digest_peer.py")
            launch.extend(("--ro-bind", str(digest_script), "/digest_peer.py"))
    launch.extend(("--setenv", "PYTHONPATH", "/fixture", "--chdir", "/tmp", "--", "/usr/bin/python3", "-B", inner, "--inside"))
    cases = MATRIX + CANDIDATE_MATRIX if args.candidate else MATRIX
    if args.tls:
        modes = ("anonymous", "correct", "incorrect", "other-scheme", "bypass")
        if args.digest:
            modes = [f"digest-{algorithm}{policy}{password}"
                     for algorithm in ("sha256", "md5") for policy in ("", "-legacy")
                     for password in ("", "-incorrect")]
        cases = [(client, mode) for client in (("signed", "candidate") if args.candidate else ("signed",)) for mode in modes]
    observations = [json.loads(subprocess.check_output([*launch, *case], timeout=25)) for case in cases]
    evidence = {
        "host": Path("/etc/os-release").read_text(), "machine": os.uname().machine, "kernel": os.uname().release,
        "signedCommit": inputs["signedCommit"], "rustSourceHead": inputs["sourceHead"], "archiveInputs": pins,
        "dotnetHost": digest(sdk / "dotnet"), "trialScript": digest(script), "cases": observations,
    }
    if args.tls:
        evidence["tlsTrialScript"] = digest(tls_script)
    if args.digest:
        evidence["digestPeerScript"] = digest(digest_script)
    if args.candidate:
        evidence["candidateBinarySha256"] = args.candidate_sha256
    with args.output.open("x") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--inside"]:
        inside(*sys.argv[2:])
    else:
        main()
