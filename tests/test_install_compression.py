import gzip
import hashlib
import random
import sys
import unittest

from dsh_pack.compression import decode, encode
from dsh_pack.errors import IntegrityError


@unittest.skipUnless(sys.platform == "win32", "requires the shipped Windows compressor")
class WindowsInstallCompressionTests(unittest.TestCase):
    def test_reproduce_preview21_install_identity(self):
        # Synthetic bytes for which classic zlib and the Preview.21 compressor
        # produce different DEFLATE streams at the same compression level.
        rng = random.Random(901)
        blocks = [rng.randbytes(rng.randrange(3, 25)) for _ in range(48)]
        raw = b"".join(rng.choice(blocks) for _ in range(32))
        native = gzip.compress(raw, compresslevel=6, mtime=0)
        path = "plugins/example.tgz"
        lock = {"plugins": [{"artifact": {"mode": "embedded", "path": path}}]}
        entries, transport = encode({"example.tgz": native}, lock, "fast")
        record = transport["artifacts"][path]
        artifact = lock["plugins"][0]["artifact"]
        published = "cd2d72ab8872a7d9c78b8593cb292f62a657d273d40ead4d764f0659d9c571b6"
        self.assertEqual(record["installSha256"], published)
        self.assertEqual(artifact["sha256"], published)
        restored = decode(entries, transport, lock)["example.tgz"]
        self.assertEqual(hashlib.sha256(restored).hexdigest(), published)
        self.assertEqual(gzip.decompress(restored), raw)

        # Older archives that used the caller's compressor remain readable.
        native_hash = hashlib.sha256(native).hexdigest()
        record["installSha256"] = artifact["sha256"] = native_hash
        self.assertEqual(decode(entries, transport, lock)["example.tgz"], native)
        for manifest_hash, lock_hash in [(published, "0" * 64), ("0" * 64, published), ("0" * 64, "0" * 64)]:
            with self.subTest(manifest=manifest_hash, lock=lock_hash):
                record["installSha256"] = manifest_hash
                artifact["sha256"] = lock_hash
                with self.assertRaises(IntegrityError):
                    decode(entries, transport, lock)
