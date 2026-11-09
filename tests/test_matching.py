import unittest
import numpy as np

from dp4500.matching import FingerprintMatcher, Minutia
from dp4500.backends.mock import MockBackend


class TestFingerprintMatching(unittest.TestCase):
    def setUp(self):
        self.matcher = FingerprintMatcher()
        self.mock = MockBackend()

    def test_minutia_distance(self):
        m1 = Minutia(x=10, y=20, type="ending")
        m2 = Minutia(x=13, y=24, type="ending")
        self.assertEqual(m1.distance_to(m2), 5.0)

    def test_zhang_suen_thinning(self):
        # Create a simple thick 5-pixel wide vertical line
        img = np.zeros((30, 30), dtype=np.uint8)
        img[5:25, 12:17] = 1

        thinned = FingerprintMatcher.zhang_suen_thinning(img)
        # Thinned line along center should be 1 pixel wide
        self.assertEqual(np.sum(thinned[15, :]), 1)

    def test_minutiae_extraction(self):
        img = self.mock.generate_synthetic_fingerprint(seed=100)
        minutiae = self.matcher.extract_minutiae(img)
        self.assertIsInstance(minutiae, list)
        self.assertGreater(len(minutiae), 5)
        for m in minutiae:
            self.assertIn(m.type, ("ending", "bifurcation"))

    def test_matching_identical_finger(self):
        img1 = self.mock.generate_synthetic_fingerprint(seed=200, noise_level=0.01)
        img2 = self.mock.generate_synthetic_fingerprint(seed=200, noise_level=0.02)

        matched, score = self.matcher.match_images(img1, img2)
        self.assertTrue(matched)
        self.assertGreaterEqual(score, 0.40)

    def test_matching_different_fingers(self):
        img1 = self.mock.generate_synthetic_fingerprint(seed=101)
        img2 = self.mock.generate_synthetic_fingerprint(seed=999)

        matched, score = self.matcher.match_images(img1, img2)
        # Impostor fingers should not exceed genuine match
        self.assertLess(score, 0.60)


if __name__ == "__main__":
    unittest.main()
