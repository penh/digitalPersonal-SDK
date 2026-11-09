import unittest
import os
import tempfile
import numpy as np
from PIL import Image

from dp4500.image import FingerprintImage


class TestFingerprintImage(unittest.TestCase):
    def setUp(self):
        # Create a sample 100x100 gradient image
        self.width = 100
        self.height = 100
        arr = np.linspace(0, 255, self.width * self.height, dtype=np.uint8).reshape((self.height, self.width))
        self.raw_data = arr.tobytes()
        self.img = FingerprintImage(self.raw_data, self.width, self.height, dpi=500)

    def test_dimensions_and_properties(self):
        self.assertEqual(self.img.width, 100)
        self.assertEqual(self.img.height, 100)
        self.assertEqual(self.img.size, (100, 100))
        self.assertEqual(self.img.dpi, 500)
        self.assertEqual(len(self.img.data), 10000)

    def test_dimension_mismatch_raises(self):
        with self.assertRaises(ValueError):
            FingerprintImage(b"too_short", 100, 100)

    def test_to_and_from_pil(self):
        pil_img = self.img.to_pil()
        self.assertIsInstance(pil_img, Image.Image)
        self.assertEqual(pil_img.size, (100, 100))
        self.assertEqual(pil_img.mode, "L")

        restored = FingerprintImage.from_pil(pil_img, dpi=500)
        self.assertEqual(restored.width, self.img.width)
        self.assertEqual(restored.height, self.img.height)
        self.assertEqual(restored.data, self.img.data)

    def test_to_and_from_numpy(self):
        arr = self.img.to_numpy()
        self.assertIsInstance(arr, np.ndarray)
        self.assertEqual(arr.shape, (100, 100))
        self.assertEqual(arr.dtype, np.uint8)

        restored = FingerprintImage.from_numpy(arr, dpi=500)
        self.assertEqual(restored.data, self.img.data)

    def test_base64_serialization(self):
        b64 = self.img.to_base64(format="PNG")
        self.assertIsInstance(b64, str)
        restored = FingerprintImage.from_base64(b64)
        self.assertEqual(restored.width, self.img.width)
        self.assertEqual(restored.height, self.img.height)

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            self.img.save(tmp_path, format="PNG")
            self.assertTrue(os.path.exists(tmp_path))
            self.assertGreater(os.path.getsize(tmp_path), 0)

            loaded = FingerprintImage.load(tmp_path)
            self.assertEqual(loaded.width, self.img.width)
            self.assertEqual(loaded.height, self.img.height)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_binarization_and_enhancement(self):
        bin_img = self.img.binarize()
        unique_vals = set(np.unique(bin_img.to_numpy()))
        self.assertTrue(unique_vals.issubset({0, 255}))

        inv_img = self.img.invert()
        self.assertEqual(inv_img.to_numpy()[0, 0], 255 - self.img.to_numpy()[0, 0])

        enhanced = self.img.enhance()
        self.assertEqual(enhanced.size, (100, 100))

    def test_quality_score(self):
        score = self.img.quality_score
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
