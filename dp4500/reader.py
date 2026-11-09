"""
High-level reader abstraction for DigitalPersona U.are.U 4500 devices.
"""

from __future__ import annotations
import logging
from typing import Optional, List, Callable, Any
from types import TracebackType

from dp4500.backends.base import (
    BaseBackend,
    DeviceInfo,
    MatchResult,
    IdentifyResult,
    LEDMode,
)
from dp4500.image import FingerprintImage
from dp4500.template import FingerprintTemplate
from dp4500.exceptions import DeviceNotOpenError, DeviceNotFoundError

logger = logging.getLogger("dp4500.reader")


class UareU4500:
    """
    High-level Python controller for the DigitalPersona U.are.U 4500 fingerprint reader.
    Supports context management, synchronous capture, multi-stage enrollment,
    and 1:1 / 1:N biometric matching.

    Usage:
        with UareU4500() as reader:
            img = reader.capture()
            img.save("finger.png")
    """

    def __init__(
        self,
        device_id: Optional[str] = None,
        backend: Optional[BaseBackend] = None,
    ):
        """
        :param device_id: Specific device ID or serial number (or None for auto-selection).
        :param backend: Specific BaseBackend instance (or None to auto-detect).
        """
        if backend is None:
            from dp4500.manager import ReaderManager
            backend = ReaderManager.auto_detect_backend()

        self._backend = backend
        self._device_info: Optional[DeviceInfo] = None
        self._handle: Any = None
        self._target_device_id = device_id

        # Resolve device info
        devices = self._backend.list_devices()
        if not devices:
            raise DeviceNotFoundError(
                f"No DigitalPersona reader detected by backend '{self._backend.backend_name()}'."
            )

        if device_id is not None:
            matched = [d for d in devices if d.device_id == str(device_id)]
            if not matched:
                raise DeviceNotFoundError(f"Device ID '{device_id}' not found.")
            self._device_info = matched[0]
        else:
            self._device_info = devices[0]

    @property
    def is_open(self) -> bool:
        """True if the device communication session is currently active."""
        return self._handle is not None

    @property
    def device_id(self) -> str:
        return self._device_info.device_id if self._device_info else ""

    @property
    def name(self) -> str:
        return self._device_info.name if self._device_info else "DigitalPersona 4500"

    @property
    def driver(self) -> str:
        return self._device_info.driver if self._device_info else ""

    @property
    def vendor_id(self) -> int:
        return self._device_info.vendor_id if self._device_info else 0x05BA

    @property
    def product_id(self) -> int:
        return self._device_info.product_id if self._device_info else 0x000A

    @property
    def serial_number(self) -> Optional[str]:
        return self._device_info.serial_number if self._device_info else None

    @property
    def backend(self) -> BaseBackend:
        return self._backend

    def open(self) -> UareU4500:
        """Open communication with the reader."""
        if self.is_open:
            return self
        self._handle = self._backend.open_device(self.device_id)
        return self

    def close(self) -> None:
        """Close communication with the reader."""
        if self._handle is not None:
            try:
                self._backend.close_device(self._handle)
            finally:
                self._handle = None

    def __enter__(self) -> UareU4500:
        return self.open()

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise DeviceNotOpenError("Reader must be opened before performing operations. Use with UareU4500() as r: ...")

    def capture(
        self,
        wait_for_finger: bool = True,
        timeout_ms: Optional[int] = None,
    ) -> FingerprintImage:
        """
        Capture a fingerprint image from the reader.

        :param wait_for_finger: Block until finger touches sensor (True) or capture immediately (False).
        :param timeout_ms: Maximum wait duration in milliseconds (None for default).
        :return: FingerprintImage instance.
        """
        self._ensure_open()
        return self._backend.capture_image(
            self._handle,
            wait_for_finger=wait_for_finger,
            timeout_ms=timeout_ms,
        )

    def enroll(
        self,
        stages: int = 5,
        on_stage_progress: Optional[Callable[[int, int], None]] = None,
        timeout_ms: Optional[int] = None,
        username: Optional[str] = None,
        finger_name: Optional[str] = None,
    ) -> FingerprintTemplate:
        """
        Perform a multi-stage enrollment procedure and generate a master template.

        :param stages: Number of touches required to construct the composite template.
        :param on_stage_progress: Optional callback function f(current_stage, total_stages).
        :param timeout_ms: Timeout per stage in milliseconds.
        :param username: Optional user account identifier to attach as metadata.
        :param finger_name: Optional name of the finger (e.g. 'right_index').
        :return: FingerprintTemplate instance.
        """
        self._ensure_open()
        template = self._backend.enroll(
            self._handle,
            stages=stages,
            progress_callback=on_stage_progress,
            timeout_ms=timeout_ms,
        )
        template.username = username
        template.finger_name = finger_name
        return template

    def verify(
        self,
        template: FingerprintTemplate,
        timeout_ms: Optional[int] = None,
    ) -> MatchResult:
        """
        Perform 1:1 verification of the live finger against an enrolled template.

        :param template: The reference FingerprintTemplate to verify against.
        :param timeout_ms: Maximum wait time for live scan.
        :return: MatchResult(matched=bool, score=float)
        """
        self._ensure_open()
        return self._backend.verify(
            self._handle,
            template=template,
            timeout_ms=timeout_ms,
        )

    def identify(
        self,
        templates: List[FingerprintTemplate],
        timeout_ms: Optional[int] = None,
    ) -> IdentifyResult:
        """
        Perform 1:N identification of the live finger against a gallery of templates.

        :param templates: List of candidate reference templates.
        :param timeout_ms: Maximum wait time for live scan.
        :return: IdentifyResult(matched=bool, index=int, template=FingerprintTemplate, score=float)
        """
        self._ensure_open()
        return self._backend.identify(
            self._handle,
            templates=templates,
            timeout_ms=timeout_ms,
        )

    def set_led(self, mode: LEDMode) -> bool:
        """
        Control reader's status light (LEDMode.ON, LEDMode.OFF, LEDMode.BLINK).
        """
        self._ensure_open()
        return self._backend.set_led(self._handle, mode)

    def __repr__(self) -> str:
        status = "OPEN" if self.is_open else "CLOSED"
        return f"<UareU4500 id='{self.device_id}' name='{self.name}' driver='{self.driver}' status={status}>"
