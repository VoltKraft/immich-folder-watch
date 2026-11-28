"""Controls for the signed-client Digest comparison on its one loopback route."""
from unittest import TestCase, main
from unittest.mock import patch

from digest_peer import DigestPeer


class ConnectDigestTests(TestCase):
    def test_authority_and_historical_root_are_independently_verified(self):
        authority = "127.0.0.1:28431"
        samples = {
            "md5": ("76e28345485621fdae6efb630e0c70d9", "44e6516592fd614edce89bfc6dc144f5"),
            "sha256": ("bd35717705180f575ae9eb5a6708c1aee71664c018a6b64bc84478bc529b8d9c",
                       "4fa254229ce2ce8abc0936eece9b0dbe2da4f129416a6224ce1269421c9c76a9"),
        }
        for algorithm, (strict_response, original_response) in samples.items():
            for legacy in (False, True):
                with self.subTest(algorithm=algorithm, legacy=legacy), patch("digest_peer.secrets.token_hex", return_value="fixture-nonce"):
                    peer = DigestPeer("kit-password", authority, algorithm, legacy_root=legacy)
                    def header(uri, response):
                        return (f'Digest username="fixture", realm="synthetic proxy", nonce="fixture-nonce", '
                                f'algorithm={peer.algorithm}, qop=auth, nc=00000001, cnonce="fixture-cnonce", '
                                f'uri="{uri}", response="{response}"')
                    self.assertEqual(peer.check([header(authority, strict_response)]), ("correct", "authority"))
                    self.assertEqual(peer.check([header("/", original_response)]),
                                     ("correct" if legacy else "target-mismatch", "root"))
                    self.assertEqual(peer.check([header(authority, original_response)]), ("incorrect", "authority"))
                    self.assertEqual(peer.check([header("other:443", strict_response)]), ("invalid-fields", "other"))
                    self.assertEqual(peer.check([header(authority, strict_response) + ', nc=00000001']),
                                     ("invalid-fields", "authority"))


if __name__ == "__main__":
    main()
