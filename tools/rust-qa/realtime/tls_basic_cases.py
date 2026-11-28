"""Normal Linux wire cases for HTTPS through one fixed HTTP proxy."""

import base64
from collections import Counter
import hmac
import secrets
import threading
from urllib.parse import quote

from digest_peer import DigestPeer


class Authentication:
    def __init__(self, case):
        self.case = case
        self.password = secrets.token_hex(12) + "@:+/"
        self.digest = None
        self.expected = "Basic " + base64.b64encode(f"fixture:{self.password}".encode()).decode()
        self.attempts = []
        self.rotated = threading.Event()
        self.lock = threading.Lock()

    def proxy_url(self, port, authority):
        if self.case.startswith("https-digest-"):
            self.digest = DigestPeer(self.password, authority, self.case.split("-")[2], check_counts=True)
        supplied = self.password + "wrong" if self.case.endswith("-refused") else self.password
        return f"http://fixture:{quote(supplied, safe='')}@127.0.0.1:{port}"

    def accept(self, handler, authority):
        headers = handler.headers
        assert handler.path == authority and headers.get_all("Host") == [authority]
        assert not any(h in headers for h in ("x-api-key", "Authorization", "Cookie"))
        values = headers.get_all("Proxy-Authorization", [])
        if self.digest:
            credential, uri = self.digest.check(values)
            assert (credential, uri) in {("correct", "authority"), ("incorrect", "authority"), ("absent", None)}
        else:
            correct = len(values) == 1 and hmac.compare_digest(values[0], self.expected)
            credential = "correct" if correct else "incorrect" if values else "absent"
        with self.lock:
            other = self.case == "https-basic-other" or self.rotated.is_set()
            offered = "other" if other else self.digest.algorithm if self.digest else "basic"
            allowed = self.case == "https-basic-origin-407" or credential == "correct" and not other
            self.attempts.append((offered, credential, 200 if allowed else 407))
        if allowed:
            del headers["Proxy-Authorization"]
            return True
        handler.send_response(407)
        challenge = 'Digest realm="not Basic, Basic realm", nonce="fixture", algorithm=unavailable' if other else 'Basic realm="private"'
        handler.send_header("Proxy-Authenticate", self.digest.challenge if self.digest else challenge)
        handler.send_header("Connection", "close")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return False

    def readback(self, outer, alerts, trace, stats, origin, direct, redirect):
        counts = Counter(self.attempts)
        assert not redirect.accepted_connections
        bypass = self.case == "https-basic-bypass"
        assert not outer.get("credentialHeaders") and not outer.get("rejectedAuthority")
        assert not direct.accepted_connections if not bypass else not outer and not counts
        if not bypass:
            assert sum(counts.values()) == outer["connections"] == outer["connects"]
        scheme = self.digest.algorithm if self.digest else "basic"
        if self.case == "https-basic-other":
            assert set(counts) == {("other", "absent", 407)}
        elif self.case.endswith("-refused"):
            assert set(counts) == {(scheme, "absent", 407), (scheme, "incorrect", 407)}
            assert counts[scheme, "absent", 407] == counts[scheme, "incorrect", 407]
        elif self.case == "https-basic-origin-407":
            assert set(counts) == {("basic", "absent", 200)} and stats["origin407"] >= 2
        elif not bypass:
            challenges = counts.pop((scheme, "absent", 407))
            accepted = counts.pop((scheme, "correct", 200))
            assert challenges == accepted >= 1
            assert outer["clientHellos"] == accepted
            if self.case == "https-basic-rotates":
                assert self.rotated.is_set() and set(counts) == {("other", "absent", 407)}
                assert counts["other", "absent", 407] >= 2
            else:
                assert not counts
        success = self.case in ("https-basic-proxy", "https-basic-rotates", "https-basic-bypass",
                                "https-digest-sha256", "https-digest-md5")
        if success:
            assert trace["Event"] == stats["sentSubscriptionEvents"] == trace["Connected"] == 1
            assert origin.namespace_posts == ["40/collection,"]
            assert origin.close_packets == [{"websocketText": "41/collection,"},
                                           {"websocketCloseCode": 1000, "reason": "io client disconnect"}]
            if self.case != "https-basic-rotates":
                assert trace["Inventory"] == stats["inventoryRequests"] >= 2
        else:
            assert trace["Event"] == trace["Inventory"] == 0
            if self.case == "https-basic-wrong-host":
                assert not stats and not outer.get("completedTls") and alerts
                assert all(r.endswith("_ALERT_BAD_CERTIFICATE") for r in alerts)
            elif self.case == "https-basic-redirect":
                assert stats["originRedirect"] >= 2
            elif self.case != "https-basic-origin-407":
                assert not stats and not outer.get("clientHellos")
        digest_evidence = {}
        if self.digest:
            accepted = sum(row[2] == 200 for row in self.attempts)
            observed = sorted(self.digest.counts)
            assert observed == list(range(1, accepted + 1)), observed
            digest_evidence = {"acceptedNonceCounts": observed}
        return {**digest_evidence, "attempts": self.attempts, "proxy": outer, "tlsAlerts": alerts, "client": dict(trace),
                "origin": dict(stats), "directConnections": direct.accepted_connections,
                "redirectConnections": redirect.accepted_connections, "closePacketsAtPeer": list(origin.close_packets)}


def origin_handler(base, authentication):
    class Origin(base):
        def routing(self):
            assert not any(h in self.headers for h in ("Proxy-Authorization", "Authorization"))
            assert self.headers.get_all("x-api-key") == ["synthetic"]
            if authentication.case == "https-basic-origin-407":
                self.server.mark("origin407")
                self.body(b"", 407, {"Proxy-Authenticate": 'Basic realm="origin"'})
                return None
            if authentication.case == "https-basic-redirect":
                self.server.mark("originRedirect")
                self.redirect()
                return None
            return super().routing()

        def body(self, data, status=200, headers=None):
            self.close_connection = True
            super().body(data, status, {**(headers or {}), "Connection": "close"})

        def send_subscription_event(self, direct):
            super().send_subscription_event(direct)
            if authentication.case == "https-basic-rotates":
                authentication.rotated.set()
    return Origin
