"""
Mock/Virtual DigitalPersona U.are.U 4500 reader backend.
Enables full development, simulation, and automated testing without physical hardware.
"""

from __future__ import annotations
import math
import time
import random
from typing import List, Optional, Tuple, Callable, Any
import numpy as np

from dp4500.backends.base import BaseBackend, DeviceInfo, MatchResult, IdentifyResult, LEDMode
from dp4500.image import FingerprintImage
from dp4500.template import FingerprintTemplate
from dp4500.matching import FingerprintMatcher


class MockDeviceHandle:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.is_open = True
        self.led_mode = LEDMode.OFF
        self.simulated_finger_seed = 42


class MockBackend(BaseBackend):
    """
    Simulated reader backend that generates realistic synthetic fingerprints,
    simulates multi-stage enrollments, and provides predictable verification.
    """

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def backend_name(cls) -> str:
        return "mock"

    def __init__(self, simulate_latency: bool = False):
        self.simulate_latency = simulate_latency
        self._matcher = FingerprintMatcher()

    def list_devices(self) -> List[DeviceInfo]:
        return [
            DeviceInfo(
                device_id="mock:0",
                name="Virtual DigitalPersona U.are.U 4500 Reader",
                driver="mock_uru4000",
                vendor_id=0x05BA,
                product_id=0x000A,
                serial_number="MOCK-4500-001",
                firmware_version="1.0.0-mock",
            )
        ]

    def open_device(self, device_id: str) -> Any:
        return MockDeviceHandle(device_id)

    def close_device(self, handle: Any) -> None:
        if handle:
            handle.is_open = False

    @staticmethod
    def generate_synthetic_fingerprint(
        seed: int = 42,
        width: int = 290,
        height: int = 384,
        noise_level: float = 0.05,
    ) -> FingerprintImage:
        """
        Generate a realistic synthetic optical fingerprint image.
        Simulates concentric ridge flow, orientation field, and fingertip contact mask.
        """
        rng = np.random.default_rng(seed)

        # Coordinate grid
        y, x = np.mgrid[0:height, 0:width]
        cx, cy = width / 2.0 + rng.uniform(-10, 10), height / 2.0 + rng.uniform(-15, 15)

        # Normalized distances
        dx = (x - cx) / (width * 0.42)
        dy = (y - cy) / (height * 0.44)
        dist_sq = dx**2 + dy**2

        # Fingertip elliptical boundary mask (faded border)
        mask = np.clip(1.0 - (dist_sq - 0.6) / 0.4, 0.0, 1.0)

        # Ridge frequency ~ 8-9 pixels (approx 500 DPI)
        freq = 2.0 * math.pi / 8.5
        r = np.sqrt((x - cx) ** 2 + 1.2 * (y - cy) ** 2)

        # Ridge flow function with spiral/whorl perturbation
        theta = np.arctan2(y - cy, x - cx)
        phase = r * freq + 1.5 * np.sin(2.0 * theta) + rng.uniform(0, 2 * math.pi)

        # Ridge signal: 0 (black ridge) to 255 (white valley)
        ridges = 128.0 + 90.0 * np.cos(phase)

        # Background illuminated optical platen is bright white (~240)
        background = 245.0 + rng.normal(0, 3, size=(height, width))
        blended = mask * ridges + (1.0 - mask) * background

        # Add fine skin pore / sensor noise
        noise = rng.normal(0, noise_level * 50.0, size=(height, width))
        final_img = np.clip(blended + noise, 0, 255).astype(np.uint8)

        return FingerprintImage.from_numpy(final_img, dpi=500)

    def capture_image(
        self,
        handle: Any,
        wait_for_finger: bool = True,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintImage:
        if self.simulate_latency:
            time.sleep(0.15)
        seed = getattr(handle, "simulated_finger_seed", 42)
        return self.generate_synthetic_fingerprint(seed=seed)

    def enroll(
        self,
        handle: Any,
        stages: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintTemplate:
        seed = getattr(handle, "simulated_finger_seed", 42)

        for s in range(stages):
            if self.simulate_latency:
                time.sleep(0.08)
            if progress_callback:
                progress_callback(s + 1, stages)

        img = self.generate_synthetic_fingerprint(seed=seed)
        # In mock mode, embed the seed and image hash in template payload
        payload = f"MOCK_TEMPLATE:SEED={seed}:SIZE={img.width}x{img.height}".encode("utf-8")
        return FingerprintTemplate(data=payload, format_type="mock")

    def verify(
        self,
        handle: Any,
        template: FingerprintTemplate,
        timeout_ms: Optional[int] = None,
    ) -> MatchResult:
        if self.simulate_latency:
            time.sleep(0.1)

        seed = getattr(handle, "simulated_finger_seed", 42)
        expected_token = f"SEED={seed}".encode("utf-8")

        if template.format_type == "mock":
            if expected_token in template.data:
                return MatchResult(matched=True, score=0.98, details="Exact mock template match")
            else:
                return MatchResult(matched=False, score=0.08, details="Mock template seed mismatch")

        # Compare using pure Python minutiae matcher for raw/generic templates
        live_img = self.generate_synthetic_fingerprint(seed=seed)
        tpl_img = self.generate_synthetic_fingerprint(seed=seed + 999)
        matched, score = self._matcher.match_images(live_img, tpl_img)
        return MatchResult(matched=matched, score=score)

    def identify(
        self,
        handle: Any,
        templates: List[FingerprintTemplate],
        timeout_ms: Optional[int] = None,
    ) -> IdentifyResult:
        for idx, tpl in enumerate(templates):
            res = self.verify(handle, tpl, timeout_ms=timeout_ms)
            if res.matched:
                return IdentifyResult(matched=True, index=idx, template=tpl, score=res.score)
        return IdentifyResult(matched=False, index=None, template=None, score=0.0)

    def set_led(self, handle: Any, mode: LEDMode) -> bool:
        if handle:
            handle.led_mode = mode
        return True
