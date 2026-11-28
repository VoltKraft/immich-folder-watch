"""Loopback HTTP proxy observers that serve a single fixed origin on their own sockets."""

from collections import Counter
import hmac
from http.server import BaseHTTPRequestHandler
import io
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
    def __init__(self, authority, tls, authentication=None):
        self.authority = authority
        self.authentication = authentication
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
                if tunnel.authentication is not None:
                    if not tunnel.authentication.accept(self, tunnel.authority):
                        return
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

def authenticated_proxy_handler(origin, authority, name, expected, digest):
    """Authenticate only the absolute HTTP request or CONNECT on this fixed listener."""
    class AuthenticatedProxy(origin):
        def parse_request(self):
            if not super().parse_request():
                return False
            assert self.headers.get_all("Host") == [authority]
            supplied = self.headers.get_all("Proxy-Authorization", [])
            if self.in_tunnel:
                assert not supplied
                return True
            if self.command == "CONNECT":
                assert self.path == authority and not self.headers.get_all("x-api-key")
                operation = "connect"
            else:
                target = urlsplit(self.path)
                assert target.scheme == "http" and target.netloc == authority
                assert target.path in (self.server.api + "/albums", "/socket.io/")
                assert self.headers.get_all("x-api-key") == ["synthetic"]
                operation = "inventory" if target.path.endswith("/albums") else "polling" + self.command
            if digest:
                body = b""
                if self.command == "POST" and digest.qop == "auth-int":
                    size = int(self.headers["Content-Length"])
                    assert 0 < size <= 1024 and "Transfer-Encoding" not in self.headers
                    self.original_body = body = self.rfile.read(size)
                    assert len(body) == size
                credentials, form = digest.check(supplied, method=self.command, target=self.path, body=body)
                if credentials == "correct":
                    assert form == ("authority" if operation == "connect" else "absolute")
                allowed = credentials == "correct"
                # HTTPServer encodes its header string as Latin-1. Preserve the actual UTF-8 octets.
                challenge = digest.challenge.encode("utf-8").decode("latin-1")
            else:
                valid = len(supplied) == 1 and hmac.compare_digest(supplied[0], expected)
                credentials = "correct" if valid else "incorrect" if supplied else "absent"
                allowed = ((name == "http-basic-connect-refused" and operation != "connect")
                           or (valid and name != "http-basic-other-scheme"))
                challenge = ('Digest realm="private, Basic realm", nonce="fixture", algorithm=unavailable'
                             if name == "http-basic-other-scheme" else 'Basic realm="fixture"')
            with self.server.lock:
                self.server.auth_attempts.append((operation, credentials, "allow" if allowed else "407"))
            if allowed:
                del self.headers["Proxy-Authorization"]
                return True
            self.close_connection = True
            self.body(b"", 407, {"Proxy-Authenticate": challenge, "Connection": "close"})
            return False
        def do_POST(self):
            if not hasattr(self, "original_body"):
                return super().do_POST()
            # Pass the exact bytes already read to verify auth-int to the ordinary origin handler.
            original_stream = self.rfile
            try:
                self.rfile = io.BytesIO(self.original_body)
                del self.original_body
                super().do_POST()
            finally:
                self.rfile = original_stream
    return AuthenticatedProxy

def check_http_auth_attempts(name, attempts, trace, stats):
    """Verify every observed retry and return whether the session was refused."""
    operations = {op for op, _, _ in attempts}
    if name == "http-basic-bypass":
        assert not attempts
        return False
    if name == "http-basic-connect-refused":
        assert operations == {"inventory", "pollingGET", "pollingPOST", "connect"}
        assert all((c, status) == ("absent", "allow") for o, c, status in attempts if o != "connect")
        assert [(c, status) for o, c, status in attempts if o == "connect"] == [
            ("absent", "407"), ("incorrect", "407")]
        assert not trace["Event"] and not stats["tunneledUpgrades"] and trace["Inventory"] >= 3
        assert trace["UpgradeDeclined Status(407)"] == 1
        return True
    refused = name.endswith("-refused") or name == "http-basic-other-scheme"
    step = [("absent", "407")]
    if refused:
        assert operations == {"inventory", "pollingGET"} and not stats["openingRequests"]
        assert not trace["Inventory"] and not trace["Event"] and not stats["tunneledUpgrades"]
        if name.endswith("-refused"):
            step.append(("incorrect", "407"))
    else:
        assert operations == {"inventory", "pollingGET", "pollingPOST", "connect"}
        step.append(("correct", "allow"))
    for operation in operations:
        observed = [(credentials, status) for op, credentials, status in attempts if op == operation]
        assert observed == step * (len(observed) // len(step))
    return refused
