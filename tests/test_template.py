import unittest
import os
import tempfile
import time

from dp4500.template import FingerprintTemplate


class TestFingerprintTemplate(unittest.TestCase):
    def test_basic_properties(self):
        payload = b"TEST_MINUTIAE_BINARY_PAYLOAD_12345"
        tpl = FingerprintTemplate(
            data=payload,
            format_type="libfprint",
            username="john_doe",
            finger_name="right_index",
            metadata={"department": "Security"},
        )
        self.assertEqual(tpl.data, payload)
        self.assertEqual(tpl.size, len(payload))
        self.assertEqual(tpl.format_type, "libfprint")
        self.assertEqual(tpl.username, "john_doe")
        self.assertEqual(tpl.finger_name, "right_index")
        self.assertEqual(tpl.metadata["department"], "Security")

    def test_serialization_roundtrip(self):
        payload = b"\x00\x01\x02\x03\x04\xff\xfe\xfd"
        tpl = FingerprintTemplate(
            data=payload,
            format_type="ansi_378",
            username="alice",
            finger_name="left_thumb",
            created_at=1700000000.0,
            metadata={"role": "admin"},
        )

        serialized = tpl.to_bytes()
        restored = FingerprintTemplate.from_bytes(serialized)

        self.assertEqual(restored.data, payload)
        self.assertEqual(restored.format_type, "ansi_378")
        self.assertEqual(restored.username, "alice")
        self.assertEqual(restored.finger_name, "left_thumb")
        self.assertEqual(restored.created_at, 1700000000.0)
        self.assertEqual(restored.metadata.get("role"), "admin")

    def test_base64_roundtrip(self):
        tpl = FingerprintTemplate(
            data=b"RANDOM_FINGERPRINT_BUFFER",
            username="bob",
        )
        b64 = tpl.to_base64()
        restored = FingerprintTemplate.from_base64(b64)
        self.assertEqual(restored.username, "bob")
        self.assertEqual(restored.data, tpl.data)

    def test_file_save_and_load(self):
        tpl = FingerprintTemplate(
            data=b"PERSISTENCE_TEST_DATA",
            username="carol",
            finger_name="right_thumb",
        )

        with tempfile.NamedTemporaryFile(suffix=".fpt", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            tpl.save(tmp_path)
            self.assertTrue(os.path.exists(tmp_path))

            loaded = FingerprintTemplate.load(tmp_path)
            self.assertEqual(loaded.username, "carol")
            self.assertEqual(loaded.finger_name, "right_thumb")
            self.assertEqual(loaded.data, b"PERSISTENCE_TEST_DATA")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
