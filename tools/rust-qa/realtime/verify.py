"""Drive the real RW-02 client against independent HTTP/TLS/WebSocket wire fixtures."""

import argparse
import base64
from collections import Counter
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit


LIMIT = 4 * 1024 * 1024
SUBSCRIPTIONS = (
    "on_upload_success", "on_asset_trash", "on_asset_delete", "on_asset_update",
    "on_asset_restore", "on_album_create", "on_album_update", "on_album_delete", "on_album_invite",
)
# Input URL and independent network path observed with System.Uri in signed 3.0.4.
ESCAPED_PATHS = {
    "escaped-namespace": ("/%63ollection/caf%c3%a9/%7esummer%2fphotos/%61PI",
                          "/collection/caf%C3%A9/~summer%2fphotos/aPI"),
    "escaped-root-api": ("/%61pi", "/api"),
}
PEER_CLOSE_PATHS = {"peer-close-root": "/api", "peer-close-namespace": "/collection/api"}
PEER_CLOSE_REASON = b"synthetic maintenance"
DIRECT_RECONNECT = {"reconnect", "reconnect-namespace", "reconnect-refused", "reconnect-redirect", "reconnect-no-max-payload"}


PRE_ACK_REFUSALS = {"upgrade-redirect": "Status(302)", "upgrade-http-503": "Status(503)", "probe-refused": "Disconnected"}
BUFFERED_EVENT = {"websocket", "ack-after-upgrade", "stalled-probe", *PRE_ACK_REFUSALS}
WEBSOCKET_OFFER = {"websocket", "ws-size", "tls", "close-timeout", "ack-after-upgrade", "stalled-probe",
                   "server-disconnect-ws", "engine-close-ws", "peer-close-ws", *DIRECT_RECONNECT, *PRE_ACK_REFUSALS}


def send_frame(stream, opcode, data=b"", final=True):
    size = len(data)
    if size <= 125:
        length = bytes([size])
    elif size <= 65535:
        length = b"\x7e" + struct.pack("!H", size)
    else:
        length = b"\x7f" + struct.pack("!Q", size)
    stream.write(bytes([opcode | (128 if final else 0)]) + length + data)
    stream.flush()


def client_frame(stream):
    # The fixture only expects short, masked client control or heartbeat messages.
    first = stream.read(2)
    assert len(first) == 2 and first[0] & 128 and first[1] & 128, "expected a complete masked client frame"
    size = first[1] & 127
    assert size <= 125
    mask, data = stream.read(4), stream.read(size)
    assert len(mask) == 4 and len(data) == size
    return first[0] & 15, bytes(v ^ mask[i % 4] for i, v in enumerate(data))


def event(name, namespace="", event_id=""):
    return ("42" + namespace + event_id + json.dumps([name, {"asset": "synthetic"}])).encode()


