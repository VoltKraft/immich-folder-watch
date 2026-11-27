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
        self.stopping = threading.Event()
        self.poll_started = threading.Event()
        self.probe_answered = threading.Event()
        self.held_poll_released = threading.Event()
        self.upgrade_committed = threading.Event()
        self.tls_client_hello = threading.Event()
        self.lock = threading.Lock()
        self.polls = {}
        self.redirect_port = 0

    def mark(self, name):
        with self.lock:
            self.counts[name] += 1
            return self.counts[name]

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
            self.body(b"[]")
            return None
        assert url.path == "/socket.io/"
        query = parse_qs(url.query, strict_parsing=True)
        assert query.pop("EIO") == ["4"]
        transport, sid = query.pop("transport")[0], query.pop("sid", [None])[0]
        assert not query and transport in ("polling", "websocket")
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
        elif packet == b"3":
            self.server.mark("pollingPongs")
            if self.server.scenario == "ack-after-upgrade":
                assert not self.server.upgrade_committed.wait(0.15), "upgrade overtook a pending polling POST"
                self.server.mark("releasedPollingPongs")
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
        if sid is None:
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
            upgrade = peer.scenario in {"websocket", "ws-size", "upgrade-redirect", "probe-refused", "tls", "reconnect",
                                        "close-timeout", "ack-after-upgrade", "stalled-probe"}
            heartbeat_timeout = {"missed-heartbeat": 150, "stalled-probe": 400}.get(peer.scenario, 3000)
            handshake = dict(sid=sid, upgrades=["websocket"] if upgrade else [],
                             pingInterval=heartbeat_timeout, pingTimeout=heartbeat_timeout, maxPayload=LIMIT)
            self.body(b"0" + json.dumps(handshake).encode())
        elif mode == "websocket":
            assert sid in peer.polls
            self.upgrade()
        else:
            assert sid in peer.polls
            self.poll(sid)

    def poll(self, sid):
        peer = self.server
        peer.polls[sid] += 1
        number = peer.polls[sid]
        if peer.scenario == "stalled-probe":
            if number == 1:
                self.body(b"6")
            elif number == 2:
                self.body(("40" + peer.ns + '{"sid":"polling-namespace-id"}').encode())
            elif number == 3:
                self.body(event("on_album_update", peer.ns))
            else:
                time.sleep(0.12)
                self.body(b"2")
        elif peer.scenario == "ack-after-upgrade":
            if number == 1:
                peer.poll_started.set()
                assert peer.probe_answered.wait(4), "client waited for a polling namespace ACK before probing"
                peer.held_poll_released.set()
                self.body(b"2\x1e6")
            else:
                assert peer.held_poll_released.is_set(), "overlapping polling GETs"
                self.body(b"6")
        elif number == 1 and peer.scenario == "stop-before-ack":
            peer.mark("pendingNamespaceAcks")
            peer.stopping.wait(6)
            self.close_connection = True
        elif number == 1:
            ack = ("40" + peer.ns + '{"sid":"separate-socket-id"}').encode()
            if peer.scenario == "websocket":
                self.body(ack + b"\x1e" + event("on_album_invite", peer.ns))
            else:
                self.body(ack)
        elif peer.scenario == "poll-size" and number == 2:
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in [b"6" * 65536] * (LIMIT // 65536) + [b"x"]:
                self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        elif number == 2 and peer.scenario in {"polling", "upgrade-redirect", "probe-refused"}:
            # Wrong namespace and unknown names must never cause refresh.
            contents = [event("on_album_update", "/other,"), event("unsubscribed", peer.ns), b"2"]
            contents += [event(name, peer.ns) for name in SUBSCRIPTIONS]
            self.body(b"\x1e".join(contents))
        elif number == 2 and peer.scenario == "exact-size":
            prefix = b'42["on_album_update","'
            self.body(prefix + b"a" * (LIMIT - len(prefix) - 2) + b'"]')
        elif peer.scenario in {"websocket", "tls", "ws-size", "reconnect", "close-timeout"}:
            assert peer.probe_answered.wait(4), "websocket did not complete its probe"
            self.body(b"6")
        else:
            peer.mark("pendingPolls")
            peer.stopping.wait(6)
            self.close_connection = True

    def upgrade(self):
        peer = self.server
        peer.mark("websocketRequests")
        if peer.scenario == "upgrade-redirect":
            self.redirect()
            return
        assert self.headers["Upgrade"].lower() == "websocket"
        assert self.headers["Sec-WebSocket-Version"] == "13"
        key = self.headers["Sec-WebSocket-Key"]
        assert len(base64.b64decode(key, validate=True)) == 16
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        self.send_response(101)
        self.send_header("Connection", "Upgrade")
        self.send_header("Upgrade", "websocket")
        self.send_header("Sec-WebSocket-Accept", accept.decode())
        self.end_headers()
        self.close_connection = True
        self.connection.settimeout(5)
        assert client_frame(self.rfile) == (1, b"2probe")
        peer.mark("probes")
        if peer.scenario == "probe-refused":
            send_frame(self.wfile, 8, struct.pack("!H", 1000))
            return
        if peer.scenario == "stalled-probe":
            peer.stopping.wait(6)
            return
        if peer.scenario == "ack-after-upgrade":
            assert peer.poll_started.wait(4), "expected the active namespace poll"
        send_frame(self.wfile, 1, b"3probe")
        peer.probe_answered.set()
        assert client_frame(self.rfile) == (1, b"5")
        peer.mark("upgrades")
        if peer.scenario == "ack-after-upgrade":
            peer.upgrade_committed.set()
            assert peer.counts["releasedPollingPongs"] == 1, "upgrade overtook the polling heartbeat reply"
            send_frame(self.wfile, 1, ("40" + peer.ns + '{"sid":"websocket-namespace-id"}').encode())
            peer.mark("websocketNamespaceAcks")
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
        payload = event("on_album_update", peer.ns, "7")
        send_frame(self.wfile, 1, payload[:8], final=False)
        send_frame(self.wfile, 0, payload[8:])
        send_frame(self.wfile, 1, event("unsubscribed", peer.ns))
        if peer.scenario == "reconnect" and peer.counts["upgrades"] == 1:
            send_frame(self.wfile, 1, b"1")
            return
        opcode, packet = client_frame(self.rfile)
        assert (opcode, packet) == (1, ("41" + peer.ns).encode())
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
    encrypted = rejected_tls or name in {"tls", "upgrade-redirect"}
    certificate_address = "127.0.0.2" if name == "wrong-host-tls" else "127.0.0.1"
    api = "/collection/api" if name in {"polling", "tls", "ack-after-upgrade"} else "/api"
    input_path, api = ESCAPED_PATHS.get(name, (api, api))
    scenario = "polling" if name in ESCAPED_PATHS else name
    with peer(scenario, api, contexts[certificate_address] if encrypted else None) as origin:
        origin.redirect_port = redirect.server_port
        protocol = "https" if encrypted else "http"
        url = f"{protocol}://127.0.0.1:{origin.server_port}{input_path}"
        trust = directory / ("other.crt" if name == "untrusted-tls" else "ca.crt")
        mode = "https" if encrypted or name == "http-default" else "allow-http"
        budget = 1300 if name in {"tls", "reconnect", "exact-size", "ws-size", "poll-size"} else 850
        if name == "stalled-probe":
            budget = 1750
        retry = 130 if name == "reconnect" else 30_000
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
            assert trace["Attempt"] == (1 if rejected_tls else stats["openingRequests"]), (events, stats)
            assert trace["Periodic"] >= 1
            if rejected_tls:
                assert trace["Lost Transport"] == 1 and not stats and not trace["Connected"], (events, stats)
            else:
                assert stats["inventoryRequests"] >= 1 and trace["Inventory"] >= 1, (events, stats)
            check_protocol(scenario, trace, stats, events)
        assert not origin.errors, origin.errors
        result = {"client": dict(trace), "peer": dict(stats), "closePacketsAtPeer": origin.close_packets.copy(),
                  "budgetMs": budget, "processElapsedMs": elapsed}
        if name in ESCAPED_PATHS:
            assert origin.namespace_posts == ["40" + origin.ns], origin.namespace_posts
            result.update(configuredPath=input_path, inventoryPathAtPeer=api + "/albums",
                          namespacePostsAtPeer=origin.namespace_posts.copy())
        if encrypted:
            result.update(tlsClientHelloObserved=True, certificateAddress=certificate_address,
                          endpointAddress="127.0.0.1", httpRequests=stats["httpRequests"],
                          trustAnchorDerSha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(trust.read_text("ascii"))).hexdigest())
        return result


