"""
Reader management, discovery, and backend selection.
"""

from __future__ import annotations
import sys
import logging
from typing import List, Optional, Type, Dict

from dp4500.backends.base import BaseBackend, DeviceInfo
from dp4500.backends.libfprint import LibfprintBackend
from dp4500.backends.official_sdk import OfficialSdkBackend
from dp4500.backends.mock import MockBackend
from dp4500.exceptions import DeviceNotFoundError, BackendNotAvailableError

logger = logging.getLogger("dp4500.manager")

BACKEND_REGISTRY: Dict[str, Type[BaseBackend]] = {
    "official_sdk": OfficialSdkBackend,
    "libfprint": LibfprintBackend,
    "mock": MockBackend,
}


class ReaderManager:
    """
    Coordinates device discovery across multiple backends and provides
    auto-selection of available hardware.
    """

    @classmethod
    def get_backend_class(cls, backend_name: str) -> Type[BaseBackend]:
        name = backend_name.lower()
        if name not in BACKEND_REGISTRY:
            raise ValueError(
                f"Unknown backend '{backend_name}'. Available: {list(BACKEND_REGISTRY.keys())}"
            )
        return BACKEND_REGISTRY[name]

    @classmethod
    def available_backends(cls) -> List[str]:
        """Return list of backends whose native libraries are present and functional."""
        results = []
        for name, b_cls in BACKEND_REGISTRY.items():
            if b_cls.is_available():
                results.append(name)
        return results

    @classmethod
    def auto_detect_backend(cls, allow_mock: bool = False) -> BaseBackend:
        """
        Auto-detect the most appropriate backend:
        1. Official DigitalPersona SDK (if installed and devices found)
        2. libfprint (if installed and devices found)
        3. If no hardware found and allow_mock is True, return MockBackend.
        4. Otherwise returns the best available backend that has drivers loaded.
        """
        # Try official SDK first
        if OfficialSdkBackend.is_available():
            try:
                b = OfficialSdkBackend()
                if b.list_devices():
                    return b
            except Exception as e:
                logger.debug(f"Official SDK probe skipped: {e}")

        # Try libfprint
        if LibfprintBackend.is_available():
            try:
                b = LibfprintBackend()
                if b.list_devices():
                    return b
            except Exception as e:
                logger.debug(f"libfprint probe skipped: {e}")

        # Check if either backend is at least available even if device not yet initialized
        if LibfprintBackend.is_available():
            return LibfprintBackend()
        if OfficialSdkBackend.is_available():
            return OfficialSdkBackend()

        if allow_mock:
            return MockBackend()

        if sys.platform.startswith("win"):
            raise BackendNotAvailableError(
                "DigitalPersona SDK runtime (dpfpdd.dll / dpfj.dll) was not found on this Windows system, "
                "or no reader is connected. Please install the DigitalPersona U.are.U SDK, "
                "copy dpfpdd.dll and dpfj.dll to the project directory, or pass backend='mock' (or --mock) to run in simulation mode."
            )
        else:
            raise BackendNotAvailableError(
                "Neither libfprint-2 nor the official DigitalPersona SDK was found on this system. "
                "Please install libfprint-2 or pass backend='mock' to run in simulation mode."
            )

    @classmethod
    def list_readers(cls, backend_name: Optional[str] = None) -> List[DeviceInfo]:
        """
        Enumerate all connected DigitalPersona readers.
        :param backend_name: Optional backend name filter ('libfprint', 'official_sdk', 'mock').
        """
        if backend_name:
            b_cls = cls.get_backend_class(backend_name)
            if not b_cls.is_available():
                return []
            backend = b_cls()
            return backend.list_devices()

        # Enumerate across all available hardware backends
        devices: List[DeviceInfo] = []
        for name in ["official_sdk", "libfprint"]:
            b_cls = BACKEND_REGISTRY[name]
            if b_cls.is_available():
                try:
                    devs = b_cls().list_devices()
                    if devs:
                        devices.extend(devs)
                        break  # Found devices with highest-priority backend
                except Exception:
                    pass

        return devices

    @classmethod
    def get_reader(
        cls,
        device_id: Optional[str] = None,
        backend_name: Optional[str] = None,
    ):
        """
        Retrieve a reader instance.
        """
        from dp4500.reader import UareU4500

        backend: Optional[BaseBackend] = None
        if backend_name:
            b_cls = cls.get_backend_class(backend_name)
            backend = b_cls()

        return UareU4500(device_id=device_id, backend=backend)
