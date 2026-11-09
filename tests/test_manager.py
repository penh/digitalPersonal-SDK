import unittest

from dp4500.manager import ReaderManager
from dp4500.backends.mock import MockBackend
from dp4500.backends.libfprint import LibfprintBackend


class TestReaderManager(unittest.TestCase):
    def test_backend_registry(self):
        backends = ReaderManager.available_backends()
        self.assertIn("mock", backends)

    def test_auto_detect_backend(self):
        backend = ReaderManager.auto_detect_backend(allow_mock=True)
        self.assertIsNotNone(backend)

    def test_get_mock_reader(self):
        reader = ReaderManager.get_reader(backend_name="mock")
        self.assertEqual(reader.name, "Virtual DigitalPersona U.are.U 4500 Reader")
        self.assertEqual(reader.vendor_id, 0x05BA)
        self.assertEqual(reader.product_id, 0x000A)


if __name__ == "__main__":
    unittest.main()
