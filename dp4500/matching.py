"""
Biometric minutiae extraction and pure-Python matching algorithms.
Provides vendor-independent fingerprint verification and matching capabilities.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np

from dp4500.image import FingerprintImage


@dataclass
class Minutia:
    x: int
    y: int
    type: str  # 'ending' or 'bifurcation'
    angle: float = 0.0  # radians (0 to 2*pi)

    def distance_to(self, other: Minutia) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


class FingerprintMatcher:
    """
    Pure-Python minutiae extractor and matcher.
    Implements:
    - Adaptive image binarization
    - Zhang-Suen morphological ridge skeletonization/thinning
    - Crossing Number (CN) minutiae extraction (endings and bifurcations)
    - Minutiae alignment and point-set matching
    - Direct image similarity scoring
    """

    def __init__(self, match_threshold: float = 0.40):
        """
        :param match_threshold: Minimum match score (0.0 to 1.0) to declare a positive match.
        """
        self.match_threshold = match_threshold

    @staticmethod
    def zhang_suen_thinning(binary_image: np.ndarray) -> np.ndarray:
        """
        Zhang-Suen thinning algorithm for ridge skeletonization.
        Expects a binary image where foreground ridges are 1 and background is 0.
        """
        image = (binary_image > 0).astype(np.uint8)
        prev = np.zeros(image.shape, dtype=np.uint8)

        while True:
            # Step 1
            marked1 = []
            h, w = image.shape
            # Pad by 1 for neighbor checking
            pad = np.pad(image, 1, mode="constant", constant_values=0)

            # Neighborhood indexing
            p2 = pad[0:h, 1 : w + 1]
            p3 = pad[0:h, 2 : w + 2]
            p4 = pad[1 : h + 1, 2 : w + 2]
            p5 = pad[2 : h + 2, 2 : w + 2]
            p6 = pad[2 : h + 2, 1 : w + 1]
            p7 = pad[2 : h + 2, 0:w]
            p8 = pad[1 : h + 1, 0:w]
            p9 = pad[0:h, 0:w]

            p = image == 1
            b = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9

            # Number of 0-to-1 transitions in ordered sequence
            a = (
                ((p2 == 0) & (p3 == 1)).astype(int)
                + ((p3 == 0) & (p4 == 1)).astype(int)
                + ((p4 == 0) & (p5 == 1)).astype(int)
                + ((p5 == 0) & (p6 == 1)).astype(int)
                + ((p6 == 0) & (p7 == 1)).astype(int)
                + ((p7 == 0) & (p8 == 1)).astype(int)
                + ((p8 == 0) & (p9 == 1)).astype(int)
                + ((p9 == 0) & (p2 == 1)).astype(int)
            )

            cond1 = p & (b >= 2) & (b <= 6) & (a == 1) & (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            image[cond1] = 0

            # Step 2
            pad = np.pad(image, 1, mode="constant", constant_values=0)
            p2 = pad[0:h, 1 : w + 1]
            p3 = pad[0:h, 2 : w + 2]
            p4 = pad[1 : h + 1, 2 : w + 2]
            p5 = pad[2 : h + 2, 2 : w + 2]
            p6 = pad[2 : h + 2, 1 : w + 1]
            p7 = pad[2 : h + 2, 0:w]
            p8 = pad[1 : h + 1, 0:w]
            p9 = pad[0:h, 0:w]

            p = image == 1
            b = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            a = (
                ((p2 == 0) & (p3 == 1)).astype(int)
                + ((p3 == 0) & (p4 == 1)).astype(int)
                + ((p4 == 0) & (p5 == 1)).astype(int)
                + ((p5 == 0) & (p6 == 1)).astype(int)
                + ((p6 == 0) & (p7 == 1)).astype(int)
                + ((p7 == 0) & (p8 == 1)).astype(int)
                + ((p8 == 0) & (p9 == 1)).astype(int)
                + ((p9 == 0) & (p2 == 1)).astype(int)
            )

            cond2 = p & (b >= 2) & (b <= 6) & (a == 1) & (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            image[cond2] = 0

            if np.array_equal(image, prev):
                break
            prev = image.copy()

        return image

    def extract_minutiae(
        self, image: FingerprintImage, border_margin: int = 15
    ) -> List[Minutia]:
        """
        Extract fingerprint minutiae (ridge endings and bifurcations) from an image.
        """
        # Step 1: Binarize image (foreground ridges are dark in raw optical prints, invert for processing)
        arr = image.to_numpy()
        bin_img = image.binarize().to_numpy()
        # Ridges in U.are.U 4500 are darker than illuminated background: invert so ridges = 1
        skeleton = self.zhang_suen_thinning(255 - bin_img)

        h, w = skeleton.shape
        minutiae: List[Minutia] = []

        # Step 2: Crossing number calculation
        for y in range(border_margin, h - border_margin):
            for x in range(border_margin, w - border_margin):
                if skeleton[y, x] != 1:
                    continue

                # 8-neighbors in clockwise order:
                # [p9, p2, p3]
                # [p8, p,  p4]
                # [p7, p6, p5]
                p2 = int(skeleton[y - 1, x])
                p3 = int(skeleton[y - 1, x + 1])
                p4 = int(skeleton[y, x + 1])
                p5 = int(skeleton[y + 1, x + 1])
                p6 = int(skeleton[y + 1, x])
                p7 = int(skeleton[y + 1, x - 1])
                p8 = int(skeleton[y, x - 1])
                p9 = int(skeleton[y - 1, x - 1])

                neighbors = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
                cn = 0.5 * sum(abs(neighbors[i] - neighbors[i + 1]) for i in range(8))

                if cn == 1:
                    # Ridge ending
                    minutiae.append(Minutia(x=x, y=y, type="ending"))
                elif cn == 3:
                    # Ridge bifurcation
                    minutiae.append(Minutia(x=x, y=y, type="bifurcation"))

        return minutiae

    def match_minutiae(
        self,
        set1: List[Minutia],
        set2: List[Minutia],
        distance_tol: float = 18.0,
    ) -> Tuple[bool, float]:
        """
        Compare two minutiae sets and return (is_match, similarity_score).
        Score is in range [0.0, 1.0].
        """
        if not set1 or not set2:
            return False, 0.0

        # Subsample if set is excessively large for performance
        s1 = set1[:60]
        s2 = set2[:60]

        best_matches = 0

        # Test relative alignments between reference minutiae pairs
        for ref1 in s1[:10]:
            for ref2 in s2[:10]:
                if ref1.type != ref2.type:
                    continue
                dx = ref2.x - ref1.x
                dy = ref2.y - ref1.y

                matches = 0
                used_s2 = set()
                for m1 in s1:
                    tx = m1.x + dx
                    ty = m1.y + dy
                    for j, m2 in enumerate(s2):
                        if j in used_s2 or m1.type != m2.type:
                            continue
                        dist = math.hypot(tx - m2.x, ty - m2.y)
                        if dist <= distance_tol:
                            matches += 1
                            used_s2.add(j)
                            break

                if matches > best_matches:
                    best_matches = matches

        score = (2.0 * best_matches) / (len(s1) + len(s2))
        score = min(1.0, max(0.0, score))
        return (score >= self.match_threshold, score)

    def match_images(
        self, img1: FingerprintImage, img2: FingerprintImage
    ) -> Tuple[bool, float]:
        """
        Compare two fingerprint images using combined minutiae and structural correlation.
        """
        m1 = self.extract_minutiae(img1)
        m2 = self.extract_minutiae(img2)
        is_match, minutiae_score = self.match_minutiae(m1, m2)

        # Normalized cross correlation of center region
        arr1 = img1.to_numpy().astype(float)
        arr2 = img2.to_numpy().astype(float)
        # Crop center 120x120 window
        ch, cw = min(arr1.shape[0], arr2.shape[0]), min(arr1.shape[1], arr2.shape[1])
        y0, y1 = ch // 4, 3 * ch // 4
        x0, x1 = cw // 4, 3 * cw // 4
        c1 = arr1[y0:y1, x0:x1]
        c2 = arr2[y0:y1, x0:x1]

        c1 = (c1 - np.mean(c1)) / (np.std(c1) + 1e-6)
        c2 = (c2 - np.mean(c2)) / (np.std(c2) + 1e-6)
        corr = float(np.mean(c1 * c2))
        corr_score = max(0.0, min(1.0, corr))

        # Fused score
        fused_score = 0.7 * minutiae_score + 0.3 * corr_score
        return (fused_score >= self.match_threshold, round(fused_score, 4))
