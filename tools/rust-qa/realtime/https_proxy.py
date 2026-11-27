"""Loopback HTTP proxy observers that serve a single fixed origin on their own sockets."""

from collections import Counter
from http.server import BaseHTTPRequestHandler
import ssl
import threading
from urllib.parse import parse_qs, urlsplit


def rejected_connect(handler, authority):
    if handler.path != authority or handler.headers.get_all("Host") != [authority]:
        return "rejectedAuthority"
    if any(key in handler.headers for key in ("x-api-key", "Authorization", "Proxy-Authorization", "Cookie")):
        return "credentialHeaders"
    return None


class FixedTunnel:
    def __init__(self, authority, tls):
        self.authority = authority
        self.tls = tls
        self.counts = Counter()
        self.alerts = Counter()
        self.pending = 0
        self.condition = threading.Condition()
        self.tls.set_servername_callback(self.client_hello)

    def mark(self, key):
        with self.condition:
            self.counts[key] += 1

    def client_hello(self, _socket, _name, _context):
        self.mark("clientHellos")

    def snapshot(self):
        with self.condition:
            assert self.condition.wait_for(lambda: self.pending == 0, 5), "CONNECT handlers did not drain"
            return dict(self.counts), dict(self.alerts)

    def handler(self, inner_handler):
        tunnel = self

        class Connect(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            rbufsize = 0

            def log_message(self, *args):
                pass

            def handle(self):
                self.connection.settimeout(4)
                with tunnel.condition:
                    tunnel.pending += 1
                    tunnel.counts["connections"] += 1
                try:
                    super().handle()
                finally:
                    with tunnel.condition:
                        tunnel.pending -= 1
                        tunnel.condition.notify_all()

            def do_CONNECT(self):
                self.close_connection = True
                tunnel.mark("connects")
                refusal = rejected_connect(self, tunnel.authority)
                if refusal:
                    tunnel.mark(refusal)
                    self.send_error(403)
                    return
                self.send_response_only(200, "Connection established")
                self.end_headers()
                self.wfile.flush()
                try:
                    stream = tunnel.tls.wrap_socket(self.connection, server_side=True)
                except ssl.SSLError as error:
                    with tunnel.condition:
                        tunnel.alerts[error.reason or "UNKNOWN"] += 1
                    return
                with stream:
                    tunnel.mark("completedTls")
                    inner_handler(stream, self.client_address, self.server)

        return Connect


def plaintext_handler(origin, authority, refuse_connect):
    """Accept absolute HTTP requests and switch this socket to the fixed origin after CONNECT."""
    class FixedPlaintext(origin):
        in_tunnel = False

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_CONNECT(self):
            self.server.mark("connects")
            refusal = rejected_connect(self, authority)
            if refusal or self.in_tunnel:
                self.server.mark(refusal or "nestedConnect")
                self.send_error(403)
                self.close_connection = True
                return
            self.record_target("connect")
            if refuse_connect:
                self.redirect()
                self.server.initial_refused.set()
                self.close_connection = True
                return
            self.send_response_only(200, "Connection established")
            self.end_headers()
            self.in_tunnel = True

        def record_target(self, label):
            with self.server.lock:
                self.server.proxy_targets.setdefault(label, self.requestline)

        def validate_target(self):
            url = urlsplit(self.path)
            mode = parse_qs(url.query).get("transport")
            assert self.headers.get_all("Host") == [authority]
            assert self.headers.get_all("Proxy-Authorization") is None
            if self.in_tunnel:
                assert self.path.startswith("/socket.io/?") and self.command == "GET" and mode == ["websocket"]
                assert not url.scheme and not url.netloc
                self.server.mark("tunneledUpgrades")
                self.record_target("directUpgrade" if "sid" not in parse_qs(url.query) else "upgrade")
            else:
                assert self.path.startswith("http://" + authority + "/") and url.netloc == authority
                if url.path == self.server.api + "/albums":
                    label = "inventory"
                else:
                    assert url.path == "/socket.io/" and mode == ["polling"]
                    label = "polling" + self.command
                self.server.mark("absoluteRequests")
                self.record_target(label)
    return FixedPlaintext
