import base64
import hashlib
import importlib
from pathlib import Path
import sys
import types
import unittest

package = types.ModuleType('lp_identity_test')
package.__path__ = [str(Path(__file__).resolve().parents[2])]
sys.modules.setdefault(package.__name__, package)
identity = importlib.import_module('lp_identity_test.file_identity')


class TestFileIdentity(unittest.TestCase):
    def test_hash_uses_exact_original_bytes(self):
        content = b'Original\x00\xff\nbytes'
        decoded, sha = identity.uploaded_file(base64.b64encode(content))
        self.assertEqual(decoded, content)
        self.assertEqual(sha, hashlib.sha256(content).hexdigest())
        self.assertNotEqual(sha, hashlib.sha256(base64.b64encode(content)).hexdigest())
        self.assertEqual(len(sha), 64)
        self.assertEqual(sha, sha.lower())

    def test_same_binary_matches_and_modified_binary_does_not(self):
        encoded = base64.b64encode(b'original')
        self.assertEqual(identity.uploaded_file(encoded)[1], identity.uploaded_file(encoded.decode())[1])
        self.assertNotEqual(identity.uploaded_file(encoded)[1], identity.uploaded_file(base64.b64encode(b'original '))[1])

    def test_invalid_or_empty_upload_rejected(self):
        for value in (None, b'', b'!invalid!', 'not-base64'):
            with self.subTest(value=value), self.assertRaises(identity.ImportValidationError):
                identity.uploaded_file(value)

    def test_oversized_upload_rejected_before_decoding(self):
        limit = identity.WorkbookReader.MAX_BYTES
        try:
            identity.WorkbookReader.MAX_BYTES = 3
            with self.assertRaises(identity.ImportValidationError):
                identity.uploaded_file(base64.b64encode(b'1234'))
        finally:
            identity.WorkbookReader.MAX_BYTES = limit