def check_protocol(name, trace, stats, events):
    polling_at_stop = name in {"polling", "upgrade-redirect", "probe-refused", "exact-size", "cancel-poll", "stalled-probe"}
    websocket_at_stop = name in {"websocket", "tls", "reconnect", "close-timeout", "ack-after-upgrade"}
    assert stats["pollingDisconnects"] == int(polling_at_stop), (events, stats)
    assert stats["websocketDisconnects"] == stats["normalCloseFrames"] == int(websocket_at_stop), (events, stats)
    assert stats["normalCloseReplies"] == int(websocket_at_stop and name != "close-timeout"), (events, stats)
    assert [e for e in events if e.startswith("StopFailed")] == (["StopFailed Timeout"] if name == "close-timeout" else [])
    if name == "stop-before-ack":
        assert stats["pendingNamespaceAcks"] == stats["namespacePosts"] == 1 and not trace["Connected"], (events, stats)
    if name == "stalled-probe":
        assert stats["probes"] == trace["Connected"] == trace["Event"] == 1, (events, stats)
        assert stats["pollingPongs"] == trace["Heartbeat"] >= 2 and not trace["Upgraded"], (events, stats)
        assert not any(e.startswith("Lost") for e in events), events
    if name in {"opening-size", "poll-size", "ws-size"}:
        assert trace["Lost Limit"] == 1 and not trace["Event"], (events, stats)
    if name == "redirect":
        assert trace["Lost Status(302)"] == 1, events
    if name in {"upgrade-redirect", "probe-refused"}:
        reason = "Status(302)" if name == "upgrade-redirect" else "Protocol"
        assert trace["UpgradeDeclined " + reason] == 1 and not trace["Upgraded"], events
    if websocket_at_stop or name == "ws-size":
        assert stats["probes"] == stats["upgrades"] == trace["Upgraded"] and stats["upgrades"] >= 1, (events, stats)
    if websocket_at_stop:
        assert stats["websocketPongs"] == stats["enginePongs"] == stats["upgrades"], (events, stats)
        assert stats["enginePongs"] + stats["pollingPongs"] == trace["Heartbeat"], (events, stats)
        assert trace["Event"] == stats["upgrades"] + int(name == "websocket"), (events, stats)
        if name == "ack-after-upgrade":
            assert events.index("Upgraded") < events.index("Connected") < events.index("Event"), events
            assert stats["websocketNamespaceAcks"] == stats["pollingPongs"] == stats["releasedPollingPongs"] == 1
            assert trace["Attempt"] == 1
        else:
            assert events.index("Connected") < events.index("Upgraded"), events
        if name == "websocket":
            assert events.index("Connected") < events.index("Event") < events.index("Upgraded"), events
    if name == "reconnect":
        assert trace["Lost Disconnected"] == 1 and trace["Connected"] == 2, (events, stats)
    if name in {"polling", "upgrade-redirect", "probe-refused"}:
        assert trace["Event"] == len(SUBSCRIPTIONS) and stats["pollingPongs"] == 1 and stats["pendingPolls"] == 1
    if name == "exact-size":
        assert trace["Event"] == 1 and stats["pendingPolls"] == 1, (events, stats)
    if name == "cancel-poll":
        assert stats["pendingPolls"] == 1 and trace["Attempt"] == 1 and not trace["Event"], (events, stats)
    if name == "missed-heartbeat":
        assert trace["Lost Timeout"] == 1 and stats["pendingPolls"] == 1, (events, stats)
    if name not in {"untrusted-tls", "wrong-host-tls", "opening-size", "redirect", "stop-before-ack"}:
        assert stats["namespacePosts"] == trace["Connected"] >= 1, (events, stats)
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
             "probe-refused", "redirect", "exact-size", "opening-size", "poll-size", "ws-size",
             "reconnect", "cancel-poll", "missed-heartbeat", "stop-before-ack", "close-timeout", "ack-after-upgrade",
             "stalled-probe", *ESCAPED_PATHS)
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