class Peer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, scenario, namespace, api):
        super().__init__(("127.0.0.1", 0), Handler)
        self.scenario, self.ns, self.api = scenario, namespace, api
        self.counts = Counter()
        self.errors = []
        self.close_packets = []
        self.namespace_posts = []
        self.open_requests = []
        self.direct_joins = []
        self.stopping = threading.Event()
        self.queued = {}
        self.queued_on_join = []
        self.sent_on_promotion = []
        self.initial_refused = threading.Event()
        self.stalled_probe = threading.Event()
        self.peer_close_complete = threading.Event()
        self.tls_client_hello = threading.Event()
        self.lock = threading.Lock()
        self.polls = {}
        self.redirect_port = 0

    def mark(self, name):
        with self.lock:
            self.counts[name] += 1
            return self.counts[name]

    def open_packet(self, sid, upgrades, heartbeat_ms):
        fields = dict(sid=sid, upgrades=upgrades, pingInterval=heartbeat_ms, pingTimeout=heartbeat_ms)
        if self.scenario != "reconnect-no-max-payload":
            fields["maxPayload"] = LIMIT
        packet = "0" + json.dumps(fields)
        if self.open_requests:
            self.open_requests[-1]["engineOpen"] = fields
            if self.scenario == "reconnect-no-max-payload":
                self.open_requests[-1]["engineOpenPacket"] = packet
        return packet.encode("utf-8")

    def handle_error(self, request, address):
        import sys
        exc = sys.exception()
        if not isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            self.errors.append(repr(exc))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def parse_request(self):
        if not super().parse_request():
            return False
        self.server.mark("httpRequests")
        return True

    def log_message(self, *args):
        pass

    def body(self, data, status=200, headers=None):
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self):
        self.body(b"", 302, {"Location": f"http://127.0.0.1:{self.server.redirect_port}/other"})

    def routing(self):
        peer = self.server
        if peer.scenario == "redirect-destination":
            peer.mark("redirectTargetRequests")
            if self.headers.get("x-api-key"):
                peer.mark("redirectTargetCredentials")
            self.body(b"", 404)
            return None
        assert self.headers.get_all("x-api-key") == ["synthetic"], "one synthetic header required"
        url = urlsplit(self.path)
        if url.path == peer.api + "/albums":
            assert self.command == "GET" and not url.query
            peer.mark("inventoryRequests")
            if peer.peer_close_complete.is_set():
                peer.mark("inventoryAfterPeerClose")
            if peer.initial_refused.is_set():
                peer.mark("inventoryAfterUpgradeRefusal")
            if peer.stalled_probe.is_set():
                peer.mark("inventoryDuringStalledProbe")
            self.body(b"[]")
            return None
        assert url.path == "/socket.io/"
        query = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
        assert query.pop("EIO") == ["4"]
        transport, = query.pop("transport")
        sid, = query.pop("sid", [None])
        assert not query and transport in ("polling", "websocket") and sid != ""
        return transport, sid

    def do_POST(self):
        route = self.routing()
        if route is None:
            return
        transport, sid = route
        assert transport == "polling" and sid in self.server.polls
        size = int(self.headers.get("Content-Length", "0"))
        assert 0 < size < 256
        packet = self.rfile.read(size)
        if packet == ("40" + self.server.ns).encode():
            self.server.mark("namespacePosts")
            self.server.namespace_posts.append(packet.decode("ascii"))
            if self.server.scenario in WEBSOCKET_OFFER:
                queued = [("40" + self.server.ns + '{"sid":"promoted-namespace-id"}').encode()]
                if self.server.scenario in BUFFERED_EVENT:
                    queued.append(event("on_album_invite", self.server.ns))
                self.server.queued[sid] = queued
                self.server.queued_on_join.extend(p.decode() for p in queued)
        elif packet == b"3":
            self.server.mark("pollingPongs")
        elif packet == ("41" + self.server.ns).encode():
            self.server.mark("pollingDisconnects")
            self.server.close_packets.append({"httpPost": packet.decode("ascii")})
        else:
            raise AssertionError("unexpected polling POST")
        self.body(b"ok")

    def do_GET(self):
        route = self.routing()
        if route is None:
            return
        mode, sid = route
        peer = self.server
        if mode == "websocket" and sid is None:
            assert peer.scenario in DIRECT_RECONNECT and peer.counts["abruptWebsocketCloses"] == 1
            self.upgrade(sid)
        elif sid is None:
            assert mode == "polling"
            count = peer.mark("openingRequests")
            if peer.scenario == "redirect":
                self.redirect()
                return
            if peer.scenario == "opening-size":
                self.send_response(200)
                self.send_header("Content-Length", str(LIMIT + 1))
                self.end_headers()
                self.close_connection = True
                return
            sid = f"synthetic-{count}"
            peer.polls[sid] = 0
            if peer.scenario in DIRECT_RECONNECT or peer.scenario == "reconnect-polling":
                peer.open_requests.append({"path": self.path, "status": 200, "sid": sid})
            upgrade = peer.scenario in WEBSOCKET_OFFER
            heartbeat_timeout = {"missed-heartbeat": 150, "server-disconnect-ws": 550}.get(peer.scenario, 3000)
            self.body(peer.open_packet(sid, ["websocket"] if upgrade else [], heartbeat_timeout))
        elif mode == "websocket":
            assert sid in peer.polls
            self.upgrade(sid)
        else:
            assert sid in peer.polls
            self.poll(sid)

    def poll(self, sid):
        peer = self.server
        peer.polls[sid] += 1
        number = peer.polls[sid]
        peer.mark("sidPollingGets")
        if sid in peer.queued:
            # An older client can collect the queued ACK and event on HTTP.
            # The native pre-admission trial requires both to stay queued until the switch.
            self.body(b"\x1e".join(peer.queued.pop(sid)))
        elif number == 1 and peer.scenario == "stop-before-ack":
            peer.mark("pendingNamespaceAcks")
            peer.stopping.wait(6)
            self.close_connection = True
        elif number == 1:
            ack = ("40" + peer.ns + '{"sid":"separate-socket-id"}').encode()
            self.body(ack)
        elif peer.scenario == "poll-size" and number == 2:
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in [b"6" * 65536] * (LIMIT // 65536) + [b"x"]:
                self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        elif number == 2 and peer.scenario == "polling":
            # Wrong namespace and unknown names must never cause refresh.
            contents = [event("on_album_update", "/other,"), event("unsubscribed", peer.ns), b"2"]
            contents += [event(name, peer.ns) for name in SUBSCRIPTIONS]
            self.body(b"\x1e".join(contents))
        elif number == 2 and peer.scenario == "exact-size":
            prefix = b'42["on_album_update","'
            self.body(prefix + b"a" * (LIMIT - len(prefix) - 2) + b'"]')
        elif number == 2 and peer.scenario in {"server-disconnect-poll", "server-disconnect-then-close"}:
            packets = [b"41/other,", event("on_album_update", peer.ns), ("41" + peer.ns).encode(),
                       event("on_album_delete", peer.ns), b"2"]
            peer.mark("serverDisconnects")
            self.body(b"\x1e".join(packets))
        elif number == 3 and peer.scenario == "server-disconnect-then-close":
            peer.mark("retiredPollingSessions")
            self.body(b'{"code":1,"message":"Session ID unknown"}', status=400)
        elif number == 2 and peer.scenario == "engine-close-poll":
            peer.mark("engineCloseNotices")
            self.body(b"\x1e".join([b"1", event("on_album_update", peer.ns), b"2"]))
        elif number == 2 and peer.scenario == "reconnect-polling":
            self.body(event("on_album_update" if sid == "synthetic-1" else "on_album_delete", peer.ns))
        elif number == 3 and peer.scenario == "reconnect-polling" and sid == "synthetic-1":
            peer.mark("retiredPollingSessions")
            self.body(b'{"code":1,"message":"Session ID unknown"}', status=400)
        else:
            peer.mark("pendingPolls")
            peer.stopping.wait(6)
            self.close_connection = True

    def upgrade(self, sid):
        peer = self.server
        direct = sid is None
        peer.mark("websocketRequests")
        if peer.scenario == "upgrade-redirect":
            self.redirect()
            peer.initial_refused.set()
            return
        if peer.scenario == "upgrade-http-503":
            self.body(b"unavailable", 503)
            peer.initial_refused.set()
            return
        assert self.headers["Upgrade"].lower() == "websocket"
        assert self.headers["Sec-WebSocket-Version"] == "13"
        key = self.headers["Sec-WebSocket-Key"]
        assert len(base64.b64decode(key, validate=True)) == 16
        if direct:
            attempt = peer.mark("directWebsocketRequests")
            status = {"reconnect-refused": 503, "reconnect-redirect": 302}.get(peer.scenario, 101) if attempt == 1 else 101
            peer.open_requests.append({"path": self.path, "status": status})
            if status == 302:
                self.redirect()
                return
            if status == 503:
                self.body(b"unavailable", status)
                return
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        self.send_response(101)
        self.send_header("Connection", "Upgrade")
        self.send_header("Upgrade", "websocket")
        self.send_header("Sec-WebSocket-Accept", accept.decode())
        self.end_headers()
        self.close_connection = True
        self.connection.settimeout(5)
        if direct:
            offers = []
            if peer.scenario == "reconnect-namespace":
                send_frame(self.wfile, 9, b"before-direct-open")
                assert client_frame(self.rfile) == (10, b"before-direct-open")
                peer.mark("directPreOpenPongs")
                offers = ["websocket"]
            send_frame(self.wfile, 1, peer.open_packet("synthetic-direct", offers, 3000))
            opcode, join = client_frame(self.rfile)
            assert (opcode, join) == (1, ("40" + peer.ns).encode()), "expected a direct masked namespace join"
            peer.direct_joins.append(join.decode("ascii"))
            peer.mark("directSessions")
            send_frame(self.wfile, 1, ("40" + peer.ns + '{"sid":"direct-namespace-id"}').encode())
        elif not self.probe_upgrade(sid):
            return
        self.websocket_session(direct)

    def probe_upgrade(self, sid):
        peer = self.server
        assert client_frame(self.rfile) == (1, b"2probe")
        peer.mark("probes")
        if peer.scenario == "probe-refused":
            send_frame(self.wfile, 8, struct.pack("!H", 1000))
            peer.initial_refused.set()
            return False
        if peer.scenario == "stalled-probe":
            peer.stalled_probe.set()
            peer.stopping.wait(6)
            return False
        send_frame(self.wfile, 1, b"3probe")
        assert client_frame(self.rfile) == (1, b"5")
        peer.mark("upgrades")
        for packet in peer.queued.pop(sid, []):
            send_frame(self.wfile, 1, packet)
            peer.sent_on_promotion.append(packet.decode())
        return True

    def websocket_session(self, direct):
        peer = self.server
        if peer.scenario == "ws-size":
            send_frame(self.wfile, 1, b'a' * (LIMIT // 2), final=False)
            send_frame(self.wfile, 0, b'b' * (LIMIT // 2 + 1))
            return
        send_frame(self.wfile, 9, b"wire-ping")
        assert client_frame(self.rfile) == (10, b"wire-ping")
        peer.mark("websocketPongs")
        send_frame(self.wfile, 1, b"2")
        assert client_frame(self.rfile) == (1, b"3")
        peer.mark("enginePongs")
        if peer.scenario == "engine-close-ws":
            send_frame(self.wfile, 1, b"1")
            peer.mark("engineCloseNotices")
        payload = event("on_album_delete" if direct else "on_album_update", peer.ns, "7")
        send_frame(self.wfile, 1, payload[:8], final=False)
        send_frame(self.wfile, 0, payload[8:])
        send_frame(self.wfile, 1, event("unsubscribed", peer.ns))
        if peer.scenario == "peer-close-ws":
            close = struct.pack("!H", 1001) + PEER_CLOSE_REASON
            send_frame(self.wfile, 8, close)
            peer.mark("peerCloseRequests")
            opcode, echo = client_frame(self.rfile)
            assert (opcode, echo) == (8, close), "expected the masked echo of the peer close"
            peer.close_packets.append({"websocketCloseCode": int.from_bytes(echo[:2], "big"),
                                       "reason": echo[2:].decode("utf-8")})
            self.connection.shutdown(socket.SHUT_WR)
            assert self.rfile.read(1) == b"", "unexpected client bytes after the close reply"
            peer.peer_close_complete.set()
            return
        if peer.scenario in DIRECT_RECONNECT and not direct:
            peer.mark("abruptWebsocketCloses")
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        if peer.scenario == "server-disconnect-ws":
            detached_at = time.monotonic()
            send_frame(self.wfile, 1, ("41" + peer.ns).encode())
            send_frame(self.wfile, 1, event("on_album_delete", peer.ns))
            send_frame(self.wfile, 1, b"2")
            peer.mark("serverDisconnects")
        opcode, packet = client_frame(self.rfile)
        assert (opcode, packet) == (1, ("41" + peer.ns).encode())
        if peer.scenario == "server-disconnect-ws":
            peer.counts["detachedUntilStopMs"] = int((time.monotonic() - detached_at) * 1000)
        peer.close_packets.append({"websocketText": packet.decode("ascii")})
        peer.mark("websocketDisconnects")
        normal = struct.pack("!H", 1000)
        opcode, close = client_frame(self.rfile)
        assert (opcode, close) == (8, normal + b"io client disconnect")
        peer.close_packets.append({"websocketCloseCode": int.from_bytes(close[:2], "big"),
                                   "reason": close[2:].decode("utf-8")})
        peer.mark("normalCloseFrames")
        if peer.scenario == "close-timeout":
            peer.stopping.wait(6)
        else:
            peer.mark("normalCloseReplies")
            send_frame(self.wfile, 8, normal)


@contextmanager
def peer(scenario, api="/api", tls=None):
    prefix = api.rsplit("/", 1)[0]
    instance = Peer(scenario, prefix + "," if prefix else "", api)
    if tls is not None:
        def observe_client_hello(connection, server_name, context):
            instance.tls_client_hello.set()

        tls.set_servername_callback(observe_client_hello)
        instance.socket = tls.wrap_socket(instance.socket, server_side=True)
    worker = threading.Thread(target=instance.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    worker.start()
    try:
        yield instance
    finally:
        instance.stopping.set()
        instance.shutdown()
        instance.server_close()
        worker.join(2)
        if tls is not None:
            tls.set_servername_callback(None)


def make_trust(directory):
    openssl = shutil.which("openssl")
    if not openssl and os.name == "nt":
        git_copy = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/openssl.exe"
        if git_copy.is_file():
            openssl = str(git_copy)
    if not openssl:
        raise RuntimeError("OpenSSL CLI is required to create ephemeral synthetic TLS certificates")
    def run(*args, check=True):
        return subprocess.run([openssl, *args], cwd=directory, env={**os.environ, "OPENSSL_CONF": str(config)},
                              check=check, capture_output=True, timeout=30)
    # Configure from scratch so the fixture never reads host OpenSSL settings.
    config = directory / "test.conf"
    config.write_text("[req]\ndistinguished_name=dn\n[dn]\n", encoding="ascii")
    for label in ("ca", "other"):
        run("req", "-config", str(config), "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "1",
            "-subj", "/CN=RW02-" + label, "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", label + ".key", "-out", label + ".crt")
    run("req", "-config", str(config), "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=RW02-loopback",
        "-keyout", "peer.key", "-out", "peer.csr")
    contexts, certificates = {}, {}
    for serial, address in enumerate(("127.0.0.1", "127.0.0.2"), start=3):
        ext = directory / "peer.ext"
        ext.write_text(f"basicConstraints=critical,CA:FALSE\nsubjectAltName=IP:{address}\nextendedKeyUsage=serverAuth\n",
                       encoding="ascii")
        leaf = directory / f"peer-{serial}.crt"
        run("x509", "-req", "-sha256", "-days", "1", "-in", "peer.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
            "-set_serial", str(serial), "-extfile", str(ext), "-out", str(leaf))
        verify = ("verify", "-CAfile", "ca.crt", "-purpose", "sslserver", "-verify_ip")
        run(*verify, address, str(leaf))
        if address != "127.0.0.1" and run(*verify, "127.0.0.1", str(leaf), check=False).returncode == 0:
            raise ValueError("The different-address certificate unexpectedly names the fixture endpoint")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(leaf, directory / "peer.key")
        contexts[address] = context
        certificates[address] = hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf.read_text("ascii"))).hexdigest()
    return contexts, certificates


def run_scenario(executable, name, directory, contexts, redirect):
    rejected_tls = name in {"untrusted-tls", "wrong-host-tls"}
    encrypted = rejected_tls or name in {"tls", "upgrade-redirect", "reconnect-redirect"}
    certificate_address = "127.0.0.2" if name == "wrong-host-tls" else "127.0.0.1"
    api = "/collection/api" if name in {"polling", "tls", "ack-after-upgrade", "server-disconnect-poll",
                                        "reconnect-namespace", "reconnect-no-max-payload"} else "/api"
    api = PEER_CLOSE_PATHS.get(name, api)
    input_path, api = ESCAPED_PATHS.get(name, (api, api))
    scenario = "polling" if name in ESCAPED_PATHS else name
    if name in PEER_CLOSE_PATHS:
        scenario = "peer-close-ws"
    with peer(scenario, api, contexts[certificate_address] if encrypted else None) as origin:
        origin.redirect_port = redirect.server_port
        protocol = "https" if encrypted else "http"
        url = f"{protocol}://127.0.0.1:{origin.server_port}{input_path}"
        trust = directory / ("other.crt" if name == "untrusted-tls" else "ca.crt")
        mode = "https" if encrypted or name == "http-default" else "allow-http"
        budget = 1300 if scenario in {"tls", "reconnect", "exact-size", "ws-size", "poll-size", "peer-close-ws"} else 850
        reconnecting = name in DIRECT_RECONNECT or name == "reconnect-polling"
        if name in {"stalled-probe", "server-disconnect-ws"} or reconnecting:
            budget = 1750
        retry = 130 if reconnecting or name in PRE_ACK_REFUSALS or name in {"stalled-probe", "peer-close-ws"} or name.startswith(("server-disconnect-", "engine-close-")) else 30_000
        before = time.monotonic()
        proc = subprocess.run([str(executable), url, mode, str(trust), str(budget), str(retry), "100"],
                              cwd=directory, text=True, capture_output=True, timeout=10)
        elapsed = round((time.monotonic() - before) * 1000)
        events = proc.stdout.splitlines()
        trace = Counter(events)
        stats = origin.counts.copy()
        if encrypted:
            assert origin.tls_client_hello.is_set(), "The loopback TLS server never received a ClientHello"
        if name == "http-default":
            assert proc.returncode != 0 and proc.stderr.strip() == "Origin" and not stats, (events, stats, proc.stderr)
        else:
            assert proc.returncode == 0 and not proc.stderr and events[-1:] == ["Stopped"], (events, stats, proc.stderr)
            close_wait = 2000 if name == "close-timeout" else 0
            assert budget + close_wait - 50 <= elapsed < budget + close_wait + 2000, (budget, elapsed)
            assert trace["Attempt"] == (1 if rejected_tls else stats["openingRequests"] + stats["directWebsocketRequests"]), (events, stats)
            assert trace["Periodic"] >= 1
            if rejected_tls:
                assert trace["Lost Transport"] == 1 and not stats and not trace["Connected"], (events, stats)
            else:
                assert stats["inventoryRequests"] >= 1 and trace["Inventory"] >= 1, (events, stats)
            check_protocol(scenario, trace, stats, events)
        assert not origin.errors, origin.errors
        result = {"client": dict(trace), "peer": dict(stats), "closePacketsAtPeer": origin.close_packets.copy(),
                  "budgetMs": budget, "processElapsedMs": elapsed}
        if scenario in WEBSOCKET_OFFER:
            ack = "40" + origin.ns + '{"sid":"promoted-namespace-id"}'
            queued = [ack, event("on_album_invite", origin.ns).decode()] if scenario in BUFFERED_EVENT else [ack]
            assert origin.queued_on_join == queued, (name, origin.queued_on_join)
            refused = scenario in PRE_ACK_REFUSALS or scenario == "stalled-probe"
            assert origin.sent_on_promotion == ([] if refused else queued), (name, origin.sent_on_promotion)
            assert stats["sidPollingGets"] == 0, (name, stats)
            result.update(queuedAtNamespaceJoin=origin.queued_on_join.copy(), sentAfterEngineUpgrade=origin.sent_on_promotion.copy())
            if refused:
                assert origin.queued == {"synthetic-1": [packet.encode() for packet in queued]}
                assert elapsed < budget + 1500, (elapsed, stats)
        if name in ESCAPED_PATHS or name in PEER_CLOSE_PATHS:
            assert origin.namespace_posts == ["40" + origin.ns], origin.namespace_posts
            result.update(configuredPath=input_path, inventoryPathAtPeer=api + "/albums",
                          namespacePostsAtPeer=origin.namespace_posts.copy())
        if name in PEER_CLOSE_PATHS:
            assert origin.close_packets == [{"websocketCloseCode": 1001, "reason": PEER_CLOSE_REASON.decode("ascii")}]
            assert origin.peer_close_complete.is_set() and elapsed < budget + 1500, (elapsed, stats)
        if reconnecting:
            direct = name in DIRECT_RECONNECT
            assert origin.namespace_posts == ["40" + origin.ns] * (1 if direct else 2)
            assert origin.direct_joins == (["40" + origin.ns] if direct else [])
            statuses = [200, 200]
            if direct:
                refusal = {"reconnect-refused": [503], "reconnect-redirect": [302]}.get(name, [])
                statuses = [200, *refusal, 101]
            assert [request["status"] for request in origin.open_requests] == statuses
            if name == "reconnect-no-max-payload":
                for request, sid, offers in zip(origin.open_requests, ("synthetic-1", "synthetic-direct"),
                                                (["websocket"], []), strict=True):
                    packet = request["engineOpenPacket"]
                    assert packet.startswith("0") and json.loads(packet[1:]) == request["engineOpen"] == {
                        "sid": sid, "upgrades": offers, "pingInterval": 3000, "pingTimeout": 3000}
            expected_close = ([{"websocketText": "41" + origin.ns}, {"websocketCloseCode": 1000, "reason": "io client disconnect"}]
                              if direct else [{"httpPost": "41" + origin.ns}])
            assert origin.close_packets == expected_close
            result.update(openRequestsAtPeer=origin.open_requests.copy(), directNamespaceJoinsAtPeer=origin.direct_joins.copy(),
                          namespacePostsAtPeer=origin.namespace_posts.copy(), inventoryPathAtPeer=api + "/albums")
        if encrypted:
            result.update(tlsClientHelloObserved=True, certificateAddress=certificate_address,
                          endpointAddress="127.0.0.1", httpRequests=stats["httpRequests"],
                          trustAnchorDerSha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(trust.read_text("ascii"))).hexdigest())
        return result


def check_protocol(name, trace, stats, events):
    polling_at_stop = name in {"polling", "exact-size", "cancel-poll", "server-disconnect-poll", "engine-close-poll", "reconnect-polling"}
    websocket_at_stop = name in DIRECT_RECONNECT or name in {"websocket", "tls", "close-timeout", "ack-after-upgrade",
                                                             "server-disconnect-ws", "engine-close-ws"}
    assert stats["pollingDisconnects"] == int(polling_at_stop), (events, stats)
    assert stats["websocketDisconnects"] == stats["normalCloseFrames"] == int(websocket_at_stop), (events, stats)
    assert stats["normalCloseReplies"] == int(websocket_at_stop and name != "close-timeout"), (events, stats)
    assert [e for e in events if e.startswith("StopFailed")] == (["StopFailed Timeout"] if name == "close-timeout" else [])
    if name == "stop-before-ack":
        assert stats["pendingNamespaceAcks"] == stats["namespacePosts"] == 1 and not trace["Connected"], (events, stats)
    if name in PRE_ACK_REFUSALS or name == "stalled-probe":
        assert stats["openingRequests"] == stats["namespacePosts"] == stats["websocketRequests"] == trace["Attempt"] == 1
        assert stats["probes"] == int(name in {"probe-refused", "stalled-probe"}), (events, stats)
        assert not any(trace[k] for k in ("Connected", "Event", "Heartbeat", "Upgraded", "DirectWebSocket")), events
        assert not any(e.startswith("Lost ") for e in events), events
        declined = [e for e in events if e.startswith("UpgradeDeclined ")]
        if name == "stalled-probe":
            assert not declined and stats["inventoryDuringStalledProbe"] >= 3, (events, stats)
        else:
            assert declined == ["UpgradeDeclined " + PRE_ACK_REFUSALS[name]], events
            after_decline = events[events.index(declined[0]) + 1:]
            assert after_decline.count("Periodic") >= 3 and after_decline.count("Inventory") >= 3
            assert stats["inventoryAfterUpgradeRefusal"] >= 3, (events, stats)
    if name in {"opening-size", "poll-size", "ws-size"}:
        assert trace["Lost Limit"] == 1 and not trace["Event"], (events, stats)
    if name == "redirect":
        assert trace["Lost Status(302)"] == 1, events
    if websocket_at_stop or name == "ws-size":
        assert stats["probes"] == stats["upgrades"] == trace["Upgraded"] and stats["upgrades"] >= 1, (events, stats)
    if websocket_at_stop:
        sessions = stats["upgrades"] + stats["directSessions"]
        assert stats["websocketPongs"] == stats["enginePongs"] == sessions, (events, stats)
        assert stats["enginePongs"] + stats["pollingPongs"] == trace["Heartbeat"], (events, stats)
        assert trace["Event"] == sessions + int(name in BUFFERED_EVENT), (events, stats)
        assert events.index("Upgraded") < events.index("Connected") < events.index("Event"), events
        if name in {"websocket", "ack-after-upgrade"}:
            # The queued event precedes the ordinary ping and second event.
            assert events.index("Event") < events.index("Heartbeat") < len(events) - 1 - events[::-1].index("Event")
    if name in DIRECT_RECONNECT:
        assert stats["openingRequests"] == stats["upgrades"] == stats["abruptWebsocketCloses"] == 1, (events, stats)
        assert stats["directSessions"] == trace["DirectWebSocket"] == 1 and trace["Connected"] == trace["Event"] == 2
        assert stats["directPreOpenPongs"] == int(name == "reconnect-namespace"), (events, stats)
        # The WSS peer closes TCP without a TLS close_notify or a WebSocket Close.
        losses = ["Lost Transport" if name == "reconnect-redirect" else "Lost Disconnected"]
        losses += {"reconnect-refused": ["Lost Status(503)"], "reconnect-redirect": ["Lost Status(302)"]}.get(name, [])
        assert [e for e in events if e.startswith("Lost ")] == losses, (events, stats)
        assert events.index("Event") < events.index(losses[0]) <= events.index(losses[-1]) < events.index("DirectWebSocket")
        later = events[events.index("DirectWebSocket") + 1:]
        assert later.index("Connected") < later.index("Event") < later.index("Stopped")
    if name == "reconnect-polling":
        assert stats["retiredPollingSessions"] == trace["Lost Status(400)"] == 1 and stats["openingRequests"] == 2
        assert trace["Connected"] == trace["Event"] == 2 and not stats["websocketRequests"] and not trace["DirectWebSocket"]
        loss = events.index("Lost Status(400)")
        assert events.index("Event") < loss and events[loss + 1:].index("Connected") < events[loss + 1:].index("Event")
    if name == "peer-close-ws":
        assert stats["peerCloseRequests"] == stats["probes"] == stats["upgrades"] == trace["Upgraded"] == 1, (events, stats)
        assert trace["Attempt"] == stats["openingRequests"] == trace["Connected"] == trace["Event"] == trace["PeerClosed"] == 1
        assert events.index("Upgraded") < events.index("Connected") < events.index("Event") < events.index("PeerClosed")
        assert not any(e.startswith("Lost ") for e in events) and not trace["ServerDisconnected"], events
        after_close = events[events.index("PeerClosed") + 1:]
        assert after_close.count("Periodic") >= 3 and after_close.count("Inventory") >= 3
        assert stats["inventoryAfterPeerClose"] >= 3, (events, stats)
    if name.startswith("engine-close-"):
        assert stats["engineCloseNotices"] == trace["Event"] == trace["Connected"] == trace["Attempt"] == 1, (events, stats)
        assert not trace["ServerDisconnected"] and not any(e.startswith("Lost ") for e in events), events
    if name.startswith("server-disconnect-"):
        assert trace["Attempt"] == stats["openingRequests"] == trace["Connected"] == 1, (events, stats)
        assert trace["Event"] == trace["ServerDisconnected"] == stats["serverDisconnects"] == 1, (events, stats)
        detached = events.index("ServerDisconnected")
        assert events.index("Event") < detached and "Periodic" in events[detached:] and "Inventory" in events[detached:]
        assert stats["retiredPollingSessions"] == trace["Lost Status(400)"] == int(name == "server-disconnect-then-close")
        if name == "server-disconnect-then-close":
            after_loss = events[events.index("Lost Status(400)") + 1:]
            assert after_loss.count("Periodic") >= 3 and "Inventory" in after_loss, (events, stats)
        if name == "server-disconnect-ws":
            assert stats["detachedUntilStopMs"] > 1100, (events, stats)
        else:
            assert stats["pollingPongs"] == trace["Heartbeat"] == 1, (events, stats)
    if name == "polling":
        assert trace["Event"] == len(SUBSCRIPTIONS) and stats["pollingPongs"] == 1 and stats["pendingPolls"] == 1
    if name == "exact-size":
        assert trace["Event"] == 1 and stats["pendingPolls"] == 1, (events, stats)
    if name == "cancel-poll":
        assert stats["pendingPolls"] == 1 and trace["Attempt"] == 1 and not trace["Event"], (events, stats)
    if name == "missed-heartbeat":
        assert trace["Lost Timeout"] == 1 and stats["pendingPolls"] == 1, (events, stats)
    if name not in {"untrusted-tls", "wrong-host-tls", "opening-size", "redirect", "stop-before-ack", "stalled-probe", *PRE_ACK_REFUSALS}:
        assert stats["namespacePosts"] + stats["directSessions"] == trace["Connected"] >= 1, (events, stats)
    if name in {"redirect", "opening-size", "missed-heartbeat", "poll-size", "ws-size"}:
        after_loss = events[next(i for i, e in enumerate(events) if e.startswith("Lost ")) + 1:]
        assert "Periodic" in after_loss and "Inventory" in after_loss and trace["Attempt"] == 1, (events, stats)


def main():
    if not __debug__:
        raise RuntimeError("Python assertions must be enabled for the wire checks")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    executable = args.probe.resolve(strict=True)
    cases = ("polling", "websocket", "tls", "untrusted-tls", "wrong-host-tls", "http-default", "upgrade-redirect",
             "probe-refused", "upgrade-http-503", "redirect", "exact-size", "opening-size", "poll-size", "ws-size",
             "reconnect", "reconnect-namespace", "reconnect-refused", "reconnect-redirect", "reconnect-polling",
             "reconnect-no-max-payload",
             "cancel-poll", "missed-heartbeat", "stop-before-ack", "close-timeout", "ack-after-upgrade",
             "stalled-probe", "server-disconnect-poll", "server-disconnect-ws", "server-disconnect-then-close",
             "engine-close-poll", "engine-close-ws", *PEER_CLOSE_PATHS, *ESCAPED_PATHS)
    with executable.open("rb") as stream:
        probe_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
              "probeSha256": probe_sha, "cases": {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ifw-rw02-") as temp, peer("redirect-destination") as redirect:
        directory = Path(temp)
        contexts, result["certificateDerSha256ByAddress"] = make_trust(directory)
        for case in cases:
            try:
                result["cases"][case] = run_scenario(executable, case, directory, contexts, redirect)
                print("Passed " + case, flush=True)
            except Exception as error:
                result["failure"] = {"case": case, "error": repr(error)}
                raise
            finally:
                result["redirectTargetRequests"] = redirect.counts["redirectTargetRequests"]
                result["redirectTargetCredentials"] = redirect.counts["redirectTargetCredentials"]
                args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            assert not redirect.counts and not redirect.errors, (redirect.counts, redirect.errors)


if __name__ == "__main__":
    main()
