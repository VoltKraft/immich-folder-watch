"""A loopback CONNECT observer serving one synthetic TLS origin on the accepted socket."""

from collections import Counter
from http.server import BaseHTTPRequestHandler
import ssl
import threading


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
                if self.path != tunnel.authority or self.headers.get_all("Host") != [tunnel.authority]:
                    tunnel.mark("rejectedAuthority")
                    self.send_error(403)
                    return
                if any(key in self.headers for key in ("x-api-key", "Authorization", "Proxy-Authorization", "Cookie")):
                    tunnel.mark("credentialHeaders")
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
