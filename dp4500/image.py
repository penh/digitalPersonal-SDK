"""
Fingerprint image representation, manipulation, and format conversions.
"""

from __future__ import annotations
import base64
import io
import math
from typing import Optional, Tuple, Union
import numpy as np
from PIL import Image


class FingerprintImage:
    """
    Represents an uncompressed 8-bit grayscale fingerprint image acquired from
    the DigitalPersona U.are.U 4500 reader (typically 500 DPI).
    """

    def __init__(
        self,
        data: bytes,
        width: int,
        height: int,
        dpi: int = 500,
        binarized_data: Optional[bytes] = None,
        quality_score: Optional[int] = None,
    ):
        expected_len = width * height
        if len(data) != expected_len:
            raise ValueError(
                f"Data length ({len(data)} bytes) does not match dimensions ({width}x{height} = {expected_len} bytes)"
            )
        self._data = bytes(data)
        self._width = int(width)
        self._height = int(height)
        self._dpi = int(dpi)
        self._binarized_data = bytes(binarized_data) if binarized_data is not None else None
        self._quality_score = quality_score

    @property
    def data(self) -> bytes:
        """Raw 8-bit grayscale bytes (row-major order)."""
        return self._data

    @property
    def width(self) -> int:
        """Image width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Image height in pixels."""
        return self._height

    @property
    def size(self) -> Tuple[int, int]:
        """(width, height) tuple."""
        return (self._width, self._height)

    @property
    def dpi(self) -> int:
        """Dots per inch (nominal 500 DPI for DigitalPersona 4500)."""
        return self._dpi

    @property
    def binarized_data(self) -> Optional[bytes]:
        """Optional hardware- or software-binarized black and white image data."""
        return self._binarized_data

    @property
    def quality_score(self) -> int:
        """Estimated image quality score between 0 and 100."""
        if self._quality_score is not None:
            return self._quality_score
        return self._calculate_quality()

    def to_pil(self) -> Image.Image:
        """Convert to a PIL (Pillow) Image in 'L' (8-bit grayscale) mode."""
        img = Image.frombytes("L", (self._width, self._height), self._data)
        img.info["dpi"] = (self._dpi, self._dpi)
        return img

    def to_numpy(self) -> np.ndarray:
        """Convert to a 2D uint8 NumPy array of shape (height, width)."""
        return np.frombuffer(self._data, dtype=np.uint8).reshape((self._height, self._width))

    @classmethod
    def from_numpy(cls, arr: np.ndarray, dpi: int = 500) -> FingerprintImage:
        """Create a FingerprintImage from a 2D uint8 NumPy array."""
        if arr.ndim != 2:
            raise ValueError("Input array must be 2-dimensional (height, width).")
        arr = np.ascontiguousarray(arr, dtype=np.uint8)
        height, width = arr.shape
        return cls(arr.tobytes(), width, height, dpi=dpi)

    @classmethod
    def from_pil(cls, pil_img: Image.Image, dpi: int = 500) -> FingerprintImage:
        """Create a FingerprintImage from a PIL Image object."""
        if pil_img.mode != "L":
            pil_img = pil_img.convert("L")
        width, height = pil_img.size
        return cls(pil_img.tobytes(), width, height, dpi=dpi)

    @classmethod
    def load(cls, filepath: str) -> FingerprintImage:
        """Load an image file from disk (PNG, BMP, JPG, etc.)."""
        with Image.open(filepath) as img:
            return cls.from_pil(img)

    def save(self, destination: Union[str, io.BytesIO], format: str = "PNG") -> None:
        """
        Save the fingerprint image to a file path or binary stream.
        Supported formats: 'PNG', 'BMP', 'JPEG', 'RAW'.
        """
        fmt = format.upper()
        if fmt == "RAW":
            if isinstance(destination, str):
                with open(destination, "wb") as f:
                    f.write(self._data)
            else:
                destination.write(self._data)
            return

        pil_img = self.to_pil()
        pil_img.save(destination, format=fmt, dpi=(self._dpi, self._dpi))

    def to_base64(self, format: str = "PNG") -> str:
        """Export as Base64-encoded string."""
        buf = io.BytesIO()
        self.save(buf, format=format)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    @classmethod
    def from_base64(cls, b64_str: str) -> FingerprintImage:
        """Load from Base64-encoded string."""
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        raw_bytes = base64.b64decode(b64_str)
        with Image.open(io.BytesIO(raw_bytes)) as img:
            return cls.from_pil(img)

    def invert(self) -> FingerprintImage:
        """Invert pixel intensities (255 - pixel)."""
        arr = 255 - self.to_numpy()
        return FingerprintImage.from_numpy(arr, dpi=self._dpi)

    def enhance(self) -> FingerprintImage:
        """
        Enhance image contrast using cumulative distribution histogram equalization.
        """
        arr = self.to_numpy()
        hist, _ = np.histogram(arr.flatten(), 256, [0, 256])
        cdf = hist.cumsum()
        cdf_m = np.ma.masked_equal(cdf, 0)
        cdf_m = (cdf_m - cdf_m.min()) * 255 / (cdf_m.max() - cdf_m.min())
        cdf_final = np.ma.filled(cdf_m, 0).astype("uint8")
        enhanced = cdf_final[arr]
        return FingerprintImage.from_numpy(enhanced, dpi=self._dpi)

    def binarize(self, threshold: Optional[int] = None) -> FingerprintImage:
        """
        Binarize the grayscale image into pure black (0) and white (255).
        If threshold is None, Otsu's optimal thresholding algorithm is used.
        """
        arr = self.to_numpy()
        if threshold is None:
            # Otsu's method
            hist, _ = np.histogram(arr, bins=256, range=(0, 256))
            total = arr.size
            current_max, optimal_thresh = 0.0, 128
            sum_total = np.dot(np.arange(256), hist)
            sum_bg, weight_bg = 0.0, 0.0
            for t in range(256):
                weight_bg += hist[t]
                if weight_bg == 0:
                    continue
                weight_fg = total - weight_bg
                if weight_fg == 0:
                    break
                sum_bg += t * hist[t]
                mean_bg = sum_bg / weight_bg
                mean_fg = (sum_total - sum_bg) / weight_fg
                variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
                if variance > current_max:
                    current_max = variance
                    optimal_thresh = t
            threshold = int(optimal_thresh)

        bin_arr = np.where(arr > threshold, 255, 0).astype(np.uint8)
        return FingerprintImage.from_numpy(bin_arr, dpi=self._dpi)

    def _calculate_quality(self) -> int:
        """
        Estimate fingerprint capture quality based on contrast, standard deviation,
        and foreground ridge-to-background ratio (score between 0 and 100).
        """
        arr = self.to_numpy().astype(float)
        std_dev = np.std(arr)
        # Background on U.are.U 4500 is typically bright white (~255) when no finger is touched
        foreground_pixels = np.count_nonzero(arr < 220)
        fg_ratio = foreground_pixels / arr.size

        # Score formulation
        std_score = min(50.0, (std_dev / 50.0) * 50.0)
        area_score = min(50.0, (fg_ratio / 0.40) * 50.0)
        total = int(std_score + area_score)
        return max(0, min(100, total))

    def __repr__(self) -> str:
        return f"<FingerprintImage width={self._width} height={self._height} dpi={self._dpi} quality={self.quality_score}%>"
