"""Verify Digest on the fixed loopback relay without retaining credentials."""
import hashlib
import hmac
import re
import secrets
import threading
from urllib.request import parse_http_list, parse_keqv_list


class DigestPeer:
    def __init__(self, password, authority, algorithm, *, legacy_root=False, check_counts=False, qop="auth",
                 realm="synthetic proxy"):
        self.password = password
        self.authority = authority
        self.realm = realm
        self.nonce = secrets.token_hex(16)
        self.algorithm = {"sha256": "SHA-256", "md5": "MD5"}[algorithm]
        self.legacy_root = legacy_root
        self.check_counts = check_counts
        assert qop in ("auth", "auth-int")
        self.qop = qop
        self.counts = set()
        self.lock = threading.Lock()
        self.challenge = (f'Digest realm="{self.realm}", nonce="{self.nonce}", '
                          f'algorithm={self.algorithm}, qop="{self.qop}"')
        if not self.realm.isascii():
            self.challenge += ', charset=UTF-8'

    def check(self, values, *, method="CONNECT", target=None, origin_form=None, body=b""):
        """Return only the comparison outcome and the observed request-target category."""
        if not values:
            return "absent", None
        if len(values) != 1 or not values[0].lower().startswith("digest "):
            return "unexpected-scheme", None
        try:
            # Python's HTTP parser maps each incoming header byte to Latin-1.
            fields = parse_http_list(values[0][7:].encode("latin-1").decode("utf-8"))
            params = parse_keqv_list(fields)
        except ValueError:
            return "malformed", None
        uri = params.get("uri")
        if method == "CONNECT":
            category = "authority" if uri == self.authority else "root" if uri == "/" else "other"
        else:
            category = "absolute" if uri and uri == target else "origin" if uri and uri == origin_form else "other"
        if (len(fields) != len(params) or params.get("username") != "fixture" or params.get("realm") != self.realm
                or params.get("nonce") != self.nonce or params.get("algorithm", "MD5").upper() != self.algorithm
                or params.get("qop") != self.qop or not re.fullmatch("[0-9a-fA-F]{8}", params.get("nc", ""))
                or not params.get("cnonce") or category == "other"):
            return "invalid-fields", category

        def hashed(value):
            data = value.encode() if isinstance(value, str) else value
            return hashlib.new(self.algorithm.replace("-", "").lower(), data, usedforsecurity=False).hexdigest()

        ha1 = hashed(f"fixture:{self.realm}:{self.password}")
        a2 = f"{method}:{uri}"
        if self.qop == "auth-int":
            a2 += ":" + hashed(body)
        expected = hashed(":".join([ha1, self.nonce, params["nc"], params["cnonce"], self.qop, hashed(a2)]))
        supplied = params.get("response", "").lower()
        valid = bool(re.fullmatch(r"[0-9a-f]+", supplied)) and hmac.compare_digest(expected, supplied)
        if valid and category in ("root", "origin") and not self.legacy_root:
            return "target-mismatch", category
        if valid and self.check_counts:
            nc = int(params["nc"], 16)
            with self.lock:
                if nc == 0 or nc in self.counts:
                    return "repeated-count", category
                self.counts.add(nc)
        return ("correct" if valid else "incorrect"), category
