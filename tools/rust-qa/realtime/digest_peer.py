"""Verify a Digest response on the fixed loopback CONNECT route without retaining credentials."""
import hashlib
import hmac
import re
import secrets
import threading
from urllib.request import parse_http_list, parse_keqv_list


class DigestPeer:
    def __init__(self, password, authority, algorithm, *, legacy_root=False, check_counts=False):
        self.password = password
        self.authority = authority
        self.realm = "synthetic proxy"
        self.nonce = secrets.token_hex(16)
        self.algorithm = {"sha256": "SHA-256", "md5": "MD5"}[algorithm]
        self.legacy_root = legacy_root
        self.check_counts = check_counts
        self.counts = set()
        self.lock = threading.Lock()
        self.challenge = (f'Digest realm="{self.realm}", nonce="{self.nonce}", '
                          f'algorithm={self.algorithm}, qop="auth"')

    def check(self, values):
        """Return only the comparison outcome and the observed request-target category."""
        if not values:
            return "absent", None
        if len(values) != 1 or not values[0].lower().startswith("digest "):
            return "unexpected-scheme", None
        fields = parse_http_list(values[0][7:])
        try:
            params = parse_keqv_list(fields)
        except ValueError:
            return "malformed", None
        uri = params.get("uri")
        category = "authority" if uri == self.authority else "root" if uri == "/" else "other"
        if (len(fields) != len(params) or params.get("username") != "fixture" or params.get("realm") != self.realm
                or params.get("nonce") != self.nonce or params.get("algorithm", "MD5").upper() != self.algorithm
                or params.get("qop") != "auth" or not re.fullmatch("[0-9a-fA-F]{8}", params.get("nc", ""))
                or not params.get("cnonce") or category == "other"):
            return "invalid-fields", category

        def hashed(value):
            return hashlib.new(self.algorithm.replace("-", "").lower(), value.encode(), usedforsecurity=False).hexdigest()

        ha1 = hashed(f"fixture:{self.realm}:{self.password}")
        ha2 = hashed(f"CONNECT:{uri}")
        expected = hashed(":".join([ha1, self.nonce, params["nc"], params["cnonce"], "auth", ha2]))
        supplied = params.get("response", "").lower()
        valid = bool(re.fullmatch(r"[0-9a-f]+", supplied)) and hmac.compare_digest(expected, supplied)
        if valid and category == "root" and not self.legacy_root:
            return "target-mismatch", category
        if valid and self.check_counts:
            nc = int(params["nc"], 16)
            with self.lock:
                if nc == 0 or nc in self.counts:
                    return "repeated-count", category
                self.counts.add(nc)
        return ("correct" if valid else "incorrect"), category
