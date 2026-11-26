"""Check that a signed Platform cannot substitute for its own matching GL deployment."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import graphics


class GraphicsInputsTests(unittest.TestCase):
    def test_hosted_extension_requires_matching_files_and_signature_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            metadata = b'[Runtime]\nname = org.freedesktop.Platform.GL.default\n'
            signature = b'synthetic signature verification output\n'
            pin = {'ref': 'runtime/org.freedesktop.Platform.GL.default/aarch64/26.08',
                   'commit': 'a' * 64, 'metadata_sha256': hashlib.sha256(metadata).hexdigest()}
            location = work / 'flatpak' / pin['ref'] / pin['commit']
            (location / 'files').mkdir(parents=True)
            (location / 'metadata').write_bytes(metadata)
            record = {**pin, 'gpg_verify_summary': True, 'gpg_verify': True,
                      'signature_sha256': hashlib.sha256(signature).hexdigest()}
            (work / 'graphics-signature.txt').write_bytes(signature)
            receipt = work / 'verified-graphics.json'
            receipt.write_text(json.dumps(record))
            with patch.object(graphics, 'hosted_work', return_value=work), patch.object(graphics, 'pinned_extension', return_value=pin):
                deployed, details = graphics.graphics_deployment(Path(folder))
                self.assertEqual(deployed, location)
                self.assertEqual(details['acquisition'], record)
                for key, wrong in (('gpg_verify', False), ('gpg_verify_summary', False),
                                   ('ref', 'another/ref'), ('commit', 'b' * 64), ('signature_sha256', '0' * 64)):
                    with self.subTest(key=key):
                        receipt.write_text(json.dumps({**record, key: wrong}))
                        with self.assertRaises(ValueError):
                            graphics.graphics_deployment(Path(folder))
                receipt.write_text(json.dumps(record))
                (location / 'metadata').write_bytes(b'another runtime')
                with self.assertRaises(ValueError):
                    graphics.graphics_deployment(Path(folder))


if __name__ == '__main__':
    unittest.main()
