"""
Abstract base class defining the hardware backend contract for DigitalPersona readers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable, Any
from enum import IntEnum

from dp4500.image import FingerprintImage
from dp4500.template import FingerprintTemplate


class LEDMode(IntEnum):
    OFF = 0
    ON = 1
    BLINK = 2


@dataclass
class DeviceInfo:
    device_id: str
    name: str
    driver: str
    vendor_id: int
    product_id: int
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None


@dataclass
class MatchResult:
    matched: bool
    score: float
    details: Optional[str] = None


@dataclass
class IdentifyResult:
    matched: bool
    index: Optional[int]
    template: Optional[FingerprintTemplate]
    score: float
    details: Optional[str] = None


class BaseBackend(ABC):
    """Abstract interface that all device backends (libfprint, official SDK, mock) implement."""

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True if backend library and runtime dependencies are available."""
        pass

    @classmethod
    @abstractmethod
    def backend_name(cls) -> str:
        """Return human-readable identifier for this backend."""
        pass

    @abstractmethod
    def list_devices(self) -> List[DeviceInfo]:
        """Scan and enumerate connected compatible fingerprint readers."""
        pass

    @abstractmethod
    def open_device(self, device_id: str) -> Any:
        """Open communication handle with the reader."""
        pass

    @abstractmethod
    def close_device(self, handle: Any) -> None:
        """Close communication handle."""
        pass

    @abstractmethod
    def capture_image(
        self,
        handle: Any,
        wait_for_finger: bool = True,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintImage:
        """Acquire a raw fingerprint image from the reader."""
        pass

    @abstractmethod
    def enroll(
        self,
        handle: Any,
        stages: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintTemplate:
        """Perform multi-stage enrollment and return a template."""
        pass

    @abstractmethod
    def verify(
        self,
        handle: Any,
        template: FingerprintTemplate,
        timeout_ms: Optional[int] = None,
    ) -> MatchResult:
        """Perform 1:1 biometric verification of finger on sensor against enrolled template."""
        pass

    @abstractmethod
    def identify(
        self,
        handle: Any,
        templates: List[FingerprintTemplate],
        timeout_ms: Optional[int] = None,
    ) -> IdentifyResult:
        """Perform 1:N biometric search against a list of enrolled templates."""
        pass

    @abstractmethod
    def set_led(self, handle: Any, mode: LEDMode) -> bool:
        """Control the reader's status LED if supported."""
        pass
