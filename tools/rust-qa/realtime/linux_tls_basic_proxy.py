"""Inner peer for the native Linux HTTPS origin and named HTTP proxy comparison."""

import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import threading
from urllib.parse import quote

from peer import Handler
from wire import make_trust


def observe(client, mode):
    assert socket.if_nameindex() == [(1, "lo")] and len(Path("/proc/net/route").read_text().splitlines()) == 1
    os.environ["PATH"] = "/usr/bin"
    keys = Path("/tmp/keys")
    keys.mkdir(mode=0o700)
    contexts, certificates = make_trust(keys)
    direct_tls = contexts["127.0.0.1"]
    authority = "127.0.0.1:28431"
    secret = secrets.token_hex(12) + "@:+/"
    required = "Basic " + base64.b64encode(f"fixture:{secret}".encode()).decode()
    digest = None
    if mode.startswith("digest-"):
        from digest_peer import DigestPeer
        digest = DigestPeer(secret, authority, mode.split("-")[1], legacy_root="legacy" in mode)
    lock = threading.Lock()
    rows = []

    class Peer(ThreadingHTTPServer):
        lang = "signed" if client == "signed" else "rust"

        def record(self, kind, **fields):
            with lock:
                assert len(rows) < 500
                rows.append(dict(kind=kind, **fields))

        def handle_error(self, _request, _address):
            self.record("handlerError", exception=sys.exc_info()[0].__name__)

    class Origin(Handler):
        def route(self):
            assert self.headers.get_all("Host") == [authority]
            supplied = self.headers.get_all("Proxy-Authorization", [])
            self.server.record("inner", route=self.server.route, subjectPort=self.client_address[1],
                               tls=self.connection.version(), proxyHeader=bool(supplied),
                               apiHeader=self.headers.get_all("x-api-key") == ["synthetic"])
            assert not supplied
            return super().route()

    class Proxy(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        rbufsize = 0

        def log_message(self, *_args):
            pass

        def do_CONNECT(self):
            self.close_connection = True
            assert self.path == authority and self.headers.get_all("Host") == [authority]
            assert not any(key in self.headers for key in ("x-api-key", "Authorization", "Cookie"))
            values = self.headers.get_all("Proxy-Authorization", [])
            valid = len(values) == 1 and hmac.compare_digest(required, values[0])
            if digest:
                credential, uri_form = digest.check(values)
                accepted = credential == "correct"
                target = {"digestUri": uri_form}
            else:
                credential = ("correct" if valid else "incorrect" if values and values[0].startswith("Basic ")
                              else "digest" if values and values[0].startswith("Digest ") else "other" if values else "absent")
                accepted = mode == "anonymous" or valid and mode != "other-scheme"
                target = {}
            self.server.record("connect", subjectPort=self.client_address[1], apiHeader=False,
                               credentials=credential, status=200 if accepted else 407, **target)
            if not accepted:
                self.send_response(407)
                scheme = 'Digest realm="other", nonce="fixture"' if mode == "other-scheme" else 'Basic realm="fixture"'
                self.send_header("Proxy-Authenticate", digest.challenge if digest else scheme)
                self.send_header("Connection", "close")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response_only(200, "Connection Established")
            self.end_headers()
            self.wfile.flush()
            with direct_tls.wrap_socket(self.connection, server_side=True) as tls:
                Origin(tls, self.client_address, self.server)

    proxy = Peer(("127.0.0.1", 28432), Proxy)
    direct = Peer(("127.0.0.1", 28431), Origin)
    direct.socket = direct_tls.wrap_socket(direct.socket, server_side=True)
    workers = []
    for server, route in ((proxy, "tunnel"), (direct, "direct")):
        server.route = route
        server.joined = threading.Event()
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        worker.start()
        workers.append(worker)
    relay = "http://127.0.0.1:28432"
    proxy_url = relay
    if mode != "anonymous":
        chosen = secret + "wrong" if mode.endswith("incorrect") else secret
        proxy_url = f"http://fixture:{quote(chosen, safe='')}@127.0.0.1:28432"
    env = {"HOME": "/tmp", "LANG": "C.UTF-8", "PATH": "/usr/bin", "HTTPS_PROXY": proxy_url,
           "SSL_CERT_FILE": str(keys / "ca.crt"), "SSL_CERT_DIR": "/tmp/empty-certs",
           "DOTNET_EnableDiagnostics": "0", "DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_PROCESSOR_COUNT": "2"}
    Path("/tmp/empty-certs").mkdir()
    if mode == "bypass":
        env["NO_PROXY"] = "127.0.0.1"
    api = f"https://{authority}/collection/api"
    if client == "signed":
        command = ["/sdk/dotnet", "exec", "--runtimeconfig", "/package/immich-folder-watch.runtimeconfig.json",
                   "--depsfile", "/package/immich-folder-watch.deps.json", "/package/proxy.dll", api]
    else:
        command = ["/candidate", api, "https-linux-proxy", str(keys / "ca.crt"), "1400", "30000", "250", relay]
    try:
        process = subprocess.run(command, env=env, text=True, capture_output=True, timeout=15)
    finally:
        for server in (proxy, direct):
            server.shutdown()
            server.server_close()
        for worker in workers:
            worker.join()
    lines = process.stdout.splitlines()
    print(json.dumps({"client": client, "mode": mode, "procExit": process.returncode,
                      "event": "Event" in lines or "stopped events=1" in lines,
                      "inventory": "inventory missing=True error=" in lines or "Inventory" in lines,
                      "fixtureRejection": "Protocol" in process.stderr.split(),
                      "netDevices": socket.if_nameindex(), "leafDerSha256": certificates["127.0.0.1"],
                      "caPemSha256": hashlib.sha256((keys / "ca.crt").read_bytes()).hexdigest(),
                      "observations": rows}))


if __name__ == "__main__":
    assert sys.argv[1] == "--inside"
    observe(*sys.argv[2:])
