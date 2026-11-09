"""
Python SDK for DigitalPersona (U.are.U) 4500 Fingerprint Readers.

Provides high-level APIs for image capture, biometric enrollment, 1:1 verification,
and 1:N identification with support for libfprint, official DigitalPersona C SDK,
and pure-Python simulation.
"""

from dp4500.reader import UareU4500
from dp4500.manager import ReaderManager
from dp4500.image import FingerprintImage
from dp4500.template import FingerprintTemplate
from dp4500.matching import FingerprintMatcher
from dp4500.backends.base import (
    DeviceInfo,
    MatchResult,
    IdentifyResult,
    LEDMode,
    BaseBackend,
)
from dp4500.utils.udev import (
    check_usb_permissions,
    get_udev_rule_content,
    install_udev_rule,
)
from dp4500.exceptions import (
    DPError,
    DeviceNotFoundError,
    DeviceBusyError,
    PermissionError,
    DeviceNotOpenError,
    CaptureError,
    EnrollmentError,
    VerificationError,
    IdentificationError,
    BackendNotAvailableError,
)

__version__ = "1.0.0"

__all__ = [
    # Core
    "UareU4500",
    "ReaderManager",
    "FingerprintImage",
    "FingerprintTemplate",
    "FingerprintMatcher",
    # Types & Enums
    "DeviceInfo",
    "MatchResult",
    "IdentifyResult",
    "LEDMode",
    "BaseBackend",
    # Utilities
    "check_usb_permissions",
    "get_udev_rule_content",
    "install_udev_rule",
    # Exceptions
    "DPError",
    "DeviceNotFoundError",
    "DeviceBusyError",
    "PermissionError",
    "DeviceNotOpenError",
    "CaptureError",
    "EnrollmentError",
    "VerificationError",
    "IdentificationError",
    "BackendNotAvailableError",
]
